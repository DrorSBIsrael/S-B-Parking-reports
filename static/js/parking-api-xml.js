/**
 * Parking Management System API Client - XML Version
 * Based on Customer Media Web Service Interface
 * Protocol: REST API with XML
 */

class ParkingAPIXML {
    constructor() {
        // ALWAYS use Flask proxy - ignore any other configuration
        this.config = {
            baseUrl: '/api/company-manager/proxy', // Always use Flask proxy endpoint
            servicePath: '', // Path will be handled by Flask
            username: '2022',
            password: '2022',
            timeout: 30000,
            useProxy: true,
            currentParkingId: null // Will be set when selecting a parking
        };
        
        this.xmlNamespace = 'http://gsph.sub.com/cust/types';
        
        console.log('Parking API XML Configuration:', {
            baseUrl: this.config.baseUrl,
            useProxy: this.config.useProxy,
            username: this.config.username,
            note: 'Using Flask proxy for all requests'
        });
    }
    
    /**
     * Set API configuration
     */
    setConfig(config) {
        // Keep the Flask proxy URL no matter what
        this.config = { 
            ...this.config, 
            ...config,
            baseUrl: '/api/company-manager/proxy', // Always override to use Flask proxy
            useProxy: true // Always use proxy
        };
    }
    
    /**
     * Set current parking ID for API calls
     */
    setCurrentParking(parkingId) {
        this.config.currentParkingId = parkingId;
        console.log('Current parking set to:', parkingId);
    }
    
    /**
     * Get full URL for endpoint
     * Note: When using Flask proxy, this just returns the proxy URL
     */
    getUrl(endpoint) {
        // When using proxy, we send the endpoint as part of the request body
        return this.config.baseUrl;
    }
}

// Create singleton instance
const parkingAPIXML = new ParkingAPIXML();

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = parkingAPIXML;
}

// Make available globally in browser
if (typeof window !== 'undefined') {
    window.parkingAPIXML = parkingAPIXML;
}