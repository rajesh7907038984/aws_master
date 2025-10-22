/**
 * Timezone Detection and Management for LMS
 * Automatically detects user's timezone and syncs with server
 */

class TimezoneDetector {
    constructor() {
        this.timezone = null;
        this.offset = null;
        this.detected = false;
        this.init();
    }

    init() {
        this.detectTimezone();
        this.setupPeriodicSync();
    }

    detectTimezone() {
        try {
            // Get timezone from Intl API (most accurate)
            this.timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
            
            // Get UTC offset in minutes
            const now = new Date();
            this.offset = -now.getTimezoneOffset(); // Note: getTimezoneOffset() returns negative offset
            
            this.detected = true;
            
            
            // Send to server
            this.sendToServer();
            
        } catch (error) {
            console.error('Error detecting timezone:', error);
            this.fallbackDetection();
        }
    }

    fallbackDetection() {
        try {
            // Fallback: use offset to guess timezone
            const now = new Date();
            this.offset = -now.getTimezoneOffset();
            
            // Map offset to common timezone
            this.timezone = this.mapOffsetToTimezone(this.offset);
            this.detected = true;
            
            
            this.sendToServer();
            
        } catch (error) {
            console.error('Fallback timezone detection failed:', error);
            this.timezone = 'UTC';
            this.offset = 0;
            this.detected = false;
        }
    }

    mapOffsetToTimezone(offsetMinutes) {
        // Map UTC offset to common timezone
        const offsetMap = {
            '-720': 'Pacific/Midway',      // UTC-12
            '-660': 'Pacific/Honolulu',    // UTC-11
            '-600': 'Pacific/Marquesas',   // UTC-10
            '-540': 'America/Anchorage',   // UTC-9
            '-480': 'America/Los_Angeles', // UTC-8
            '-420': 'America/Denver',      // UTC-7
            '-360': 'America/Chicago',     // UTC-6
            '-300': 'America/New_York',    // UTC-5
            '-240': 'America/Caracas',     // UTC-4
            '-180': 'America/Argentina/Buenos_Aires', // UTC-3
            '-120': 'Atlantic/South_Georgia', // UTC-2
            '-60': 'Atlantic/Azores',      // UTC-1
            '0': 'UTC',                    // UTC+0
            '60': 'Europe/London',         // UTC+1
            '120': 'Europe/Paris',         // UTC+2
            '180': 'Europe/Moscow',        // UTC+3
            '240': 'Asia/Dubai',           // UTC+4
            '300': 'Asia/Karachi',         // UTC+5
            '360': 'Asia/Dhaka',           // UTC+6
            '420': 'Asia/Bangkok',         // UTC+7
            '480': 'Asia/Shanghai',        // UTC+8
            '540': 'Asia/Tokyo',           // UTC+9
            '600': 'Australia/Sydney',     // UTC+10
            '660': 'Pacific/Noumea',       // UTC+11
            '720': 'Pacific/Auckland',     // UTC+12
        };
        
        return offsetMap[offsetMinutes.toString()] || 'UTC';
    }

    async sendToServer() {
        if (!this.detected || !this.timezone) {
            return;
        }

        // Check if user is authenticated before trying to save timezone
        if (!window.userAuthenticated) {
            localStorage.setItem('user_timezone', this.timezone);
            localStorage.setItem('timezone_offset', this.offset.toString());
            return;
        }

        try {
            const response = await fetch('/api/timezone/set/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken(),
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    timezone: this.timezone,
                    offset: this.offset,
                    auto_detected: true
                }),
                credentials: 'same-origin'
            });

            if (response.ok) {
                const data = await response.json();
                
                // Store in localStorage for future use
                localStorage.setItem('user_timezone', this.timezone);
                localStorage.setItem('timezone_offset', this.offset.toString());
                
            } else if (response.status === 404) {
                localStorage.setItem('user_timezone', this.timezone);
                localStorage.setItem('timezone_offset', this.offset.toString());
            } else {
                // Still store locally as fallback
                localStorage.setItem('user_timezone', this.timezone);
                localStorage.setItem('timezone_offset', this.offset.toString());
            }
            
        } catch (error) {
            // Store locally as fallback
            localStorage.setItem('user_timezone', this.timezone);
            localStorage.setItem('timezone_offset', this.offset.toString());
        }
    }

    getCSRFToken() {
        const token = document.querySelector('[name=csrfmiddlewaretoken]');
        return token ? token.value : '';
    }

    setupPeriodicSync() {
        // Sync timezone every 30 minutes in case user travels
        setInterval(() => {
            this.detectTimezone();
        }, 30 * 60 * 1000); // 30 minutes
    }

    getTimezoneInfo() {
        return {
            timezone: this.timezone,
            offset: this.offset,
            detected: this.detected,
            currentTime: new Date().toISOString(),
            localTime: new Date().toString()
        };
    }

    // Utility methods for time conversion
    convertToUserTime(utcString) {
        if (!utcString) return null;
        
        const utcDate = new Date(utcString);
        return utcDate.toLocaleString('en-US', {
            timeZone: this.timezone,
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        });
    }

    formatTimeForUser(date, options = {}) {
        const defaultOptions = {
            timeZone: this.timezone,
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        };
        
        const formatOptions = { ...defaultOptions, ...options };
        return new Date(date).toLocaleString('en-US', formatOptions);
    }

    getTimeDifference() {
        // Get difference between local time and UTC
        const now = new Date();
        const utc = new Date(now.getTime() + (now.getTimezoneOffset() * 60000));
        return (now.getTime() - utc.getTime()) / 1000; // seconds
    }
}

// Global timezone detector instance
window.timezoneDetector = new TimezoneDetector();

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = TimezoneDetector;
}
