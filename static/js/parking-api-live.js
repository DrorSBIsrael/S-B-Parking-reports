/**
 * Parking API v2 - Complete version with all methods
 */

class ParkingAPIXML {
    constructor() {
        // Check if we're running locally or on production
        const isLocal = window.location.hostname === 'localhost' || 
                       window.location.hostname === '127.0.0.1';
        
        // CRITICAL FIX: Different endpoints for local vs production
        if (isLocal) {
            // LOCAL: Direct connection to parking server
            this.config = {
                baseUrl: 'https://10.35.240.100:8443/CustomerMediaWebService',
                username: '2022',
                password: '2022',
                timeout: 30000,
                useProxy: false,  // NO PROXY LOCALLY!
                currentParkingId: null
            };
            console.log('🏠 LOCAL MODE: Direct connection to parking server');
        } else {
            // PRODUCTION: Use proxy (Render can access external IP)
            this.config = {
                baseUrl: '/api/company-manager/proxy',
                username: '2022',
                password: '2022',
                timeout: 30000,
                useProxy: true,  // USE PROXY ON RENDER!
                currentParkingId: null
            };
            console.log('☁️ PRODUCTION MODE: Using proxy');
        }
        
        console.log('Parking API v2 initialized:', {
            baseUrl: this.config.baseUrl,
            useProxy: this.config.useProxy,
            mode: isLocal ? 'LOCAL' : 'PRODUCTION'
        });
    }
    
    setConfig(config) {
        // Don't override baseUrl and useProxy - they're set based on environment
        const { baseUrl, useProxy, ...otherConfig } = config;
        this.config = { 
            ...this.config, 
            ...otherConfig
        };
    }
    
    setCurrentParking(parkingId) {
        this.config.currentParkingId = parkingId;
        console.log('Current parking set to:', parkingId);
    }
    
    parseXML(xmlString) {
        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(xmlString, "text/xml");
        
        const parseError = xmlDoc.querySelector('parsererror');
        if (parseError) {
            throw new Error('XML Parse Error: ' + parseError.textContent);
        }
        
        return this.xmlToJson(xmlDoc.documentElement);
    }
    
    xmlToJson(xml) {
        let obj = {};
        
        if (xml.nodeType === 1) {
            if (xml.attributes.length > 0) {
                obj["@attributes"] = {};
                for (let j = 0; j < xml.attributes.length; j++) {
                    const attribute = xml.attributes.item(j);
                    obj["@attributes"][attribute.nodeName] = attribute.nodeValue;
                }
            }
        } else if (xml.nodeType === 3) {
            obj = xml.nodeValue;
        }
        
        if (xml.hasChildNodes()) {
            for (let i = 0; i < xml.childNodes.length; i++) {
                const item = xml.childNodes.item(i);
                const nodeName = item.nodeName;
                
                if (typeof obj[nodeName] === "undefined") {
                    obj[nodeName] = this.xmlToJson(item);
                } else {
                    if (typeof obj[nodeName].push === "undefined") {
                        const old = obj[nodeName];
                        obj[nodeName] = [];
                        obj[nodeName].push(old);
                    }
                    obj[nodeName].push(this.xmlToJson(item));
                }
            }
        }
        
        return obj;
    }
    
    async makeRequest(endpoint, method = 'GET', data = null) {
        try {
            let response;
            
            if (this.config.useProxy) {
                // PRODUCTION: Use proxy endpoint
                response = await fetch(this.config.baseUrl, {
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
            } else {
                // LOCAL: Direct connection to parking server
                const url = `${this.config.baseUrl}/${endpoint}`;
                const headers = {
                    'Authorization': 'Basic ' + btoa(`${this.config.username}:${this.config.password}`),
                    'Accept': 'application/xml',
                    'Content-Type': 'application/json'
                };
                
                console.log(`🔗 Direct request to: ${url}`);
                
                response = await fetch(url, {
                    method: method,
                    headers: headers,
                    body: data ? JSON.stringify(data) : null
                });
            }
            
            const contentType = response.headers.get('content-type');
            let result;
            
            if (contentType && contentType.includes('application/xml')) {
                const xmlText = await response.text();
                const jsonData = this.parseXML(xmlText);
                result = { success: true, data: jsonData };
            } else if (contentType && contentType.includes('application/json')) {
                result = await response.json();
                } else {
                const text = await response.text();
                if (text.startsWith('<?xml') || text.startsWith('<')) {
                    const jsonData = this.parseXML(text);
                    result = { success: true, data: jsonData };
                } else {
                    result = { success: false, error: 'Unknown response format' };
                }
            }
            
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
    
    // API Methods
    async getContracts() {
        return this.makeRequest('contracts');
    }
    
    async getContractDetails(contractId) {
        return this.makeRequest(`contracts/${contractId}`);
    }
    
    async getEnhancedContractDetails(contractId) {
        return this.makeRequest(`contracts/${contractId}/detail`);
    }
    
    async getConsumers(companyNum, contractId) {
        return this.makeRequest(`contracts/${contractId}/consumers`);
    }
    
    async addConsumer(contractId, consumerData) {
        return this.makeRequest(`contracts/${contractId}/consumers`, 'POST', consumerData);
    }
    
    async updateConsumer(contractId, consumerId, consumerData) {
        return this.makeRequest(`consumers/${contractId},${consumerId}`, 'PUT', consumerData);
    }
    
    async deleteConsumer(contractId, consumerId) {
        return this.makeRequest(`consumers/${contractId},${consumerId}`, 'DELETE');
    }
    
    async getUsageProfiles() {
        return this.makeRequest('usageprofiles');
    }
    
    /**
     * Get detailed information for a single consumer
     */
    async getConsumerDetail(contractId, consumerId) {
        const parkingId = this.getCurrentParkingId();
        
        const response = await fetch('/api/company-manager/consumer-detail', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                parking_id: parkingId,
                contract_id: contractId,
                consumer_id: consumerId
            })
        });
        
        const result = await response.json();
        return result;
    }
    
    // Progressive loading methods for large datasets with optimization
    async getSubscribersProgressive(companyId, callbacks = {}) {
        const { 
            onBasicLoaded = () => {}, 
            onDetailLoaded = () => {}, 
            onProgress = () => {} 
        } = callbacks;
        
        try {
            console.log('[Progressive] Starting progressive loading for company:', companyId);
            
            // Step 1: Get basic list
            const result = await this.getConsumers(companyId, companyId);
            
            if (!result.success) {
                console.error('[Progressive] Failed to get consumers list');
                return result;
            }
            
            const consumers = result.data || [];
            const consumersArray = Array.isArray(consumers) ? consumers : [consumers];
            
            console.log(`[Progressive] Found ${consumersArray.length} consumers`);
            
            // PERFORMANCE OPTIMIZATION: Check company size
            const LARGE_COMPANY_THRESHOLD = 300;
            const isLargeCompany = consumersArray.length > LARGE_COMPANY_THRESHOLD;
            
            if (isLargeCompany) {
                console.log(`[Progressive] LARGE COMPANY: ${consumersArray.length} subscribers > ${LARGE_COMPANY_THRESHOLD}`);
                console.log(`[Progressive] Will load details on-demand only (hover)`);
            } else {
                console.log(`[Progressive] Small company - will load details in background`);
            }
            
            // Map basic data
            const basicSubscribers = consumersArray.map(consumer => ({
                id: consumer.id || consumer.subscriberNum,
                subscriberNum: consumer.id || consumer.subscriberNum,
                lastName: consumer.name || consumer.lastName || '',
                vehicleNum: consumer.vehicleNum || '',
                hasFullDetails: false,
                isLargeCompany: isLargeCompany,
                contractId: companyId
            }));
            
            // Return basic data immediately
            onBasicLoaded(basicSubscribers);
            
            // Step 2: Load details in background ONLY for small companies
            if (!isLargeCompany && consumersArray.length > 0) {
                this.loadDetailsInBackground(companyId, consumersArray, basicSubscribers, {
                    onDetailLoaded,
                    onProgress
                });
            } else if (isLargeCompany) {
                // Notify that we're in on-demand mode
                if (onProgress) {
                    onProgress({ 
                        loaded: consumersArray.length, 
                        total: consumersArray.length,
                        message: `חברה גדולה (${consumersArray.length} מנויים) - פרטים יטענו בעת מעבר עכבר`
                    });
                }
            }
            
            return { 
                success: true,
                data: basicSubscribers,
                total: consumersArray.length,
                progressive: true,
                isLargeCompany: isLargeCompany
            };
            
        } catch (error) {
            console.error('[Progressive] Error:', error);
            return { success: false, error: error.message };
        }
    }
    
    /**
     * Load details in background for small companies
     */
    async loadDetailsInBackground(contractId, consumers, subscribers, options) {
        const { onDetailLoaded, onProgress } = options;
        const batchSize = 10; // Load 10 at a time
        const totalBatches = Math.ceil(consumers.length / batchSize);
        
        console.log(`[Background] Loading ${consumers.length} details in ${totalBatches} batches`);
        
        for (let batchIndex = 0; batchIndex < totalBatches; batchIndex++) {
            const start = batchIndex * batchSize;
            const end = Math.min(start + batchSize, consumers.length);
            const batch = consumers.slice(start, end);
            
            // Process batch
            const batchPromises = batch.map(async (consumer) => {
                try {
                    const consumerId = consumer.id || consumer.subscriberNum;
                    const detailResult = await this.getConsumerDetail(contractId, consumerId);
                    
                    if (detailResult.success) {
                        // Find and update subscriber
                        const subscriber = subscribers.find(s => s.id === consumerId);
                        if (subscriber) {
                            Object.assign(subscriber, detailResult.data);
                            subscriber.hasFullDetails = true;
                            onDetailLoaded(subscriber);
                        }
                    }
                } catch (error) {
                    console.error(`[Background] Error loading details for ${consumer.id}:`, error);
                }
            });
            
            await Promise.all(batchPromises);
            
            // Update progress
            const loaded = Math.min((batchIndex + 1) * batchSize, consumers.length);
            if (onProgress) {
                onProgress({ 
                    loaded, 
                    total: consumers.length,
                    percentage: Math.round((loaded / consumers.length) * 100)
                });
            }
            
            // Small delay between batches
            if (batchIndex < totalBatches - 1) {
                await new Promise(resolve => setTimeout(resolve, 100));
            }
        }
        
        console.log('[Background] Finished loading all details');
    }
    
    // Additional helper methods
    async saveSubscriber(companyId, subscriberData) {
        return this.addConsumer(companyId, subscriberData);
    }
    
    async loadUsageProfiles() {
        return this.getUsageProfiles();
    }
    
    async refreshSingleSubscriber(companyId, subscriberId) {
        return this.makeRequest(`consumers/${companyId},${subscriberId}`);
    }
    
    async exportToCSV(companyId) {
        // This would typically return a CSV download URL
        return { success: false, error: 'Export not implemented for XML API' };
    }
    
    async viewTransactions(companyId, subscriberId) {
        return this.makeRequest(`contracts/${companyId}/consumers/${subscriberId}/transactions`);
    }
}

// Create instance
const parkingAPIXML = new ParkingAPIXML();

// Make available globally
if (typeof window !== 'undefined') {
    window.parkingAPIXML = parkingAPIXML;
    window.parkingAPI = parkingAPIXML;
}