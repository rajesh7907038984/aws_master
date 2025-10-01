/**
 * Unified Timezone Handler for LMS
 * Handles timezone detection and management across the application
 */
(function() {
    'use strict';

    // Create global timezone handler
    window.TimezoneHandler = {
        // Get user's current timezone
        getUserTimezone: function() {
            try {
                return Intl.DateTimeFormat().resolvedOptions().timeZone;
            } catch (e) {
                console.warn('Could not detect timezone:', e);
                return 'UTC';
            }
        },

        // Format date according to user's timezone
        formatDate: function(dateString, options = {}) {
            try {
                const date = new Date(dateString);
                const defaultOptions = {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                };
                const formatOptions = Object.assign(defaultOptions, options);
                return date.toLocaleDateString(undefined, formatOptions);
            } catch (e) {
                console.warn('Could not format date:', e);
                return dateString;
            }
        },

        // Initialize timezone handling
        init: function() {
            const timezone = this.getUserTimezone();
            
            // Store timezone in session storage for server-side usage
            if (typeof(Storage) !== "undefined") {
                sessionStorage.setItem('userTimezone', timezone);
            }

            // Add timezone to forms
            const forms = document.querySelectorAll('form');
            forms.forEach(form => {
                // Add hidden timezone field if it doesn't exist
                if (!form.querySelector('input[name="user_timezone"]')) {
                    const timezoneInput = document.createElement('input');
                    timezoneInput.type = 'hidden';
                    timezoneInput.name = 'user_timezone';
                    timezoneInput.value = timezone;
                    form.appendChild(timezoneInput);
                }
            });

            console.log('Timezone handler initialized with timezone:', timezone);
        }
    };

    // Auto-initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            window.TimezoneHandler.init();
        });
    } else {
        window.TimezoneHandler.init();
    }
})();
