/**
 * Parking Management System API Client
 * Connects to parking server at specified IP and port
 * Protocol: REST API with JSON
 */

class ParkingAPI {
    constructor() {
        // Load configuration
        const config = window.parkingConfig || {};
        const currentConfig = config.current || config.development || {};
        
        // Default configuration for development
        this.config = {
            baseUrl: currentConfig.useProxy ? currentConfig.proxyUrl : currentConfig.apiUrl,
            username: currentConfig.username || '2022',
            password: currentConfig.password || '2022',
            timeout: 30000, // 30 seconds
            retryAttempts: 3,
            retryDelay: 1000, // 1 second
            useProxy: currentConfig.useProxy || false
        };
        
        // Authentication token (if needed)
        this.authToken = null;
        
        // Cache configuration
        this.cache = {
            enabled: true,
            duration: 60000, // 1 minute
            data: new Map()
        };
    }
    
    /**
     * Set API configuration
     */
    setConfig(config) {
        this.config = { ...this.config, ...config };
    }
    
    /**
     * Basic authentication header
     */
    getAuthHeaders() {
        const auth = btoa(`${this.config.username}:${this.config.password}`);
        return {
            'Authorization': `Basic ${auth}`,
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        };
    }
    
    /**
     * Generic API request with retry logic
     */
    async makeRequest(endpoint, options = {}, retryCount = 0) {
        const url = `${this.config.baseUrl}${endpoint}`;
        
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), this.config.timeout);
            
            const response = await fetch(url, {
                ...options,
                headers: {
                    ...this.getAuthHeaders(),
                    ...options.headers
                },
                signal: controller.signal,
                // For self-signed certificates in development
                mode: 'cors',
                credentials: 'include'
            });
            
            clearTimeout(timeoutId);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            return { success: true, data };
            
        } catch (error) {
            console.error(`API request failed: ${error.message}`);
            
            // Retry logic
            if (retryCount < this.config.retryAttempts) {
                console.log(`Retrying... (${retryCount + 1}/${this.config.retryAttempts})`);
                await new Promise(resolve => setTimeout(resolve, this.config.retryDelay));
                return this.makeRequest(endpoint, options, retryCount + 1);
            }
            
            return { 
                success: false, 
                error: error.message,
                isNetworkError: error.name === 'AbortError' || error.message.includes('Failed to fetch')
            };
        }
    }
    
    /**
     * Authenticate with the server
     */
    async authenticate() {
        const result = await this.makeRequest('/api/auth/login', {
            method: 'POST',
            body: JSON.stringify({
                username: this.config.username,
                password: this.config.password
            })
        });
        
        if (result.success && result.data.token) {
            this.authToken = result.data.token;
        }
        
        return result;
    }
    
    /**
     * Get companies list for authenticated user
     */
    async getCompanies() {
        const cacheKey = 'companies';
        
        // Check cache
        if (this.cache.enabled) {
            const cached = this.getCachedData(cacheKey);
            if (cached) return { success: true, data: cached };
        }
        
        const result = await this.makeRequest('/api/companies');
        
        if (result.success) {
            this.setCachedData(cacheKey, result.data);
        }
        
        return result;
    }
    
    /**
     * Get subscribers for a specific company
     */
    async getSubscribers(companyId) {
        const cacheKey = `subscribers_${companyId}`;
        
        // Check cache
        if (this.cache.enabled) {
            const cached = this.getCachedData(cacheKey);
            if (cached) return { success: true, data: cached };
        }
        
        const result = await this.makeRequest(`/api/companies/${companyId}/subscribers`);
        
        if (result.success) {
            this.setCachedData(cacheKey, result.data);
        }
        
        return result;
    }
    
    /**
     * Get single subscriber details
     */
    async getSubscriber(companyId, subscriberId) {
        return await this.makeRequest(`/api/companies/${companyId}/subscribers/${subscriberId}`);
    }
    
    /**
     * Create new subscriber
     */
    async createSubscriber(companyId, subscriberData) {
        // Clear cache for this company
        this.clearCache(`subscribers_${companyId}`);
        
        const result = await this.makeRequest(`/api/companies/${companyId}/subscribers`, {
            method: 'POST',
            body: JSON.stringify(subscriberData)
        });
        
        // Send email notification for guest
        if (result.success && subscriberData.profile === 'guest' && subscriberData.guestEmail) {
            await this.sendGuestNotification(subscriberData.guestEmail, subscriberData);
        }
        
        return result;
    }
    
    /**
     * Update existing subscriber
     */
    async updateSubscriber(companyId, subscriberId, subscriberData) {
        // Clear cache for this company
        this.clearCache(`subscribers_${companyId}`);
        
        return await this.makeRequest(`/api/companies/${companyId}/subscribers/${subscriberId}`, {
            method: 'PUT',
            body: JSON.stringify(subscriberData)
        });
    }
    
    /**
     * Delete subscriber
     */
    async deleteSubscriber(companyId, subscriberId) {
        // Clear cache for this company
        this.clearCache(`subscribers_${companyId}`);
        
        return await this.makeRequest(`/api/companies/${companyId}/subscribers/${subscriberId}`, {
            method: 'DELETE'
        });
    }
    
    /**
     * Update subscriber presence status
     */
    async updatePresence(companyId, subscriberId, isPresent) {
        return await this.makeRequest(`/api/companies/${companyId}/subscribers/${subscriberId}/presence`, {
            method: 'PATCH',
            body: JSON.stringify({ present: isPresent })
        });
    }
    
    /**
     * Send guest notification email
     */
    async sendGuestNotification(email, guestData) {
        return await this.makeRequest('/api/notifications/guest', {
            method: 'POST',
            body: JSON.stringify({
                email: email,
                guest: guestData
            })
        });
    }
    
    /**
     * Export subscribers to Excel
     */
    async exportToExcel(companyId) {
        const result = await this.makeRequest(`/api/companies/${companyId}/export`, {
            method: 'GET'
        });
        
        if (result.success && result.data.url) {
            // Download the file
            window.open(result.data.url, '_blank');
        }
        
        return result;
    }
    
    /**
     * Search subscribers across all companies
     */
    async searchSubscribers(searchTerm) {
        return await this.makeRequest(`/api/search/subscribers?q=${encodeURIComponent(searchTerm)}`);
    }
    
    /**
     * Get parking lot status and information
     */
    async getParkingStatus() {
        return await this.makeRequest('/api/parking/status');
    }
    
    /**
     * Cache management
     */
    getCachedData(key) {
        const cached = this.cache.data.get(key);
        if (cached && Date.now() - cached.timestamp < this.cache.duration) {
            console.log(`Using cached data for: ${key}`);
            return cached.data;
        }
        return null;
    }
    
    setCachedData(key, data) {
        this.cache.data.set(key, {
            data: data,
            timestamp: Date.now()
        });
    }
    
    clearCache(key = null) {
        if (key) {
            this.cache.data.delete(key);
        } else {
            this.cache.data.clear();
        }
    }
    
    /**
     * Batch operations for performance
     */
    async batchUpdate(companyId, updates) {
        return await this.makeRequest(`/api/companies/${companyId}/subscribers/batch`, {
            method: 'PATCH',
            body: JSON.stringify({ updates })
        });
    }
    
    /**
     * Real-time updates via WebSocket (if supported)
     */
    connectWebSocket() {
        try {
            const wsUrl = this.config.baseUrl.replace('https://', 'wss://').replace('http://', 'ws://');
            this.ws = new WebSocket(`${wsUrl}/ws`);
            
            this.ws.onopen = () => {
                console.log('WebSocket connected');
                // Send authentication
                this.ws.send(JSON.stringify({
                    type: 'auth',
                    username: this.config.username,
                    password: this.config.password
                }));
            };
            
            this.ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleRealtimeUpdate(data);
            };
            
            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
            
            this.ws.onclose = () => {
                console.log('WebSocket disconnected');
                // Attempt to reconnect after 5 seconds
                setTimeout(() => this.connectWebSocket(), 5000);
            };
            
        } catch (error) {
            console.error('Failed to connect WebSocket:', error);
        }
    }
    
    handleRealtimeUpdate(data) {
        // Handle real-time updates
        if (data.type === 'subscriber_update') {
            // Clear relevant cache
            this.clearCache(`subscribers_${data.companyId}`);
            
            // Trigger UI update
            if (window.parkingUI) {
                window.parkingUI.handleRealtimeUpdate(data);
            }
        }
    }
    
    /**
     * Test connection to server
     */
    async testConnection() {
        try {
            const result = await this.makeRequest('/api/ping', {
                method: 'GET'
            }, 0); // No retries for ping
            
            return result.success;
        } catch (error) {
            return false;
        }
    }
}

// Create singleton instance
const parkingAPI = new ParkingAPI();

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = parkingAPI;
}
