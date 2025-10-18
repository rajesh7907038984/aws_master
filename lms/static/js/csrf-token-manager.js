/**
 * CSRF Token Manager for LMS
 * Centralized CSRF token handling
 */

(function() {
    'use strict';

    const CSRFManager = {
        token: null,
        
        init: function() {
            this.loadToken();
            this.setupTokenRefresh();
        },
        
        loadToken: function() {
            // Try multiple sources for CSRF token
            const sources = [
                function() {
                    var meta = document.querySelector('meta[name="csrf-token"]');
                    return meta ? meta.getAttribute('content') : null;
                },
                function() {
                    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
                    return input ? input.value : null;
                },
                function() {
                    return window.CSRF_TOKEN;
                },
                function() {
                    return this.getTokenFromCookie();
                }.bind(this)
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
                    console.error('Error getting CSRF token from source:', e);
                    continue;
                }
            }
            
            console.warn('CSRF token not found');
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
            try {
                // Refresh token every 30 minutes
                setInterval(() => {
                    try {
                        this.loadToken();
                    } catch (error) {
                        console.error('Error refreshing CSRF token:', error);
                    }
                }, 30 * 60 * 1000);
            } catch (error) {
                console.error('Error setting up token refresh:', error);
            }
        },
        
        addTokenToForm: function(form) {
            const token = this.getToken();
            if (!token) return false;
            
            // Check if token already exists
            if (form.querySelector('input[name="csrfmiddlewaretoken"]')) {
                return true;
            }
            
            const csrfInput = document.createElement('input');
            csrfInput.type = 'hidden';
            csrfInput.name = 'csrfmiddlewaretoken';
            csrfInput.value = token;
            form.appendChild(csrfInput);
            return true;
        },
        
        addTokenToHeaders: function(headers = {}) {
            const token = this.getToken();
            if (token) {
                headers['X-CSRFToken'] = token;
            }
            return headers;
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            CSRFManager.init();
        });
    } else {
        CSRFManager.init();
    }

    // Export to global scope
    window.CSRFManager = CSRFManager;
    window.getCSRFToken = () => CSRFManager.getToken();
})();