/**
 * Mobile Parking Controller API
 * ==============================
 * API for controlling parking devices (barriers, gates, etc.)
 * Based on REST Device Control Web Service Interface
 */

class MobileParkingController {
    constructor() {
        this.baseUrl = '/api/mobile-controller';
        this.devices = [];
        this.selectedDevice = null; // Changed to single selection
        this.parkingId = null;
        this.connectionStatus = false;
        this.events = [];
        this.refreshInterval = null;
        
        // Device type mapping
        this.deviceTypes = {
            entry: { range: [101, 199], name: 'כניסה', icon: '➡️', color: '#4CAF50' },
            exit: { range: [201, 299], name: 'יציאה', icon: '⬅️', color: '#f44336' },
            pass: { range: [301, 399], name: 'מעבר', icon: '↔️', color: '#2196F3' }
        };
        
        // Command mapping based on protocol
        this.commands = {
            open: { code: 42250, name: 'HAND_OPEN', display: 'פתח מחסום' },      // A50A
            close: { code: 42251, name: 'HAND_CLOSE', display: 'סגור מחסום' },    // A50B
            lock: { code: 42240, name: 'BLOCK', display: 'נעל מחסום' },          // A500
            unlock: { code: 42241, name: 'UNBLOCK', display: 'בטל נעילה' }      // A501
        };
        
        // Device states mapping
        this.deviceStates = {
            1: { name: 'תקין', class: 'normal' },
            2: { name: 'שינוי ידני', class: 'manual' },
            3: { name: 'נדרשת תחזוקה', class: 'maintenance' },
            4: { name: 'אזהרה', class: 'warning' },
            5: { name: 'לא פעיל חלקית', class: 'partial' },
            6: { name: 'לא פעיל', class: 'inactive' },
            7: { name: 'כניסה כפויה', class: 'forced' },
            8: { name: 'חיבור מנותק', class: 'disconnected' }
        };
    }
    
    /**
     * Initialize the controller
     */
    async init() {
        try {
            // Load user parking info
            const userInfo = await this.getUserInfo();
            if (userInfo && userInfo.project_number) {
                this.parkingId = userInfo.project_number;
            }
            
            // Start monitoring
            this.startConnectionMonitor();
            this.startEventsMonitor();
            
            return true;
        } catch (error) {
            console.error('Failed to initialize controller:', error);
            return false;
        }
    }
    
    /**
     * Get user info including parking details
     */
    async getUserInfo() {
        try {
            const response = await fetch('/api/user-info');
            const data = await response.json();
            
            if (data.success) {
                return data.user;
            }
            throw new Error(data.message || 'Failed to get user info');
        } catch (error) {
            console.error('Error getting user info:', error);
            throw error;
        }
    }
    
    /**
     * Get device type based on device number
     */
    getDeviceType(deviceNumber) {
        for (const [type, config] of Object.entries(this.deviceTypes)) {
            if (deviceNumber >= config.range[0] && deviceNumber <= config.range[1]) {
                return type;
            }
        }
        return 'unknown';
    }
    
    /**
     * Load devices from server
     */
    async loadDevices() {
        try {
            const response = await fetch(`${this.baseUrl}/devices`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({ parking_id: this.parkingId })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.devices = data.devices || [];
                this.updateConnectionStatus(true);
                return this.devices;
            } else {
                throw new Error(data.message || 'Failed to load devices');
            }
        } catch (error) {
            console.error('Error loading devices:', error);
            this.updateConnectionStatus(false);
            throw error;
        }
    }
    
    /**
     * Execute command on selected device
     */
    async executeCommand(commandType, deviceNumber = null) {
        const device = deviceNumber || this.selectedDevice;
        
        console.log(`🔧 MobileParkingController.executeCommand called with: commandType=${commandType}, deviceNumber=${deviceNumber}, selectedDevice=${this.selectedDevice}`);
        
        if (!device) {
            throw new Error('לא נבחר מכשיר');
        }
        
        const command = this.commands[commandType];
        console.log(`📋 Command mapping for ${commandType}:`, command);
        
        if (!command) {
            throw new Error('פקודה לא תקינה');
        }
        
        try {
            const requestData = {
                parking_id: this.parkingId,
                devices: [device], // Send as array for backward compatibility
                command: command.code,
                command_name: command.name
            };
            
            console.log(`📤 Sending command request:`, requestData);
            
            const response = await fetch(`${this.baseUrl}/command`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify(requestData)
            });
            
            const data = await response.json();
            
            if (data.success) {
                // Update local device status based on command
                const deviceIndex = this.devices.findIndex(d => d.number === device);
                if (deviceIndex !== -1) {
                    switch(commandType) {
                        case 'open':
                            this.devices[deviceIndex].barrier = 'open';
                            this.devices[deviceIndex].doorOpen = true;
                            console.log(`✅ Updated device ${device} status to OPEN`);
                            break;
                        case 'close':
                            this.devices[deviceIndex].barrier = 'closed';
                            this.devices[deviceIndex].doorOpen = false;
                            console.log(`✅ Updated device ${device} status to CLOSED`);
                            break;
                        case 'lock':
                            this.devices[deviceIndex].barrier = 'locked';
                            this.devices[deviceIndex].doorOpen = false;
                            console.log(`✅ Updated device ${device} status to LOCKED`);
                            break;
                        case 'unlock':
                            // Unlock doesn't change barrier state, just removes lock
                            console.log(`✅ Device ${device} UNLOCKED`);
                            break;
                    }
                }
                
                // Also refresh devices to get server status
                setTimeout(() => this.loadDevices(), 1000);
                
                return data;
            } else {
                throw new Error(data.message || 'Command execution failed');
            }
        } catch (error) {
            console.error('Error executing command:', error);
            throw error;
        }
    }
    
    /**
     * Get device status
     */
    async getDeviceStatus(deviceNumber) {
        try {
            const response = await fetch(`${this.baseUrl}/device-status`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({
                    parking_id: this.parkingId,
                    device: deviceNumber
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                return data.status;
            } else {
                throw new Error(data.message || 'Failed to get device status');
            }
        } catch (error) {
            console.error('Error getting device status:', error);
            throw error;
        }
    }
    
    /**
     * Load events
     */
    async loadEvents(limit = 100) {
        try {
            const response = await fetch(`${this.baseUrl}/events`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({
                    parking_id: this.parkingId,
                    limit: limit
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.events = data.events || [];
                return this.events;
            } else {
                throw new Error(data.message || 'Failed to load events');
            }
        } catch (error) {
            console.error('Error loading events:', error);
            throw error;
        }
    }
    
    /**
     * Send price to exit device
     */
    async sendPrice(deviceNumber, amount) {
        try {
            const response = await fetch(`${this.baseUrl}/send-price`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({
                    parking_id: this.parkingId,
                    device: deviceNumber,
                    amount: amount
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                return data;
            } else {
                throw new Error(data.message || 'Failed to send price');
            }
        } catch (error) {
            console.error('Error sending price:', error);
            throw error;
        }
    }
    
    /**
     * Calculate lost ticket fee
     */
    async calculateLostTicket(deviceNumber) {
        try {
            const response = await fetch(`${this.baseUrl}/lost-ticket`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({
                    parking_id: this.parkingId,
                    device: deviceNumber
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                return data;
            } else {
                throw new Error(data.message || 'Failed to calculate lost ticket');
            }
        } catch (error) {
            console.error('Error calculating lost ticket:', error);
            throw error;
        }
    }
    
    /**
     * Get system status
     */
    async getSystemStatus() {
        try {
            const response = await fetch(`${this.baseUrl}/system-status`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({
                    parking_id: this.parkingId
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                return data.status;
            } else {
                throw new Error(data.message || 'Failed to get system status');
            }
        } catch (error) {
            console.error('Error getting system status:', error);
            throw error;
        }
    }
    
    /**
     * Select a single device (radio button behavior)
     */
    selectDevice(deviceNumber) {
        // If same device clicked, deselect it
        if (this.selectedDevice === deviceNumber) {
            this.selectedDevice = null;
        } else {
            this.selectedDevice = deviceNumber;
        }
        
        return this.selectedDevice;
    }
    
    /**
     * Clear device selection
     */
    clearSelection() {
        this.selectedDevice = null;
        return this.selectedDevice;
    }
    
    /**
     * Get selected device info
     */
    getSelectedDevice() {
        if (!this.selectedDevice) return null;
        return this.devices.find(d => d.number === this.selectedDevice);
    }
    
    /**
     * Check if device is selected
     */
    isDeviceSelected(deviceNumber) {
        return this.selectedDevice === deviceNumber;
    }
    
    /**
     * Update connection status
     */
    updateConnectionStatus(connected) {
        this.connectionStatus = connected;
        
        // Trigger custom event
        const event = new CustomEvent('connectionStatusChanged', {
            detail: { connected: connected }
        });
        window.dispatchEvent(event);
    }
    
    /**
     * Start connection monitor
     */
    startConnectionMonitor() {
        // Check connection every 10 seconds
        this.connectionInterval = setInterval(async () => {
            try {
                await this.loadDevices();
            } catch (error) {
                this.updateConnectionStatus(false);
            }
        }, 10000);
    }
    
    /**
     * Start events monitor
     */
    startEventsMonitor() {
        // Load new events every 5 seconds
        this.eventsInterval = setInterval(async () => {
            try {
                await this.loadEvents();
            } catch (error) {
                console.error('Failed to load events:', error);
            }
        }, 5000);
    }
    
    /**
     * Stop all monitors
     */
    stopMonitors() {
        if (this.connectionInterval) {
            clearInterval(this.connectionInterval);
            this.connectionInterval = null;
        }
        
        if (this.eventsInterval) {
            clearInterval(this.eventsInterval);
            this.eventsInterval = null;
        }
    }
    
    /**
     * Destroy controller instance
     */
    destroy() {
        this.stopMonitors();
        this.devices = [];
        this.selectedDevice = null;
        this.events = [];
    }
}

// Export for use in other modules
window.MobileParkingController = MobileParkingController;
