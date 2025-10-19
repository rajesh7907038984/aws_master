/**
 * CSRF Enhanced Fetch - Handles CSRF tokens for fetch requests
 */
(function() {
    'use strict';
    
    const CSRFEnhancedFetch = {
        init: function() {
            this.setupCSRFToken();
            this.enhanceFetch();
        },
        
        setupCSRFToken: function() {
            // Get CSRF token from cookie or meta tag
            this.csrfToken = this.getCSRFToken();
        },
        
        getCSRFToken: function() {
            try {
                // Try to get from meta tag first
                const metaTag = document.querySelector('meta[name="csrf-token"]');
                if (metaTag) {
                    const token = metaTag.getAttribute('content');
                    if (token && token.trim() !== '') {
                        return token;
                    }
                }
                
                // Try to get from input field
                const inputField = document.querySelector('input[name="csrfmiddlewaretoken"]');
                if (inputField) {
                    const token = inputField.value;
                    if (token && token.trim() !== '') {
                        return token;
                    }
                }
                
                // Try to get from window object
                if (window.CSRF_TOKEN && window.CSRF_TOKEN.trim() !== '') {
                    return window.CSRF_TOKEN;
                }
                
                // Fall back to cookie
                const cookies = document.cookie.split(';');
                for (let cookie of cookies) {
                    const [name, value] = cookie.trim().split('=');
                    if (name === 'csrftoken' && value && value.trim() !== '') {
                        return value;
                    }
                }
                
                console.warn('CSRF token not found in any source');
                return null;
            } catch (error) {
                console.error('Error getting CSRF token:', error);
                return null;
            }
        },
        
        enhanceFetch: function() {
            const originalFetch = window.fetch;
            const self = this;
            
            window.fetch = function(url, options = {}) {
                try {
                    // Add CSRF token to requests that need it
                    if (options.method === 'POST' || options.method === 'PUT' || options.method === 'DELETE' || options.method === 'PATCH' || 
                        (options.method === undefined && url && typeof url === 'string')) {
                        
                        // Get fresh CSRF token for each request
                        const csrfToken = self.getCSRFToken();
                        if (csrfToken) {
                            options.headers = options.headers || {};
                            options.headers['X-CSRFToken'] = csrfToken;
                        } else {
                            console.warn('CSRF token not available for request to:', url);
                        }
                    }
                    
                    return originalFetch.call(this, url, options);
                } catch (error) {
                    console.error('Error in enhanced fetch:', error);
                    throw error;
                }
            };
        }
    };
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            CSRFEnhancedFetch.init();
        });
    } else {
        CSRFEnhancedFetch.init();
    }
    
    // Export to global scope
    window.CSRFEnhancedFetch = CSRFEnhancedFetch;
})();
