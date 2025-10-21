/**
 * Unified CSRF Handler for LMS
 * Centralized CSRF token management
 */

(function() {
    'use strict';

    const UnifiedCSRFHandler = {
        token: null,
        
        init: function() {
            this.loadToken();
            this.setupTokenRefresh();
            this.interceptRequests();
        },
        
        loadToken: function() {
            const sources = [
                () => document.querySelector('meta[name="csrf-token"]')?.getAttribute('content'),
                () => document.querySelector('input[name="csrfmiddlewaretoken"]')?.value,
                () => window.CSRF_TOKEN,
                () => this.getTokenFromCookie()
            ];

            for (let source of sources) {
                try {
                    const token = source();
                    if (token && token.length > 0 && /^[a-zA-Z0-9]+$/.test(token)) {
                        this.token = token;
                        window.CSRF_TOKEN = token;
                        return token;
                    }
                } catch (e) {
                    continue;
                }
            }
            
            return null;
        },
        
        getTokenFromCookie: function() {
            const cookies = document.cookie.split(';');
            for (let cookie of cookies) {
                const [name, value] = cookie.trim().split('=');
                if (name === 'csrftoken') {
                    return value;
                }
            }
            return null;
        },
        
        getToken: function() {
            if (!this.token) {
                this.loadToken();
            }
            return this.token;
        },
        
        setupTokenRefresh: function() {
            setInterval(() => {
                this.loadToken();
            }, 30 * 60 * 1000);
        },
        
        interceptRequests: function() {
            const originalFetch = window.fetch;
            window.fetch = function(url, options = {}) {
                if (options.method && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(options.method.toUpperCase())) {
                    options.headers = options.headers || {};
                    if (!options.headers['X-CSRFToken']) {
                        const token = UnifiedCSRFHandler.getToken();
                        if (token) {
                            options.headers['X-CSRFToken'] = token;
                        }
                    }
                }
                return originalFetch(url, options);
            };
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            UnifiedCSRFHandler.init();
        });
    } else {
        UnifiedCSRFHandler.init();
    }

    // Export to global scope
    window.UnifiedCSRFHandler = UnifiedCSRFHandler;
})();