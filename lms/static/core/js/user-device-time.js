/**
 * User Device Time Handler for LMS
 * Captures and manages user device time information
 */
(function() {
    'use strict';

    window.UserDeviceTime = {
        // Get user's local time
        getLocalTime: function() {
            return new Date();
        },

        // Get timezone offset in minutes
        getTimezoneOffset: function() {
            return new Date().getTimezoneOffset();
        },

        // Get timezone name
        getTimezoneName: function() {
            try {
                return Intl.DateTimeFormat().resolvedOptions().timeZone;
            } catch (e) {
                console.warn('Could not detect timezone name:', e);
                return 'Unknown';
            }
        },

        // Get device time info object
        getDeviceTimeInfo: function() {
            const now = this.getLocalTime();
            return {
                localTime: now.toISOString(),
                timestamp: now.getTime(),
                timezoneOffset: this.getTimezoneOffset(),
                timezoneName: this.getTimezoneName(),
                localTimeString: now.toString()
            };
        },

        // Send time info to server (if endpoint exists)
        syncWithServer: function() {
            const timeInfo = this.getDeviceTimeInfo();
            
            // Store locally
            if (typeof(Storage) !== "undefined") {
                sessionStorage.setItem('deviceTimeInfo', JSON.stringify(timeInfo));
            }

            // Optional: sync with server
            const syncEndpoint = '/api/sync-device-time/';
            if (window.fetch && typeof window.CSRFHandler !== 'undefined') {
                fetch(syncEndpoint, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': window.CSRFHandler.getToken()
                    },
                    body: JSON.stringify(timeInfo)
                }).catch(e => {
                    // Silently fail - this is optional functionality
                    console.debug('Device time sync failed (optional):', e);
                });
            }
        },

        // Add time info to forms
        addToForms: function() {
            const timeInfo = this.getDeviceTimeInfo();
            const forms = document.querySelectorAll('form');
            
            forms.forEach(form => {
                // Add device timestamp if not exists
                if (!form.querySelector('input[name="device_timestamp"]')) {
                    const timestampInput = document.createElement('input');
                    timestampInput.type = 'hidden';
                    timestampInput.name = 'device_timestamp';
                    timestampInput.value = timeInfo.timestamp;
                    form.appendChild(timestampInput);
                }

                // Add timezone offset if not exists
                if (!form.querySelector('input[name="timezone_offset"]')) {
                    const offsetInput = document.createElement('input');
                    offsetInput.type = 'hidden';
                    offsetInput.name = 'timezone_offset';
                    offsetInput.value = timeInfo.timezoneOffset;
                    form.appendChild(offsetInput);
                }
            });
        },

        // Initialize device time handling
        init: function() {
            this.syncWithServer();
            this.addToForms();
            
            // Update device time periodically (every 5 minutes)
            setInterval(() => {
                this.syncWithServer();
            }, 5 * 60 * 1000);

            console.log('User device time handler initialized');
        }
    };

    // Auto-initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            window.UserDeviceTime.init();
        });
    } else {
        window.UserDeviceTime.init();
    }
})();
