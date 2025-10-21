
// Console fallback for older browsers
if (typeof console === 'undefined') {
    window.console = {
        log: function() {},
        error: function() {},
        warn: function() {},
        info: function() {}
    };
}

/**
 * Unified Timezone Handler
 * Handles timezone detection and conversion across the LMS
 */

(function() {
    'use strict';
    
    const TimezoneHandler = {
        userTimezone: null,
        
        init: function() {
            this.detectTimezone();
            this.setupTimezoneDisplay();
        },
        
        detectTimezone: function() {
            try {
                this.userTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
            } catch (error) {
                this.userTimezone = 'UTC';
            }
        },
        
        setupTimezoneDisplay: function() {
            // Convert timestamps on page if needed
            const timestamps = document.querySelectorAll('[data-timestamp]');
            timestamps.forEach(element => {
                const timestamp = element.getAttribute('data-timestamp');
                if (timestamp) {
                    try {
                        const date = new Date(parseInt(timestamp) * 1000);
                        element.textContent = date.toLocaleString();
                    } catch (error) {
                    }
                }
            });
        },
        
        formatDate: function(date, format = 'full') {
            try {
                const options = format === 'full' ? 
                    { year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' } :
                    { year: 'numeric', month: 'short', day: 'numeric' };
                
                return date.toLocaleString(undefined, options);
            } catch (error) {
                return date.toString();
            }
        }
    };
    
// Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => TimezoneHandler.init());
    } else {
        TimezoneHandler.init();
    }
    
    // Export globally
    window.TimezoneHandler = TimezoneHandler;
    
})();
