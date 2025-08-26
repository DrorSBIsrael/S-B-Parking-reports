/**
 * Parking API v2 - Complete version with all methods
 */

class ParkingAPIXML {
    constructor() {
        // ALWAYS use proxy for consistency and security
        this.config = {
            baseUrl: '/api/company-manager/proxy',
            username: '2022',
            password: '2022',
            timeout: 30000,
            useProxy: true,  // Always use proxy
            currentParkingId: null
        };
        console.log('☁️ Using secure proxy connection');
        console.log('Parking API v2 initialized');
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
                // PRODUCTION: Use proxy to avoid CORS
                console.log(`📡 Proxy request - endpoint: ${endpoint}`);
                
                // Make sure endpoint includes CustomerMediaWebService prefix
                // Remove leading slash if exists
                if (endpoint.startsWith('/')) {
                    endpoint = endpoint.substring(1);
                }
                
                if (!endpoint.startsWith('CustomerMediaWebService')) {
                    endpoint = `CustomerMediaWebService/${endpoint}`;
                }
                
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
                // LOCAL: Direct connection
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
        console.log(`[getEnhancedContractDetails] Fetching details for contract ${contractId}`);
        const result = await this.makeRequest(`contracts/${contractId}/detail`);
        
        // Log the response structure for debugging
        if (result.success) {
            console.log(`[getEnhancedContractDetails] Response structure:`, result.data);
            
            // Check if we got a message or XML preview
            if (result.data && result.data.message) {
                console.log(`\n${'='.repeat(60)}`);
                console.log(`📋 CONTRACT ${contractId} - MESSAGE: ${result.data.message}`);
                console.log(`📋 ENDPOINT WAS: ${result.data.endpoint}`);
                console.log(`${'='.repeat(60)}\n`);
            }
            
            if (result.data && result.data.xml_preview) {
                console.log(`\n${'='.repeat(60)}`);
                console.log(`📋 CONTRACT ${contractId} - GOT XML PREVIEW!`);
                console.log(`${'='.repeat(60)}`);
                console.log(result.data.xml_preview);
                console.log(`${'='.repeat(60)}\n`);
            }
            
            // Show debug info if available
            if (result.debug) {
                console.log(`\n${'='.repeat(60)}`);
                console.log(`📋 CONTRACT ${contractId} - RAW XML FROM SERVER:`);
                console.log(`${'='.repeat(60)}`);
                console.log(result.debug.raw_xml);
                console.log(`${'='.repeat(60)}`);
                console.log(`   - Has pooling: ${result.debug.has_pooling}`);
                console.log(`   - Parsed keys: ${result.debug.parsed_keys}`);
                console.log(`${'='.repeat(60)}\n`);
            }
            
            if (result.data && result.data.pooling) {
                console.log(`[getEnhancedContractDetails] ✅ Pooling data found:`, result.data.pooling);
            }
        }
        
        return result;
    }
    
    async getConsumers(companyNum, contractId) {
        console.log(`[getConsumers] Fetching consumers for contract ${contractId}`);
        
        // Always pass contractId in payload for proper filtering
        const result = await this.makeRequest('consumers', 'GET', { contractId: contractId });
        
        // Check if we got the consumers
        if (result.success && result.data) {
            // Handle both array and single object responses
            let consumers = Array.isArray(result.data) ? result.data : [result.data];
            console.log(`[getConsumers] Got ${consumers.length} consumers from server`);
            
            // If we got too many consumers, it might mean the server doesn't support filtering
            // In that case, we'll need to filter client-side
            if (consumers.length > 1000) {
                console.log(`[getConsumers] Got ${consumers.length} consumers - filtering client-side for contract ${contractId}`);
                const filtered = consumers.filter(c => {
                    // IMPORTANT: Server returns 'contractid' in lowercase!
                    return c.contractid === contractId ||  // lowercase version - THIS IS KEY!
                           c.contractid === String(contractId) ||
                           c.contractId === contractId || 
                           c.contractId === String(contractId) ||
                           c.contract === contractId ||
                           c.contract === String(contractId) ||
                           c.contractNum === contractId ||
                           c.contractNum === String(contractId) ||
                           c.companyId === contractId ||
                           c.companyId === String(contractId);
                });
                
                if (filtered.length > 0) {
                    console.log(`[getConsumers] Filtered to ${filtered.length} consumers for contract ${contractId}`);
                    return { success: true, data: filtered };
                } else {
                    console.log(`[getConsumers] Warning: No consumers found for contract ${contractId} after filtering`);
                    // Log first consumer to see structure for debugging
                    if (consumers.length > 0) {
                        console.log(`[getConsumers] First consumer structure:`, consumers[0]);
                        console.log(`[getConsumers] Looking for contractId: ${contractId}`);
                    }
                    // Return empty array if no consumers found
                    return { success: true, data: [] };
                }
            }
        }
        
        return result;
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
    
    async getOccupancy(contractId) {
        // Try to get occupancy data for a contract
        return this.makeRequest(`occupancy?contractId=${contractId}`);
    }
    
    async getFacilityStatus(contractId) {
        // Alternative endpoint for facility/parking status
        return this.makeRequest(`facilities/status?contractId=${contractId}`);
    }
    
    /**
     * Get detailed information for a single consumer
     */
    async getConsumerDetail(contractId, consumerId) {
        const parkingId = this.config.currentParkingId;
        
        console.log(`[getConsumerDetail] Fetching detail for consumer ${consumerId} in contract ${contractId}`);
        console.log(`[getConsumerDetail] Using parking ID: ${parkingId}`);
        
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
        
        console.log(`[getConsumerDetail] Response status: ${response.status}`);
        const result = await response.json();
        console.log(`[getConsumerDetail] Result:`, result);
        return result;
    }
    
    /**
     * Get detailed information on-demand (for hover loading)
     * Used when hovering over subscribers in large companies
     */
    async getConsumerDetailOnDemand(contractId, consumerId) {
        console.log(`[getConsumerDetailOnDemand] Loading details for consumer ${consumerId} in contract ${contractId}`);
        // Call the regular getConsumerDetail method
        return this.getConsumerDetail(contractId, consumerId);
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
            
            let consumers = result.data || [];
            const consumersArray = Array.isArray(consumers) ? consumers : [consumers];
            
            // Filter by contractId if API returns all consumers
            if (consumersArray.length > 1000) {
                console.log(`[Progressive] Got ${consumersArray.length} consumers - filtering by contractId ${companyId}`);
                const filtered = consumersArray.filter(c => 
                    c.contractId === companyId || 
                    c.contractId === String(companyId) ||
                    c.contract === companyId ||
                    c.contract === String(companyId) ||
                    c.contractNum === companyId ||
                    c.contractNum === String(companyId) ||
                    c.companyId === companyId ||
                    c.companyId === String(companyId)
                );
                if (filtered.length > 0) {
                    consumers = filtered;
                    console.log(`[Progressive] Filtered to ${filtered.length} consumers for contract ${companyId}`);
                } else {
                    console.log(`[Progressive] No consumers found for contract ${companyId} after filtering`);
                    // Log first consumer to see structure
                    if (consumersArray.length > 0) {
                        console.log(`[Progressive] First consumer structure:`, consumersArray[0]);
                        console.log(`[Progressive] Looking for contractId: ${companyId}`);
                    }
                    // TEMPORARY: Return first 100 consumers for testing
                    console.log(`[Progressive] TEMPORARY: Returning first 100 consumers for testing`);
                    consumers = consumersArray.slice(0, 100);
                }
            }
            
            const finalConsumers = Array.isArray(consumers) ? consumers : [consumers];
            console.log(`[Progressive] Found ${finalConsumers.length} consumers`);
            
            // PERFORMANCE OPTIMIZATION: Check company size
            const LARGE_COMPANY_THRESHOLD = 300;
            const isLargeCompany = finalConsumers.length > LARGE_COMPANY_THRESHOLD;
            
            if (isLargeCompany) {
                console.log(`[Progressive] LARGE COMPANY: ${finalConsumers.length} subscribers > ${LARGE_COMPANY_THRESHOLD}`);
                console.log(`[Progressive] Will load details on-demand only (hover)`);
            } else {
                console.log(`[Progressive] Small company - will load details in background`);
            }
            
            // Map basic data
            const basicSubscribers = finalConsumers.map(consumer => ({
                id: consumer.id || consumer.subscriberNum,
                subscriberNum: consumer.id || consumer.subscriberNum,
                lastName: consumer.name || consumer.lastName || '',
                vehicleNum: consumer.vehicleNum || '',
                hasFullDetails: false,
                isLargeCompany: isLargeCompany,
                contractId: companyId,
                companyNum: companyId  // Add company number for display
            }));
            
            // Return basic data immediately
            onBasicLoaded(basicSubscribers);
            
            // Skip loading details - basic data is sufficient
            // Details can be loaded on-demand if needed
            if (isLargeCompany) {
                // Notify that we're in on-demand mode
                if (onProgress) {
                    onProgress({ 
                        loaded: finalConsumers.length, 
                        total: finalConsumers.length,
                        message: `חברה גדולה (${finalConsumers.length} מנויים) - פרטים יטענו בעת מעבר עכבר`
                    });
                }
            }
            
                        return { 
                success: true,
                data: basicSubscribers,
                total: finalConsumers.length,
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
                    console.log(`[Background] Loading details for consumer ${consumerId} in contract ${contractId}`);
                    const detailResult = await this.getConsumerDetail(contractId, consumerId);
                    
                    if (detailResult.success) {
                        console.log(`[Background] Got details for consumer ${consumerId}:`, detailResult.data);
                        // Find and update subscriber
                        const subscriber = subscribers.find(s => s.id === consumerId);
                        if (subscriber) {
                            Object.assign(subscriber, detailResult.data);
                            subscriber.hasFullDetails = true;
                            onDetailLoaded(subscriber);
                            console.log(`[Background] Updated subscriber ${consumerId} with full details`);
                        } else {
                            console.warn(`[Background] Could not find subscriber ${consumerId} to update`);
                        }
                    } else {
                        console.warn(`[Background] Failed to get details for consumer ${consumerId}:`, detailResult);
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
