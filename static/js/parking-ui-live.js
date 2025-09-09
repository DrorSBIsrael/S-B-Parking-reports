/**
 * UI Integration Layer for XML API 
 * Connects the parking XML API with the HTML interface
 */

class ParkingUIIntegrationXML {
    constructor() {
        this.api = window.parkingAPIXML || parkingAPIXML;
        this.currentContract = null; // Contract = Company
        this.subscribers = [];
        this.isLoading = false;
        
        // Sorting state
        this.currentSortField = null;
        this.currentSortDirection = 'asc';
        
        // Map company IDs to contract IDs - for new server
        this.companyToContract = {
            '1000': '1000',
            '2': '2',
            '3': '3',
            '4': '4',
        };
        
        // Initialize API configuration
        this.initializeAPI();
        
        // Setup sorting after DOM is ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.setupSorting());
        } else {
            this.setupSorting();
        }
    }
    
    /**
     * Setup filter listeners
     */
    setupFilters() {
        // Setup presence filter
        const presenceFilter = document.getElementById('filterPresence');
        if (presenceFilter) {
            presenceFilter.addEventListener('change', () => this.applyFilters());
        }
        
        // Setup date filter
        const dateFilter = document.getElementById('filterDate');
        if (dateFilter) {
            dateFilter.addEventListener('change', () => this.applyFilters());
        }
        
        // Setup search box
        const searchBox = document.getElementById('searchBox');
        if (searchBox) {
            searchBox.addEventListener('input', () => this.applyFilters());
        }
    }
    
    /**
     * Apply filters to current subscribers
     */
    applyFilters() {
        if (!this.subscribers || this.subscribers.length === 0) return;
        
        const searchTerm = document.getElementById('searchBox')?.value?.toLowerCase() || '';
        const presenceFilter = document.getElementById('filterPresence')?.value || '';
        const dateFilter = document.getElementById('filterDate')?.value || '';
        
        let filtered = [...this.subscribers];
        
        // Apply search filter
        if (searchTerm) {
            filtered = filtered.filter(s => 
                s.firstName?.toLowerCase().includes(searchTerm) ||
                s.lastName?.toLowerCase().includes(searchTerm) ||
                s.subscriberNum?.toString().includes(searchTerm) ||
                s.vehicle1?.includes(searchTerm) ||
                s.vehicle2?.includes(searchTerm) ||
                s.vehicle3?.includes(searchTerm) ||
                s.lpn1?.includes(searchTerm) ||
                s.lpn2?.includes(searchTerm) ||
                s.lpn3?.includes(searchTerm) ||
                s.tagNum?.toLowerCase().includes(searchTerm)
            );
        }
        
        // Apply presence filter
        if (presenceFilter) {
            filtered = filtered.filter(s => {
                if (presenceFilter === 'present') return s.presence === true;
                if (presenceFilter === 'absent') return s.presence === false;
                return true;
            });
        }
        
        // Apply date filter
        if (dateFilter) {
            const now = new Date();
            filtered = filtered.filter(s => {
                const validDate = new Date(s.validUntil);
                const daysUntilExpiry = Math.floor((validDate - now) / (1000 * 60 * 60 * 24));
                
                switch(dateFilter) {
                    case 'valid':
                        return validDate >= now;
                    case 'expired':
                        return validDate < now;
                    case 'expiring30':
                        return daysUntilExpiry >= 0 && daysUntilExpiry <= 30;
                    case 'expiring7':
                        return daysUntilExpiry >= 0 && daysUntilExpiry <= 7;
                    default:
                        return true;
                }
            });
        }
        
        // Apply current sorting if exists
        if (this.currentSortField) {
            filtered = this.sortSubscribers(filtered);
        }
        
        this.displaySubscribers(filtered);
    }
    
    /**
     * Initialize API with configuration
     */
    initializeAPI() {
        // Get configuration from config.js if available
        const globalConfig = window.parkingConfig?.current || {};
        
        // Check if we should use proxy based on config or auto-detect
        const useProxy = globalConfig.useProxy !== undefined 
            ? globalConfig.useProxy 
            : (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');
        
        this.api.setConfig({
            baseUrl: '/api/company-manager/proxy', // Always use Flask proxy
            servicePath: useProxy ? '' : '/CustomerMediaWebService',
            username: globalConfig.username || '2022',
            password: globalConfig.password || '2022'
        });
        
        // XML API configured for parking server
    }
    
    /**
     * Load companies from server or use mock data
     */
    async loadCompanies() {
        this.setLoading(true);
        // Loading parkings from Flask
        
        try {
            // Get parkings list from Flask (not from parking API)
            // Calling Flask API
            const response = await fetch('/api/company-manager/get-parkings');
            const result = await response.json();
            // Flask API result received
            
            if (result.success && result.parkings) {
                // Got parkings from Flask
                
                // Use parkings instead of contracts/companies
                const parkings = result.parkings;
                
                if (!parkings || parkings.length === 0) {
                    console.warn('[loadCompanies] No parkings found, using fallback');
                    this.loadMockParkings();
                    return;
                }
                
                // Found parkings
                
                // If only one parking, auto-select it (without displaying it)
                if (parkings.length === 1) {
                    // Auto-selecting single parking
                    await this.selectParking(parkings[0]);
                } else {
                    // Display parkings as cards only if multiple
                    this.displayParkings(parkings);
                }
                

            } else {
                // Use mock data as fallback
                // API failed or no data
                await this.loadMockParkings();
            }
        } catch (error) {
            console.error('[loadCompanies] Error loading parkings:', error);
            this.showNotification('שגיאה בטעינת חניונים', 'error');
            await this.loadMockParkings();
        } finally {
            this.setLoading(false);
        }
    }
    
    /**
     * Load mock parkings for fallback
     */
    async loadMockParkings() {
        // Using mock parkings data
        const mockParkings = [
            { 
                id: 'mock-1', 
                name: 'חניון בדיקות', 
                location: 'תל אביב',
                project_number: '1000',
                ip_address: '10.0.0.1',
                port: 8443,
                is_active: true
            }
        ];
        this.displayParkings(mockParkings);
        
        // Auto-select if only one parking
        if (mockParkings.length === 1) {
            // Auto-selecting single parking
            await this.selectParking(mockParkings[0]);
        }
    }
    
    /**
     * Display parkings as cards
     */
    displayParkings(parkings) {
        const companyList = document.getElementById('companyList');
        if (!companyList) return;
        
        companyList.innerHTML = '';
        
        parkings.forEach(parking => {
            const card = document.createElement('div');
            card.className = 'company-card';
            card.onclick = () => this.selectParking(parking);
            
            card.innerHTML = `
                <div class="company-header">
                    <h3>${parking.name}</h3>
                    <span class="company-number">#${parking.project_number}</span>
                </div>
                <div class="stats-row">
                    <div class="stat-item">
                        <span class="stat-label">מיקום</span>
                        <span class="stat-value">${parking.location || 'לא ידוע'}</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">סטטוס</span>
                        <span class="stat-value">${parking.is_active ? '🟢 פעיל' : '🔴 לא פעיל'}</span>
                    </div>
                </div>
                <div class="facilities-info" style="font-size: 12px; margin-top: 10px; color: #666;">
                    ${parking.ip_address}:${parking.port}
                </div>
            `;
            
            companyList.appendChild(card);
        });
    }
    
    /**
     * Select a parking and then load its companies
     */
    async selectParking(parking) {
        // Selected parking
        
        // Show loading message immediately
        const companyList = document.getElementById('companyList');
        if (companyList) {
            companyList.innerHTML = `
                <div style="text-align: center; padding: 50px; color: #666;">
                    <div style="font-size: 48px; margin-bottom: 10px;">⏳</div>
                    <div style="font-size: 18px;">טוען חברות מ${parking.name}...</div>
                </div>
            `;
        }
        
        // Set the current parking in API
        this.api.setCurrentParking(parking.id);
        
        // Store parking info
        this.currentParking = parking;
        window.currentParking = parking;
        
        // Update user display with parking name
        if (typeof loadCurrentUser === 'function') {
            loadCurrentUser();
        }
        
        // Update UI
        document.querySelectorAll('.company-card').forEach(card => {
            card.classList.remove('selected');
        });
        
        if (event && event.currentTarget) {
            event.currentTarget.classList.add('selected');
        }
        
        // Now load companies/contracts from this parking
        await this.loadCompaniesFromParking();
    }
    
    /**
     * Load companies from selected parking
     */
    async loadCompaniesFromParking() {
        if (!this.currentParking) {
            console.error('No parking selected');
            return;
        }
        
        this.setLoading(true);
        // Loading companies from parking
        
        try {
            // Now we can call the parking API
            const result = await this.api.getContracts();
            
            if (result.success && result.data) {
                // Received company data
                
                // Process contracts/companies - handle array, 'contracts' and 'contract'
                let contracts = [];
                
                // Check if result.data is already an array (from XML parser)
                if (Array.isArray(result.data)) {
                    // Data is already an array
                    contracts = result.data;
                }
                // Check for 'contracts' (plural)
                else if (result.data.contracts) {
                    // Found contracts object
                    // If contracts.contract exists, use it
                    if (result.data.contracts.contract) {
                        contracts = Array.isArray(result.data.contracts.contract) 
                            ? result.data.contracts.contract 
                            : [result.data.contracts.contract];
                    }
                } 
                // Fallback to 'contract' (singular)
                else if (result.data.contract) {
                    // Found contract object
                    contracts = Array.isArray(result.data.contract) 
                        ? result.data.contract 
                        : [result.data.contract];
                }
                
                // Total contracts found
                
                // Filter companies based on user's company_list (if provided)
                const userCompanyList = window.userCompanyList || localStorage.getItem('company_list') || '';
                // User company list retrieved
                
                let filteredContracts = contracts;
                if (userCompanyList && userCompanyList !== 'all') {
                    // Use the new parseCompanyList function that supports ranges
                    const allowedIds = this.parseCompanyList(userCompanyList);
                    // Filtering for companies
                    
                    filteredContracts = contracts.filter(contract => {
                        const contractId = String(contract.id?.['#text'] || contract.id || '');
                        const isAllowed = allowedIds.includes(contractId);
                        if (!isAllowed && contractId) {
                            // Filtering out company
                        }
                        return isAllowed;
                    });
                    
                    // After filtering
                }
                
                // Convert to company format - extract the actual values from XML structure
                const companies = filteredContracts.map(contract => {
                    // Extract values from XML structure (they come as {#text: "value"})
                    const id = contract.id?.['#text'] || contract.id || '';
                    const name = contract.name?.['#text'] || contract.name || '';
                    
                    // Debug: log what we got
                    if (id === '2') {
                        // Debug contract data
                    }
                    
                    return {
                        id: id,
                        name: name || this.currentParking?.name || `חברה ${id}`,  // Use parking name as fallback
                        companyName: name || this.currentParking?.name || `חברה ${id}`,  // Use parking name as fallback
                        subscribersCount: 0
                    };
                });
                
                // Displaying companies
                this.displayCompanies(companies);
                
                if (companies.length === 1) {
                    await this.selectCompany(companies[0]);
                }
            } else {
                // Using mock companies
                this.loadMockCompanies();
            }
        } catch (error) {
            console.error('[loadCompaniesFromParking] Error:', error);
            this.loadMockCompanies();
        } finally {
            this.setLoading(false);
        }
    }
    
    /**
     * Load mock companies for fallback
     */
    async loadMockCompanies() {
        // Using mock companies data
        // Only show companies 2 and 1000 that match user's company_list
        const mockCompanies = [
            { id: '2', name: 'חברה בדיקה א', companyName: 'חברה בדיקה א', subscribersCount: 120 },
            { id: '1000', name: 'חברה בדיקה ב', companyName: 'חברה בדיקה ב', subscribersCount: 45 }
        ];
        this.displayCompanies(mockCompanies);
        
        // Auto-select if only one company
        if (mockCompanies.length === 1) {
            // Auto-selecting single company
            await this.selectCompany(mockCompanies[0]);
        }
    }
    
    /**
     * Display companies in UI
     */
    displayCompanies(companies) {
        const companyList = document.getElementById('companyList');
        if (!companyList) return;
        
        companyList.innerHTML = '';
        
        companies.forEach(async (company) => {
            const card = document.createElement('div');
            card.className = 'company-card';
            card.onclick = () => this.selectCompany(company);
            
            // Start with basic info
            card.innerHTML = `
                <div class="company-header">
                    <h3>${company.name || company.companyName || this.currentParking?.name || 'חניון'} <span style="color: #666; font-size: 0.9em;">[${company.id}]</span></h3>
                    <div style="display: flex; gap: 5px; align-items: center;">
                    <span class="company-number">#${company.id}</span>
                        <button class="btn btn-sm" onclick="event.stopPropagation(); window.parkingUIXML.refreshCompanyCard('${company.id}')" 
                                style="padding: 2px 6px; font-size: 12px; background: #f0f0f0; border: 1px solid #ddd; border-radius: 4px; cursor: pointer;"
                                title="רענן נתוני חברה">
                            🔄
                        </button>
                    </div>
                </div>
                <div class="stats-row">
                    <div class="stat-item">
                        <span class="stat-label">מנויים</span>
                        <span class="stat-value" id="subscribers-${company.id}">${company.subscribersCount || 0}</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">רכבים</span>
                        <span class="stat-value" id="vehicles-${company.id}">-</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">נוכחים</span>
                        <span class="stat-value" id="present-${company.id}">-</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">מקסימום</span>
                        <span class="stat-value" id="max-${company.id}">-</span>
                    </div>
                </div>
                <div class="occupancy-bar">
                    <div class="occupancy-fill" id="occupancy-${company.id}" style="width: 0%"></div>
                </div>
                <div class="facilities-info" id="facilities-${company.id}" style="display: none;">
                </div>
            `;
            
            companyList.appendChild(card);
            
            // Load additional data asynchronously
            this.loadCompanyCardData(company);
        });
    }
    
    /**
     * Refresh single company card data
     */
    async refreshCompanyCard(companyId) {
        // Find company from displayed companies
        const companyCards = document.querySelectorAll('.company-card');
        let company = null;
        
        // Look for the company in the current contract list
        if (this.currentParking && this.currentParking.contracts) {
            company = this.currentParking.contracts.find(c => c.id === companyId);
        }
        
        if (!company) {
            // Try to find in any available company data
            const companyCard = Array.from(companyCards).find(card => 
                card.innerHTML.includes(`#${companyId}`)
            );
            if (companyCard) {
                company = { id: companyId, name: '' };
            }
        }
        
        if (!company) return;
        
        // Show loading indicator on refresh button
        const refreshBtn = document.querySelector(`button[onclick*="refreshCompanyCard('${companyId}')"]`);
        if (refreshBtn) {
            refreshBtn.innerHTML = '⏳';
            refreshBtn.disabled = true;
        }
        
        try {
            // Reload company data
            await this.loadCompanyCardData(company);
            this.showNotification('✅ נתוני החברה עודכנו', 'success', 2000);
        } catch (error) {
            this.showNotification('❌ שגיאה ברענון נתוני החברה', 'error');
        } finally {
            // Restore refresh button
            if (refreshBtn) {
                refreshBtn.innerHTML = '🔄';
                refreshBtn.disabled = false;
            }
        }
    }
    
    /**
     * Load additional data for company card
     */
    async loadCompanyCardData(company) {
        try {
            // Get company contract data with facility info
            // Loading detailed data for company
            
            // Get company basic data
            const directResult = await this.api.makeRequest(`/contracts/${company.id}`);
            // Direct API response received
            
            // Get enhanced details with pooling data
            const result = await this.api.getEnhancedContractDetails(company.id);
            
            if (result.success && result.data) {
                // Handle both array and single object responses
                let contractData = Array.isArray(result.data) ? result.data[0] : result.data;
                // Enhanced contract data received
                
                // DON'T USE totalVehicles - removed from API as it's not accurate
                // We'll count actual subscribers later when we fetch them
                
                // For now, don't update subscriber count here - will be done when fetching actual subscribers
                // Contract detail received
                
                // Process facilities data - check for pooling data!
                let facilityData = null;
                
                // Check for pooling data
                if (contractData.pooling && contractData.pooling.poolingDetail) {
                    facilityData = contractData.pooling.poolingDetail;
                    // Found facility data in pooling.poolingDetail
                } else if (contractData.poolingDetail) {
                    // Sometimes poolingDetail is at the root level
                    facilityData = contractData.poolingDetail;
                    // Found facility data at root level
                } 
                
                if (!facilityData) {
                    // No pooling data found
                }
                
                // DON'T use consumerCount from pooling - it's not accurate
                // We'll count actual subscribers when we fetch them
                // totalVehicles removed completely from API
                
                if (facilityData) {
                    const facilities = Array.isArray(facilityData) ? facilityData : [facilityData];
                    // Processing facilities
                    
                    // Find main facility (facility: "0" with extCardProfile: "0") - this is the general company data
                    const mainFacility = facilities.find(f => {
                        const facilityId = f.facility;
                        const profileId = f.extCardProfile;
                        // Checking facility
                        // Look for facility="0" with extCardProfile="0"
                        return (facilityId === "0" || facilityId === 0) && (profileId === "0" || profileId === 0);
                    });
                    
                    let presentCount = 0;
                    let maxCount = 0;
                    
                    if (mainFacility) {
                        // Use main facility data (facility="0" is the general company data)
                        presentCount = parseInt(mainFacility.presentCounter) || 0;
                        maxCount = parseInt(mainFacility.maxCounter) || 0;
                        // Main facility found
                    } else {
                        // If no main facility found, sum all facilities
                        // No main facility found
                        facilities.forEach(f => {
                            const present = parseInt(f.presentCounter) || 0;
                            const max = parseInt(f.maxCounter) || 0;
                            // Facility stats
                            presentCount += present;
                            maxCount += max;
                        });
                    }
                    
                    // Store facilities breakdown for tooltip/details
                    const facilitiesBreakdown = facilities
                        .filter(f => f.facility !== "0" && f.facility !== 0) // Skip the summary
                        .map(f => ({
                            id: f.facility,
                            present: parseInt(f.presentCounter) || 0,
                            max: parseInt(f.maxCounter) || 0
                        }));
                    
                    if (facilitiesBreakdown.length > 0) {
                        // Parking lots breakdown calculated
                    }
                    
                    // Update presence data
                    const presentEl = document.getElementById(`present-${company.id}`);
                    const maxEl = document.getElementById(`max-${company.id}`);
                    if (presentEl) {
                        presentEl.textContent = presentCount.toString();
                        // Setting present count
                    }
                    if (maxEl) {
                        maxEl.textContent = maxCount.toString();
                        // Setting max count
                    }
                    
                    // Update occupancy bar
                    const occupancy = maxCount > 0 ? Math.round((presentCount / maxCount) * 100) : 0;
                    const occupancyBar = document.getElementById(`occupancy-${company.id}`);
                    if (occupancyBar) {
                        occupancyBar.style.width = `${occupancy}%`;
                        // Set color based on occupancy
                        if (occupancy > 90) {
                            occupancyBar.style.background = 'linear-gradient(90deg, #dc3545, #ff6b6b)';
                        } else if (occupancy > 70) {
                            occupancyBar.style.background = 'linear-gradient(90deg, #ffc107, #ffdd57)';
                        }
                    }
                    
                    // Show sub-facilities if any
                    const subFacilities = facilities.filter(f => f.facility !== "0" && f.facility !== 0);
                    if (subFacilities.length > 0) {
                        const facilitiesEl = document.getElementById(`facilities-${company.id}`);
                        if (facilitiesEl) {
                            facilitiesEl.style.display = 'block';
                            facilitiesEl.innerHTML = '<strong>חניונים:</strong>';
                            subFacilities.forEach(f => {
                                const fPresent = parseInt(f.presentCounter) || 0;
                                const fMax = parseInt(f.maxCounter) || 0;
                                facilitiesEl.innerHTML += `
                                    <div class="facility-item">
                                        <span>חניון ${f.facility}</span>
                                        <span>${fPresent}/${fMax}</span>
                                    </div>
                                `;
                            });
                        }
                    }
                } else {
                    // No facility data found
                    // No facility data found
                    
                    const presentEl = document.getElementById(`present-${company.id}`);
                    const maxEl = document.getElementById(`max-${company.id}`);
                    
                    // Show real data: 0 if no data
                    if (presentEl) {
                        presentEl.textContent = "?";
                        // No data for present
                    }
                    if (maxEl) {
                        maxEl.textContent = "?";
                        // No data for max
                    }
                    
                    // Hide occupancy bar when no data
                    const occupancyBar = document.getElementById(`occupancy-${company.id}`);
                    if (occupancyBar) {
                        occupancyBar.style.width = `0%`;
                        occupancyBar.style.background = '#ccc';
                    }
                }
            } else {
                // No contract data - but check if we have it from enhanced API
                // No contract data in response
                const presentEl = document.getElementById(`present-${company.id}`);
                const maxEl = document.getElementById(`max-${company.id}`);
                
                // Define contractData from result if not defined
                const contractData = result?.data || {};
                
                // Try to use data from enhanced API response
                const present = contractData.presentConsumers || 0;
                const max = contractData.consumerCount || 0;
                
                if (presentEl) presentEl.textContent = present.toString();
                if (maxEl) maxEl.textContent = max.toString();
                
                // Using enhanced API data
            }
        } catch (error) {
            console.warn(`Could not load detailed data for company ${company.id}:`, error);
            // Use default values
            const vehiclesEl = document.getElementById(`vehicles-${company.id}`);
            const presentEl = document.getElementById(`present-${company.id}`);
            const maxEl = document.getElementById(`max-${company.id}`);
            
            if (vehiclesEl) vehiclesEl.textContent = company.subscribersCount * 2 || 0;
            if (presentEl) presentEl.textContent = "0";
            if (maxEl) maxEl.textContent = "0";
        }
    }
    
    /**
     * Select a company and load its subscribers
     */
    async selectCompany(company) {
        // Store the full company object with correct name
        // If no name, use the parking name or a default
        const contractName = company.name || company.firstName || company.companyName || 
                            this.currentParking?.name || 'חניון';
        
        this.currentContract = {
            ...company,
            name: contractName,
            parkingName: this.currentParking?.name || contractName,
            filialId: company.filialId || '2228'  // Default filialId
        };
        
        // Also set global currentCompany for form compatibility
        window.currentCompany = company;
        
        // Update UI
        document.querySelectorAll('.company-card').forEach(card => {
            card.classList.remove('selected');
        });
        
        if (event && event.currentTarget) {
            event.currentTarget.classList.add('selected');
        }
        
        // Log company name for debugging
        // Company selected
        
        // Keep company selector visible even with one company (for occupancy data)
        const companySelector = document.getElementById('companySelector');
        const companies = document.querySelectorAll('.company-card');
        // Removed hiding logic - always show company card for occupancy info
        
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
        
        // Update button permissions after loading
        this.updateButtonPermissions();
    }
    
    /**
     * Parse company_list format with ranges
     * Example: "1,2,5-10,60" => ["1", "2", "5", "6", "7", "8", "9", "10", "60"]
     */
    parseCompanyList(companyListString) {
        if (!companyListString || companyListString === 'all') {
            return 'all';
        }
        
        const companies = [];
        const parts = companyListString.split(',');
        
        for (const part of parts) {
            const trimmed = part.trim();
            
            // Check if it's a range (e.g., "5-10")
            if (trimmed.includes('-')) {
                const [start, end] = trimmed.split('-').map(n => parseInt(n.trim()));
                
                if (!isNaN(start) && !isNaN(end)) {
                    // Add all numbers in range
                    for (let i = start; i <= end; i++) {
                        companies.push(i.toString());
                    }
                }
            } else {
                // Single company ID
                if (trimmed) {
                    companies.push(trimmed);
                }
            }
        }
        
        // Remove duplicates and sort
        return [...new Set(companies)].sort((a, b) => parseInt(a) - parseInt(b));
    }
    

    
    /**
     * Update a single subscriber row with new data
     */
    updateSubscriberRowOld(subscriber, index) {
        // Skip debug logs for performance
        
        // Update the subscriber in the main array FIRST
        if (this.subscribers && index >= 0 && index < this.subscribers.length) {
            // Update the array with the new data
            this.subscribers[index] = {
                ...this.subscribers[index],
                ...subscriber,
                hasFullDetails: true
            };
        }
        
        const tbody = document.getElementById('subscribersTableBody');
        if (!tbody) return;
        
        const rows = tbody.getElementsByTagName('tr');
        if (index >= 0 && index < rows.length) {
            const row = rows[index];
            
            // Find row by subscriberNum if index doesn't match
            const targetRow = row.dataset.subscriberNum === subscriber.subscriberNum ? 
                row : 
                Array.from(rows).find(r => r.dataset.subscriberNum === subscriber.subscriberNum);
                
            if (!targetRow) {
                return;
            }
            
            // Re-render the entire row with updated data
            const validUntil = new Date(subscriber.validUntil || subscriber.xValidUntil || '2030-12-31');
            const isExpired = validUntil < new Date();
            
            targetRow.innerHTML = `
                <td>${subscriber.companyNum || ''}</td>
                <td>${subscriber.companyName || ''}</td>
                <td>${subscriber.subscriberNum || subscriber.id || ''}</td>
                <td>${subscriber.firstName || ''}</td>
                <td>${subscriber.lastName || subscriber.surname || subscriber.name || ''}</td>
                <td>${subscriber.tagNum ? `<span class="tag-badge">${subscriber.tagNum}</span>` : ''}</td>
                <td>${subscriber.lpn1 || ''}</td>
                <td>${subscriber.lpn2 || ''}</td>
                <td>${subscriber.lpn3 || ''}</td>
                <td class="${isExpired ? 'status-inactive' : 'status-active'}">${this.formatDate(validUntil) || ''}</td>
                <td style="color: #888;" title="פרופיל ${subscriber.profile || ''}">${subscriber.profileName || (subscriber.profile ? `פרופיל ${subscriber.profile}` : '')}</td>
                <td>${this.formatDate(subscriber.validFrom || subscriber.xValidFrom) || ''}</td>
                <td style="text-align: center; font-size: 18px;">${subscriber.presence || subscriber.present ? '✅' : '❌'}</td>
            `;
            
            // Remove hover indicator if has full details
            if (subscriber.hasFullDetails) {
                targetRow.removeAttribute('data-hover-loadable');
                targetRow.title = '';
                targetRow.style.opacity = '1';
            }
        }
    }
    
    /**
     * Load subscribers for current company - Progressive Loading
     */
    async loadSubscribers(forceFullLoad = false) {
        if (!this.currentContract) return;
        
        // Clear any existing progress messages first
        this.hideProgressMessage();
        
        this.setLoading(true, 'loadingState');
        this.showProgressMessage(forceFullLoad ? 'טוען את כל נתוני המנויים...' : 'טוען רשימת מנויים...');
        
        try {
            // Get performance settings from config
            const perfConfig = window.parkingConfig?.performance || {};
            
            // Get subscribers progressively
            const result = await this.api.getSubscribersProgressive(this.currentContract.id, {
                batchSize: perfConfig.batchSize || 5,
                companyName: this.currentContract.name || this.currentContract.firstName || this.currentContract.companyName || `חברה ${this.currentContract.id}`,  // Pass correct company name
                forceFullLoad: forceFullLoad,  // Force loading all details if requested
                
                // Callback when basic data is ready
                onBasicLoaded: (basicSubscribers) => {
                    this.subscribers = basicSubscribers;
                    
                    // Update the actual subscriber count in the company card
                    const subscribersEl = document.getElementById(`subscribers-${this.currentContract.id}`);
                    if (subscribersEl) {
                        subscribersEl.textContent = basicSubscribers.length;
                    }
                    
                    // Update all subscribers with correct company name and loading strategy
                    const companyName = this.currentContract.name || this.currentContract.firstName || `חברה ${this.currentContract.id}`;
                    const isLargeCompany = this.subscribers.length > 300;
                    this.subscribers.forEach(sub => {
                        // Only update company name if it's missing
                        if (!sub.companyName) {
                        sub.companyName = companyName.trim();
                        }
                        sub.isLargeCompany = isLargeCompany;
                    });
                    
                    // Get company name and display immediately
                    this.updateCompanyInfo();
                    
                    // Display basic data immediately - with fade transition for smooth update
                    const tbody = document.getElementById('subscribersTableBody');
                    if (tbody) {
                        tbody.style.transition = 'opacity 0.3s ease';
                        tbody.style.opacity = '0.8';
                    }
                    this.displaySubscribers(this.subscribers);
                    if (tbody) {
                        setTimeout(() => {
                            tbody.style.opacity = '1';
                        }, 100);
                    }
                    
                    // Hide loading but show progress in status bar
                    this.setLoading(false, 'loadingState');
                    const tableContainer = document.getElementById('tableContainer');
                    if (tableContainer) {
                        tableContainer.style.display = 'block';
                    }
                    
                    // Setup sorting and filters after table is populated
                    setTimeout(() => {
                        this.setupSorting();
                        this.setupFilters();
                    }, 100);
                    
                    // Show subtle progress indicator only for medium/large companies
                    // Small companies (≤30) load instantly, so no need for progress
                    if (basicSubscribers.length > 30) {
                        this.showBackgroundProgress('טוען פרטים מלאים ברקע...');
                    }
                },
                
                // Callback when each detail is loaded
                onDetailLoaded: (subscriber, index) => {
                    // Update the specific row in the table
                    this.updateSubscriberRow(subscriber, index);
                    // Update present count in header
                    this.updatePresentCount();
                },
                
                // Progress callback
                onProgress: (progress) => {
                    // Check if this is a large company notification
                    if (progress.message && progress.message.includes('חברה גדולה')) {
                        this.updateBackgroundProgress(progress.message);
                        // Show a special notification for large companies
                        setTimeout(() => {
                            this.showNotification(
                                `⚠️ ${progress.message}\n💡 עמוד על מנוי או ערוך כדי לטעון פרטים מלאים`,
                                'warning',
                                5000 // Show for 5 seconds
                            );
                            this.hideBackgroundProgress();
                        }, 500);
                    } else if (progress.message) {
                        // Show progress message
                        this.showProgressMessage(progress.message);
                        
                        // If we reached 100%, hide progress after a short delay
                        if (progress.percent && progress.percent >= 100) {
                            // Show completion message briefly, then hide
                            setTimeout(() => {
                                this.hideProgressMessage();
                            }, 300); // Show completion message for 300ms only
                        }
                    } else if (progress.current && progress.total) {
                        this.updateBackgroundProgress(
                            `טוען פרטים... ${progress.current}/${progress.total} (${progress.percent}%)`
                        );
                        
                        if (progress.percent >= 100) {
                            // Hide immediately when done
                            this.hideBackgroundProgress();
                        }
                    }
                }
            });
            
            if (!result.success) {
                console.error('Failed to load subscribers:', result);
                this.showNotification('לא נמצאו מנויים לחברה זו', 'warning');
                this.subscribers = [];
                this.displaySubscribers([]);
                // Make sure loading is cleared
                this.setLoading(false, 'loadingState');
            }
        } catch (error) {
            console.error('Error loading subscribers:', error);
            this.showNotification('שגיאה בטעינת מנויים', 'error');
            this.subscribers = [];
            this.displaySubscribers([]);
            // Hide progress message on error
            this.hideProgressMessage();
            // Make sure loading is cleared on error
            this.setLoading(false, 'loadingState');
        } finally {
            // Hide background loading message
            this.hideBackgroundProgress();
            
            // If we're still showing the progress message after 5 seconds, something went wrong
            setTimeout(() => {
                const progressMsg = document.getElementById('progressMessage');
                if (progressMsg && progressMsg.style.display !== 'none') {
                    this.hideProgressMessage();
                    this.setLoading(false, 'loadingState');
                }
            }, 5000);
        }
    }
    
    /**
     * Update button permissions based on user permissions
     */
    updateButtonPermissions() {
        // Call the function from parking_subscribers.html if it exists
        if (typeof updateButtonPermissions === 'function') {
            updateButtonPermissions();
        }
        
        // Show permissions info to user
        const permissions = window.userPermissions || '';
        if (permissions) {
            let permissionText = 'הרשאות: ';
            if (permissions === 'B' || permissions === '') {
                permissionText += 'בסיס (צפייה בלבד)';
            } else {
                const permMap = {
                    'G': 'אורח',
                    'N': 'מנוי חדש',
                    'P': 'עדכון פרופיל',
                    'R': 'דוחות',
                    'T': 'מספר תג',
                    '1': 'רכב 1',
                    '2': 'רכבים 1-2',
                    '3': 'רכבים 1-3'
                };
                const permList = permissions.split('').map(p => permMap[p] || p).join(', ');
                permissionText += permList;
            }
            
            // Show notification briefly
            setTimeout(() => {
                this.showNotification(permissionText, 'info', 3000);
            }, 1000);
        }
    }
    
    /**
     * Update company info in header
     */
    async updateCompanyInfo() {
        try {
            const companyResult = await this.api.getContractDetails(this.currentContract.id);
            if (companyResult.success) {
                const companyName = companyResult.data.name || `חברה ${this.currentContract.id}`;
                
                // Update company name in subscribers
                this.subscribers.forEach(sub => {
                    sub.companyName = companyName;
                });
                
                // Count present subscribers
                const presentCount = this.subscribers.filter(s => s.presence).length;
                
                // Update header with clean company name
                const companyNameElement = document.getElementById('companyName');
                if (companyNameElement) {
                    // Check if this is a large company
                    const isLargeCompany = this.subscribers.length > 300;
                    const statusText = isLargeCompany ? ' 🚀' : '';
                    companyNameElement.textContent = `- ${companyName} (${this.subscribers.length} מנויים${presentCount > 0 ? ` | ${presentCount} נוכחים` : ''})${statusText}`;
                    
                    // Add tooltip for large companies
                    if (isLargeCompany) {
                        companyNameElement.title = 'חברה גדולה - פרטי מנויים נטענים לפי דרישה';
                    }
                    
                    // Show/hide reload button for large companies
                    const reloadButton = document.getElementById('reloadFullButton');
                    if (reloadButton) {
                        reloadButton.style.display = isLargeCompany ? 'inline-block' : 'none';
                    }
                }
            }
        } catch (error) {
            console.warn('Could not update company info:', error);
        }
    }
    
    /**
     * Update present count after loading details
     */
    updatePresentCount() {
        const presentCount = this.subscribers.filter(s => s.presence).length;
        const companyNameElement = document.getElementById('companyName');
        if (companyNameElement) {
            const currentText = companyNameElement.textContent;
            const companyName = currentText.split('(')[0].trim().replace('- ', '').replace(' 🚀', '');
            
            // Check if this is a large company
            const isLargeCompany = this.subscribers.length > 300;
            const statusText = isLargeCompany ? ' 🚀 מצב מהיר' : '';
            
            // Update with clean format
            companyNameElement.textContent = `- ${companyName} (${this.subscribers.length} מנויים${presentCount > 0 ? ` | ${presentCount} נוכחים` : ''})${statusText}`;
            
            // Add tooltip for large companies
            if (isLargeCompany) {
                companyNameElement.title = 'חברה גדולה - פרטי מנויים נטענים לפי דרישה';
            }
        }
    }
    
    /**
     * Refresh only a single subscriber instead of reloading all
     * @param {string} subscriberNum - The subscriber number to refresh
     */
    async refreshSingleSubscriber(subscriberNum) {
        try {
            if (!subscriberNum || !this.currentContract) {
                // If no subscriber number, just refresh the display
                this.displaySubscribers(this.subscribers);
                return;
            }
            
            // Find the subscriber in our list
            const existingIndex = this.subscribers.findIndex(s => s.subscriberNum === subscriberNum);
            
            // Get the updated subscriber data from server
            const result = await this.api.getSubscriber(this.currentContract.id, subscriberNum);
            
            if (result.success && result.data) {
                const updatedSubscriber = result.data;
                
                if (existingIndex >= 0) {
                    // Update existing subscriber
                    this.subscribers[existingIndex] = updatedSubscriber;
                    
                    // Update only the specific row in the table
                    this.updateSubscriberRow(updatedSubscriber, existingIndex);
                } else {
                    // New subscriber - add to list
                    this.subscribers.push(updatedSubscriber);
                    
                    // Re-display the entire table (easier than inserting a new row)
                    this.displaySubscribers(this.subscribers);
                }
                
                // Update counts in header
                this.updatePresentCount();
                
                // Show success notification
                this.showNotification('המנוי עודכן בהצלחה', 'success');
            } else {
                // If we can't get the specific subscriber, just refresh the display
                this.displaySubscribers(this.subscribers);
            }
        } catch (error) {
            console.error('Error refreshing single subscriber:', error);
            // Fallback to refreshing the display
            this.displaySubscribers(this.subscribers);
        }
    }
    
    /**
     * Update a single subscriber row when detail is loaded
     */
    updateSubscriberRow(subscriber, index) {
        const tbody = document.getElementById('subscribersTableBody');
        if (!tbody) return;
        
        // Update the subscriber in the main array
        const subIndex = this.subscribers.findIndex(s => 
            String(s.subscriberNum) === String(subscriber.subscriberNum)
        );
        if (subIndex !== -1) {
            this.subscribers[subIndex] = subscriber;
        }
        
        const rows = tbody.getElementsByTagName('tr');
        // Try to find row by index or by subscriber number
        let targetRow = rows[index];
        if (!targetRow || targetRow.dataset.subscriberNum !== String(subscriber.subscriberNum)) {
            targetRow = Array.from(rows).find(r => r.dataset.subscriberNum === String(subscriber.subscriberNum));
        }
        
        if (targetRow) {
            // Update the row with full data
            const validUntil = new Date(subscriber.validUntil || subscriber.xValidUntil || '2030-12-31');
            const isExpired = validUntil < new Date();
            
            // Update the onclick handler to use the updated subscriber
            targetRow.onclick = () => {
                const currentSubscriber = this.subscribers.find(s => 
                    String(s.subscriberNum) === String(subscriber.subscriberNum)
                ) || subscriber;
                this.editSubscriber(currentSubscriber);
            };
            
            targetRow.innerHTML = `
                <td>${subscriber.companyNum || ''}</td>
                <td>${subscriber.companyName || ''}</td>
                <td>${subscriber.subscriberNum || subscriber.id || ''}</td>
                <td>${subscriber.firstName || ''}</td>
                <td>${subscriber.lastName || subscriber.surname || subscriber.name || ''}</td>
                <td>${subscriber.tagNum || subscriber.cardno ? `<span class="tag-badge">${subscriber.tagNum || subscriber.cardno}</span>` : ''}</td>
                <td>${subscriber.vehicle1 || subscriber.lpn1 || ''}</td>
                <td>${subscriber.vehicle2 || subscriber.lpn2 || ''}</td>
                <td>${subscriber.vehicle3 || subscriber.lpn3 || ''}</td>
                <td class="${isExpired ? 'status-inactive' : 'status-active'}">${this.formatDate(subscriber.validUntil || subscriber.xValidUntil)}</td>
                <td style="color: #888;" title="פרופיל ${subscriber.profile || ''}">${subscriber.profileName || (subscriber.profile ? `פרופיל ${subscriber.profile}` : '')}</td>
                <td>${this.formatDate(subscriber.validFrom || subscriber.xValidFrom) || ''}</td>
                <td style="text-align: center; font-size: 18px;">${subscriber.presence || subscriber.present ? '✅' : '❌'}</td>
            `;
            
            // Remove hover loading attributes if has full details
            if (subscriber.hasFullDetails) {
                targetRow.style.opacity = '1';
                targetRow.removeAttribute('data-hover-loadable');
                targetRow.title = '';
            }
            
            // Add subtle animation to show update - only if visible
            if (window.getComputedStyle(targetRow).display !== 'none') {
                targetRow.style.transition = 'background-color 0.5s, opacity 0.2s';
            targetRow.style.backgroundColor = '#e8f5e9';
            setTimeout(() => {
                targetRow.style.backgroundColor = '';
            }, 500);
            }
        }
    }
    
    /**
     * Show background progress indicator
     */
    showBackgroundProgress(message) {
        let progressBar = document.getElementById('backgroundProgress');
        if (!progressBar) {
            progressBar = document.createElement('div');
            progressBar.id = 'backgroundProgress';
            progressBar.style.cssText = `
                position: fixed;
                bottom: 20px;
                right: 20px;
                background: #2196F3;
                color: white;
                padding: 10px 20px;
                border-radius: 20px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.2);
                z-index: 1000;
                font-size: 14px;
                opacity: 0.9;
                transition: all 0.3s;
            `;
            document.body.appendChild(progressBar);
        }
        progressBar.textContent = message;
        progressBar.style.display = 'block';
    }
    
    /**
     * Update background progress
     */
    updateBackgroundProgress(message) {
        const progressBar = document.getElementById('backgroundProgress');
        if (progressBar) {
            progressBar.textContent = message;
        }
    }
    
    /**
     * Hide background progress
     */
    hideBackgroundProgress() {
        const progressBar = document.getElementById('backgroundProgress');
        if (progressBar) {
            progressBar.style.opacity = '0';
            setTimeout(() => {
                progressBar.style.display = 'none';
                progressBar.style.opacity = '0.9';
            }, 300);
        }
    }
    
    /**
     * Show progress message
     */
    showProgressMessage(message) {
        let progressDiv = document.getElementById('progressMessage');
        if (!progressDiv) {
            progressDiv = document.createElement('div');
            progressDiv.id = 'progressMessage';
            progressDiv.style.cssText = `
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background: #2196F3;
                color: white;
                padding: 20px 40px;
                border-radius: 8px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.3);
                z-index: 10000;
                font-size: 16px;
                font-weight: bold;
                text-align: center;
            `;
            document.body.appendChild(progressDiv);
        }
        progressDiv.textContent = message;
        progressDiv.style.display = 'block';
    }
    
    /**
     * Hide progress message
     */
    hideProgressMessage() {
        const progressDiv = document.getElementById('progressMessage');
        if (progressDiv) {
            progressDiv.style.display = 'none';
            // Also try to remove it completely to avoid issues
            progressDiv.remove();
        }
    }
    
    /**
     * Load mock subscribers for demo
     */
    loadMockSubscribers() {
        // Setup filters for mock data
        setTimeout(() => {
            this.setupSorting();
            this.setupFilters();
        }, 100);
        
        const mockSubscribers = [
            {
                companyNum: this.currentContract.id,
                companyName: this.currentContract.name,
                subscriberNum: '1',
                firstName: 'דוד',
                lastName: 'כהן',
                tagNum: 'TAG001',
                vehicle1: '12-345-67',
                vehicle2: '98-765-43',
                vehicle3: '',
                validFrom: '2024-01-01',
                validUntil: '2025-12-31',
                profile: 'regular',
                presence: true
            },
            {
                companyNum: this.currentContract.id,
                companyName: this.currentContract.name,
                subscriberNum: '2',
                firstName: 'רחל',
                lastName: 'לוי',
                tagNum: 'TAG002',
                vehicle1: '55-666-77',
                vehicle2: '',
                vehicle3: '',
                validFrom: '2024-06-01',
                validUntil: '2025-06-30',
                profile: 'vip',
                presence: false
            }
        ];
        
        this.subscribers = mockSubscribers;
        this.displaySubscribers(mockSubscribers);
    }
    
    /**
     * Setup sorting functionality on table headers
     */
    setupSorting() {
        const sortableHeaders = document.querySelectorAll('.sortable');
        sortableHeaders.forEach(header => {
            header.addEventListener('click', () => {
                const field = header.getAttribute('data-sort');
                
                // Reset all headers
                sortableHeaders.forEach(h => {
                    h.classList.remove('sort-asc', 'sort-desc');
                    const icon = h.querySelector('.sort-icon');
                    if (icon) icon.innerHTML = '⇅';
                });
                
                // Update sort direction
                if (this.currentSortField === field) {
                    this.currentSortDirection = this.currentSortDirection === 'asc' ? 'desc' : 'asc';
                } else {
                    this.currentSortField = field;
                    this.currentSortDirection = 'asc';
                }
                
                // Update header visual
                header.classList.add(this.currentSortDirection === 'asc' ? 'sort-asc' : 'sort-desc');
                
                // Update sort icon
                const icon = header.querySelector('.sort-icon');
                if (icon) {
                    icon.innerHTML = this.currentSortDirection === 'asc' ? '↑' : '↓';
                }
                
                // Sort and redisplay
                this.sortAndDisplaySubscribers();
            });
        });
    }
    
    /**
     * Sort subscribers array
     */
    sortSubscribers(subscribers) {
        if (!this.currentSortField || !subscribers) return subscribers;
        
        return [...subscribers].sort((a, b) => {
            let aVal = a[this.currentSortField];
            let bVal = b[this.currentSortField];
            
            // Handle dates
            if (this.currentSortField === 'validUntil' || this.currentSortField === 'validFrom') {
                aVal = new Date(aVal || '1900-01-01');
                bVal = new Date(bVal || '1900-01-01');
            }
            
            // Handle presence (boolean)
            if (this.currentSortField === 'presence') {
                aVal = aVal ? 1 : 0;
                bVal = bVal ? 1 : 0;
            }
            
            // Handle numbers
            if (!isNaN(aVal) && !isNaN(bVal)) {
                aVal = Number(aVal);
                bVal = Number(bVal);
            }
            
            // Handle null/undefined
            if (aVal === null || aVal === undefined) aVal = '';
            if (bVal === null || bVal === undefined) bVal = '';
            
            // Compare
            if (aVal < bVal) return this.currentSortDirection === 'asc' ? -1 : 1;
            if (aVal > bVal) return this.currentSortDirection === 'asc' ? 1 : -1;
            return 0;
        });
    }
    
    /**
     * Sort and display subscribers
     */
    sortAndDisplaySubscribers() {
        // Apply filters (which includes sorting)
        this.applyFilters();
    }
    
    /**
     * Setup hover loading for a row
     */
    setupHoverLoading(row, subscriber, index) {
        let hoverTimeout = null;
        let isLoadingDetails = false;
        
        // Get hover delay from config or use default
        const hoverDelay = window.parkingConfig?.performance?.hoverLoadDelay || 500; // Default 500ms
        
        // Mouse enter - start timer
        row.addEventListener('mouseenter', async (e) => {
            // Don't load if already has full details or already loading
            if (subscriber.hasFullDetails || isLoadingDetails) return;
            
            // Clear any existing timeout
            if (hoverTimeout) {
                clearTimeout(hoverTimeout);
            }
            
            // Start loading after configured delay
            hoverTimeout = setTimeout(async () => {
                if (isLoadingDetails || subscriber.hasFullDetails) return;
                
                isLoadingDetails = true;
                
                // Add loading indicator to the row
                const originalOpacity = row.style.opacity;
                const originalBackground = row.style.background;
                row.style.opacity = '0.7';
                row.style.background = 'linear-gradient(90deg, #f0f0f0 0%, #ffffff 50%, #f0f0f0 100%)';
                row.style.backgroundSize = '200% 100%';
                row.style.animation = 'shimmer 1.5s infinite';
                row.classList.add('loading-details');
                
                // Update title
                const originalTitle = row.title;
                row.title = '⏳ טוען פרטים...';
                
                // Add loading icon to first cell
                const firstCell = row.querySelector('td:first-child');
                const originalFirstCellContent = firstCell ? firstCell.innerHTML : '';
                if (firstCell) {
                    firstCell.innerHTML = `<span style="display: inline-block; animation: spin 1s linear infinite;">⏳</span> ${originalFirstCellContent}`;
                }
                
                try {
                    console.log(`[Hover Loading] Loading details for subscriber ${subscriber.subscriberNum}`);
                    
                    // Get full details
                    const result = await this.api.getConsumerDetailOnDemand(
                        this.currentContract.id,
                        subscriber.subscriberNum
                    );
                    
                    if (result.success && result.data) {
                        // Update subscriber with full details - preserve important fields
                        const detail = result.data;
                        
                        // Preserve company name and other UI-specific fields
                        const preservedFields = {
                            companyName: subscriber.companyName,
                            isLargeCompany: subscriber.isLargeCompany,
                            loadingStrategy: subscriber.loadingStrategy
                        };
                        
                        // Map the detail fields properly - DON'T let detail override preserved fields
                        Object.assign(subscriber, {
                            ...detail,
                            ...preservedFields,  // This must come AFTER detail to preserve our fields
                            // Map profile correctly
                            profile: detail.identification?.usageProfile?.id || detail.profile || subscriber.profile,
                            profileName: detail.identification?.usageProfile?.name || detail.profileName || subscriber.profileName,
                            // Map dates
                            validFrom: detail.identification?.validFrom || detail.validFrom || subscriber.validFrom,
                            validUntil: detail.identification?.validUntil || detail.validUntil || subscriber.validUntil,
                            xValidFrom: detail.consumer?.xValidFrom || detail.xValidFrom || subscriber.xValidFrom,
                            xValidUntil: detail.consumer?.xValidUntil || detail.xValidUntil || subscriber.xValidUntil,
                            // Map presence correctly
                            presence: detail.identification?.present === 'true' || detail.presence,
                            present: detail.identification?.present === 'true' || detail.present,
                            // Map vehicles
                            lpn1: detail.lpn1 || subscriber.lpn1,
                            lpn2: detail.lpn2 || subscriber.lpn2,
                            lpn3: detail.lpn3 || subscriber.lpn3,
                            vehicle1: detail.lpn1 || subscriber.vehicle1,
                            vehicle2: detail.lpn2 || subscriber.vehicle2,
                            vehicle3: detail.lpn3 || subscriber.vehicle3,
                            // Map tag/card
                            tagNum: detail.identification?.cardno || detail.tagNum || subscriber.tagNum,
                            cardno: detail.identification?.cardno || detail.cardno || subscriber.cardno,
                            hasFullDetails: true
                        });
                        
                        // Update the row in the table
                        this.updateSubscriberRow(subscriber, index);
                        
                        // Remove hover effects
                        row.style.opacity = '1';
                        row.style.background = '';
                        row.style.animation = '';
                        row.classList.remove('loading-details');
                        row.title = '';
                        row.removeAttribute('data-hover-loadable');
                        
                        // Restore first cell
                        if (firstCell) {
                            firstCell.innerHTML = originalFirstCellContent;
                        }
                        
                        console.log(`[Hover Loading] Details loaded successfully for subscriber ${subscriber.subscriberNum}`);
                    } else {
                        // Restore original styles on error
                        row.style.opacity = originalOpacity;
                        row.style.background = originalBackground;
                        row.style.animation = '';
                        row.classList.remove('loading-details');
                        row.title = originalTitle;
                        
                        // Restore first cell
                        if (firstCell) {
                            firstCell.innerHTML = originalFirstCellContent;
                        }
                    }
                } catch (error) {
                    console.error('[Hover Loading] Error loading details:', error);
                    // Restore original styles
                    row.style.opacity = originalOpacity;
                    row.style.background = originalBackground;
                    row.style.animation = '';
                    row.classList.remove('loading-details');
                    row.title = originalTitle;
                    
                    // Restore first cell
                    if (firstCell) {
                        firstCell.innerHTML = originalFirstCellContent;
                    }
                } finally {
                    isLoadingDetails = false;
                }
            }, hoverDelay); // Configurable delay before loading
        });
        
        // Mouse leave - cancel loading
        row.addEventListener('mouseleave', () => {
            if (hoverTimeout) {
                clearTimeout(hoverTimeout);
                hoverTimeout = null;
            }
        });
    }
    
    /**
     * Display subscribers in table
     */
    displaySubscribers(subscribers) {
        // Skip debug logs for performance
        
        const tbody = document.getElementById('subscribersTableBody');
        if (!tbody) return;
        
        // Check if user can edit subscribers (for permission display)
        const permissions = window.userPermissions || '';
        const canEdit = permissions !== 'B' && permissions !== '';
        
        // Ensure the actions column header exists
        const tableHead = document.querySelector('#subscribersTable thead tr');
        if (tableHead && !tableHead.querySelector('th[data-translate="actions"]')) {
            const actionsHeader = document.createElement('th');
            actionsHeader.setAttribute('data-translate', 'actions');
            actionsHeader.textContent = 'פעולות';
            tableHead.appendChild(actionsHeader);
        }
        
        tbody.innerHTML = '';
        
        // For very large lists, use DocumentFragment for better performance
        let fragment = document.createDocumentFragment();
        const isVeryLarge = subscribers.length > 500;
        
        if (isVeryLarge) {
            console.log(`[displaySubscribers] Rendering ${subscribers.length} subscribers using batch rendering for performance`);
            
            // Show loading message for very large companies
            const loadingRow = document.createElement('tr');
            loadingRow.innerHTML = `
                <td colspan="11" style="text-align: center; padding: 20px;">
                    <div style="font-size: 18px; color: #667eea;">
                        <span>⏳ טוען ${subscribers.length} מנויים...</span>
                        <br>
                        <span style="font-size: 14px; color: #666;">פרטים מלאים ייטענו בעת מעבר עכבר</span>
                    </div>
                </td>
            `;
            tbody.appendChild(loadingRow);
        }
        
        // Batch rendering for very large lists
        const BATCH_SIZE = 100;
        let currentBatch = 0;
        
        const renderBatch = () => {
            const start = currentBatch * BATCH_SIZE;
            const end = Math.min(start + BATCH_SIZE, subscribers.length);
            
            for (let index = start; index < end; index++) {
                const subscriber = subscribers[index];
            const row = document.createElement('tr');
            
            // Always allow viewing subscriber details
            // P permission is only needed for profile updates
            row.onclick = () => {
                const currentSubscriber = this.subscribers.find(s => 
                    String(s.subscriberNum) === String(subscriber.subscriberNum)
                ) || subscriber;
                this.editSubscriber(currentSubscriber);
            };
            row.style.cursor = 'pointer';
            
            row.dataset.subscriberNum = subscriber.subscriberNum;
            row.dataset.index = index;
            
            // Add hover loading for large companies without full details
            if (subscriber.isLargeCompany && !subscriber.hasFullDetails) {
                row.setAttribute('data-hover-loadable', 'true');
                if (canEdit) {
                row.title = 'עמוד עם העכבר לטעינת פרטים מלאים';
                } else {
                    row.title = 'אין הרשאה לערוך מנויים (דרושה הרשאת P) | עמוד עם העכבר לטעינת פרטים מלאים';
                }
                if (!row.style.opacity || row.style.opacity === '1') {
                row.style.opacity = '0.85';
                }
                // Setup hover loading only once
                this.setupHoverLoading(row, subscriber, index);
            } else if (!subscriber.hasFullDetails) {
                // For small/medium companies without full details
                if (!row.style.opacity || row.style.opacity === '1') {
                row.style.opacity = '0.85';
                }
                if (!row.title) {
                    row.title = 'נתונים בסיסיים - טוען פרטים...';
                }
            }
            
            const validUntil = new Date(subscriber.validUntil || subscriber.xValidUntil || '2030-12-31');
            const isExpired = validUntil < new Date();
            
            row.innerHTML = `
                <td>${subscriber.companyNum || ''}</td>
                <td>${subscriber.companyName || ''}</td>
                <td>${subscriber.subscriberNum || subscriber.id || ''}</td>
                <td>${subscriber.firstName || ''}</td>
                <td>${subscriber.lastName || subscriber.name || ''}</td>
                <td>${subscriber.tagNum || subscriber.cardno ? `<span class="tag-badge">${subscriber.tagNum || subscriber.cardno}</span>` : ''}</td>
                <td>${subscriber.vehicle1 || subscriber.lpn1 || ''}</td>
                <td>${subscriber.vehicle2 || subscriber.lpn2 || ''}</td>
                <td>${subscriber.vehicle3 || subscriber.lpn3 || ''}</td>
                <td class="${isExpired ? 'status-inactive' : 'status-active'}">${this.formatDate(subscriber.validUntil || subscriber.xValidUntil) || ''}</td>
                <td style="color: #888;" title="פרופיל ${subscriber.profile || subscriber.extCardProfile || ''}">${subscriber.profileName || `פרופיל ${subscriber.profile || subscriber.extCardProfile || ''}`}</td>
                <td>${this.formatDate(subscriber.validFrom || subscriber.xValidFrom) || ''}</td>
                <td style="text-align: center; font-size: 18px;">${subscriber.presence || subscriber.present ? '✅' : '❌'}</td>
            `;
            // Add to fragment for better performance
            if (isVeryLarge) {
                fragment.appendChild(row);
            } else {
            tbody.appendChild(row);
            }
            }
            
            // For batch rendering, schedule next batch
            if (isVeryLarge && end < subscribers.length) {
                currentBatch++;
                // Append current batch
                if (fragment.hasChildNodes()) {
                    // Remove loading message on first batch
                    if (currentBatch === 1) {
                        tbody.innerHTML = '';
                    }
                    // Don't use cloneNode - it doesn't copy event listeners!
                    tbody.appendChild(fragment);
                    // Create new fragment for next batch
                    fragment = document.createDocumentFragment();
                }
                // Schedule next batch
                setTimeout(renderBatch, 10);
            } else if (isVeryLarge) {
                // Last batch
                if (currentBatch === 0) {
                    tbody.innerHTML = '';
                }
                tbody.appendChild(fragment);
                console.log(`[displaySubscribers] Finished rendering ${subscribers.length} subscribers in ${currentBatch + 1} batches`);
                
                // Clear loading state after all batches are done
                this.setLoading(false, 'loadingState');
                this.hideProgressMessage();
                this.hideBackgroundProgress();
                
                // Force remove any loading overlays
                const loadingState = document.getElementById('loadingState');
                if (loadingState) {
                    loadingState.style.display = 'none';
                }
                
                const progressMsg = document.getElementById('progressMessage');
                if (progressMsg) {
                    progressMsg.remove();
                }
                
                // Make sure table is visible
                const tableContainer = document.getElementById('tableContainer');
                if (tableContainer) {
                    tableContainer.style.display = 'block';
                }
                
                // Show completion message
                this.showNotification(`✅ נטענו ${subscribers.length} מנויים`, 'success', 3000);
                
            }
        };
        
        // Start rendering
        if (isVeryLarge) {
            renderBatch();
        } else {
            // For smaller lists, use the regular forEach
            subscribers.forEach((subscriber, index) => {
                const row = document.createElement('tr');
                
                // Always allow viewing subscriber details
                // P permission is only needed for profile updates
                row.onclick = () => {
                    // Find the current subscriber data
                    const currentSubscriber = this.subscribers.find(s => 
                        s.subscriberNum === subscriber.subscriberNum
                    ) || subscriber;
                    // Trigger the edit function from the HTML page
                    if (window.editSubscriber) {
                        window.editSubscriber(currentSubscriber);
                    }
                };
                
                row.dataset.subscriberNum = subscriber.subscriberNum;
                row.dataset.index = index;
                
                // Add hover loading for large companies without full details
                if (subscriber.isLargeCompany && !subscriber.hasFullDetails) {
                    row.setAttribute('data-hover-loadable', 'true');
                    if (canEdit) {
                    row.title = 'עמוד עם העכבר לטעינת פרטים מלאים';
                    } else {
                        row.title = 'אין הרשאה לערוך מנויים (דרושה הרשאת P) | עמוד עם העכבר לטעינת פרטים מלאים';
                    }
                    if (!row.style.opacity || row.style.opacity === '1') {
                    row.style.opacity = '0.85';
                    }
                    // Setup hover loading only once
                    this.setupHoverLoading(row, subscriber, index);
                } else if (!subscriber.hasFullDetails) {
                    // For small/medium companies without full details
                    if (!row.style.opacity || row.style.opacity === '1') {
                    row.style.opacity = '0.85';
                    }
                    if (!row.title) {
                        row.title = 'נתונים בסיסיים - טוען פרטים...';
                    }
                }
                
                const validUntil = new Date(subscriber.validUntil || subscriber.xValidUntil || '2030-12-31');
                const isExpired = validUntil < new Date();
                
                row.innerHTML = `
                    <td>${subscriber.companyNum || ''}</td>
                    <td>${subscriber.companyName || ''}</td>
                    <td>${subscriber.subscriberNum || subscriber.id || ''}</td>
                    <td>${subscriber.firstName || ''}</td>
                    <td>${subscriber.lastName || subscriber.name || ''}</td>
                    <td>${subscriber.tagNum || subscriber.cardno ? `<span class="tag-badge">${subscriber.tagNum || subscriber.cardno}</span>` : ''}</td>
                    <td>${subscriber.vehicle1 || subscriber.lpn1 || ''}</td>
                    <td>${subscriber.vehicle2 || subscriber.lpn2 || ''}</td>
                    <td>${subscriber.vehicle3 || subscriber.lpn3 || ''}</td>
                    <td class="${isExpired ? 'status-inactive' : 'status-active'}">${this.formatDate(subscriber.validUntil || subscriber.xValidUntil) || ''}</td>
                    <td style="color: #888;" title="פרופיל ${subscriber.profile || subscriber.extCardProfile || ''}">${subscriber.profileName || `פרופיל ${subscriber.profile || subscriber.extCardProfile || ''}`}</td>
                    <td>${this.formatDate(subscriber.validFrom || subscriber.xValidFrom) || ''}</td>
                    <td style="text-align: center; font-size: 18px;">${subscriber.presence || subscriber.present ? '✅' : '❌'}</td>
            `;
            tbody.appendChild(row);
        });
            
            // Clear loading state for smaller companies
            this.setLoading(false, 'loadingState');
            this.hideProgressMessage();
            this.hideBackgroundProgress();
        }
    }
    
    /**
     * Get profiles used in current company
     */
    async getCompanyProfiles() {
        
        if (!this.currentContract) {
            return [];
        }
        
        try {
            // Getting profiles for company
            
            // Get all subscribers to see what profiles are in use
            const profilesInUse = new Map();
            let needToLoadDetails = true;
            
            // First check if we already have profiles in current subscribers
            if (this.subscribers && this.subscribers.length > 0) {
                this.subscribers.forEach((subscriber, idx) => {
                    
                    // Check multiple places for profile info
                    const profileId = subscriber.profileId || subscriber.profile || subscriber.extCardProfile || 
                                     subscriber.identification?.usageProfile?.id;
                    // Profile name might be the profile field itself if it contains name
                    let profileName = subscriber.profileName || subscriber.identification?.usageProfile?.name;
                    
                    // If no profile name but we have profile field with text, use it
                    if (!profileName && subscriber.profile && isNaN(subscriber.profile)) {
                        profileName = subscriber.profile;
                    }
                    
                    // If still no name, create default based on ID
                    if (!profileName && profileId) {
                        profileName = profileId === '1' ? 'כול החניונים' : 
                                    profileId === '0' ? 'רגיל' : 
                                    profileId === '2' ? 'חניון ראשי' :
                                    `פרופיל ${profileId}`;
                    }
                    
                    if (profileId && profileName) {
                        profilesInUse.set(profileId, profileName);
                        needToLoadDetails = false;
                    }
                });
            }
            
            // If we don't have profiles, load details for a few subscribers
            if (needToLoadDetails && this.subscribers && this.subscribers.length > 0) {
                // Load details for up to 5 subscribers to find profiles
                const subscribersToCheck = this.subscribers.slice(0, Math.min(5, this.subscribers.length));
                
                for (const subscriber of subscribersToCheck) {
                    try {
                        const details = await this.api.getConsumerDetailOnDemand(
                            this.currentContract.id,
                            subscriber.subscriberNum || subscriber.id
                        );
                        
                        if (details.success && details.data) {
                            
                            // Try different ways to get profile ID
                            let profileId = null;
                            let profileName = null;
                            
                            // Check if data has identification
                            if (details.data.identification) {
                                if (details.data.identification.usageProfile) {
                                    profileId = details.data.identification.usageProfile.id;
                                    profileName = details.data.identification.usageProfile.name;
                                }
                                // Also check direct properties
                                profileId = profileId || details.data.identification.extCardProfile;
                            }
                            
                            // Check direct properties on data
                            profileId = profileId || details.data.profileId || details.data.profile || details.data.extCardProfile;
                            profileName = profileName || details.data.profileName ||
                                        (profileId === '1' ? 'כול החניונים' : 
                                         profileId === '0' ? 'רגיל' : 
                                         profileId === '2' ? 'חניון ראשי' :
                                         `פרופיל ${profileId}`);
                            
                            if (profileId && profileName) {
                                profilesInUse.set(profileId, profileName);
                            }
                        }
                    } catch (err) {
                        // Continue to next subscriber
                    }
                }
            }
            
            // If we found profiles in use, return them
            if (profilesInUse.size > 0) {
                const profiles = [];
                profilesInUse.forEach((name, id) => {
                    profiles.push({ id, name });
                });
                return profiles;
            }
            
            // If no profiles in use, return a default based on company
            // Company 2 typically uses profile 1 (חניון ראשי)
            return [{ id: '1', name: 'חניון ראשי' }];
            
        } catch (error) {
            console.error('[getCompanyProfiles] Error:', error);
            // Return default profile on error
            return [{ id: '1', name: 'חניון ראשי' }];
        }
    }
    
    /**
     * Load and populate usage profiles in the select element
     */
    async loadUsageProfiles(isNewSubscriber = false) {
        try {
            const profileSelect = document.getElementById('editProfile');
            if (!profileSelect) {
                return;
            }
            
            // Always get company profiles (for both new and existing subscribers)
            const profiles = await this.getCompanyProfiles();
                
                // Clear and populate select
                profileSelect.innerHTML = '';
            
            // Check if user has permission to change profile
            const permissions = window.userPermissions || '';
            const canChangeProfile = permissions.includes('P');
                
                if (profiles.length > 0) {
                // If user can't change profile, get the last subscriber's profile
                let defaultProfileId = null;
                if (!canChangeProfile && this.subscribers && this.subscribers.length > 0) {
                    // Try to find the last subscriber with a profile
                    // First check if any subscriber already has profile info
                    for (let i = this.subscribers.length - 1; i >= 0; i--) {
                        const sub = this.subscribers[i];
                        if (sub.profileId || sub.profile) {
                            defaultProfileId = sub.profileId || sub.profile;
                            break;
                        }
                    }
                    
                    // If still no profile found, load details of the last subscriber
                    if (!defaultProfileId) {
                        try {
                            const lastSubscriber = this.subscribers[this.subscribers.length - 1];
                            const details = await this.api.getConsumerDetailOnDemand(
                                this.currentContract.id,
                                lastSubscriber.subscriberNum || lastSubscriber.id
                            );
                            
                            if (details.success && details.data) {
                                defaultProfileId = details.data.profileId || 
                                                 details.data.profile || 
                                                 details.data.extCardProfile ||
                                                 details.data.identification?.usageProfile?.id || '1';
                            }
                        } catch (err) {
                            defaultProfileId = '1'; // Default fallback
                        }
                    }
                        
                    // Find if this profile exists in our profiles list
                    const profileExists = profiles.some(p => p.id === defaultProfileId);
                    if (!profileExists) {
                        // Add the profile to the list
                        let profileName = `פרופיל ${defaultProfileId}`;
                        if (defaultProfileId === '1') profileName = 'כול החניונים';
                        else if (defaultProfileId === '0') profileName = 'רגיל';
                        else if (defaultProfileId === '2') profileName = 'חניון ראשי';
                        
                        profiles.push({
                            id: defaultProfileId,
                            name: profileName
                        });
                    }
                }
                    
                profiles.forEach(profile => {
                    const option = document.createElement('option');
                    option.value = profile.id;
                    option.setAttribute('data-profile-name', profile.name);
                    option.textContent = profile.name;
                    profileSelect.appendChild(option);
                });
                
                // Set default value
                if (!canChangeProfile && defaultProfileId) {
                    profileSelect.value = defaultProfileId;
                    profileSelect.disabled = true;
                    profileSelect.style.backgroundColor = '#f0f0f0';
                    profileSelect.style.cursor = 'not-allowed';
                    profileSelect.title = 'אין הרשאה לשנות פרופיל';
                } else {
                    profileSelect.disabled = false;
                    profileSelect.style.backgroundColor = '';
                    profileSelect.style.cursor = '';
                    profileSelect.title = '';
                }
                
                // If only one profile, disable the select
                if (profiles.length === 1) {
                    profileSelect.disabled = true;
                    profileSelect.style.backgroundColor = '#f0f0f0';
                    profileSelect.style.color = '#888';
                    profileSelect.style.cursor = 'not-allowed';
                        
                    const profileHelpText = document.getElementById('profileHelpText');
                    if (profileHelpText) {
                        profileHelpText.textContent = '* פרופיל יחיד בחברה';
                        profileHelpText.style.color = '#666';
                    }
                } else {
                    // Multiple profiles - enable selection
                    profileSelect.disabled = false;
                    profileSelect.style.backgroundColor = '';
                    profileSelect.style.color = '';
                    profileSelect.style.cursor = '';
                    
                    const profileHelpText = document.getElementById('profileHelpText');
                    if (profileHelpText) {
                        profileHelpText.textContent = '* בחר פרופיל מהרשימה';
                        profileHelpText.style.color = '#666';
                    }
                }
            } else {
                // No profiles - shouldn't happen but add fallback
                const option = document.createElement('option');
                option.value = '1';
                option.textContent = 'חניון ראשי';
                profileSelect.appendChild(option);
                profileSelect.disabled = true;
            }
            
            
            // Log final state
        } catch (error) {
            console.error('[loadUsageProfiles] Error loading profiles:', error);
        }
    }
    
    /**
     * Edit subscriber - prepare data for modal
     */
    async editSubscriber(subscriber) {
        console.log(`[editSubscriber] Called with subscriber ${subscriber.subscriberNum}, hasFullDetails: ${subscriber.hasFullDetails}`);
        
        // Always allow viewing subscriber details
        // Permission check will be done when saving changes
        
        // Check if we have full details
        if (!subscriber.hasFullDetails) {
            console.log(`[UI] Loading full details for subscriber ${subscriber.subscriberNum}`);
            
            // Show loading indicator
            this.showProgressMessage('טוען פרטי מנוי...');
            
            try {
                // Check if this is from a large company
                if (subscriber.isLargeCompany) {
                    // Large company subscriber - loading details on-demand
                }
                
                // Get full details on demand
                const result = await this.api.getConsumerDetailOnDemand(
                    this.currentContract.id, 
                    subscriber.subscriberNum
                );
                
                if (result.success) {
                    const detail = result.data;
                    
                    console.log(`[editSubscriber] Loaded detail from server:`, JSON.stringify({
                        validFrom: detail.identification?.validFrom,
                        validUntil: detail.identification?.validUntil,
                        xValidFrom: detail.consumer?.xValidFrom,
                        xValidUntil: detail.consumer?.xValidUntil,

                        present: detail.identification?.present
                    }, null, 2));
                    
                    // Preserve important fields and map correctly
                    const preservedFields = {
                        companyName: subscriber.companyName,
                        companyNum: subscriber.companyNum,
                        contractId: subscriber.contractId,
                        isLargeCompany: subscriber.isLargeCompany,
                        loadingStrategy: subscriber.loadingStrategy
                    };
                    
                    // Update subscriber with full details - map fields properly
                    Object.assign(subscriber, {
                        ...detail,
                        ...preservedFields,  // Preserve our fields
                        // Map profile correctly from identification.usageProfile
                        profile: detail.identification?.usageProfile?.id || detail.profile || detail.extCardProfile || subscriber.profile,
                        profileName: detail.identification?.usageProfile?.name || detail.profileName || subscriber.profileName,
                        extCardProfile: detail.identification?.usageProfile?.id || detail.extCardProfile || subscriber.extCardProfile,
                        // Map dates correctly
                        validFrom: detail.identification?.validFrom || detail.validFrom || subscriber.validFrom,
                        validUntil: detail.identification?.validUntil || detail.validUntil || subscriber.validUntil,
                        // Map vehicles
                        vehicle1: detail.lpn1 || subscriber.vehicle1 || '',
                        vehicle2: detail.lpn2 || subscriber.vehicle2 || '',
                        vehicle3: detail.lpn3 || subscriber.vehicle3 || '',
                        // Map presence correctly
                        presence: detail.identification?.present === 'true' || detail.presence,
                        // Mark as having full details
                        hasFullDetails: true
                    });
                    
                    // Update the row in the table
                    const index = this.subscribers.findIndex(s => 
                        s.subscriberNum === subscriber.subscriberNum
                    );
                    if (index !== -1) {
                        this.updateSubscriberRow(subscriber, index);
                    }
                    
                    if (subscriber.isLargeCompany) {
                        // Full details loaded successfully
                    }
                }
            } catch (error) {
                console.error('Error loading subscriber details:', error);
                this.showNotification('שגיאה בטעינת פרטי מנוי', 'error');
            } finally {
                this.hideProgressMessage();
            }
        }
        
        // Open edit modal with full data
        if (window.editSubscriber) {
            // ALWAYS use the company name from current contract, don't trust subscriber data
            if (this.currentContract) {
                subscriber.companyName = this.currentContract.name || this.currentContract.firstName || subscriber.companyName || '';
            }
            // Ensure we have all vehicle data mapped correctly
            subscriber.vehicle1 = subscriber.vehicle1 || subscriber.lpn1 || '';
            subscriber.vehicle2 = subscriber.vehicle2 || subscriber.lpn2 || '';
            subscriber.vehicle3 = subscriber.vehicle3 || subscriber.lpn3 || '';
            
            console.log('[editSubscriber from UI] Full subscriber data:', JSON.stringify(subscriber, null, 2));
            window.editSubscriber(subscriber);
        } else {
            console.error('[editSubscriber] window.editSubscriber function not found!');
        }
    }
    
    /**
     * Save subscriber (create or update)
     */
    async saveSubscriber(subscriberData) {
        if (!this.currentContract) return;
        
        // Check if trying to update profile
        const permissions = window.userPermissions || '';
        const currentSubscriber = this.subscribers.find(s => 
            String(s.subscriberNum) === String(subscriberData.subscriberNum)
        );
        
        // If updating an existing subscriber and changing profile, need P permission
        if (currentSubscriber && subscriberData.profileId && 
            String(currentSubscriber.profile) !== String(subscriberData.profileId) && 
            !permissions.includes('P')) {
            this.showNotification('אין לך הרשאה לשנות פרופיל (דרושה הרשאת P)', 'error');
            return;
        }
        
        this.setLoading(true);
        
        try {
            let result;
            
            // Double-check if this is really a new subscriber
            // If subscriberNum is provided and not empty, it's likely an update
            // Only consider it new if isNew is true AND no subscriber number
            const isReallyNew = subscriberData.isNew === true && (!subscriberData.subscriberNum || subscriberData.subscriberNum === '');
            
            // Additional check: if we have a subscriber number but isNew is somehow undefined/null,
            // assume it's an update
            const shouldUpdate = !isReallyNew && subscriberData.subscriberNum && subscriberData.subscriberNum !== '';
            

            
            // Prepare consumer data for XML API
            let consumerData;
            
            if (shouldUpdate) {
                // Preparing UPDATE data

                
                // For UPDATE - structure data according to API spec for /detail endpoint
                // Add timezone to dates for XML format
                const formatDateWithTimezone = (date) => {
                    if (!date) return '';
                    
                    let formattedDate = date;
                    
                    // Convert DD/MM/YYYY to YYYY-MM-DD if needed
                    if (/^\d{1,2}\/\d{1,2}\/\d{4}$/.test(date)) {
                        const parts = date.split('/');
                        const day = parts[0].padStart(2, '0');
                        const month = parts[1].padStart(2, '0');
                        const year = parts[2];
                        formattedDate = `${year}-${month}-${day}`;
                    }
                    
                    // Add Israel timezone (+02:00 or +03:00 depending on DST)
                    return formattedDate + '+02:00';
                };
                
                consumerData = {
                    consumer: {
                        id: subscriberData.subscriberNum,
                        contractid: this.currentContract.id,
                        name: `${subscriberData.lastName || ''} ${subscriberData.firstName || ''}`.trim() || '',
                        // Send dates with timezone
                        xValidFrom: formatDateWithTimezone(subscriberData.validFrom),
                        xValidUntil: formatDateWithTimezone(subscriberData.validUntil),
                        filialId: this.currentContract.filialId || '2228'  // Add filialId
                    },
                    person: {
                        firstName: (subscriberData.firstName || '').trim(),
                        surname: (subscriberData.lastName || subscriberData.surname || '').trim()
                    },
                    identification: {
                        ptcptType: '2',  // Required field from documentation
                        cardno: subscriberData.tagNum || '',
                        cardclass: '1',  // Keep as 1
                        identificationType: '54',  // Back to 54 as per your requirement
                        validFrom: formatDateWithTimezone(subscriberData.validFrom),
                        validUntil: formatDateWithTimezone(subscriberData.validUntil),
                        usageProfile: {
                            id: subscriberData.profileId || '1',
                            name: subscriberData.profile || 'Standard'
                        },
                        admission: '',  // Empty as in documentation
                        status: '0',  // Active status (0 = active, 6 = locked)
                        ptcptGrpNo: '-1',  // Default group
                        chrgOvdrftAcct: '0'  // Don't charge overdraft
                    },
                    displayText: '-1',
                    limit: '9999900',
                    status: '0',  // Active status
                    delete: '0',  // Not deleted
                    // Vehicle data - clean dashes from vehicle numbers
                    lpn1: (subscriberData.vehicle1 || '').replace(/-/g, ''),
                    lpn2: (subscriberData.vehicle2 || '').replace(/-/g, ''),
                    lpn3: (subscriberData.vehicle3 || '').replace(/-/g, '')
                };
                
                // UPDATE payload prepared
            } else {
                // For NEW subscriber - send full structure matching documentation
                const formatDateWithTimezone = (date) => {
                    if (!date) return '';
                    
                    let formattedDate = date;
                    
                    // Convert DD/MM/YYYY to YYYY-MM-DD if needed
                    if (/^\d{1,2}\/\d{1,2}\/\d{4}$/.test(date)) {
                        const parts = date.split('/');
                        const day = parts[0].padStart(2, '0');
                        const month = parts[1].padStart(2, '0');
                        const year = parts[2];
                        formattedDate = `${year}-${month}-${day}`;
                    }
                    
                    // Add Israel timezone
                    return formattedDate + '+02:00';
                };
                
                consumerData = {
                    consumer: {
                        id: '',  // Empty for new subscriber
                        contractid: this.currentContract.id,
                        name: `${subscriberData.lastName || ''} ${subscriberData.firstName || ''}`.trim() || '',
                        xValidFrom: formatDateWithTimezone(subscriberData.validFrom),
                        xValidUntil: formatDateWithTimezone(subscriberData.validUntil),
                        filialId: this.currentContract.filialId || '2228'
                    },
                    person: {
                        firstName: (subscriberData.firstName || '').trim(),
                        surname: (subscriberData.lastName || subscriberData.surname || '').trim()
                    },
                identification: {
                    ptcptType: '2',
                    cardno: subscriberData.tagNum || '',
                        cardclass: '1',  // Keep as 1
                        identificationType: '54',  // Back to 54 as per your requirement
                        validFrom: formatDateWithTimezone(subscriberData.validFrom),
                        validUntil: formatDateWithTimezone(subscriberData.validUntil),

                        status: '0',  // Active
                        ptcptGrpNo: '-1',
                        chrgOvdrftAcct: '0',
                    usageProfile: {
                        id: subscriberData.profileId || '1',
                            name: subscriberData.profile || 'Standard'
                        }
                    },
                    displayText: '-1',
                    limit: '9999900',
                    status: '0',
                    delete: '0',
                    // Vehicles
                    lpn1: (subscriberData.vehicle1 || '').replace(/-/g, ''),
                    lpn2: (subscriberData.vehicle2 || '').replace(/-/g, ''),
                    lpn3: (subscriberData.vehicle3 || '').replace(/-/g, '')
                };
                
                // NEW payload prepared
            }
            
            if (isReallyNew) {
                // Need to ensure subscribers list is loaded
                if (!this.subscribers || this.subscribers.length === 0) {
                    // Loading subscribers list for numbering
                    await this.loadSubscribers();
                }
                
                // Calculate next available subscriber number
                if (!subscriberData.subscriberNum || subscriberData.subscriberNum === '') {
                    // Check if this is a guest
                    if (subscriberData.isGuest || subscriberData.profile === 'guest' || subscriberData.firstName === 'אורח') {
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
                        
                        consumerData.consumer.id = String(nextGuestId);
                        // Creating guest
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
                        
                        // Don't send ID for regular subscribers - let server assign
                        consumerData.consumer.id = '';
                        // Creating regular subscriber
                    }
                } else {
                    // Use provided subscriber number
                    consumerData.consumer.id = subscriberData.subscriberNum;
                    // Using provided subscriber number
                }
                
                // Create new consumer with all details in one call
                result = await this.api.addConsumer(this.currentContract.id, consumerData);
                
                // Server response received
                
                if (result.success) {
                    console.log('New consumer created successfully');
                    
                    // Check if we got the created consumer ID from server
                    if (result.data && result.data.id) {
                        consumerData.consumer.id = result.data.id;
                        // Server assigned ID
                    }
                    // Send email notification if email provided
                    if (subscriberData.email) {
                        console.log(`Sending email notification to: ${subscriberData.email}`);
                        try {
                            const emailResponse = await fetch('/api/company-manager/send-guest-email', {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                },
                                body: JSON.stringify({
                                    email: subscriberData.email,
                                    name: `${subscriberData.lastName || ''} ${subscriberData.firstName || ''}`.trim() || 'אורח',
                                    validFrom: subscriberData.validFrom,
                                    validUntil: subscriberData.validUntil,
                                    parkingName: this.currentParking?.name || this.currentContract.parkingName || this.currentContract.name || 'החניון',
                                    companyName: this.currentContract.name || '',
                                    vehicleNumber: subscriberData.vehicle1 || ''
                                })
                            });
                            const emailResult = await emailResponse.json();
                            if (emailResult.success) {
                                console.log('Email sent successfully');
                                showToast('מייל אישור נשלח לאורח', 'success');
                            } else {
                                console.error('Failed to send email:', emailResult.message);
                                showToast('האורח נוצר בהצלחה אך לא ניתן לשלוח מייל', 'warning');
                            }
                        } catch (emailError) {
                            console.error('Error sending email:', emailError);
                            showToast('האורח נוצר בהצלחה אך לא ניתן לשלוח מייל', 'warning');
                        }
                    }
                }
            } else {
                // Update existing consumer with all details
                // Updating existing consumer
                result = await this.api.updateConsumer(
                    this.currentContract.id,
                    subscriberData.subscriberNum,
                    consumerData
                );
                
                // Server response
                

                
                // If update failed with 500 error, try different approaches
                if (!result.success && result.error && result.error.includes('500')) {
                    // Update failed with 500
                    
                    // Check if this is company 8 or other large companies
                    const isLargeCompany = this.currentContract.id === '8' || 
                                          this.currentContract.id === '4' || 
                                          this.currentContract.id === '10';
                    
                    if (isLargeCompany) {
                        // Large company detected
                        
                        // For large companies, try WITHOUT identification at all
                        const minimalData = {
                            firstName: consumerData.firstName || consumerData.surname || consumerData.lastName || 'Unknown',
                            surname: consumerData.surname || consumerData.lastName || consumerData.firstName || 'Unknown',
                            lpn1: consumerData.lpn1 || '',
                            // Only include lpn2 if not empty
                            ...(consumerData.lpn2 ? { lpn2: consumerData.lpn2 } : {}),
                            // Only include lpn3 if lpn2 exists
                            ...(consumerData.lpn2 && consumerData.lpn3 ? { lpn3: consumerData.lpn3 } : {}),
                            consumer: consumerData.consumer
                            // NO identification block at all for large companies
                        };
                        
                        // Trying with minimal data
                        result = await this.api.updateConsumer(
                            this.currentContract.id,
                            subscriberData.subscriberNum,
                            minimalData
                        );
                        
                        if (result.success) {
                            // Consumer updated successfully
                            this.showNotification('✅ הנתונים הבסיסיים נשמרו בהצלחה', 'success');
                        }
                    }
                    
                    // If still failed, try without identification at all for problematic companies
                    if (!result.success) {
                        // Still failing
                        
                        // Create a copy without identification
                        const dataWithoutIdentification = {
                            firstName: consumerData.firstName || consumerData.surname || 'Unknown',
                            surname: consumerData.surname || consumerData.firstName || 'Unknown',
                            lpn1: consumerData.lpn1 || '',
                            // Only include lpn2 if not empty
                            ...(consumerData.lpn2 ? { lpn2: consumerData.lpn2 } : {}),
                            // Only include lpn3 if lpn2 exists
                            ...(consumerData.lpn2 && consumerData.lpn3 ? { lpn3: consumerData.lpn3 } : {}),
                            consumer: consumerData.consumer
                            // NO identification at all
                        };
                        
                        result = await this.api.updateConsumer(
                            this.currentContract.id,
                            subscriberData.subscriberNum,
                            dataWithoutIdentification
                        );
                        
                        if (result.success) {
                            // Consumer updated successfully
                            this.showNotification('⚠️ הנתונים נשמרו ללא פרופיל שימוש', 'warning');
                        }
                    }
                }
                
                if (result.success) {
                    // Consumer updated successfully
                }
            }
            
            if (result.success) {
                // Use message from server if available, otherwise show generic success
                const message = result.message || result.data?.message || 'הנתונים נשמרו בהצלחה';
                this.showNotification(message, 'success');
                
                // Only update the specific subscriber in the list, don't reload everything
                if (shouldUpdate && subscriberData.subscriberNum) {
                    // Find and update the subscriber in our local array
                    // IMPORTANT: Compare subscriberNum to subscriberNum, not id!
                    // Convert to string for comparison
                    const subscriberNumStr = String(subscriberData.subscriberNum);
                    
                    // Looking for subscriber in array
                    
                    const index = this.subscribers.findIndex(s => 
                        String(s.subscriberNum) === subscriberNumStr || 
                        String(s.id) === subscriberNumStr
                    );
                    
                    // Found subscriber
                    
                    if (index !== -1) {
                        // Updating subscriber
                        
                        // Update local data - preserve important fields
                        const updatedSubscriber = {
                            ...this.subscribers[index],
                            firstName: subscriberData.firstName,
                            lastName: subscriberData.lastName,
                            name: subscriberData.lastName,
                            vehicle1: subscriberData.vehicle1,
                            vehicle2: subscriberData.vehicle2,
                            vehicle3: subscriberData.vehicle3,
                            lpn1: subscriberData.vehicle1,
                            lpn2: subscriberData.vehicle2,
                            lpn3: subscriberData.vehicle3,
                            validFrom: subscriberData.validFrom,
                            validUntil: subscriberData.validUntil,
                            xValidFrom: subscriberData.validFrom,
                            xValidUntil: subscriberData.validUntil,
                            tagNum: subscriberData.tagNum,
                            cardno: subscriberData.tagNum,
                            profile: subscriberData.profileId,
                            profileName: subscriberData.profile,
                            // Keep current presence - it will be updated from server on next load
                            presence: this.subscribers[index].presence,
                            // DO NOT update 'present' - it's read-only from server
                            // Preserve company name and other UI fields
                            companyName: this.subscribers[index].companyName,
                            isLargeCompany: this.subscribers[index].isLargeCompany,
                            loadingStrategy: this.subscribers[index].loadingStrategy,
                            hasFullDetails: false  // Reset to force reload on next edit
                        };
                        
                        // CRITICAL: Actually update the subscriber in the array!
                        this.subscribers[index] = updatedSubscriber;
                        
                        // Updated subscriber in array
                        
                        // Update the specific row in the table
                        this.updateSubscriberRow(this.subscribers[index], index);
                    }
                } else if (isReallyNew) {
                    // For new subscribers, add to the list without reloading
                    // Use the ID from server response if available
                    const subscriberId = result.data?.id || consumerData.consumer.id || subscriberData.subscriberNum;
                    
                    const newSubscriber = {
                        ...subscriberData,
                        id: subscriberId,
                        subscriberNum: subscriberId,
                        hasFullDetails: true,
                        companyNum: this.currentContract.id,
                        companyName: subscriberData.companyName || this.currentContract.name,
                        // Ensure we have all required fields
                        firstName: subscriberData.firstName || '',
                        lastName: subscriberData.lastName || '',
                        tagNum: subscriberData.tagNum || '',
                        vehicle1: subscriberData.vehicle1 || '',
                        vehicle2: subscriberData.vehicle2 || '',
                        vehicle3: subscriberData.vehicle3 || '',
                        validFrom: subscriberData.validFrom || '',
                        validUntil: subscriberData.validUntil || '',
                        profile: subscriberData.profile || subscriberData.profileId || '',
                        profileName: subscriberData.profileName || ''
                    };
                    
                    // Add to subscribers array
                    this.subscribers.push(newSubscriber);
                    
                    // Add only the new row instead of re-displaying the entire table
                    const tbody = document.querySelector('#subscribersTable tbody');
                    if (tbody) {
                        const newRow = document.createElement('tr');
                        const newIndex = this.subscribers.length - 1;
                        
                        // Set row attributes
                        newRow.dataset.subscriberNum = newSubscriber.subscriberNum;
                        newRow.onclick = () => {
                            // Find the current subscriber data (might have been updated)
                            const currentSubscriber = this.subscribers.find(s => 
                                s.subscriberNum === newSubscriber.subscriberNum
                            ) || newSubscriber;
                            this.editSubscriber(currentSubscriber);
                        };
                        
                        // Create row content - match the structure from displaySubscribers
                        const validUntil = new Date(newSubscriber.validUntil || '2030-12-31');
                        const isExpired = validUntil < new Date();
                        
                        newRow.innerHTML = `
                            <td>${newSubscriber.companyNum || ''}</td>
                            <td>${newSubscriber.companyName || ''}</td>
                            <td>${newSubscriber.subscriberNum || newSubscriber.id || ''}</td>
                            <td>${newSubscriber.firstName || ''}</td>
                            <td>${newSubscriber.lastName || ''}</td>
                            <td>${newSubscriber.tagNum ? `<span class="tag-badge">${newSubscriber.tagNum}</span>` : ''}</td>
                            <td>${newSubscriber.vehicle1 || ''}</td>
                            <td>${newSubscriber.vehicle2 || ''}</td>
                            <td>${newSubscriber.vehicle3 || ''}</td>
                            <td class="${isExpired ? 'status-inactive' : 'status-active'}">${this.formatDate(newSubscriber.validUntil) || ''}</td>
                            <td style="color: #888;" title="פרופיל ${newSubscriber.profile || ''}">${newSubscriber.profileName || `פרופיל ${newSubscriber.profile || ''}`}</td>
                            <td>${this.formatDate(newSubscriber.validFrom) || ''}</td>
                            <td style="text-align: center; font-size: 18px;">${newSubscriber.presence ? '✅' : '❌'}</td>
                        `;
                        
                        tbody.appendChild(newRow);
                    }
                    
                    // Update counts in header
                    this.updatePresentCount();
                }
                
                // Send email notification if email provided (for updates too)
                if (!isReallyNew && subscriberData.email && result.success) {
                    console.log(`Sending email notification for updated subscriber to: ${subscriberData.email}`);
                    try {
                        const emailResponse = await fetch('/api/company-manager/send-guest-email', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({
                                email: subscriberData.email,
                                name: `${subscriberData.lastName || ''} ${subscriberData.firstName || ''}`.trim() || 'מנוי',
                                validFrom: subscriberData.validFrom,
                                validUntil: subscriberData.validUntil,
                                parkingName: this.currentParking?.name || this.currentContract.parkingName || this.currentContract.name || 'החניון',
                                companyName: this.currentContract.name || '',
                                vehicleNumber: subscriberData.vehicle1 || ''
                            })
                        });
                        const emailResult = await emailResponse.json();
                        if (emailResult.success) {
                            console.log('Email sent successfully');
                            showToast('מייל אישור נשלח למנוי', 'success');
                        } else {
                            console.error('Failed to send email:', emailResult.message);
                            // Don't show error for updates - email is optional
                        }
                    } catch (emailError) {
                        console.error('Error sending email:', emailError);
                        // Don't show error for updates - email is optional
                    }
                }
                
                return true;
            } else {
                // Provide clearer error messages based on the error type
                let errorMessage = 'שגיאה בשמירת הנתונים';
                
                if (result.error) {
                    if (result.error.includes('500') || result.error.includes('Internal Server Error')) {
                        // Check if it's a present subscriber error
                        if (consumerData.identification && consumerData.identification.present === 'true') {
                            errorMessage = '⚠️ לא ניתן לעדכן מנוי נוכח בחניון - יש להוציא את הרכב מהחניון לפני עדכון פרטים';
                        } else {
                            errorMessage = '⚠️ שגיאת שרת - ייתכן שהמנוי נוכח בחניון או שיש בעיה בנתונים שנשלחו';
                        }
                    } else if (result.error.includes('400') || result.error.includes('Bad Request')) {
                        errorMessage = '❌ הנתונים שהוזנו אינם תקינים - אנא בדוק את הפרטים';
                    } else if (result.error.includes('404')) {
                        errorMessage = '❌ המנוי לא נמצא במערכת';
                    } else if (result.error.includes('403') || result.error.includes('Forbidden')) {
                        errorMessage = '🔒 אין הרשאה לבצע פעולה זו';
                    } else {
                        errorMessage = `❌ ${result.error}`;
                    }
                }
                
                this.showNotification(errorMessage, 'error');
                return false;
            }
        } catch (error) {
            console.error('Error saving subscriber:', error);
            
            // Try to provide a meaningful error message
            let errorMessage = 'שגיאה בשמירת הנתונים';
            if (error.message) {
                if (error.message.includes('present')) {
                    errorMessage = '⚠️ לא ניתן לעדכן מנוי נוכח בחניון';
                } else if (error.message.includes('network')) {
                    errorMessage = '🌐 בעיית תקשורת - אנא בדוק את החיבור לאינטרנט';
                } else {
                    errorMessage = `❌ ${error.message}`;
                }
            }
            
            this.showNotification(errorMessage, 'error');
            return false;
        } finally {
            this.setLoading(false);
        }
    }
    
    /**
     * Delete subscriber
     */
    async deleteSubscriber(subscriberId) {
        if (!this.currentContract) return;
        
        if (!confirm('האם אתה בטוח שברצונך למחוק מנוי זה?')) {
            return;
        }
        
        this.setLoading(true);
        
        try {
            const result = await this.api.deleteConsumer(this.currentContract.id, subscriberId);
            
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
     * Report Functions
     */
    
    // Get parking transactions report for a subscriber
    async getSubscriberReport(subscriberNum, minDate = null, maxDate = null) {
        console.log('🏢 Current Contract:', this.currentContract);
        
        try {
            // Starting report for subscriber
            
            if (!this.currentContract || !this.currentContract.id) {
                console.error('❌ No current contract!');
                // No current contract set
                throw new Error('לא נבחרה חברה');
            }
            
            const contractId = this.currentContract.id;
            console.log('📋 Contract ID:', contractId);
            
            // Getting report for subscriber
            
            // Get parking transactions from API
            const result = await this.api.getParkingTransactions(contractId, subscriberNum, minDate, maxDate);
            // API response received
            
            console.log('📥 API Result:', result);
            
            if (!result.success) {
                console.error('❌ API Failed:', result.error);
                throw new Error(result.error || 'Failed to get parking transactions');
            }
            
            const transactions = result.data || [];
            console.log('📋 Transactions received:', transactions.length);
            // Found transactions
            
            // Filter transactions by type (1, 2, 11, 12)
            const allowedTypes = ['1', '2', '11', '12'];
            const filteredTransactions = transactions.filter(trans => {
                const typeStr = String(trans.transactionType);
                return allowedTypes.includes(typeStr);
            });
            
            // Filtered transactions
            
            // Format transactions for display
            console.log('🔍 First transaction raw data:', filteredTransactions[0]);
            const formattedTransactions = filteredTransactions.map(trans => {
                console.log('📝 Processing transaction:', trans);
                const formatted = {
                    date: this.formatDateTime(trans.transactionTime),
                    type: this.getTransactionTypeName(trans.transactionType),
                    entrance: trans.facilityin || '-',
                    exit: trans.facilityout || '-',
                    device: trans.device || '-',
                    amount: trans.amount ? `₪${trans.amount}` : '-'
                };
                console.log('✅ Formatted transaction:', formatted);
                return formatted;
            });
            
            return {
                success: true,
                data: formattedTransactions,
                summary: {
                    total: filteredTransactions.length,
                    totalAmount: filteredTransactions.reduce((sum, t) => sum + (parseFloat(t.amount) || 0), 0)
                }
            };
            
        } catch (error) {
            console.error('[getSubscriberReport] Error:', error);
            return {
                success: false,
                error: error.message || 'Failed to get report'
            };
        }
    }
    
    // Format date and time for display
    formatDateTime(dateTimeStr) {
        if (!dateTimeStr) return '-';
        try {
            const date = new Date(dateTimeStr);
            const day = String(date.getDate()).padStart(2, '0');
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const year = date.getFullYear();
            const hours = String(date.getHours()).padStart(2, '0');
            const minutes = String(date.getMinutes()).padStart(2, '0');
            return `${day}/${month}/${year} ${hours}:${minutes}`;
        } catch (e) {
            return dateTimeStr;
        }
    }
    
    // Get transaction type name
    getTransactionTypeName(typeCode) {
        const types = {
            '1': 'כניסה רגילה',
            '2': 'יציאה רגילה',
            '11': 'כניסה חריגה',
            '12': 'יציאה חריגה',
            '42': 'כניסה',
            '43': 'יציאה',
            '44': 'תשלום',
            '45': 'ביטול'
        };
        return types[String(typeCode)] || `סוג ${typeCode}`;
    }
    
    /**
     * UI Helper Functions
     */
    exportToCSV() {
        if (!this.subscribers || this.subscribers.length === 0) {
            this.showNotification('אין נתונים לייצוא', 'warning');
            return;
        }
        
        console.log('[exportToCSV] Exporting data for', this.subscribers.length, 'subscribers');
        console.log('[exportToCSV] Sample subscriber data:', this.subscribers[0]);
        
        // Check if all subscribers have full details
        const subscribersWithoutDetails = this.subscribers.filter(s => !s.hasFullDetails);
        if (subscribersWithoutDetails.length > 0) {
            console.log(`[exportToCSV] Warning: ${subscribersWithoutDetails.length} subscribers without full details`);
            
            // For large companies, offer to load all details first
            if (subscribersWithoutDetails.length > 10) {
                const confirmLoad = confirm(`יש ${subscribersWithoutDetails.length} מנויים ללא פרטים מלאים.\nהאם לטעון את כל הפרטים לפני הייצוא? (עלול לקחת זמן)`);
                if (confirmLoad) {
                    this.showNotification('טוען פרטים מלאים...', 'info');
                    // In the future, we could implement loading all details here
                    // For now, just warn the user
                }
            }
        }
        
        // Create CSV content
        const headers = [
            'מספר חברה',
            'שם חברה', 
            'מספר מנוי',
            'שם פרטי',
            'שם משפחה',
            'מספר תג',
            'רכב 1',
            'רכב 2', 
            'רכב 3',
            'תחילת תוקף',
            'בתוקף עד',
            'פרופיל',
            'נוכחות'
        ];
        
        // Create CSV rows
        const rows = this.subscribers.map(subscriber => {
            // Debug log for first few subscribers
            if (this.subscribers.indexOf(subscriber) < 3) {
                console.log(`[exportToCSV] Subscriber ${subscriber.subscriberNum}:`, {
                    firstName: subscriber.firstName,
                    lastName: subscriber.lastName,
                    surname: subscriber.surname,
                    vehicle1: subscriber.vehicle1,
                    lpn1: subscriber.lpn1,
                    hasFullDetails: subscriber.hasFullDetails
                });
            }
            
            return [
            subscriber.companyNum || '',
            subscriber.companyName || '',
            subscriber.subscriberNum || '',
            subscriber.firstName || '',
                subscriber.lastName || subscriber.surname || subscriber.name || '',
                subscriber.tagNum || subscriber.cardno || '',
                subscriber.vehicle1 || subscriber.lpn1 || '',
                subscriber.vehicle2 || subscriber.lpn2 || '',
                subscriber.vehicle3 || subscriber.lpn3 || '',
                this.formatDate(subscriber.validFrom || subscriber.xValidFrom) || '',
                this.formatDate(subscriber.validUntil || subscriber.xValidUntil) || '',
                subscriber.profileName || subscriber.profile || subscriber.extCardProfile || '',
                subscriber.presence || subscriber.present ? 'נוכח' : 'לא נוכח'
            ];
        });
        
        // Combine headers and rows
        const csvContent = [
            headers.join(','),
            ...rows.map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
        ].join('\n');
        
        // Add BOM for Hebrew support in Excel
        const BOM = '\uFEFF';
        const csvWithBOM = BOM + csvContent;
        
        // Create blob and download
        const blob = new Blob([csvWithBOM], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);
        
        // Generate filename with timestamp
        const now = new Date();
        const dateStr = now.toISOString().split('T')[0];
        const timeStr = now.toTimeString().split(':').slice(0,2).join('-');
        const companyName = this.currentContract ? this.currentContract.name : 'all';
        const filename = `parking_subscribers_${companyName}_${dateStr}_${timeStr}.csv`;
        
        link.setAttribute('href', url);
        link.setAttribute('download', filename);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        this.showNotification(`הקובץ ${filename} יוצא בהצלחה`, 'success');
    }
    
    /**
     * Helper methods for UI
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
        if (window.showToast) {
            window.showToast(message, type);
        } else {
            alert(message);
        }
    }
    
    formatDate(dateString) {
        if (!dateString) return '';
        
        // If already in DD/MM/YYYY format, return as is
        if (/^\d{1,2}\/\d{1,2}\/\d{4}$/.test(dateString)) {
            return dateString;
        }
        
        // Handle XML date format with timezone (e.g., "2014-08-15+02:00")
        const cleanDate = dateString.split('+')[0].split('T')[0];
        
        // If in server format (YYYY-MM-DD), convert to European
        if (/^\d{4}-\d{2}-\d{2}/.test(cleanDate)) {
            const parts = cleanDate.split('-');
            const year = parts[0];
            const month = parts[1];
            const day = parts[2];
            return `${day}/${month}/${year}`;
        }
        
        // Try to parse as date
        const date = new Date(cleanDate);
        if (!isNaN(date.getTime())) {
            const day = String(date.getDate()).padStart(2, '0');
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const year = date.getFullYear();
            return `${day}/${month}/${year}`;
        }
        
        return dateString;
    }
    
    getProfileText(profile) {
        const profiles = {
            'regular': 'רגיל',
            'vip': 'VIP',
            'disabled': 'נכה',
            'guest': 'אורח'
        };
        return profiles[profile] || profile || 'רגיל';
    }
    
    /**
     * Initialize the integration
     */

    
    async initialize() {
        console.log('Initializing Parking XML UI Integration...');
        
        // Load initial data
        await this.loadCompanies();
        
        // Update button permissions
        this.updateButtonPermissions();
        
        // Set up event listeners
        this.setupEventListeners();
        
        console.log('Parking XML UI Integration initialized');
    }
    
    setupEventListeners() {
        // Override the global save function
        if (window.saveSubscriber) {
            const originalSave = window.saveSubscriber;
            window.saveSubscriber = async () => {
                // Get form data
                const profileSelect = document.getElementById('editProfile');
                const selectedOption = profileSelect.selectedOptions[0];
                
                const formData = {
                    companyNum: document.getElementById('editCompanyNum').value,
                    companyName: document.getElementById('editCompanyName').value,
                    subscriberNum: document.getElementById('editSubscriberNum').value || '',
                    firstName: document.getElementById('editFirstName').value || '',
                    lastName: document.getElementById('editLastName').value,
                    tagNum: document.getElementById('editTagNum').value || '',
                    // Clean vehicle numbers - remove dashes
                    vehicle1: (document.getElementById('editVehicle1').value || '').replace(/-/g, ''),
                    vehicle2: (document.getElementById('editVehicle2').value || '').replace(/-/g, ''),
                    vehicle3: (document.getElementById('editVehicle3').value || '').replace(/-/g, ''),
                    validFrom: document.getElementById('editValidFrom').value,
                    validUntil: document.getElementById('editValidUntil').value,
                    profileId: profileSelect.value || '1',
                    profile: selectedOption?.getAttribute('data-profile-name') || selectedOption?.text || 'regular',
                    email: document.getElementById('editEmail')?.value || '',
                    isNew: !window.editingSubscriber,  // New subscriber if editingSubscriber is null
                    isGuest: document.getElementById('editFirstName').value === 'אורח' || 
                            document.getElementById('editModal')?.classList.contains('guest-mode')
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
    }
}

// Create global instance
window.parkingUIXML = new ParkingUIIntegrationXML();

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.parkingUIXML.initialize();
    });
} else {
    window.parkingUIXML.initialize();
}
