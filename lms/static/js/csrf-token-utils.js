/**
 * Enhanced CSRF Token Utilities
 * Provides robust CSRF token retrieval with multiple fallback methods
 */

(function() {
    'use strict';
    
    // Cache for CSRF token to avoid repeated DOM queries
    let csrfTokenCache = null;
    let cacheTimestamp = 0;
    const CACHE_DURATION = 300000; // 5 minutes
    
    /**
     * Enhanced CSRF token retrieval with multiple fallback methods
     * @returns {string|null} CSRF token or null if not found
     */
    function getCSRFToken() {
        // Check cache first
        const now = Date.now();
        if (csrfTokenCache && (now - cacheTimestamp) < CACHE_DURATION) {
            return csrfTokenCache;
        }
        
        const sources = [
            // Method 1: Meta tag (preferred)
            function() {
                const csrfMeta = document.querySelector('meta[name="csrf-token"]');
                return csrfMeta ? csrfMeta.getAttribute('content') : null;
            },
            
            // Method 2: Input field
            function() {
                const csrfInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
                return csrfInput ? csrfInput.value : null;
            },
            
            // Method 3: Cookie fallback
            function() {
                const cookies = document.cookie.split(';');
                for (let cookie of cookies) {
                    const [name, value] = cookie.trim().split('=');
                    if (name === 'csrftoken') {
                        return value;
                    }
                }
                return null;
            },
            
            // Method 4: Django's CSRF token in forms
            function() {
                const forms = document.querySelectorAll('form');
                for (let form of forms) {
                    const tokenInput = form.querySelector('input[name="csrfmiddlewaretoken"]');
                    if (tokenInput && tokenInput.value) {
                        return tokenInput.value;
                    }
                }
                return null;
            },
            
            // Method 5: Data attribute on body
            function() {
                const body = document.body;
                if (body) {
                    return body.getAttribute('data-csrf-token') || null;
                }
                return null;
            }
        ];
        
        // Try each source
        for (let source of sources) {
            try {
                const token = source();
                if (token && token.length > 0 && token !== 'undefined' && token !== 'null') {
                    // Cache the token
                    csrfTokenCache = token;
                    cacheTimestamp = now;
                    return token;
                }
            } catch (error) {
                ProductionLogger.warn('CSRF token source failed:', error);
                continue;
            }
        }
        
        ProductionLogger.error('CSRF token not found using any method');
        return null;
    }
    
    /**
     * Get CSRF token with retry mechanism
     * @param {number} retries Number of retries (default: 3)
     * @param {number} delay Delay between retries in ms (default: 100)
     * @returns {Promise<string|null>} CSRF token or null
     */
    function getCSRFTokenWithRetry(retries = 3, delay = 100) {
        return new Promise((resolve) => {
            let attempts = 0;
            
            function tryGetToken() {
                const token = getCSRFToken();
                if (token) {
                    resolve(token);
                    return;
                }
                
                attempts++;
                if (attempts < retries) {
                    setTimeout(tryGetToken, delay);
                } else {
                    resolve(null);
                }
            }
            
            tryGetToken();
        });
    }
    
    /**
     * Clear CSRF token cache
     */
    function clearCSRFTokenCache() {
        csrfTokenCache = null;
        cacheTimestamp = 0;
    }
    
    /**
     * Enhanced fetch with automatic CSRF token inclusion
     * @param {string} url Request URL
     * @param {object} options Fetch options
     * @returns {Promise<Response>} Fetch response
     */
    function fetchWithCSRF(url, options = {}) {
        const token = getCSRFToken();
        
        // Set default headers
        const headers = {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            ...options.headers
        };
        
        // Add CSRF token if available
        if (token) {
            headers['X-CSRFToken'] = token;
        }
        
        // Add CSRF token to form data if it's a FormData object
        if (options.body instanceof FormData && token) {
            options.body.append('csrfmiddlewaretoken', token);
        }
        
        return fetch(url, {
            ...options,
            headers
        });
    }
    
    /**
     * Enhanced XMLHttpRequest with automatic CSRF token inclusion
     * @param {string} method HTTP method
     * @param {string} url Request URL
     * @param {object} options Request options
     * @returns {XMLHttpRequest} XMLHttpRequest instance
     */
    function createXHRWithCSRF(method, url, options = {}) {
        const xhr = new XMLHttpRequest();
        const token = getCSRFToken();
        
        xhr.open(method, url, true);
        
        // Set headers
        xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
        if (token) {
            xhr.setRequestHeader('X-CSRFToken', token);
        }
        
        if (options.headers) {
            Object.keys(options.headers).forEach(key => {
                xhr.setRequestHeader(key, options.headers[key]);
            });
        }
        
        return xhr;
    }
    
    // Expose functions globally
    window.CSRFUtils = {
        getToken: getCSRFToken,
        getTokenWithRetry: getCSRFTokenWithRetry,
        clearCache: clearCSRFTokenCache,
        fetch: fetchWithCSRF,
        createXHR: createXHRWithCSRF
    };
    
    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            ProductionLogger.log('✅ CSRF Token Utils initialized');
        });
    } else {
        ProductionLogger.log('✅ CSRF Token Utils initialized');
    }
    
})();
