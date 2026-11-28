/**
 * Parking API v2 - Complete version with all methods
 */

class ParkingAPIXML {
    constructor() {
        // ALWAYS use proxy for consistency and security
        // Determine base URL based on current location
        let baseUrl = '/api/company-manager/proxy';
        
        // If running on localhost, use relative path
        if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
            baseUrl = '/api/company-manager/proxy';
        } else {
            // If running on production, use absolute URL to correct server
            baseUrl = window.location.origin + '/api/company-manager/proxy';
        }
        
        let savedParkingId = null;
        try {
            if (typeof localStorage !== 'undefined') {
                savedParkingId = localStorage.getItem('currentParkingId');
            }
        } catch(e) {}

        this.config = {
            baseUrl: baseUrl,
            username: '2022',
            password: '2022',
            timeout: 30000,
            useProxy: true,  // Always use proxy
            currentParkingId: savedParkingId
        };
        // Initialization complete - using secure proxy
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
        if (parkingId && typeof localStorage !== 'undefined') {
            try {
                localStorage.setItem('currentParkingId', parkingId);
            } catch(e) {}
        }
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
                // Proxy request to endpoint
                
                // Make sure endpoint includes CustomerMediaWebService prefix
                // Remove leading slash if exists
                if (endpoint.startsWith('/')) {
                    endpoint = endpoint.substring(1);
                }
                
                if (!endpoint.startsWith('CustomerMediaWebService')) {
                    endpoint = `CustomerMediaWebService/${endpoint}`;
                }
                
                const effectiveParkingId = this.config.currentParkingId || 
                                           window.currentParking?.id || 
                                           (typeof localStorage !== 'undefined' ? localStorage.getItem('currentParkingId') : null) || 
                                           '1';
                
                const requestBody = {
                    parking_id: effectiveParkingId,
                    endpoint: endpoint,
                    method: method,
                    payload: data
                };
                // Only log profile requests for debugging
                response = await fetch(this.config.baseUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(requestBody)
                });
            } else {
                // LOCAL: Direct connection
                const url = `${this.config.baseUrl}/${endpoint}`;
                const headers = {
                    'Authorization': 'Basic ' + btoa(`${this.config.username}:${this.config.password}`),
                    'Accept': 'application/xml',
                    'Content-Type': 'application/json'
                };
                
                // Direct request
                
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
            
            // Only log errors and profile-related responses
            if (!response.ok || endpoint.includes('profile')) {
            }
            
            if (!response.ok) {
                console.error('[makeRequest] Response not OK:', response.status, response.statusText, result);
                const errMsg = result?.message || result?.error || `HTTP ${response.status}: ${response.statusText}`;
                return { success: false, error: errMsg, status: response.status, data: result?.data };
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
        // Fetching enhanced contract details
        const result = await this.makeRequest(`contracts/${contractId}/detail`);
        
        // Log the response structure for debugging
        if (result.success) {
            // Response received
            
            // Debug info removed for production
        }
        
        return result;
    }
    
    async getConsumers(companyNum, contractId) {
        // Fetching consumers
        
        // Send contractId in payload - Flask will build the correct URL
        const result = await this.makeRequest('consumers', 'GET', { 
            contractId: contractId  // Pass contractId in payload for Flask to use
        });
        
        // Check if we got the consumers
        if (result.success && result.data) {
            // Handle both array and single object responses
            let consumers = Array.isArray(result.data) ? result.data : [result.data];
            // Minimal debug - just count
            // Consumers received from server
            
            // SAFETY CHECK: If we got too many consumers, something is wrong!
            if (consumers.length > 500) {
                // Large consumer list detected - server returned all consumers
            } else {
                // Consumers filtered successfully
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
        // Loading consumer details on demand
        // Call the regular getConsumerDetail method
        return this.getConsumerDetail(contractId, consumerId);
    }

    /**
     * Get bulk detailed information for all consumers in a contract in one request
     * Supports optional minId / maxId range chunking for very large contracts
     */
    async getContractConsumersDetail(contractId, minId = null, maxId = null) {
        let endpoint = `contracts/${contractId}/consumersdetail`;
        const params = [];
        if (minId !== null && minId !== undefined) params.push(`minId=${minId}`);
        if (maxId !== null && maxId !== undefined) params.push(`maxId=${maxId}`);
        if (params.length > 0) {
            endpoint += `?${params.join('&')}`;
        }
        return this.makeRequest(endpoint, 'GET');
    }

    /**
     * Normalize a raw consumerDetail object into a UI subscriber object
     */
    mapConsumerDetailToSubscriber(detail, companyId, companyName = '', isLargeCompany = false, loadingStrategy = 'bulk', fallbackSubscriber = null) {
        const base = fallbackSubscriber || {};
        const consumerNode = detail.consumer || detail || {};
        const person = detail.person || {};
        const ident = detail.identification || {};
        const usageProf = ident.usageProfile || detail.usageProfile || {};

        const subId = consumerNode.id || detail.id || detail.subscriberNum || base.subscriberNum || base.id;
        const fname = person.firstName || detail.firstName || base.firstName || '';
        const lname = person.surname || detail.surname || detail.lastName || consumerNode.name || detail.name || base.lastName || '';
        const tag = ident.cardno || detail.tagNum || detail.cardno || base.tagNum || '';
        const profId = usageProf.id || detail.profile || detail.profileId || detail.extCardProfile || base.profile || '1';
        const profName = usageProf.name || detail.profileName || base.profileName || (profId ? `פרופיל ${profId}` : 'רגיל');
        const vFrom = ident.validFrom || consumerNode.xValidFrom || detail.validFrom || detail.xValidFrom || base.validFrom || '2024-01-01';
        const vUntil = ident.validUntil || consumerNode.xValidUntil || detail.validUntil || detail.xValidUntil || base.validUntil || '2030-12-31';
        const isPres = ident.present === 'true' || ident.present === true || detail.present === 'true' || detail.present === true || detail.presence === true || base.presence || false;
        const cleanLpn = (val) => (typeof val === 'string' ? val.trim() : '');
        const l1 = cleanLpn(detail.lpn1) || cleanLpn(detail.vehicle1) || base.vehicle1 || '';
        const l2 = cleanLpn(detail.lpn2) || cleanLpn(detail.vehicle2) || base.vehicle2 || '';
        const l3 = cleanLpn(detail.lpn3) || cleanLpn(detail.vehicle3) || base.vehicle3 || '';
        const filialId = consumerNode.filialId || detail.filialId || base.filialId || '2240';
        const ignorePres = ident.ignorePresence === '1' ||
                           ident.ignorePresence === 'true' ||
                           ident.ignorePresence === true ||
                           detail.ignorePresence === '1' ||
                           detail.ignorePresence === 'true' ||
                           detail.ignorePresence === true ||
                           base.ignorePresence || false;

        return {
            ...base,
            id: subId,
            subscriberNum: subId,
            contractId: companyId,
            companyNum: companyId,
            companyName: companyName || base.companyName || '',
            firstName: fname,
            lastName: lname,
            name: lname,
            vehicleNum: l1,
            lpn1: l1,
            lpn2: l2,
            lpn3: l3,
            vehicle1: l1,
            vehicle2: l2,
            vehicle3: l3,
            validFrom: vFrom,
            validUntil: vUntil,
            xValidFrom: vFrom,
            xValidUntil: vUntil,
            tagNum: tag,
            cardno: tag,
            profile: profId,
            profileId: profId,
            profileName: profName,
            extCardProfile: profId,
            facility: detail.facility || base.facility || '0',
            filialId: filialId,
            present: isPres,
            presence: isPres,
            ignorePresence: ignorePres,
            hasFullDetails: true,
            loadingStrategy: loadingStrategy,
            isLargeCompany: isLargeCompany
        };
    }

    // Cancel any in-flight progressive loading when switching companies
    cancelActiveLoad() {
        this._activeLoadGeneration = (this._activeLoadGeneration || 0) + 1;
    }

    getCacheKey(companyId) {
        const effectiveParkingId = this.config.currentParkingId ||
                                   window.currentParking?.id ||
                                   (typeof localStorage !== 'undefined' ? localStorage.getItem('currentParkingId') : null) ||
                                   '1';
        return `skidata_cache_p${effectiveParkingId}_c${companyId}`;
    }

    _saveToLocalCache(cacheKey, companyId, timestamp, subscribers) {
        try {
            // Remove legacy unscoped cache key if present
            try { localStorage.removeItem('skidata_cache_company_' + companyId); } catch (e) {}
            const payloadStr = JSON.stringify({
                timestamp: timestamp,
                subscribers: subscribers
            });
            try {
                localStorage.setItem(cacheKey, payloadStr);
            } catch (quotaErr) {
                // Evict oldest skidata_cache_* entries to free space and retry
                const cacheEntries = [];
                for (let i = 0; i < localStorage.length; i++) {
                    const k = localStorage.key(i);
                    if (k && k.startsWith('skidata_cache_')) {
                        let ts = 0;
                        try {
                            const m = localStorage.getItem(k)?.match(/"timestamp"\s*:\s*(\d+)/);
                            if (m) ts = parseInt(m[1], 10) || 0;
                        } catch (e) {}
                        cacheEntries.push({ key: k, ts });
                    }
                }
                cacheEntries.sort((a, b) => a.ts - b.ts);
                for (const entry of cacheEntries) {
                    try { localStorage.removeItem(entry.key); } catch (e) {}
                    try {
                        localStorage.setItem(cacheKey, payloadStr);
                        break;
                    } catch (e) {}
                }
            }
        } catch (e) {
            console.warn('[Cache] Failed to save company cache:', e);
        }
    }
    
    // Progressive loading methods for large datasets with bulk consumersdetail optimization
    async getSubscribersProgressive(companyId, callbacks = {}) {
        const { 
            onBasicLoaded = () => {}, 
            onDetailLoaded = () => {}, 
            onChunkLoaded = null,
            onProgress = () => {},
            onComplete = () => {},
            forceFullLoad = false
        } = callbacks;

        this._activeLoadGeneration = (this._activeLoadGeneration || 0) + 1;
        const myLoadGen = this._activeLoadGeneration;
        const isCancelled = () => this._activeLoadGeneration !== myLoadGen;
        
        const cacheKey = this.getCacheKey(companyId);
        const legacyCacheKey = 'skidata_cache_company_' + companyId;
        
        if (forceFullLoad) {
            try {
                localStorage.removeItem(cacheKey);
                localStorage.removeItem(legacyCacheKey);
            } catch(e) {}
        } else {
            try {
                const cached = localStorage.getItem(cacheKey);
                if (cached) {
                    const parsedData = JSON.parse(cached);
                    const CACHE_VALID_HOURS = 12; 
                    const cacheAgeMs = Date.now() - (parsedData.timestamp || 0);
                    const isCacheValid = cacheAgeMs < (CACHE_VALID_HOURS * 60 * 60 * 1000);
                    const allHaveDetails = parsedData.subscribers && parsedData.subscribers.every(s => s.hasFullDetails);
                    
                    // שמירת מטמון לחברות בינוניות וגדולות (200+ מנויים) כאשר כל הפרטים מלאים
                    if (isCacheValid && parsedData.subscribers && parsedData.subscribers.length >= 200 && allHaveDetails) {
                        const isLarge = parsedData.subscribers.length > 500;
                        console.log(`[Cache] Loaded ${parsedData.subscribers.length} subscribers from cache for company ${companyId}`);
                        
                        parsedData.subscribers = parsedData.subscribers.map(sub => ({
                            ...sub,
                            companyNum: companyId,
                            contractId: companyId,
                            companyName: callbacks.companyName || sub.companyName,
                            hasFullDetails: true,
                            isLargeCompany: isLarge
                        }));
                        
                        onBasicLoaded(parsedData.subscribers, true, parsedData.timestamp);
                        if (onProgress) onProgress({ percent: 100, message: 'הנתונים נטענו מזיכרון מקומי (מטמון)' });
                        if (onComplete) onComplete(parsedData.subscribers, true, parsedData.timestamp);
                        return { success: true, data: parsedData.subscribers, fromCache: true, timestamp: parsedData.timestamp };
                    } else {
                        localStorage.removeItem(cacheKey);
                    }
                }
            } catch(e) {
                try { localStorage.removeItem(cacheKey); } catch(err) {}
            }
        }
        
        try {
            // Step 1: Get basic consumer list (fast ~0.5-1.1s) so table renders immediately
            const result = await this.getConsumers(companyId, companyId);
            if (isCancelled()) {
                return { success: false, cancelled: true };
            }
            
            if (!result.success) {
                console.error('[Progressive] Failed to get consumers list');
                return result;
            }
            
            let consumers = result.data || [];
            const consumersArray = Array.isArray(consumers) ? consumers : [consumers];
            
            // Filter by contractId if API returns all consumers
            if (consumersArray.length > 1000) {
                const filtered = consumersArray.filter(c => 
                    c.contractId === companyId || 
                    c.contractId === String(companyId) ||
                    c.contractid === companyId ||
                    c.contractid === String(companyId) ||
                    c.contract === companyId ||
                    c.contract === String(companyId) ||
                    c.contractNum === companyId ||
                    c.contractNum === String(companyId) ||
                    c.companyId === companyId ||
                    c.companyId === String(companyId)
                );
                if (filtered.length > 0) {
                    consumers = filtered;
                } else {
                    consumers = consumersArray;
                }
            }
            
            const finalConsumers = Array.isArray(consumers) ? consumers : [consumers];
            const subscriberCount = finalConsumers.length;
            const BULK_SINGLE_CALL_LIMIT = 800; // Up to 800 subscribers in a single /consumersdetail request
            const BULK_CHUNK_SIZE = 400;        // For > 800 subscribers, load in chunks of 400 (2 chunks in parallel)
            const CONCURRENT_CHUNKS = 2;
            const isLargeCompany = subscriberCount > 500;
            const shouldCacheCompany = subscriberCount >= 200;
            const loadingStrategy = subscriberCount <= BULK_SINGLE_CALL_LIMIT ? 'bulk' : 'bulk-chunked';

            let basicSubscribers = finalConsumers.map(consumer => {
                const person = consumer.person || {};
                const ident = consumer.identification || {};
                const usageProf = ident.usageProfile || consumer.usageProfile || {};

                const fname = person.firstName || consumer.firstName || '';
                const lname = person.surname || consumer.lastName || consumer.name || '';
                const tag = ident.cardno || consumer.tagNum || consumer.cardNum || consumer.cardno || '';
                const profId = usageProf.id || consumer.profile || consumer.extCardProfile || '1';
                const profName = usageProf.name || consumer.profileName || (profId ? `פרופיל ${profId}` : 'רגיל');
                const vFrom = ident.validFrom || consumer.xValidFrom || consumer.validFrom || '2024-01-01';
                const vUntil = ident.validUntil || consumer.xValidUntil || consumer.validUntil || '2030-12-31';
                const isPres = ident.present === 'true' || ident.present === true || consumer.presence || consumer.present || false;
                const l1 = consumer.lpn1 || consumer.vehicle1 || consumer.vehicleNum || '';
                const l2 = consumer.lpn2 || consumer.vehicle2 || '';
                const l3 = consumer.lpn3 || consumer.vehicle3 || '';

                return {
                    id: consumer.id || consumer.subscriberNum,
                    subscriberNum: consumer.id || consumer.subscriberNum,
                    contractId: companyId,
                    companyNum: companyId,
                    companyName: callbacks.companyName || '',
                    firstName: fname,
                    lastName: lname,
                    name: lname,
                    vehicleNum: l1,
                    lpn1: l1,
                    lpn2: l2,
                    lpn3: l3,
                    vehicle1: l1,
                    vehicle2: l2,
                    vehicle3: l3,
                    validFrom: vFrom,
                    validUntil: vUntil,
                    xValidFrom: vFrom,
                    xValidUntil: vUntil,
                    tagNum: tag,
                    cardno: tag,
                    profile: profId,
                    profileId: profId,
                    profileName: profName,
                    extCardProfile: profId,
                    facility: consumer.facility || '0',
                    filialId: consumer.filialId || '2240',
                    presence: isPres,
                    ignorePresence: consumer.ignorePresence || false,
                    hasFullDetails: false,
                    loadingStrategy: loadingStrategy,
                    isLargeCompany: isLargeCompany
                };
            });
            
            // Render initial table immediately
            onBasicLoaded(basicSubscribers, false);

            if (subscriberCount === 0) {
                const emptyTs = Date.now();
                if (onProgress) onProgress({ percent: 100 });
                if (onComplete) onComplete([], false, emptyTs);
                return { success: true, data: [], total: 0, progressive: false, loadingStrategy: 'bulk' };
            }

            // Step 2: Fetch full details via bulk /contracts/{id}/consumersdetail
            setTimeout(async () => {
                if (isCancelled()) return;

                const subMapById = new Map();
                basicSubscribers.forEach((sub, idx) => {
                    subMapById.set(String(sub.subscriberNum), { sub, idx });
                });

                let bulkSucceeded = false;

                try {
                    if (subscriberCount <= BULK_SINGLE_CALL_LIMIT) {
                        if (onProgress) {
                            onProgress({
                                percent: 15,
                                message: `טוען פרטי ${subscriberCount} מנויים...`
                            });
                        }

                        const bulkRes = await this.getContractConsumersDetail(companyId);
                        if (isCancelled()) return;

                        if (bulkRes.success && bulkRes.data) {
                            const detailList = Array.isArray(bulkRes.data) ? bulkRes.data : [bulkRes.data];
                            if (detailList.length > 0) {
                                detailList.forEach(detail => {
                                    const consumerNode = detail.consumer || detail || {};
                                    const sid = String(consumerNode.id || detail.id || detail.subscriberNum || '');
                                    const existingEntry = subMapById.get(sid);
                                    const mapped = this.mapConsumerDetailToSubscriber(
                                        detail,
                                        companyId,
                                        callbacks.companyName,
                                        isLargeCompany,
                                        loadingStrategy,
                                        existingEntry ? existingEntry.sub : null
                                    );
                                    if (existingEntry) {
                                        basicSubscribers[existingEntry.idx] = mapped;
                                    } else if (sid) {
                                        basicSubscribers.push(mapped);
                                    }
                                });
                                bulkSucceeded = true;
                            }
                        }
                    } else {
                        // Large company (> 800 subscribers): load in chunks of 400 with 2 parallel requests at a time
                        const sortedNumericIds = basicSubscribers
                            .map(s => parseInt(s.subscriberNum, 10))
                            .filter(n => !isNaN(n))
                            .sort((a, b) => a - b);

                        if (sortedNumericIds.length > 0) {
                            const chunkRanges = [];
                            for (let i = 0; i < sortedNumericIds.length; i += BULK_CHUNK_SIZE) {
                                const slice = sortedNumericIds.slice(i, Math.min(i + BULK_CHUNK_SIZE, sortedNumericIds.length));
                                chunkRanges.push({
                                    minId: slice[0],
                                    maxId: slice[slice.length - 1],
                                    count: slice.length
                                });
                            }

                            let loadedCount = 0;
                            let allChunksOk = true;
                            let rangeBugDetected = false;

                            for (let cIdx = 0; cIdx < chunkRanges.length; cIdx += CONCURRENT_CHUNKS) {
                                if (isCancelled()) return;
                                const activeGroup = chunkRanges.slice(cIdx, cIdx + CONCURRENT_CHUNKS);

                                const pct = Math.max(5, Math.round((loadedCount / subscriberCount) * 100));
                                if (onProgress) {
                                    onProgress({
                                        percent: pct,
                                        current: loadedCount,
                                        total: subscriberCount,
                                        message: `טוען פרטי מנויים... ${loadedCount} מתוך ${subscriberCount}`
                                    });
                                }

                                const groupResponses = await Promise.all(
                                    activeGroup.map(r => this.getContractConsumersDetail(companyId, r.minId, r.maxId))
                                );
                                if (isCancelled()) return;

                                for (let g = 0; g < groupResponses.length; g++) {
                                    const chunkRes = groupResponses[g];
                                    const rangeInfo = activeGroup[g];

                                    if (chunkRes.success && chunkRes.data) {
                                        const detailList = Array.isArray(chunkRes.data) ? chunkRes.data : [chunkRes.data];
                                        // Detect older Skidata WAR bug where minId/maxId returns only 1 item (id == minId)
                                        if (rangeInfo.count > 2 && detailList.length <= 1) {
                                            rangeBugDetected = true;
                                            break;
                                        }
                                        // Update in-memory array WITHOUT calling onDetailLoaded 1500 times (prevents DOM layout thrashing!)
                                        for (let d = 0; d < detailList.length; d++) {
                                            const detail = detailList[d];
                                            const consumerNode = detail.consumer || detail || {};
                                            const sid = String(consumerNode.id || detail.id || detail.subscriberNum || '');
                                            const existingEntry = subMapById.get(sid);
                                            if (existingEntry) {
                                                const mapped = this.mapConsumerDetailToSubscriber(
                                                    detail,
                                                    companyId,
                                                    callbacks.companyName,
                                                    isLargeCompany,
                                                    loadingStrategy,
                                                    existingEntry.sub
                                                );
                                                basicSubscribers[existingEntry.idx] = mapped;
                                            }
                                        }
                                        loadedCount += rangeInfo.count;
                                    } else {
                                        allChunksOk = false;
                                        break;
                                    }
                                }

                                if (rangeBugDetected) {
                                    console.warn('[Progressive] Server ignores minId/maxId range, switching to full bulk request');
                                    const fullBulkRes = await this.getContractConsumersDetail(companyId);
                                    if (isCancelled()) return;
                                    if (fullBulkRes.success && fullBulkRes.data) {
                                        const fullList = Array.isArray(fullBulkRes.data) ? fullBulkRes.data : [fullBulkRes.data];
                                        for (let d = 0; d < fullList.length; d++) {
                                            const detail = fullList[d];
                                            const consumerNode = detail.consumer || detail || {};
                                            const sid = String(consumerNode.id || detail.id || detail.subscriberNum || '');
                                            const existingEntry = subMapById.get(sid);
                                            if (existingEntry) {
                                                basicSubscribers[existingEntry.idx] = this.mapConsumerDetailToSubscriber(
                                                    detail,
                                                    companyId,
                                                    callbacks.companyName,
                                                    isLargeCompany,
                                                    'bulk',
                                                    existingEntry.sub
                                                );
                                            }
                                        }
                                        allChunksOk = true;
                                    } else {
                                        allChunksOk = false;
                                    }
                                    break;
                                }

                                if (!allChunksOk) break;

                                // Batch UI update once per chunk group if not the final group
                                if (onChunkLoaded && loadedCount < subscriberCount) {
                                    onChunkLoaded(basicSubscribers, loadedCount, subscriberCount);
                                }
                            }
                            bulkSucceeded = allChunksOk;
                        }
                    }
                } catch (bulkErr) {
                    console.warn('[Progressive] Bulk consumersdetail failed, falling back to safe small batches:', bulkErr);
                    bulkSucceeded = false;
                }

                // Safe fallback if bulk endpoint is unavailable on an older server:
                // Use small batch size of 3 (never 25!) so the Skidata server never chokes or times out
                if (!bulkSucceeded && !isCancelled()) {
                    const SAFE_BATCH_SIZE = 3;
                    for (let i = 0; i < basicSubscribers.length; i += SAFE_BATCH_SIZE) {
                        if (isCancelled()) return;
                        const batch = basicSubscribers.slice(i, Math.min(i + SAFE_BATCH_SIZE, basicSubscribers.length));
                        const batchResults = await Promise.all(batch.map(async (sub) => {
                            if (sub.hasFullDetails) return sub;
                            const detailRes = await this.getConsumerDetail(sub.contractId, sub.id);
                            if (detailRes.success && detailRes.data) {
                                return this.mapConsumerDetailToSubscriber(
                                    detailRes.data,
                                    companyId,
                                    callbacks.companyName,
                                    isLargeCompany,
                                    'safe-batch',
                                    sub
                                );
                            }
                            return sub;
                        }));

                        if (isCancelled()) return;

                        batchResults.forEach((updated, idx) => {
                            const originalIndex = i + idx;
                            basicSubscribers[originalIndex] = updated;
                            if (onDetailLoaded) {
                                onDetailLoaded(updated, originalIndex);
                            }
                        });

                        const doneCount = Math.min(i + SAFE_BATCH_SIZE, basicSubscribers.length);
                        const progress = Math.round((doneCount / basicSubscribers.length) * 100);
                        if (onProgress) {
                            onProgress({
                                percent: progress,
                                current: doneCount,
                                total: basicSubscribers.length,
                                message: `טוען פרטי מנויים... ${doneCount} מתוך ${basicSubscribers.length}`
                            });
                        }
                    }
                }

                if (isCancelled()) return;

                const finishTimestamp = Date.now();
                onBasicLoaded(basicSubscribers, false, finishTimestamp);

                if (shouldCacheCompany) {
                    this._saveToLocalCache(cacheKey, companyId, finishTimestamp, basicSubscribers);
                } else {
                    try { localStorage.removeItem(cacheKey); } catch (e) {}
                }

                if (onProgress) {
                    onProgress({
                        percent: 100,
                        message: `הושלמה טעינת ${basicSubscribers.length} מנויים`
                    });
                }
                if (onComplete) {
                    onComplete(basicSubscribers, false, finishTimestamp);
                }
            }, 10);

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
        return;
    }
    
    // Additional helper methods
    async saveSubscriber(companyId, subscriberData) {
        return this.addConsumer(companyId, subscriberData);
    }
    
    async loadUsageProfiles() {
        return this.getUsageProfiles();
    }
    
    async getSubscriber(companyId, subscriberId) {
        const res = await this.getConsumerDetail(companyId, subscriberId);
        if (res.success && res.data) {
            return {
                success: true,
                data: this.mapConsumerDetailToSubscriber(res.data, companyId)
            };
        }
        return res;
    }

    async refreshSingleSubscriber(companyId, subscriberId) {
        return this.getSubscriber(companyId, subscriberId);
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
            // Getting parking transactions
            
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
            const endpoint = `consumers/${contractId},${consumerId}/parktrans${queryString}`;
            
            // Requesting parking transactions through proxy
            
            // Use the proxy for parking transactions
            const proxyUrl = `${this.config.proxy.baseURL}`;
            const requestData = {
                parking_id: this.currentParkingId,
                endpoint: endpoint,
                method: 'GET'
            };
            
            const response = await fetch(proxyUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify(requestData)
            });
            
            // Response received
            
            if (!response.ok) {
                if (response.status === 204) {
                    // No parking transactions found
                    return { success: true, data: [] };
                }
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const proxyResponse = await response.json();
            // Received proxy response
            
            if (!proxyResponse.success) {
                return { success: false, error: proxyResponse.error || 'Failed to get transactions' };
            }
            
            // Handle both XML and JSON responses from proxy
            const data = proxyResponse.data;
            
            // Check if data is already parsed (JSON) or needs XML parsing
            if (typeof data === 'object' && data !== null) {
                // Data is already parsed - handle the transaction data
                if (data.parkTransactions && data.parkTransactions.parkTransaction) {
                    const transData = data.parkTransactions.parkTransaction;
                    const transactions = Array.isArray(transData) ? transData : [transData];
                    return { success: true, data: transactions };
                } else if (data.length === 0 || Object.keys(data).length === 0) {
                    // Empty response - no transactions
                    return { success: true, data: [] };
                } else {
                    // Unexpected format
                    return { success: false, error: 'Unexpected response format' };
                }
            }
            
            // If data is a string, it might be XML that needs parsing
            const xmlText = typeof data === 'string' ? data : JSON.stringify(data);
            const parser = new DOMParser();
            const xmlDoc = parser.parseFromString(xmlText, 'text/xml');
            
            // Check for parsing errors
            if (xmlDoc.getElementsByTagName('parsererror').length > 0) {
                console.error('[ParkingAPIXML] XML parsing error');
                return { success: false, error: 'Failed to parse response' };
            }
            
            // Also check for namespace issues
            const rootElement = xmlDoc.documentElement;
            // Root element found
            
            // Extract parking transactions
            const transactions = [];
            let transactionNodes = xmlDoc.getElementsByTagName('parkTransaction');
            
            // If no nodes found, try with namespace
            if (transactionNodes.length === 0) {
                // Trying with namespace
                const namespace = 'http://gsph.sub.com/cust/types';
                transactionNodes = xmlDoc.getElementsByTagNameNS(namespace, 'parkTransaction');
            }
            
            // Found transaction nodes
            
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
                
                // Transaction parsed
                transactions.push(transaction);
            }
            
            // Found parking transactions
            
            // If no transactions found, check if we got an empty response
            if (transactions.length === 0) {
                if (xmlText.includes('parkTransactions')) {
                    // Empty parkTransactions response
                } else {
                    // Unexpected response format - no parkTransactions element found
                }
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
