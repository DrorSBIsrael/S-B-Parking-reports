/**
 * Parking Management System API Client - XML Version
 * Based on Customer Media Web Service Interface
 * Protocol: REST API with XML
 */

class ParkingAPIXML {
    constructor() {
        // Get configuration from config.js if available
        const globalConfig = window.parkingConfig?.current || {};
        
        // Check if we should use proxy based on config or auto-detect
        const useProxy = globalConfig.useProxy !== undefined 
            ? globalConfig.useProxy 
            : (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');
        
        this.config = {
            baseUrl: useProxy 
                ? (globalConfig.proxyUrl || '/api/company-manager/proxy')
                : (globalConfig.apiUrl || '/api/company-manager/proxy'),
            servicePath: useProxy ? '' : '/CustomerMediaWebService',
            username: globalConfig.username || '2022',
            password: globalConfig.password || '2022',
            timeout: globalConfig.timeout || 30000,
            useProxy: useProxy
        };
        
        this.xmlNamespace = 'http://gsph.sub.com/cust/types';
        
        console.log('Parking API XML Configuration:', {
            baseUrl: this.config.baseUrl,
            useProxy: this.config.useProxy,
            username: this.config.username
        });
    }
    
    /**
     * Set API configuration
     */
    setConfig(config) {
        this.config = { ...this.config, ...config };
    }
    
    /**
     * Get full URL for endpoint
     */
    getUrl(endpoint) {
        return `${this.config.baseUrl}${this.config.servicePath}${endpoint}`;
    }
    
    /**
     * Basic authentication header
     */
    getAuthHeaders() {
        const auth = btoa(`${this.config.username}:${this.config.password}`);
        return {
            'Authorization': `Basic ${auth}`,
            'Content-Type': 'application/xml',
            'Accept': 'application/xml'
        };
    }
    
    /**
     * Parse XML response
     */
    parseXML(xmlString) {
        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(xmlString, "text/xml");
        
        // Check for parse errors
        const parseError = xmlDoc.querySelector('parsererror');
        if (parseError) {
            throw new Error('XML Parse Error: ' + parseError.textContent);
        }
        
        return xmlDoc;
    }
    
    /**
     * Convert XML to JavaScript object
     */
    xmlToObject(xmlNode) {
        const obj = {};
        
        // Handle attributes
        if (xmlNode.attributes) {
            for (let attr of xmlNode.attributes) {
                obj['@' + attr.name] = attr.value;
            }
        }
        
        // Handle child nodes
        for (let child of xmlNode.children) {
            const nodeName = child.nodeName;
            const nodeValue = child.children.length === 0 ? child.textContent : this.xmlToObject(child);
            
            if (obj[nodeName]) {
                // Convert to array if multiple elements with same name
                if (!Array.isArray(obj[nodeName])) {
                    obj[nodeName] = [obj[nodeName]];
                }
                obj[nodeName].push(nodeValue);
            } else {
                obj[nodeName] = nodeValue;
            }
        }
        
        return obj;
    }
    
    /**
     * Create XML from JavaScript object
     */
    objectToXML(obj, rootName = 'consumer') {
        let xml = `<?xml version="1.0" encoding="UTF-8"?>\n`;
        xml += `<${rootName} xmlns="${this.xmlNamespace}">\n`;
        
        const buildXML = (data, indent = '  ') => {
            let result = '';
            for (let key in data) {
                if (data[key] === null || data[key] === undefined) {
                    result += `${indent}<${key}/>\n`;
                } else if (typeof data[key] === 'object') {
                    result += `${indent}<${key}>\n`;
                    // Handle nested object
                    for (let subKey in data[key]) {
                        const subValue = data[key][subKey];
                        if (subValue === null || subValue === undefined) {
                            result += `${indent}  <${subKey}/>\n`;
                        } else if (typeof subValue === 'object') {
                            // Handle one more level of nesting (for usageProfile)
                            result += `${indent}  <${subKey}>\n`;
                            for (let subSubKey in subValue) {
                                result += `${indent}    <${subSubKey}>${this.escapeXML(subValue[subSubKey])}</${subSubKey}>\n`;
                            }
                            result += `${indent}  </${subKey}>\n`;
                        } else {
                            result += `${indent}  <${subKey}>${this.escapeXML(subValue)}</${subKey}>\n`;
                        }
                    }
                    result += `${indent}</${key}>\n`;
                } else {
                    result += `${indent}<${key}>${this.escapeXML(data[key])}</${key}>\n`;
                }
            }
            return result;
        };
        
        xml += buildXML(obj);
        xml += `</${rootName}>`;
        return xml;
    }
    
    /**
     * Create nested XML elements
     */
    createNestedXML(key, value, indent = '') {
        let xml = '';
        
        if (Array.isArray(value)) {
            // Handle arrays
            for (let item of value) {
                xml += `${indent}<${key}>${this.escapeXML(item)}</${key}>\n`;
            }
        } else if (typeof value === 'object') {
            xml += `${indent}<${key}>\n`;
            for (let subKey in value) {
                if (value[subKey] !== null && value[subKey] !== undefined) {
                    xml += `${indent}  <${subKey}>${this.escapeXML(value[subKey])}</${subKey}>\n`;
                } else {
                    xml += `${indent}  <${subKey}/>\n`;
                }
            }
            xml += `${indent}</${key}>\n`;
        } else {
            xml += `${indent}<${key}>${this.escapeXML(value)}</${key}>\n`;
        }
        
        return xml;
    }
    
    /**
     * Escape XML special characters
     */
    escapeXML(str) {
        if (typeof str !== 'string') str = String(str);
        return str
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&apos;');
    }
    
    /**
     * Format date for server - handles multiple input formats
     */
    formatDateForServer(dateStr) {
        if (!dateStr) return '';
        
        // If already in server format (YYYY-MM-DD), return as is
        if (/^\d{4}-\d{2}-\d{2}/.test(dateStr)) {
            return dateStr.split('T')[0]; // Remove time if present
        }
        
        // If in European format (DD/MM/YYYY or DD-MM-YYYY)
        if (/^\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4}/.test(dateStr)) {
            const parts = dateStr.split(/[\/\-]/);
            const day = parts[0].padStart(2, '0');
            const month = parts[1].padStart(2, '0');
            const year = parts[2];
            return `${year}-${month}-${day}`;
        }
        
        // Try to parse as date object
        const date = new Date(dateStr);
        if (!isNaN(date)) {
            return date.toISOString().split('T')[0];
        }
        
        return dateStr; // Return as is if can't parse
    }
    
    /**
     * Make API request with XML
     */
    async makeRequest(endpoint, options = {}) {
        const url = this.getUrl(endpoint);
        console.log(`[API] Making ${options.method || 'GET'} request to: ${url}`);
        
        // Log the body for PUT/POST requests
        if (options.body && (options.method === 'PUT' || options.method === 'POST')) {
            console.log('[API] Request body:', options.body);
        }
        
        try {
            const response = await fetch(url, {
                ...options,
                headers: {
                    ...this.getAuthHeaders(),
                    ...options.headers
                }
            });
            
            console.log(`[API] Response status: ${response.status}`);
            
            if (!response.ok) {
                // Try to get error message from response
                const errorText = await response.text();
                console.error(`[API] Error response body:`, errorText.substring(0, 500));
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const xmlText = await response.text();
            console.log(`[API] Response length: ${xmlText.length} chars`);
            
            // For PUT/POST, show more of the response to see what was saved
            if (options.method === 'PUT' || options.method === 'POST') {
                console.log(`[API] ${options.method} Response:`, xmlText.substring(0, 500));
            } else {
                console.log(`[API] Response preview: ${xmlText.substring(0, 200)}...`);
            }
            
            const xmlDoc = this.parseXML(xmlText);
            const data = this.xmlToObject(xmlDoc.documentElement);
            
            console.log(`[API] Parsed data:`, data);
            
            return { success: true, data };
            
        } catch (error) {
            console.error(`[API] Request failed for ${endpoint}:`, error.message);
            
            // Check if it's a CORS or certificate issue
            if (error.message.includes('Failed to fetch')) {
                console.error('[API] Possible CORS or certificate issue. Make sure proxy is running: node proxy-xml-server.js');
            }
            
            return { 
                success: false, 
                error: error.message
            };
        }
    }
    
    /**
     * Get all contracts (companies)
     */
    async getContracts() {
        return await this.makeRequest('/contracts');
    }
    
    /**
     * Get all consumers (subscribers) for a contract
     */
    async getConsumers(contractId) {
        return await this.makeRequest(`/contracts/${contractId}/consumers`);
    }
    
    /**
     * Get single consumer basic details
     */
    async getConsumer(contractId, consumerId) {
        return await this.makeRequest(`/consumers/${contractId},${consumerId}`);
    }
    
    /**
     * Get single consumer FULL details (includes vehicles, card info, etc)
     */
    async getConsumerDetail(contractId, consumerId) {
        return await this.makeRequest(`/consumers/${contractId},${consumerId}/detail`);
    }
    
    /**
     * Get contract (company) details
     */
    async getContractDetails(contractId) {
        return await this.makeRequest(`/contracts/${contractId}`);
    }
    
    /**
     * Create new consumer with full detail structure
     */
    async createConsumer(contractId, consumerData) {
        // For creation, use same structure as update
        const xmlPayload = {
            consumer: {
                // Include ID if provided (for manual numbering)
                ...(consumerData.consumer?.id ? { id: consumerData.consumer.id } : {}),
                contractid: contractId,  // This should be the company/contract ID, not subscriber ID
                filialId: consumerData.consumer?.filialId || '2240'
            },
            // Names in person element - like update!
            person: {
                firstName: consumerData.firstName || '',
                surname: consumerData.surname || consumerData.lastName || ''
            },
            // Vehicle info - only include if not empty
            ...(consumerData.lpn1 ? { lpn1: consumerData.lpn1 } : {}),
            ...(consumerData.lpn2 ? { lpn2: consumerData.lpn2 } : {}),
            ...(consumerData.lpn3 ? { lpn3: consumerData.lpn3 } : {}),
            identification: {
                // Required fields for new subscribers
                ptcptType: consumerData.identification?.ptcptType || '2',
                cardclass: consumerData.identification?.cardclass || '0',
                identificationType: consumerData.identification?.identificationType || '54',
                ignorePresence: consumerData.identification?.ignorePresence || '1',
                
                // Optional fields
                ...(consumerData.identification?.cardno ? { cardno: consumerData.identification.cardno } : {}),
                validFrom: this.formatDateForServer(consumerData.identification?.validFrom || consumerData.validFrom || '2024-01-01'),
                validUntil: this.formatDateForServer(consumerData.identification?.validUntil || consumerData.validUntil || '2025-12-31'),
                usageProfile: {
                    id: consumerData.identification?.usageProfile?.id || '1',
                    name: consumerData.identification?.usageProfile?.name || 'רגיל'
                },
                present: false
            }
        };
        
        const xmlData = this.objectToXML(xmlPayload, 'consumerDetail');
        
        return await this.makeRequest(`/contracts/${contractId}/consumers`, {
            method: 'POST',
            body: xmlData
        });
    }
    
    /**
     * Update consumer with full detail structure
     */
    async updateConsumer(contractId, consumerId, consumerData) {
        console.log('[updateConsumer] Updating consumer:', { contractId, consumerId, consumerData });
        
        // Build update data - names must be in person element!
        // Check if this is a problematic company FIRST
        const problematicCompanies = ['8', '4', '10'];
        const contractIdStr = String(contractId);
        const isProblematicCompany = problematicCompanies.includes(contractIdStr);
        
        const updateData = {
            consumer: {
                id: consumerId,
                contractid: contractId,
                filialId: consumerData.consumer?.filialId || '2240'
            },
            // Names MUST be inside person element - server requirement!
            person: {
                // For problematic companies, use minimal but valid names
                firstName: isProblematicCompany ? '-' : (consumerData.firstName || consumerData.surname || consumerData.lastName || 'Unknown'),
                surname: consumerData.surname || consumerData.lastName || consumerData.firstName || 'Unknown'
            },
            // Vehicle info at root level - include only non-empty values
            ...(consumerData.lpn1 ? { lpn1: consumerData.lpn1 } : {})
        };
        
        // Already checked above
        console.log('[updateConsumer] Checking if company is problematic. contractId:', contractId, 'type:', typeof contractId);
        console.log('[updateConsumer] contractIdStr:', contractIdStr, 'isProblematicCompany:', isProblematicCompany);
        
        // For problematic companies, don't include ANY vehicle info
        if (!isProblematicCompany) {
            // Add lpn2 only if not empty
            if (consumerData.lpn2 && consumerData.lpn2.trim() !== '') {
                updateData.lpn2 = consumerData.lpn2;
                // Add lpn3 ONLY if lpn2 was added and lpn3 is not empty
                if (consumerData.lpn3 && consumerData.lpn3.trim() !== '') {
                    updateData.lpn3 = consumerData.lpn3;
                }
            } else {
                // If lpn2 is empty, log warning if lpn3 is not empty
                if (consumerData.lpn3 && consumerData.lpn3.trim() !== '') {
                    console.warn('[updateConsumer] WARNING: lpn3 provided without lpn2, skipping lpn3:', consumerData.lpn3);
                }
            }
        } else {
            console.log('[updateConsumer] PROBLEMATIC COMPANY - removing all vehicle info');
            // Remove lpn1 for problematic companies too
            delete updateData.lpn1;
            
            // For very problematic companies, keep minimal firstName
            if (contractIdStr === '10') {
                console.log('[updateConsumer] Company 10 detected - using minimal firstName "-"');
                // Keep minimal firstName to avoid empty field error
                updateData.person.firstName = '-';
            }
        }
        
        if (isProblematicCompany) {
            console.log('[updateConsumer] PROBLEMATIC COMPANY DETECTED:', contractId, '- NOT adding identification');
            // DO NOT add identification for problematic companies
        } else if (consumerData.identification && Object.keys(consumerData.identification).length > 0) {
            // For normal companies only, include simple identification
            console.log('[updateConsumer] Normal company, adding identification');
            updateData.identification = {
                // Basic required fields only
                ptcptType: '2',
                cardclass: '0', 
                identificationType: '54',
                ignorePresence: consumerData.identification.ignorePresence || '1'
            };
            
            // Add dates if provided
            if (consumerData.identification.validFrom) {
                updateData.identification.validFrom = this.formatDateForServer(consumerData.identification.validFrom);
            }
            if (consumerData.identification.validUntil) {
                updateData.identification.validUntil = this.formatDateForServer(consumerData.identification.validUntil);
            }
            
            // Add cardno if provided
            if (consumerData.identification.cardno) {
                updateData.identification.cardno = consumerData.identification.cardno;
            }
        }
        // NOTE: Tag (cardno) update is currently not supported by the API
        
        const xmlData = this.objectToXML(updateData, 'consumerDetail');
        
        console.log('[updateConsumer] Update data object:', JSON.stringify(updateData, null, 2));
        console.log('[updateConsumer] Sending XML:', xmlData);
        console.log('[updateConsumer] Names being sent - firstName:', updateData.person?.firstName, 'surname:', updateData.person?.surname);
        console.log('[updateConsumer] Is problematic company?', isProblematicCompany, 'for contractId:', contractId);
        
        // Try to update via detail endpoint first
        let result = await this.makeRequest(`/consumers/${contractId},${consumerId}/detail`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/xml',
                'Accept': 'application/xml'
            },
            body: xmlData
        });
        
        // Don't try regular endpoint as it doesn't support PUT (405 error)
        if (!result.success) {
            console.log('[updateConsumer] Update failed:', result.error);
            // Check if it's an XML structure issue
            if (result.error && result.error.includes('500')) {
                console.error('[updateConsumer] Server error - checking XML structure...');
                console.log('[updateConsumer] XML sent:', xmlData);
                
                // Log potential issues
                if (updateData.person.surname?.length > 50) {
                    console.warn('[updateConsumer] WARNING: Surname is very long, might exceed server limits');
                }
                if (updateData.person.firstName === '') {
                    console.warn('[updateConsumer] WARNING: First name is empty');
                }
                if (updateData.identification?.usageProfile) {
                    console.warn('[updateConsumer] WARNING: Usage profile included:', updateData.identification.usageProfile);
                }
                if (updateData.identification?.present !== undefined) {
                    console.warn('[updateConsumer] WARNING: Present field included:', updateData.identification.present);
                }
                // Log the contract ID for debugging large companies
                console.log('[updateConsumer] Contract/Company ID:', contractId);
                console.log('[updateConsumer] Full update data structure:', JSON.stringify(updateData, null, 2));
            }
        }
        
        if (result.success) {
            console.log('[updateConsumer] Successfully updated consumer:', consumerId);
            
            // Get the consumer details again to see what was actually saved
            console.log('[updateConsumer] Fetching updated consumer to verify changes...');
            const verifyResult = await this.getConsumerDetail(contractId, consumerId);
            if (verifyResult.success) {
                const data = verifyResult.data;
                console.log('[updateConsumer] ✅ Updated fields that were saved:');
                
                // Check names
                if (data.firstName) {
                    console.log('  ✓ firstName:', data.firstName);
                } else if (data.consumer?.firstName) {
                    console.log('  ✓ consumer.firstName:', data.consumer.firstName);
                } else {
                    console.log('  ✗ firstName: NOT SAVED');
                }
                
                if (data.surname) {
                    console.log('  ✓ surname:', data.surname);
                } else if (data.consumer?.surname) {
                    console.log('  ✓ consumer.surname:', data.consumer.surname);
                } else if (data.lastName) {
                    console.log('  ✓ lastName:', data.lastName);
                } else if (data.consumer?.lastName) {
                    console.log('  ✓ consumer.lastName:', data.consumer.lastName);
                } else {
                    console.log('  ✗ surname/lastName: NOT SAVED');
                }
                
                // Check vehicles
                console.log('  ' + (data.lpn1 ? '✓' : '✗') + ' lpn1:', data.lpn1 || 'NOT SAVED');
                console.log('  ' + (data.lpn2 ? '✓' : '✗') + ' lpn2:', data.lpn2 || 'NOT SAVED');
                console.log('  ' + (data.lpn3 ? '✓' : '✗') + ' lpn3:', data.lpn3 || 'NOT SAVED');
                
                // Check other fields
                if (data.identification?.cardno) {
                    console.log('  ✓ tagNum:', data.identification.cardno);
                }
                if (data.identification?.validUntil) {
                    console.log('  ✓ validUntil:', data.identification.validUntil);
                }
            }
        } else {
            console.error('[updateConsumer] Failed to update consumer:', result.error);
        }
        
        return result;
    }
    
    /**
     * Delete consumer
     */
    async deleteConsumer(contractId, consumerId) {
        return await this.makeRequest(`/consumers/${contractId},${consumerId}`, {
            method: 'DELETE'
        });
    }
    
    /**
     * Get consumer cards (vehicles)
     */
    async getConsumerCards(contractId, consumerId) {
        return await this.makeRequest(`/consumers/${contractId},${consumerId}/cards`);
    }
    
    /**
     * Add card to consumer
     */
    async addConsumerCard(contractId, consumerId, cardData) {
        const xmlData = this.objectToXML({
            cardNumber: cardData.cardNumber,
            vehicleNumber: cardData.vehicleNumber,
            validFrom: cardData.validFrom,
            validUntil: cardData.validUntil,
            cardType: cardData.cardType || 'REGULAR'
        }, 'card');
        
        return await this.makeRequest(`/consumers/${contractId},${consumerId}/cards`, {
            method: 'POST',
            body: xmlData
        });
    }
    
    /**
     * Update card
     */
    async updateConsumerCard(contractId, consumerId, cardId, cardData) {
        const xmlData = this.objectToXML({
            id: cardId,
            cardNumber: cardData.cardNumber,
            vehicleNumber: cardData.vehicleNumber,
            validFrom: cardData.validFrom,
            validUntil: cardData.validUntil,
            cardType: cardData.cardType || 'REGULAR'
        }, 'card');
        
        return await this.makeRequest(`/consumers/${contractId},${consumerId}/cards/${cardId}`, {
            method: 'PUT',
            body: xmlData
        });
    }
    
    /**
     * Delete card
     */
    async deleteConsumerCard(contractId, consumerId, cardId) {
        return await this.makeRequest(`/consumers/${contractId},${consumerId}/cards/${cardId}`, {
            method: 'DELETE'
        });
    }
    
    /**
     * Map parking data to our format (from basic consumer data)
     */
    mapConsumerToSubscriber(consumer, contractId) {
        return {
            companyNum: contractId,
            subscriberNum: consumer.id,
            firstName: consumer.firstName || '',
            lastName: consumer.lastName || '',
            name: consumer.name || '',
            validFrom: consumer.xValidFrom,
            validUntil: consumer.xValidUntil,
            filialId: consumer.filialId,
            // Cards will be loaded separately
            vehicle1: '',
            vehicle2: '',
            vehicle3: '',
            tagNum: '',
            profile: 'regular',
            presence: false
        };
    }
    
    /**
     * Map parking DETAIL data to our format (from /detail endpoint)
     */
    mapConsumerDetailToSubscriber(detail, contractId, listName = '') {
        // Extract nested data
        const consumer = detail.consumer || {};
        const identification = detail.identification || {};
        const usageProfile = identification.usageProfile || {};
        
        return {
            // Basic info
            companyNum: contractId,
            subscriberNum: consumer.id || detail.id,
            firstName: detail.firstName || '',
            lastName: detail.surname || listName || '', // Use surname from detail or name from list
            
            // Vehicles from lpn1, lpn2, lpn3
            vehicle1: detail.lpn1 || '',
            vehicle2: detail.lpn2 || '',
            vehicle3: detail.lpn3 || '',
            
            // Card and profile info
            tagNum: identification.cardno || '',
            profile: usageProfile.name || 'regular',
            profileId: usageProfile.id || '',
            
            // Validity dates
            validFrom: identification.validFrom || consumer.xValidFrom || '',
            validUntil: identification.validUntil || consumer.xValidUntil || '',
            
            // Presence info
            presence: identification.present === 'true' || identification.present === true,
            
            // Additional data
            filialId: consumer.filialId || detail.filialId || '',
            email: detail.email || '',
            phone: detail.phone || ''
        };
    }
    
    /**
     * Get usage profiles from server
     */
    async getUsageProfiles() {
        console.log('[getUsageProfiles] Fetching usage profiles from server...');
        
        try {
            const response = await this.makeRequest('/usageProfile');
            
            if (response && response.usageProfile) {
                const profiles = Array.isArray(response.usageProfile) 
                    ? response.usageProfile 
                    : [response.usageProfile];
                
                console.log('[getUsageProfiles] Found profiles:', profiles);
                return {
                    success: true,
                    data: profiles
                };
            }
            
            // If no profiles found, return default profiles
            console.log('[getUsageProfiles] No profiles from server, using defaults');
            return {
                success: true,
                data: [
                    { id: '1', name: 'רגיל' },
                    { id: '2', name: 'פלאזה מזרח' },
                    { id: '3', name: 'VIP' }
                ]
            };
        } catch (error) {
            console.error('[getUsageProfiles] Error:', error);
            // Return default profiles on error
            return {
                success: true,
                data: [
                    { id: '1', name: 'רגיל' },
                    { id: '2', name: 'פלאזה מזרח' },
                    { id: '3', name: 'VIP' }
                ]
            };
        }
    }
    
    /**
     * Get all subscribers - basic data first, then details progressively
     * Progressive loading for better UX
     */
    async getSubscribersProgressive(contractId, options = {}) {
        try {
            const onBasicLoaded = options.onBasicLoaded || (() => {});
            const onDetailLoaded = options.onDetailLoaded || (() => {});
            const onProgress = options.onProgress || (() => {});
            const batchSize = options.batchSize || 5; // Smaller batches for background
            
            console.log(`[Progressive] Getting subscribers for contract ${contractId}...`);
            
            // Step 1: Get basic list quickly
            const consumersResult = await this.getConsumers(contractId);
            if (!consumersResult.success) {
                return consumersResult;
            }
            
            const consumers = Array.isArray(consumersResult.data.consumer) 
                ? consumersResult.data.consumer 
                : [consumersResult.data.consumer];
            
            console.log(`[Progressive] Found ${consumers.length} consumers`);
            
            // PERFORMANCE OPTIMIZATION: Check company size
            const LARGE_COMPANY_THRESHOLD = 300;
            const isLargeCompany = consumers.length > LARGE_COMPANY_THRESHOLD;
            
            if (isLargeCompany) {
                console.log(`[Progressive] LARGE COMPANY DETECTED: ${consumers.length} subscribers > ${LARGE_COMPANY_THRESHOLD}`);
                console.log(`[Progressive] Will load details on-demand only (when hovering or editing)`);
            }
            
            // Map basic data immediately
            const basicSubscribers = consumers.map(consumer => {
                const subscriber = this.mapConsumerToSubscriber(consumer, contractId);
                subscriber.lastName = consumer.name || '';
                subscriber.hasFullDetails = false; // Mark as basic data
                subscriber.isLargeCompany = isLargeCompany; // Mark if from large company
                return subscriber;
            });
            
            // Return basic data immediately
            onBasicLoaded(basicSubscribers);
            
            // Step 2: Load details in background ONLY for small companies
            if (!isLargeCompany) {
                console.log(`[Progressive] Small company (${consumers.length} subscribers) - loading full details in background`);
                this.loadDetailsInBackground(contractId, consumers, basicSubscribers, {
                    batchSize,
                    onDetailLoaded,
                    onProgress
                });
            } else {
                console.log(`[Progressive] Large company - skipping automatic detail loading to improve performance`);
                // Notify that we're in on-demand mode
                if (onProgress) {
                    onProgress({ 
                        loaded: consumers.length, 
                        total: consumers.length,
                        message: `חברה גדולה (${consumers.length} מנויים) - פרטים יטענו לפי דרישה`
                    });
                }
            }
            
            return { 
                success: true, 
                data: basicSubscribers,
                progressive: true,
                consumers: consumers // Keep original for detail loading
            };
            
        } catch (error) {
            console.error('[Progressive] Error:', error);
            return { success: false, error: error.message };
        }
    }
    
    /**
     * Load details in background without blocking UI
     */
    async loadDetailsInBackground(contractId, consumers, subscribers, options) {
        const { batchSize, onDetailLoaded, onProgress } = options;
        const totalBatches = Math.ceil(consumers.length / batchSize);
        
        console.log(`[Background] Starting to load ${consumers.length} details in ${totalBatches} batches`);
        
        for (let batchIndex = 0; batchIndex < totalBatches; batchIndex++) {
            const start = batchIndex * batchSize;
            const end = Math.min(start + batchSize, consumers.length);
            const batch = consumers.slice(start, end);
            
            // Process batch
            const batchPromises = batch.map(async (consumer) => {
                try {
                    const detailResult = await this.getConsumerDetail(contractId, consumer.id);
                    
                    if (detailResult.success) {
                        const fullSubscriber = this.mapConsumerDetailToSubscriber(
                            detailResult.data, 
                            contractId, 
                            consumer.name || ''
                        );
                        fullSubscriber.hasFullDetails = true;
                        
                        // Update the subscriber in the array
                        const index = subscribers.findIndex(s => s.subscriberNum == consumer.id);
                        if (index !== -1) {
                            Object.assign(subscribers[index], fullSubscriber);
                            onDetailLoaded(subscribers[index], index);
                        }
                        
                        return fullSubscriber;
                    }
                } catch (error) {
                    console.warn(`[Background] Error loading detail for ${consumer.id}:`, error.message);
                }
                return null;
            });
            
            await Promise.all(batchPromises);
            
            onProgress({
                current: Math.min(end, consumers.length),
                total: consumers.length,
                percent: Math.round((end / consumers.length) * 100)
            });
            
            // Small delay between batches
            if (batchIndex < totalBatches - 1) {
                await new Promise(resolve => setTimeout(resolve, 100));
            }
        }
        
        console.log(`[Background] Finished loading all details`);
    }
    
    /**
     * Get single consumer detail on demand
     */
    async getConsumerDetailOnDemand(contractId, consumerId) {
        try {
            console.log(`[OnDemand] Getting details for consumer ${contractId},${consumerId}`);
            
            const detailResult = await this.getConsumerDetail(contractId, consumerId);
            
            if (detailResult.success) {
                const subscriber = this.mapConsumerDetailToSubscriber(
                    detailResult.data, 
                    contractId, 
                    ''
                );
                subscriber.hasFullDetails = true;
                return { success: true, data: subscriber };
            }
            
            return detailResult;
        } catch (error) {
            console.error(`[OnDemand] Error:`, error);
            return { success: false, error: error.message };
        }
    }
    
    /**
     * Legacy method - kept for backwards compatibility
     * @deprecated Use getSubscribersProgressive instead
     */
    async getSubscribersWithDetails(contractId, options = {}) {
        return this.getSubscribersProgressive(contractId, options);
    }
    
    /**
     * Legacy method - kept for backwards compatibility
     * @deprecated Use getSubscribersWithDetails instead
     */
    async getSubscribersWithCards(contractId) {
        return this.getSubscribersWithDetails(contractId);
    }
    
    /**
     * Get a single subscriber's details
     * @param {string} contractId - The contract/company ID
     * @param {string} subscriberNum - The subscriber number
     * @returns {Promise<{success: boolean, data?: object, error?: string}>}
     */
    async getSubscriber(contractId, subscriberNum) {
        try {
            console.log(`[API] Getting single subscriber: contract=${contractId}, subscriber=${subscriberNum}`);
            
            // Get the specific consumer
            const url = `/consumers/${contractId},${subscriberNum}`;
            const response = await this.makeRequest(url);
            
            if (response.success && response.data) {
                const consumer = response.data;
                
                // Format the subscriber data
                const subscriber = {
                    companyNum: contractId,
                    subscriberNum: consumer.id || subscriberNum,
                    name: consumer.name || '',
                    firstName: consumer.name?.split(' ')[0] || '',
                    lastName: consumer.name?.split(' ').slice(1).join(' ') || consumer.name || '',
                    tagNum: consumer.tagNo || '',
                    vehicle1: consumer.cardNo1 || '',
                    vehicle2: consumer.cardNo2 || '',
                    vehicle3: consumer.cardNo3 || '',
                    validFrom: consumer.xValidFrom || '',
                    validUntil: consumer.xValidUntil || '',
                    presence: consumer.present === '1' || consumer.present === true,
                    profileId: consumer.extCardProfile || '1',
                    profile: this.getProfileName(consumer.extCardProfile || '1'),
                    ignorePresence: consumer.ignorePresence === '1' || consumer.ignorePresence === true,
                    notes: consumer.memo || '',
                    email: consumer.email || ''
                };
                
                return { success: true, data: subscriber };
            }
            
            return { success: false, error: 'Subscriber not found' };
        } catch (error) {
            console.error('[API] Error getting single subscriber:', error);
            return { success: false, error: error.message };
        }
    }
    
    /**
     * Get enhanced contract (company) details with statistics
     */
    async getEnhancedContractDetails(contractId) {
        console.log('[getEnhancedContractDetails] Getting FULL details for contract:', contractId);
        
        try {
            // First get the contract detail with facility data
            const result = await this.makeRequest(`/contracts/${contractId}/detail`);
            
            if (result.success && result.data) {
                console.log('[getEnhancedContractDetails] Got contract details with facility:', result.data);
                
                // Parse the contract detail
                const detail = result.data;
                const contract = detail.contract || {};
                
                // Count consumers if we have them
                let consumerCount = 0;
                let activeConsumers = 0;
                let presentConsumers = 0;
                
                try {
                    const consumersResult = await this.getConsumers(contractId);
                    if (consumersResult.success && consumersResult.data) {
                        const consumers = Array.isArray(consumersResult.data.consumer) 
                            ? consumersResult.data.consumer 
                            : consumersResult.data.consumer ? [consumersResult.data.consumer] : [];
                        
                        consumerCount = consumers.length;
                        
                        // Count active and present
                        const today = new Date();
                        consumers.forEach(c => {
                            if (c.xValidUntil && new Date(c.xValidUntil) >= today) {
                                activeConsumers++;
                            }
                            if (c.present === 'true' || c.present === true) {
                                presentConsumers++;
                            }
                        });
                    }
                } catch (error) {
                    console.warn('[getEnhancedContractDetails] Could not get consumer count:', error);
                }
                
                return {
                    success: true,
                    data: {
                        ...detail,
                        consumerCount,
                        activeConsumers,
                        presentConsumers,
                        totalVehicles: consumerCount * 2 // Estimate
                    }
                };
            }
            
            return result;
        } catch (error) {
            console.error('[getEnhancedContractDetails] Error:', error);
            return { success: false, error: error.message };
        }
    }
    
    /**
     * Get parking transactions for a consumer
     */
    async getConsumerTransactions(contractId, consumerId, params = {}) {
        console.log('[getConsumerTransactions] Getting transactions:', { contractId, consumerId, params });
        
        try {
            let url = `/consumers/${contractId},${consumerId}/parktrans`;
            const queryParams = [];
            
            if (params.minDate) {
                queryParams.push(`minDate=${params.minDate}`);
            }
            if (params.maxDate) {
                queryParams.push(`maxDate=${params.maxDate}`);
            }
            if (params.exported !== undefined) {
                queryParams.push(`exported=${params.exported}`);
            }
            
            if (queryParams.length > 0) {
                url += '?' + queryParams.join('&');
            }
            
            const result = await this.makeRequest(url);
            
            if (result.success && result.data) {
                console.log('[getConsumerTransactions] Got transactions:', result.data);
                return result;
            }
            
            return result;
        } catch (error) {
            console.error('[getConsumerTransactions] Error:', error);
            return { success: false, error: error.message };
        }
    }
}

// Create singleton instance
const parkingAPIXML = new ParkingAPIXML();

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = parkingAPIXML;
}
