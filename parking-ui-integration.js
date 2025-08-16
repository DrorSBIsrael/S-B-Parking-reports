/**
 * UI Integration Layer
 * Connects the parking API with the HTML interface
 */

class ParkingUIIntegration {
    constructor() {
        this.api = parkingAPI;
        this.currentCompany = null;
        this.subscribers = [];
        this.isLoading = false;
        
        // Initialize API configuration
        this.initializeAPI();
    }
    
    /**
     * Initialize API with configuration
     */
    initializeAPI() {
        // Configuration for connecting to the parking server
        const config = window.parkingConfig || {};
        const currentConfig = config.current || {};
        
        this.api.setConfig({
            baseUrl: currentConfig.apiUrl || '/api/company-manager/proxy',  // Use Flask proxy, not direct IP
            username: currentConfig.username || '2022',
            password: currentConfig.password || '2022',
            useProxy: currentConfig.useProxy || false
        });
        
        // Test connection on startup - disabled for now
        // this.testConnection();
        console.log('API configured for direct connection to parking server');
    }
    
    /**
     * Test server connection
     */
    async testConnection() {
        console.log('Testing connection to parking server...');
        const connected = await this.api.testConnection();
        
        if (connected) {
            console.log('✅ Connected to parking server');
            this.showNotification('מחובר לשרת החניון', 'success');
        } else {
            console.warn('⚠️ Cannot connect to parking server, using mock data');
            this.showNotification('עובד במצב לא מקוון - נתוני דמה', 'warning');
        }
        
        return connected;
    }
    
    /**
     * Load companies from server
     */
    async loadCompanies() {
        this.setLoading(true);
        
        try {
            const result = await this.api.getCompanies();
            
            if (result.success) {
                const companies = result.data;
                this.displayCompanies(companies);
                
                // If only one company, select it automatically
                if (companies.length === 1) {
                    this.selectCompany(companies[0]);
                }
            } else {
                // Fallback to mock data
                console.log('Using mock companies data');
                this.displayCompanies(window.mockCompanies || []);
            }
        } catch (error) {
            console.error('Error loading companies:', error);
            this.showNotification('שגיאה בטעינת חברות', 'error');
            // Use mock data as fallback
            this.displayCompanies(window.mockCompanies || []);
        } finally {
            this.setLoading(false);
        }
    }
    
    /**
     * Display companies in UI
     */
    displayCompanies(companies) {
        const companyList = document.getElementById('companyList');
        if (!companyList) return;
        
        companyList.innerHTML = '';
        
        companies.forEach(company => {
            const card = document.createElement('div');
            card.className = 'company-card';
            card.onclick = () => this.selectCompany(company);
            card.innerHTML = `
                <h3>${company.name || company.companyName}</h3>
                <p>${company.subscribersCount || 0} מנויים</p>
            `;
            companyList.appendChild(card);
        });
    }
    
    /**
     * Select a company and load its subscribers
     */
    async selectCompany(company) {
        this.currentCompany = company;
        
        // Update UI
        document.querySelectorAll('.company-card').forEach(card => {
            card.classList.remove('selected');
        });
        
        if (event && event.currentTarget) {
            event.currentTarget.classList.add('selected');
        }
        
        // Hide company selector if only one company
        const companySelector = document.getElementById('companySelector');
        const companies = document.querySelectorAll('.company-card');
        if (companies.length === 1 && companySelector) {
            companySelector.style.display = 'none';
        }
        
        // Show main content
        const mainContent = document.getElementById('mainContent');
        if (mainContent) {
            mainContent.style.display = 'block';
            const companyNameElement = document.getElementById('companyName');
            if (companyNameElement) {
                companyNameElement.textContent = `- ${company.name || company.companyName}`;
            }
        }
        
        // Load subscribers
        await this.loadSubscribers();
    }
    
    /**
     * Load subscribers for current company
     */
    async loadSubscribers() {
        if (!this.currentCompany) return;
        
        this.setLoading(true, 'loadingState');
        
        try {
            const result = await this.api.getSubscribers(this.currentCompany.id);
            
            if (result.success) {
                this.subscribers = result.data;
                this.displaySubscribers(this.subscribers);
            } else {
                // Fallback to mock data
                console.log('Using mock subscribers data');
                const mockSubs = window.mockSubscribers?.filter(s => 
                    s.companyNum === this.currentCompany.id
                ) || [];
                this.subscribers = mockSubs;
                this.displaySubscribers(mockSubs);
            }
        } catch (error) {
            console.error('Error loading subscribers:', error);
            this.showNotification('שגיאה בטעינת מנויים', 'error');
        } finally {
            this.setLoading(false, 'loadingState');
            const tableContainer = document.getElementById('tableContainer');
            if (tableContainer) {
                tableContainer.style.display = 'block';
            }
        }
    }
    
    /**
     * Display subscribers in table
     */
    displaySubscribers(subscribers) {
        const tbody = document.getElementById('subscribersTableBody');
        if (!tbody) return;
        
        tbody.innerHTML = '';
        
        subscribers.forEach(subscriber => {
            const row = document.createElement('tr');
            row.onclick = () => this.editSubscriber(subscriber);
            
            const validUntil = new Date(subscriber.validUntil);
            const isExpired = validUntil < new Date();
            
            row.innerHTML = `
                <td>${subscriber.companyNum}</td>
                <td>${subscriber.companyName}</td>
                <td>${subscriber.subscriberNum}</td>
                <td>${subscriber.firstName}</td>
                <td>${subscriber.lastName}</td>
                <td>${subscriber.tagNum ? `<span class="tag-badge">${subscriber.tagNum}</span>` : '-'}</td>
                <td>${subscriber.vehicle1 || '-'}</td>
                <td>${subscriber.vehicle2 || '-'}</td>
                <td>${subscriber.vehicle3 || '-'}</td>
                <td class="${isExpired ? 'status-inactive' : 'status-active'}">${this.formatDate(subscriber.validUntil)}</td>
                <td>${this.getProfileText(subscriber.profile)}</td>
                <td>${this.formatDate(subscriber.validFrom) || '-'}</td>
                <td>${subscriber.presence ? '✅' : '❌'} ${subscriber.presence ? 'נוכח' : 'לא נוכח'}</td>
                <td>${subscriber.lastEntry || '-'}</td>
            `;
            tbody.appendChild(row);
        });
    }
    
    /**
     * Save subscriber (create or update)
     */
    async saveSubscriber(subscriberData) {
        if (!this.currentCompany) return;
        
        this.setLoading(true);
        
        try {
            let result;
            
            if (subscriberData.isNew) {
                // Need to ensure subscribers list is loaded
                if (!this.subscribers || this.subscribers.length === 0) {
                    console.log('Loading subscribers list for numbering...');
                    await this.loadSubscribers();
                }
                
                // Calculate next available subscriber number if not provided
                if (!subscriberData.subscriberNum || subscriberData.subscriberNum === '') {
                    // Check if this is a guest
                    if (subscriberData.isGuest || subscriberData.firstName === 'אורח') {
                        // Guest numbers start from 40001
                        const existingGuests = this.subscribers.filter(s => {
                            const num = parseInt(s.subscriberNum);
                            return !isNaN(num) && num >= 40001;
                        });
                        
                        let nextGuestId = 40001;
                        if (existingGuests.length > 0) {
                            const maxGuestId = Math.max(...existingGuests.map(s => parseInt(s.subscriberNum)));
                            nextGuestId = maxGuestId + 1;
                        }
                        
                        subscriberData.subscriberNum = String(nextGuestId);
                        console.log(`Creating guest with ID: ${subscriberData.subscriberNum}`);
                        console.log(`Found ${existingGuests.length} existing guests`);
                    } else {
                        // Regular subscriber - get next number in company
                        const companySubscribers = this.subscribers.filter(s => {
                            const num = parseInt(s.subscriberNum);
                            return !isNaN(num) && num < 40001;
                        });
                        
                        let nextId = 1;
                        if (companySubscribers.length > 0) {
                            const maxId = Math.max(...companySubscribers.map(s => parseInt(s.subscriberNum)));
                            nextId = maxId + 1;
                        }
                        
                        subscriberData.subscriberNum = String(nextId);
                        console.log(`Creating regular subscriber with ID: ${subscriberData.subscriberNum}`);
                        console.log(`Found ${companySubscribers.length} existing subscribers`);
                    }
                }
                
                // Create new subscriber
                delete subscriberData.isNew;
                result = await this.api.createSubscriber(this.currentCompany.id, subscriberData);
            } else {
                // Update existing subscriber
                result = await this.api.updateSubscriber(
                    this.currentCompany.id, 
                    subscriberData.subscriberNum, 
                    subscriberData
                );
            }
            
            if (result.success) {
                this.showNotification('הנתונים נשמרו בהצלחה', 'success');
                await this.loadSubscribers(); // Refresh the list
                return true;
            } else {
                this.showNotification('שגיאה בשמירת הנתונים: ' + result.error, 'error');
                return false;
            }
        } catch (error) {
            console.error('Error saving subscriber:', error);
            this.showNotification('שגיאה בשמירת הנתונים', 'error');
            return false;
        } finally {
            this.setLoading(false);
        }
    }
    
    /**
     * Delete subscriber
     */
    async deleteSubscriber(subscriberId) {
        if (!this.currentCompany) return;
        
        if (!confirm('האם אתה בטוח שברצונך למחוק מנוי זה?')) {
            return;
        }
        
        this.setLoading(true);
        
        try {
            const result = await this.api.deleteSubscriber(this.currentCompany.id, subscriberId);
            
            if (result.success) {
                this.showNotification('המנוי נמחק בהצלחה', 'success');
                await this.loadSubscribers(); // Refresh the list
            } else {
                this.showNotification('שגיאה במחיקת המנוי', 'error');
            }
        } catch (error) {
            console.error('Error deleting subscriber:', error);
            this.showNotification('שגיאה במחיקת המנוי', 'error');
        } finally {
            this.setLoading(false);
        }
    }
    
    /**
     * Export to Excel
     */
    async exportToExcel() {
        if (!this.currentCompany) return;
        
        this.setLoading(true);
        
        try {
            const result = await this.api.exportToExcel(this.currentCompany.id);
            
            if (result.success) {
                this.showNotification('הייצוא החל', 'success');
            } else {
                // Fallback: Create client-side Excel
                this.exportToExcelClientSide();
            }
        } catch (error) {
            console.error('Error exporting to Excel:', error);
            // Fallback: Create client-side Excel
            this.exportToExcelClientSide();
        } finally {
            this.setLoading(false);
        }
    }
    
    /**
     * Client-side Excel export fallback
     */
    exportToExcelClientSide() {
        if (!this.subscribers || this.subscribers.length === 0) {
            this.showNotification('אין נתונים לייצוא', 'warning');
            return;
        }
        
        // Create CSV content
        const headers = ['מספר חברה', 'שם חברה', 'מספר מנוי', 'שם פרטי', 'שם משפחה', 
                        'מספר תג', 'רכב 1', 'רכב 2', 'רכב 3', 'תחילת תוקף', 'סוף תוקף', 
                        'פרופיל', 'נוכחות', 'כניסה אחרונה'];
        
        const rows = this.subscribers.map(s => [
            s.companyNum, s.companyName, s.subscriberNum, s.firstName, s.lastName,
            s.tagNum || '', s.vehicle1 || '', s.vehicle2 || '', s.vehicle3 || '',
            s.validFrom || '', s.validUntil, s.profile,
            s.presence ? 'נוכח' : 'לא נוכח', s.lastEntry || ''
        ]);
        
        // Add BOM for UTF-8
        let csvContent = '\ufeff';
        csvContent += headers.join(',') + '\n';
        csvContent += rows.map(row => row.join(',')).join('\n');
        
        // Create download link
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);
        
        link.setAttribute('href', url);
        link.setAttribute('download', `subscribers_${this.currentCompany.id}_${Date.now()}.csv`);
        link.style.visibility = 'hidden';
        
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        this.showNotification('הקובץ הורד בהצלחה', 'success');
    }
    
    /**
     * Handle real-time updates from WebSocket
     */
    handleRealtimeUpdate(data) {
        console.log('Received real-time update:', data);
        
        // If update is for current company, refresh subscribers
        if (data.companyId === this.currentCompany?.id) {
            this.loadSubscribers();
        }
    }
    
    /**
     * UI Helper Functions
     */
    setLoading(isLoading, elementId = 'loadingState') {
        this.isLoading = isLoading;
        const loadingElement = document.getElementById(elementId);
        if (loadingElement) {
            loadingElement.style.display = isLoading ? 'block' : 'none';
        }
        
        const tableContainer = document.getElementById('tableContainer');
        if (tableContainer && elementId === 'loadingState') {
            tableContainer.style.display = isLoading ? 'none' : 'block';
        }
    }
    
    showNotification(message, type = 'info') {
        // Use the toast notification system
        if (window.showToast) {
            window.showToast(message, type);
        } else {
            // Fallback to alert
            alert(message);
        }
    }
    
    formatDate(dateString) {
        if (!dateString) return '';
        const date = new Date(dateString);
        return date.toLocaleDateString('he-IL');
    }
    
    getProfileText(profile) {
        const profiles = {
            'regular': 'רגיל',
            'vip': 'VIP',
            'disabled': 'נכה',
            'guest': 'אורח'
        };
        return profiles[profile] || profile;
    }
    
    /**
     * Initialize the integration
     */
    async initialize() {
        console.log('Initializing Parking UI Integration...');
        
        // Connect WebSocket for real-time updates
        this.api.connectWebSocket();
        
        // Load initial data
        await this.loadCompanies();
        
        // Set up event listeners
        this.setupEventListeners();
        
        console.log('Parking UI Integration initialized');
    }
    
    setupEventListeners() {
        // Override the global save function
        if (window.saveSubscriber) {
            const originalSave = window.saveSubscriber;
            window.saveSubscriber = async () => {
                // Get form data
                const formData = {
                    companyNum: document.getElementById('editCompanyNum').value,
                    companyName: document.getElementById('editCompanyName').value,
                    subscriberNum: document.getElementById('editSubscriberNum').value,
                    firstName: document.getElementById('editFirstName').value,
                    lastName: document.getElementById('editLastName').value,
                    tagNum: document.getElementById('editTagNum').value,
                    vehicle1: document.getElementById('editVehicle1').value,
                    vehicle2: document.getElementById('editVehicle2').value,
                    vehicle3: document.getElementById('editVehicle3').value,
                    validFrom: document.getElementById('editValidFrom').value,
                    validUntil: document.getElementById('editValidUntil').value,
                    profile: document.getElementById('editProfile').value,
                    notes: document.getElementById('editNotes').value,
                    isNew: window.editingSubscriber?.isNew || false
                };
                
                // Save via API
                const success = await this.saveSubscriber(formData);
                
                if (success) {
                    // Close modal
                    if (window.closeModal) {
                        window.closeModal();
                    }
                }
            };
        }
        
        // Override export function
        if (window.exportToExcel) {
            window.exportToExcel = () => this.exportToExcel();
        }
    }
}

// Create global instance
window.parkingUI = new ParkingUIIntegration();

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.parkingUI.initialize();
    });
} else {
    window.parkingUI.initialize();
}
