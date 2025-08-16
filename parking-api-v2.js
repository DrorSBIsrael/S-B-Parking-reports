/**
 * Parking API v2 - Simplified version for Flask proxy
 */

class ParkingAPIXML {
    constructor() {
        this.config = {
            baseUrl: '/api/company-manager/proxy',
            username: '2022',
            password: '2022',
            timeout: 30000,
            useProxy: true,
            currentParkingId: null
        };
        
        console.log('Parking API v2 initialized:', {
            baseUrl: this.config.baseUrl,
            useProxy: true
        });
    }
    
    setConfig(config) {
        this.config = { 
            ...this.config, 
            ...config,
            baseUrl: '/api/company-manager/proxy',
            useProxy: true
        };
    }
    
    setCurrentParking(parkingId) {
        this.config.currentParkingId = parkingId;
        console.log('Current parking set to:', parkingId);
    }
    
    async makeRequest(endpoint, method = 'GET', data = null) {
        try {
            const response = await fetch(this.config.baseUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    parking_id: this.config.currentParkingId,
                    endpoint: endpoint,
                    method: method,
                    payload: data
                })
            });
            
            const result = await response.json();
            
            if (result.success && result.data) {
                return { success: true, data: result.data };
            } else {
                return { success: false, error: result.message || 'Unknown error' };
            }
        } catch (error) {
            console.error('API Error:', error);
            return { success: false, error: error.message };
        }
    }
}

// Create instance
const parkingAPIXML = new ParkingAPIXML();

// Make available globally
if (typeof window !== 'undefined') {
    window.parkingAPIXML = parkingAPIXML;
    window.parkingAPI = parkingAPIXML; // For compatibility
}
