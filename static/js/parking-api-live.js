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
                return { success: true, data: result.data, message: result.message };
            } else {
                return { success: false, error: result.message || result.error || 'Unknown error' };
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
        
        // Send contractId in payload - Flask will build the correct URL
        const result = await this.makeRequest('consumers', 'GET', { 
            contractId: contractId  // Pass contractId in payload for Flask to use
        });
        
        // Check if we got the consumers
        if (result.success && result.data) {
            // Handle both array and single object responses
            let consumers = Array.isArray(result.data) ? result.data : [result.data];
            // Minimal debug - just count
            console.log(`[getConsumers] Got ${consumers.length} consumers from server`);
            
            // SAFETY CHECK: If we got too many consumers, something is wrong!
            if (consumers.length > 500) {
                console.error(`[getConsumers] ERROR: Got ${consumers.length} consumers! Server might be returning ALL consumers instead of just contract ${contractId}`);
                console.warn('[getConsumers] This will cause performance issues. Check Flask proxy endpoint!');
            } else {
                console.log(`[getConsumers] ✅ Got ${consumers.length} consumers for contract ${contractId}`);
            }
            
            return { success: true, data: consumers };
        }
        
        return result;
    }
    
    async addConsumer(contractId, consumerData) {
        return this.makeRequest(`contracts/${contractId}/consumers`, 'POST', consumerData);
    }
    
    async updateConsumer(contractId, consumerId, consumerData) {
        // Use the /detail endpoint for updating consumer as per API spec
        return this.makeRequest(`consumers/${contractId},${consumerId}/detail`, 'PUT', consumerData);
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
        // Silently fetch detail - no debug logs for performance
        const endpoint = `consumers/${contractId},${consumerId}/detail`;
        
        try {
            const result = await this.makeRequest(endpoint, 'GET');
            
            if (result.success && result.data) {
        return result;
            }
            
            return { success: false, error: 'Failed to get consumer detail' };
        } catch (error) {
            return { success: false, error: error.message };
        }
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
                    // No limit - return all consumers
                    consumers = consumersArray;
                }
            }
            
            const finalConsumers = Array.isArray(consumers) ? consumers : [consumers];
            // PERFORMANCE OPTIMIZATION: Smart loading based on company size
            const INSTANT_LOAD_THRESHOLD = 30;    // Load all at once (1 batch)
            const BATCH_LOAD_THRESHOLD = 300;     // Load in batches of 50
            const ON_DEMAND_THRESHOLD = 300;      // Load on hover only (>300)
            
            const subscriberCount = finalConsumers.length;
            let loadingStrategy = 'instant';
            
            if (subscriberCount <= INSTANT_LOAD_THRESHOLD) {
                loadingStrategy = 'instant';
            } else if (subscriberCount <= BATCH_LOAD_THRESHOLD) {
                loadingStrategy = 'batch-50';
            } else {
                loadingStrategy = 'on-demand';
            }
            
            // Map ALL available data from consumer list
            let basicSubscribers = finalConsumers.map(consumer => ({
                // IDs
                id: consumer.id || consumer.subscriberNum,
                subscriberNum: consumer.id || consumer.subscriberNum,
                contractId: companyId,
                companyNum: companyId,
                companyName: callbacks.companyName || `חברה ${companyId}`,  // Will be passed from UI
                
                // Names - don't duplicate if only last name exists
                firstName: consumer.firstName || '',
                lastName: consumer.lastName || consumer.name || '',
                name: consumer.name || '',
                
                // Vehicles
                vehicleNum: consumer.vehicleNum || consumer.lpn1 || '',
                lpn1: consumer.lpn1 || consumer.vehicleNum || '',
                lpn2: consumer.lpn2 || '',
                lpn3: consumer.lpn3 || '',
                vehicle1: consumer.lpn1 || consumer.vehicleNum || '',
                vehicle2: consumer.lpn2 || '',
                vehicle3: consumer.lpn3 || '',
                
                // Dates
                validFrom: consumer.xValidFrom || consumer.validFrom || '2024-01-01',
                validUntil: consumer.xValidUntil || consumer.validUntil || '2030-12-31',
                xValidFrom: consumer.xValidFrom || consumer.validFrom || '2024-01-01',
                xValidUntil: consumer.xValidUntil || consumer.validUntil || '2030-12-31',
                
                // Other fields
                tagNum: consumer.tagNum || consumer.cardNum || '',
                profile: consumer.profile || consumer.extCardProfile || '0',
                extCardProfile: consumer.extCardProfile || consumer.profile || '0',
                facility: consumer.facility || '0',
                filialId: consumer.filialId || '2240',
                
                // Status
                presence: consumer.presence || false,
                ignorePresence: consumer.ignorePresence || false,
                hasFullDetails: false,  // Will be set to true after loading details
                loadingStrategy: loadingStrategy,
                isLargeCompany: loadingStrategy === 'on-demand'
            }));
            
            // Skip heavy debug logs for performance
            
            // Return basic data immediately
            onBasicLoaded(basicSubscribers);
            
            // Load details based on company size strategy  
            if (loadingStrategy !== 'on-demand') {
                // Load details in background AFTER showing the table
                setTimeout(async () => {
                
                    const processSubscriber = async (subscriber) => {
                        try {
                            const detailResult = await this.getConsumerDetail(
                                subscriber.contractId,
                                subscriber.id
                            );
                            
                            if (detailResult.success && detailResult.data) {
                                const detail = detailResult.data;
                                
                                return {
                                    ...subscriber,
                                    companyName: callbacks.companyName || subscriber.companyName,
                                    tagNum: detail.identification?.cardno || '',
                                    cardno: detail.identification?.cardno || '',
                                    firstName: detail.person?.firstName || detail.firstName || subscriber.firstName,
                                    lastName: detail.person?.surname || detail.surname || subscriber.lastName,
                                    lpn1: detail.lpn1 || '',
                                    lpn2: detail.lpn2 || '',
                                    lpn3: detail.lpn3 || '',
                                    vehicle1: detail.lpn1 || '',
                                    vehicle2: detail.lpn2 || '',
                                    vehicle3: detail.lpn3 || '',
                                    profile: detail.identification?.usageProfile?.id || '',
                                    profileName: detail.identification?.usageProfile?.name || '',
                                    validFrom: detail.identification?.validFrom || detail.validFrom || subscriber.validFrom,
                                    validUntil: detail.identification?.validUntil || detail.validUntil || subscriber.validUntil,
                                    present: detail.identification?.present === 'true',
                                    presence: detail.identification?.present === 'true',
                                    ignorePresence: detail.identification?.ignorePresence === '1' || 
                                                   detail.identification?.ignorePresence === 'true' || 
                                                   detail.identification?.ignorePresence === true ||
                                                   detail.ignorePresence === '1' ||
                                                   detail.ignorePresence === 'true' ||
                                                   detail.ignorePresence === true,
                                    hasFullDetails: true
                                };
                            }
                            return subscriber;
                        } catch (error) {
                            console.error(`Error loading detail for consumer ${subscriber.id}:`, error);
                            return subscriber;
                        }
                    };
                    
                    if (loadingStrategy === 'instant') {
                        // Load all at once for small companies
                        const detailPromises = basicSubscribers.map(processSubscriber);
                        const detailedSubscribers = await Promise.all(detailPromises);
                        onBasicLoaded(detailedSubscribers);
                        basicSubscribers = detailedSubscribers;
                    } else if (loadingStrategy === 'batch-50') {
                        // Load in batches of 50 for companies up to 300 subscribers
                        const BATCH_SIZE = 50;
                        const totalBatches = Math.ceil(basicSubscribers.length / BATCH_SIZE);
                        console.log(`[BATCH-50 Strategy] Loading ${basicSubscribers.length} subscribers in ${totalBatches} batches of up to ${BATCH_SIZE} each`);
                        let allUpdated = [];
                        
                        for (let i = 0; i < basicSubscribers.length; i += BATCH_SIZE) {
                            const batch = basicSubscribers.slice(i, Math.min(i + BATCH_SIZE, basicSubscribers.length));
                            const batchNumber = Math.floor(i / BATCH_SIZE) + 1;
                            console.log(`[BATCH-50] Loading batch ${batchNumber}/${totalBatches} (${batch.length} subscribers)`);
                            
                            const batchPromises = batch.map(processSubscriber);
                            const batchResults = await Promise.all(batchPromises);
                            
                            allUpdated = [...allUpdated, ...batchResults];
                            
                            // Update UI after each batch
                            const progress = Math.round((allUpdated.length / basicSubscribers.length) * 100);
                            if (callbacks.onProgress) {
                                callbacks.onProgress({ 
                                    percent: progress,
                                    current: allUpdated.length,
                                    total: basicSubscribers.length
                                });
                            }
                            
                            // Update only the changed items in the UI
                            batchResults.forEach((updated, idx) => {
                                const originalIndex = i + idx;
                                if (callbacks.onDetailLoaded) {
                                    callbacks.onDetailLoaded(updated, originalIndex);
                                }
                            });
                            
                            // Small delay between batches to let UI breathe
                            if (i + BATCH_SIZE < basicSubscribers.length) {
                                await new Promise(resolve => setTimeout(resolve, 200)); // 200ms delay
                            }
                        }
                        
                        basicSubscribers = allUpdated;
                        console.log('[BATCH-50] ✅ All details loaded');
                    } else {
                        // Should not reach here with current strategy
                        console.warn('[Strategy] Unknown loading strategy:', loadingStrategy);
                    }
                    
                    // Hide loading message
                    if (callbacks.onProgress) {
                        callbacks.onProgress({ percent: 100 });
                    }
                }, 100); // Small delay to let UI render first
            }
            else if (loadingStrategy === 'on-demand') {
                // For very large companies (300+), don't auto-load details
                if (callbacks.onProgress) {
                    callbacks.onProgress({ percent: 100 });
                }
            }
            
                        return { 
                success: true,
                data: basicSubscribers,
                total: finalConsumers.length,
                progressive: true,
                loadingStrategy: loadingStrategy
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
        // DISABLED - we don't need details loading, basic data is sufficient
        console.log('[Background] Detail loading is DISABLED - basic data is enough');
        return;
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

    // Get parking transactions for a consumer
    async getParkingTransactions(contractId, consumerId, minDate = null, maxDate = null) {
        try {
            console.log(`[ParkingAPIXML] Getting parking transactions for contract ${contractId}, consumer ${consumerId}`);
            
            // Build query parameters
            let queryParams = [];
            if (minDate) {
                // Convert date to YYYY-MM-DD format if needed
                const formattedMinDate = this.formatDateForAPI(minDate);
                queryParams.push(`minDate=${formattedMinDate}`);
            }
            if (maxDate) {
                const formattedMaxDate = this.formatDateForAPI(maxDate);
                queryParams.push(`maxDate=${formattedMaxDate}`);
            }
            
            const queryString = queryParams.length > 0 ? '?' + queryParams.join('&') : '';
            const url = `/consumers/${contractId},${consumerId}/parktrans${queryString}`;
            
            console.log(`[ParkingAPIXML] Requesting parking transactions from: ${url}`);
            
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'Accept': 'application/xml, text/xml',
                    'Content-Type': 'application/xml'
                }
            });
            
            if (!response.ok) {
                if (response.status === 204) {
                    console.log('[ParkingAPIXML] No parking transactions found');
                    return { success: true, data: [] };
                }
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const xmlText = await response.text();
            console.log('[ParkingAPIXML] Received XML response:', xmlText.substring(0, 500) + (xmlText.length > 500 ? '...' : ''));
            console.log('[ParkingAPIXML] Response length:', xmlText.length);
            
            // Parse XML response
            const parser = new DOMParser();
            const xmlDoc = parser.parseFromString(xmlText, 'text/xml');
            
            // Check for parsing errors
            if (xmlDoc.getElementsByTagName('parsererror').length > 0) {
                console.error('[ParkingAPIXML] XML parsing error');
                return { success: false, error: 'Failed to parse XML response' };
            }
            
            // Also check for namespace issues
            const rootElement = xmlDoc.documentElement;
            console.log(`[ParkingAPIXML] Root element: ${rootElement?.tagName}, namespace: ${rootElement?.namespaceURI}`);
            
            // Extract parking transactions
            const transactions = [];
            let transactionNodes = xmlDoc.getElementsByTagName('parkTransaction');
            
            // If no nodes found, try with namespace
            if (transactionNodes.length === 0) {
                console.log('[ParkingAPIXML] No nodes found with getElementsByTagName, trying with namespace');
                const namespace = 'http://gsph.sub.com/cust/types';
                transactionNodes = xmlDoc.getElementsByTagNameNS(namespace, 'parkTransaction');
            }
            
            console.log(`[ParkingAPIXML] Found ${transactionNodes.length} transaction nodes`);
            
            for (let node of transactionNodes) {
                const transaction = {
                    transactionTime: this.getXMLNodeValue(node, 'transactionTime'),
                    transactionType: this.getXMLNodeValue(node, 'transactionType'),
                    facilityin: this.getXMLNodeValue(node, 'facilityin'),
                    facilityout: this.getXMLNodeValue(node, 'facilityout'),
                    computer: this.getXMLNodeValue(node, 'computer'),
                    device: this.getXMLNodeValue(node, 'device'),
                    amount: this.getXMLNodeValue(node, 'amount')
                };
                
                console.log(`[ParkingAPIXML] Transaction: Type=${transaction.transactionType}, Time=${transaction.transactionTime}, Amount=${transaction.amount}`);
                transactions.push(transaction);
            }
            
            console.log(`[ParkingAPIXML] Found ${transactions.length} parking transactions`);
            
            // If no transactions found, check if we got an empty response
            if (transactions.length === 0 && xmlText.includes('parkTransactions')) {
                console.log('[ParkingAPIXML] Empty transactions response from server');
            }
            
            return { success: true, data: transactions };
            
        } catch (error) {
            console.error('[ParkingAPIXML] Error getting parking transactions:', error);
            return { 
                success: false, 
                error: error.message || 'Failed to get parking transactions' 
            };
        }
    }

    // Helper function to format date for API
    formatDateForAPI(dateStr) {
        if (!dateStr) return '';
        
        // If already in YYYY-MM-DD format
        if (/^\d{4}-\d{2}-\d{2}/.test(dateStr)) {
            return dateStr;
        }
        
        // If in DD/MM/YYYY format, convert
        if (/^\d{1,2}\/\d{1,2}\/\d{4}$/.test(dateStr)) {
            const parts = dateStr.split('/');
            const day = parts[0].padStart(2, '0');
            const month = parts[1].padStart(2, '0');
            const year = parts[2];
            return `${year}-${month}-${day}`;
        }
        
        // Try to parse as Date object
        const date = new Date(dateStr);
        if (!isNaN(date)) {
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            return `${year}-${month}-${day}`;
        }
        
        return dateStr;
    }
}

// Create instance
const parkingAPIXML = new ParkingAPIXML();

// Make available globally
if (typeof window !== 'undefined') {
    window.parkingAPIXML = parkingAPIXML;
    window.parkingAPI = parkingAPIXML;
}
