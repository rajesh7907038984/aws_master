
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
 * User Device Time Handler
 * Handles user device time synchronization and display
 */

(function() {
    'use strict';
    
    const UserDeviceTime = {
        timeOffset: 0,
        updateInterval: null,
        
        init: function() {
            this.calculateTimeOffset();
            this.startTimeUpdates();
        },
        
        calculateTimeOffset: function() {
            // Calculate offset between server and client time
            const serverTimeElement = document.querySelector('[data-server-time]');
            if (serverTimeElement) {
                const serverTime = parseInt(serverTimeElement.getAttribute('data-server-time')) * 1000;
                const clientTime = Date.now();
                this.timeOffset = serverTime - clientTime;
            }
        },
        
        startTimeUpdates: function() {
            try {
                // Update time displays every minute
                this.updateInterval = setInterval(() => {
                    try {
                        this.updateTimeDisplays();
                    } catch (error) {
                        console.error('Error in time update interval:', error);
                    }
                }, 60000);
                
                // Initial update
                this.updateTimeDisplays();
            } catch (error) {
                console.error('Error starting time updates:', error);
            }
        },
        
        updateTimeDisplays: function() {
            try {
                const timeElements = document.querySelectorAll('[data-live-time]');
                
                timeElements.forEach(element => {
                    try {
                        const currentTime = new Date(Date.now() + this.timeOffset);
                        const format = element.getAttribute('data-time-format') || 'default';
                        
                        element.textContent = this.formatTime(currentTime, format);
                    } catch (error) {
                        console.error('Error updating time display for element:', error);
                    }
                });
            } catch (error) {
                console.error('Error in updateTimeDisplays:', error);
            }
        },
        
        formatTime: function(date, format) {
            try {
                switch (format) {
                    case 'time':
                        return date.toLocaleTimeString();
                    case 'date':
                        return date.toLocaleDateString();
                    case 'datetime':
                        return date.toLocaleString();
                    default:
                        return date.toLocaleString();
                }
            } catch (error) {
                return date.toString();
            }
        },
        
        getCurrentTime: function() {
            return new Date(Date.now() + this.timeOffset);
        },
        
        destroy: function() {
            if (this.updateInterval) {
                clearInterval(this.updateInterval);
                this.updateInterval = null;
            }
        }
    };
    
// Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => UserDeviceTime.init());
    } else {
        UserDeviceTime.init();
    }
    
    // Cleanup on page unload
    window.addEventListener('beforeunload', () => UserDeviceTime.destroy());
    
    // Export globally
    window.UserDeviceTime = UserDeviceTime;
    
})();
