/**
 * Unified CSRF Handler for LMS
 * Provides CSRF token management for all AJAX requests and forms
 */
(function() {
    'use strict';

    window.CSRFHandler = {
        token: null,

        // Get CSRF token from various sources
        getToken: function() {
            if (this.token) {
                return this.token;
            }

            // Try to get token from meta tag
            const metaToken = document.querySelector('meta[name="csrf-token"]');
            if (metaToken) {
                this.token = metaToken.getAttribute('content');
                return this.token;
            }

            // Try to get token from hidden input
            const hiddenInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
            if (hiddenInput) {
                this.token = hiddenInput.value;
                return this.token;
            }

            // Try to get token from cookie
            const cookies = document.cookie.split(';');
            for (let cookie of cookies) {
                const [name, value] = cookie.trim().split('=');
                if (name === 'csrftoken') {
                    this.token = decodeURIComponent(value);
                    return this.token;
                }
            }

            console.warn('CSRF token not found');
            return null;
        },

        // Refresh CSRF token
        refresh: function() {
            this.token = null;
            return this.getToken();
        },

        // Setup CSRF token for jQuery AJAX requests
        setupJQuery: function() {
            if (typeof $ !== 'undefined' && $.ajaxSetup) {
                const token = this.getToken();
                if (token) {
                    $.ajaxSetup({
                        beforeSend: function(xhr, settings) {
                            if (!this.crossDomain && settings.type !== 'GET') {
                                xhr.setRequestHeader('X-CSRFToken', token);
                            }
                        }
                    });
                }
            }
        },

        // Setup CSRF token for fetch requests
        setupFetch: function() {
            const token = this.getToken();
            if (token && window.fetch) {
                const originalFetch = window.fetch;
                window.fetch = function(url, options = {}) {
                    // Only add CSRF token for same-origin POST/PUT/DELETE requests
                    if (options.method && options.method !== 'GET' && 
                        (!url.startsWith('http') || url.startsWith(window.location.origin))) {
                        
                        options.headers = options.headers || {};
                        if (typeof options.headers.set === 'function') {
                            options.headers.set('X-CSRFToken', token);
                        } else {
                            options.headers['X-CSRFToken'] = token;
                        }
                    }
                    return originalFetch(url, options);
                };
            }
        },

        // Add CSRF token to all forms
        setupForms: function() {
            const token = this.getToken();
            if (!token) return;

            const forms = document.querySelectorAll('form');
            forms.forEach(form => {
                // Skip forms that already have CSRF token
                if (form.querySelector('input[name="csrfmiddlewaretoken"]')) {
                    return;
                }

                // Skip GET forms
                if (form.method.toLowerCase() === 'get') {
                    return;
                }

                // Add CSRF token input
                const csrfInput = document.createElement('input');
                csrfInput.type = 'hidden';
                csrfInput.name = 'csrfmiddlewaretoken';
                csrfInput.value = token;
                form.appendChild(csrfInput);
            });
        },

        // Initialize CSRF handling
        init: function() {
            this.getToken();
            this.setupJQuery();
            this.setupFetch();
            this.setupForms();
            
            console.log('CSRF handler initialized');
        }
    };

    // Auto-initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            window.CSRFHandler.init();
        });
    } else {
        window.CSRFHandler.init();
    }
})();
