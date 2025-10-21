/**
 * User Device Time Utility for LMS
 * Handles user device time detection and synchronization
 */

(function() {
    'use strict';

    const UserDeviceTime = {
        deviceTime: null,
        serverTime: null,
        timeOffset: 0,
        
        init: function() {
            this.detectDeviceTime();
            this.setupTimeSync();
        },
        
        detectDeviceTime: function() {
            this.deviceTime = new Date();
            window.deviceTime = this.deviceTime;
        },
        
        setupTimeSync: function() {
            // Sync time with server every 5 minutes
            setInterval(() => {
                this.syncWithServer();
            }, 5 * 60 * 1000);
            
            // Initial sync
            this.syncWithServer();
        },
        
        syncWithServer: function() {
            fetch('/api/time/', {
                method: 'GET',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.server_time) {
                    this.serverTime = new Date(data.server_time);
                    this.timeOffset = this.serverTime.getTime() - this.deviceTime.getTime();
                    window.serverTime = this.serverTime;
                    window.timeOffset = this.timeOffset;
                }
            })
            .catch(error => {
                console.warn('Time sync failed:', error);
            });
        },
        
        getCurrentTime: function() {
            if (this.serverTime) {
                return new Date(Date.now() + this.timeOffset);
            }
            return new Date();
        },
        
        formatTime: function(date, format = 'datetime') {
            const time = date || this.getCurrentTime();
            
            switch (format) {
                case 'date':
                    return time.toLocaleDateString();
                case 'time':
                    return time.toLocaleTimeString();
                case 'datetime':
                default:
                    return time.toLocaleString();
            }
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            UserDeviceTime.init();
        });
    } else {
        UserDeviceTime.init();
    }

    // Export to global scope
    window.UserDeviceTime = UserDeviceTime;
})();