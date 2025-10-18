/**
 * Unified Timezone Handler for LMS
 * Handles timezone detection and conversion
 */

(function() {
    'use strict';

    const UnifiedTimezoneHandler = {
        userTimezone: null,
        serverTimezone: 'UTC',
        
        init: function() {
            this.detectTimezone();
            this.setupTimezoneHandling();
        },
        
        detectTimezone: function() {
            try {
                this.userTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
                window.userTimezone = this.userTimezone;
            } catch (e) {
                this.userTimezone = 'UTC';
                window.userTimezone = 'UTC';
            }
        },
        
        setupTimezoneHandling: function() {
            // Add timezone to all form submissions
            document.addEventListener('submit', (e) => {
                const form = e.target;
                if (form.tagName === 'FORM') {
                    this.addTimezoneToForm(form);
                }
            });
            
            // Add timezone to all fetch requests
            const originalFetch = window.fetch;
            window.fetch = function(url, options = {}) {
                options.headers = options.headers || {};
                options.headers['X-User-Timezone'] = UnifiedTimezoneHandler.userTimezone;
                return originalFetch(url, options);
            };
        },
        
        addTimezoneToForm: function(form) {
            if (!form.querySelector('input[name="user_timezone"]')) {
                const timezoneInput = document.createElement('input');
                timezoneInput.type = 'hidden';
                timezoneInput.name = 'user_timezone';
                timezoneInput.value = this.userTimezone;
                form.appendChild(timezoneInput);
            }
        },
        
        getTimezone: function() {
            return this.userTimezone;
        },
        
        formatDate: function(date, options = {}) {
            const defaultOptions = {
                timeZone: this.userTimezone,
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            };
            
            return new Intl.DateTimeFormat('en-US', { ...defaultOptions, ...options }).format(date);
        },
        
        convertToUserTimezone: function(date) {
            if (typeof date === 'string') {
                date = new Date(date);
            }
            
            return new Date(date.toLocaleString('en-US', { timeZone: this.userTimezone }));
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            UnifiedTimezoneHandler.init();
        });
    } else {
        UnifiedTimezoneHandler.init();
    }

    // Export to global scope
    window.UnifiedTimezoneHandler = UnifiedTimezoneHandler;
})();