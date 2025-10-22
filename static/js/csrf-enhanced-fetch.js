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
            // Try to get from meta tag first
            const metaTag = document.querySelector('meta[name="csrf-token"]');
            if (metaTag) {
                return metaTag.getAttribute('content');
            }
            
            // Fall back to cookie
            const cookies = document.cookie.split(';');
            for (let cookie of cookies) {
                const [name, value] = cookie.trim().split('=');
                if (name === 'csrftoken') {
                    return value;
                }
            }
            return null;
        },
        
        enhanceFetch: function() {
            const originalFetch = window.fetch;
            const self = this;
            
            window.fetch = function(url, options = {}) {
                // Add CSRF token to requests
                if (self.csrfToken && (options.method === 'POST' || options.method === 'PUT' || options.method === 'DELETE' || options.method === 'PATCH')) {
                    options.headers = options.headers || {};
                    options.headers['X-CSRFToken'] = self.csrfToken;
                }
                
                return originalFetch.call(this, url, options);
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
