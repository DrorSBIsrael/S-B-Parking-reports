
/**
 * Configuration file for Parking Management System
 */

const config = {
    // Development mode settings
    development: {
        useProxy: true, // Use proxy through Flask server
        proxyUrl: '/api/company-manager/proxy', // Use Flask proxy endpoint
        apiUrl: '', // Will be set dynamically per parking
        username: '2022',
        password: '2022',
        mockData: false, // Use real server
        cacheEnabled: true,
        cacheDuration: 60000 // 1 minute
    },
    
    // Production settings
    production: {
        useProxy: true, // Always use Flask proxy to avoid CORS
        proxyUrl: '/api/company-manager/proxy', // Use Flask proxy endpoint
        apiUrl: '', // Will be set dynamically per parking
        username: '', // Will be set from login
        password: '', // Will be set from login
        mockData: false,
        cacheEnabled: true,
        cacheDuration: 300000 // 5 minutes
    },
    
    // Current parking configuration (will be set dynamically)
    currentParking: {
        id: null,
        name: null,
        ip_address: null,
        port: null,
        api_url: null
    },
    
    // Current environment
    environment: 'development',
    
    // Get current configuration
    get current() {
        return this[this.environment];
    },
    
    // Company lists that user can access - Updated for new server
    allowedCompanies: [], // Empty array = show all companies the user has access to
    
    // UI Settings
    ui: {
        language: 'he', // Default language: 'he' or 'en'
        itemsPerPage: 50,
        autoRefreshInterval: 60000, // Auto refresh every minute
        enableRealtime: true, // Enable WebSocket for real-time updates
        showNotifications: true,
        maxCompaniesToShow: 10, // Maximum companies to display initially
        autoSelectSingleCompany: true // Auto-select if only one company
    },
    
    // Performance settings
    performance: {
        batchSize: 10, // How many details to fetch at once
        maxDetailsLoad: 100, // Maximum subscribers to load with full details
        largeCompanyThreshold: 300, // Companies with more than this are "large" (updated to 300)
        delayBetweenBatches: 200, // Milliseconds between batches
        hoverLoadDelay: 500, // Delay before loading on hover (milliseconds)
        enableHoverLoading: true // Enable/disable hover loading feature
    },
    
    // Features flags
    features: {
        guestSubscribers: true,
        exportToExcel: true,
        bulkOperations: false, // Coming soon
        advancedSearch: true,
        accessibilityMode: true
    },
    
    // Validation rules
    validation: {
        vehiclePlatePattern: /^\d{2,3}-\d{2,3}-\d{2,3}$/,
        phonePattern: /^0\d{1,2}-?\d{7}$/,
        emailPattern: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
        maxVehiclesPerSubscriber: 3,
        defaultValidityDays: 365
    }
};

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = config;
}

// Make available globally in browser
if (typeof window !== 'undefined') {
    window.parkingConfig = config;
}
