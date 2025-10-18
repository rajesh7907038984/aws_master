/**
 * Safe Fetch Utilities for LMS
 * Enhanced fetch with error handling and retry logic
 */

(function() {
    'use strict';

    const SafeFetchUtils = {
        defaultOptions: {
            timeout: 30000,
            retries: 3,
            retryDelay: 1000
        },
        
        fetch: async function(url, options = {}) {
            const config = { ...this.defaultOptions, ...options };
            let lastError;
            
            for (let attempt = 1; attempt <= config.retries; attempt++) {
                try {
                    const controller = new AbortController();
                    const timeoutId = setTimeout(() => controller.abort(), config.timeout);
                    
                    const response = await window.fetch(url, {
                        ...config,
                        signal: controller.signal
                    });
                    
                    clearTimeout(timeoutId);
                    
                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                    }
                    
                    return response;
                } catch (error) {
                    lastError = error;
                    
                    if (attempt < config.retries && this.isRetryableError(error)) {
                        await this.delay(config.retryDelay * attempt);
                        continue;
                    }
                    
                    throw error;
                }
            }
            
            throw lastError;
        },
        
        isRetryableError: function(error) {
            return error.name === 'AbortError' || 
                   error.message.includes('Failed to fetch') ||
                   error.message.includes('NetworkError');
        },
        
        delay: function(ms) {
            return new Promise(resolve => setTimeout(resolve, ms));
        },
        
        get: function(url, options = {}) {
            return this.fetch(url, { ...options, method: 'GET' });
        },
        
        post: function(url, data, options = {}) {
            return this.fetch(url, {
                ...options,
                method: 'POST',
                body: JSON.stringify(data),
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                }
            });
        },
        
        put: function(url, data, options = {}) {
            return this.fetch(url, {
                ...options,
                method: 'PUT',
                body: JSON.stringify(data),
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                }
            });
        },
        
        delete: function(url, options = {}) {
            return this.fetch(url, { ...options, method: 'DELETE' });
        }
    };

    // Export to global scope
    window.SafeFetchUtils = SafeFetchUtils;
})();