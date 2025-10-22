// SCORM API Integration
const API_ENDPOINT = window.API_ENDPOINT || '';
const ATTEMPT_ID = window.ATTEMPT_ID || '';
const IS_PREVIEW = window.IS_PREVIEW || false;

// API Cache for performance optimization
const apiCache = new Map();
const pendingRequests = new Map();
const CACHE_DURATION = 30000; // 30 seconds
let apiCallCount = 0;

// Make API call to Django backend with caching and request deduplication
async function makeApiCall(method, parameters) {
    try {
        // Create cache key for this request
        const cacheKey = `${method}_${JSON.stringify(parameters)}`;
        
        // Check cache first for read-only operations
        if (['GetValue', 'LMSGetValue', 'GetLastError', 'LMSGetLastError', 'GetErrorString', 'LMSGetErrorString', 'GetDiagnostic', 'LMSGetDiagnostic'].includes(method)) {
            if (apiCache.has(cacheKey)) {
                console.log(`[SCORM API] ${method} -> cached result`);
                return apiCache.get(cacheKey);
            }
        }
        
        // Check if request is already pending
        if (pendingRequests.has(cacheKey)) {
            console.log(`[SCORM API] ${method} -> waiting for pending request`);
            return await pendingRequests.get(cacheKey);
        }
        
        apiCallCount++;
        console.log(`[SCORM API] ${method}(${parameters.join(', ')}) - Call #${apiCallCount}`);
        
        // Create promise for this request
        const requestPromise = fetch(API_ENDPOINT, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                method: method,
                parameters: parameters,
                attempt_id: ATTEMPT_ID
            })
        }).then(async response => {
            pendingRequests.delete(cacheKey);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                console.log(`[SCORM API] ${method} -> ${data.result}`);
                
                // Cache read-only results for 30 seconds
                if (['GetValue', 'LMSGetValue', 'GetLastError', 'LMSGetLastError', 'GetErrorString', 'LMSGetErrorString', 'GetDiagnostic', 'LMSGetDiagnostic'].includes(method)) {
                    apiCache.set(cacheKey, {
                        value: data.result,
                        expiry: Date.now() + CACHE_DURATION
                    });
                }
                
                return data.result;
            } else {
                console.error(`[SCORM API] ${method} failed: ${data.error}`);
                return 'false';
            }
        }).catch(error => {
            pendingRequests.delete(cacheKey);
            throw error;
        });
        
        // Store pending request
        pendingRequests.set(cacheKey, requestPromise);
        
        return await requestPromise;
        
    } catch (error) {
        console.error(`[SCORM API] ${method} error:`, error);
        return 'false';
    }
}

// Synchronous API call for SCORM requirements
function makeApiCallSync(method, parameters) {
    try {
        const cacheKey = `${method}_${JSON.stringify(parameters)}`;
        
        // Check cache first
        if (['GetValue', 'LMSGetValue', 'GetLastError', 'LMSGetLastError', 'GetErrorString', 'LMSGetErrorString', 'GetDiagnostic', 'LMSGetDiagnostic'].includes(method)) {
            if (apiCache.has(cacheKey)) {
                const cached = apiCache.get(cacheKey);
                if (cached.expiry && Date.now() < cached.expiry) {
                    console.log(`[SCORM API] ${method} -> cached result`);
                    return cached.value;
                } else {
                    apiCache.delete(cacheKey);
                }
            }
        }
        
        // Check for pending requests
        if (pendingRequests.has(cacheKey)) {
            console.log(`[SCORM API] ${method} -> waiting for pending request`);
            return pendingRequests.get(cacheKey);
        }
        
        // Make synchronous request
        const xhr = new XMLHttpRequest();
        xhr.open('POST', API_ENDPOINT, false);
        xhr.setRequestHeader('Content-Type', 'application/json');
        xhr.setRequestHeader('X-CSRFToken', getCookie('csrftoken'));
        
        try {
            xhr.send(JSON.stringify({
                method: method,
                parameters: parameters,
                attempt_id: ATTEMPT_ID
            }));
            
            if (xhr.status === 200) {
                const response = JSON.parse(xhr.responseText);
                if (response.success) {
                    console.log(`[SCORM API] ${method}(${parameters.join(', ')}) -> ${response.result}`);
                    
                    // Cache read-only results
                    if (['GetValue', 'LMSGetValue', 'GetLastError', 'LMSGetLastError', 'GetErrorString', 'LMSGetErrorString', 'GetDiagnostic', 'LMSGetDiagnostic'].includes(method)) {
                        apiCache.set(cacheKey, {
                            value: response.result,
                            expiry: Date.now() + CACHE_DURATION
                        });
                    }
                    
                    return response.result;
                } else {
                    console.error(`[SCORM API] ${method} failed: ${response.error}`);
                }
            } else {
                console.error(`[SCORM API] ${method} HTTP error: ${xhr.status}`);
            }
        } catch (e) {
            console.error(`[SCORM API] ${method} sync error:`, e);
        }
        
        return 'false';
        
    } catch (error) {
        console.error(`[SCORM API] ${method} sync error:`, error);
        return 'false';
    }
}

// Helper function to get CSRF token
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Export functions and variables for global access
window.makeApiCall = makeApiCall;
window.makeApiCallSync = makeApiCallSync;
window.apiCache = apiCache;
window.pendingRequests = pendingRequests;
