/**
 * Auto-Timezone Detector for First Login
 * Automatically detects and sets user timezone on first login
 */

class AutoTimezoneDetector {
    constructor() {
        this.timezone = null;
        this.offset = null;
        this.isDetected = false;
        this.init();
    }

    async init() {
        // Only run if user is authenticated
        if (!this.isUserAuthenticated()) {
            return;
        }

        try {
            // Check if user needs timezone detection
            const needsDetection = await this.checkTimezoneStatus();
            if (needsDetection) {
                console.log('User needs timezone detection, proceeding...');
                await this.detectAndSetTimezone();
            }
        } catch (error) {
            console.error('Error in auto-timezone detection:', error);
        }
    }

    isUserAuthenticated() {
        // Check if user is authenticated (various methods)
        return (
            window.userAuthenticated === true ||
            document.querySelector('[name=csrfmiddlewaretoken]') !== null ||
            document.body.classList.contains('authenticated') ||
            window.location.pathname.includes('/dashboard')
        );
    }

    async checkTimezoneStatus() {
        try {
            const response = await fetch('/users/api/auto-timezone/status/', {
                method: 'GET',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json'
                },
                credentials: 'same-origin'
            });

            if (response.ok) {
                const data = await response.json();
                console.log('Timezone status:', data);
                return data.needs_detection === true;
            }
            
            return false;
        } catch (error) {
            console.error('Error checking timezone status:', error);
            return false;
        }
    }

    detectDeviceTimezone() {
        try {
            // Method 1: Use Intl API (most accurate)
            this.timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
            
            // Method 2: Get UTC offset in minutes
            const now = new Date();
            this.offset = -now.getTimezoneOffset(); // Negative because getTimezoneOffset returns opposite
            
            this.isDetected = true;
            
            console.log('Detected timezone:', this.timezone);
            console.log('Detected offset:', this.offset);
            
            return true;
        } catch (error) {
            console.error('Error detecting device timezone:', error);
            return this.fallbackDetection();
        }
    }

    fallbackDetection() {
        try {
            // Fallback: use offset to guess timezone
            const now = new Date();
            this.offset = -now.getTimezoneOffset();
            
            // Map offset to common timezone
            this.timezone = this.mapOffsetToTimezone(this.offset);
            this.isDetected = true;
            
            console.log('Fallback timezone detection:', this.timezone, this.offset);
            return true;
        } catch (error) {
            console.error('Fallback timezone detection failed:', error);
            this.timezone = 'UTC';
            this.offset = 0;
            this.isDetected = false;
            return false;
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

    async detectAndSetTimezone() {
        // Step 1: Detect device timezone
        if (!this.detectDeviceTimezone()) {
            console.warn('Could not detect device timezone');
            return false;
        }

        // Step 2: Send to server
        try {
            const response = await fetch('/users/api/auto-timezone/set/', {
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
                console.log('Timezone set successfully:', data);
                
                // Store in localStorage for immediate use
                localStorage.setItem('user_timezone', this.timezone);
                localStorage.setItem('timezone_offset', this.offset.toString());
                localStorage.setItem('timezone_auto_detected', 'true');
                
                // Show notification to user
                this.showTimezoneNotification(data);
                
                return true;
            } else {
                console.error('Failed to set timezone on server:', response.status);
                return false;
            }
        } catch (error) {
            console.error('Error setting timezone on server:', error);
            // Store locally as fallback
            localStorage.setItem('user_timezone', this.timezone);
            localStorage.setItem('timezone_offset', this.offset.toString());
            localStorage.setItem('timezone_auto_detected', 'true');
            return false;
        }
    }

    showTimezoneNotification(data) {
        // Only show notification if this is the first time
        if (data.first_time) {
            const notification = document.createElement('div');
            notification.className = 'timezone-notification';
            notification.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                background: #10b981;
                color: white;
                padding: 12px 20px;
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                z-index: 10000;
                font-family: system-ui, -apple-system, sans-serif;
                font-size: 14px;
                max-width: 350px;
                opacity: 0;
                transform: translateX(100%);
                transition: all 0.3s ease;
            `;
            
            notification.innerHTML = `
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 18px;">🕐</span>
                    <div>
                        <div style="font-weight: 600;">Timezone Auto-Detected</div>
                        <div style="font-size: 12px; opacity: 0.9;">Set to: ${this.timezone}</div>
                    </div>
                    <button onclick="this.parentElement.parentElement.remove()" style="
                        background: none; 
                        border: none; 
                        color: white; 
                        font-size: 16px; 
                        cursor: pointer;
                        margin-left: auto;
                    ">×</button>
                </div>
            `;
            
            document.body.appendChild(notification);
            
            // Animate in
            setTimeout(() => {
                notification.style.opacity = '1';
                notification.style.transform = 'translateX(0)';
            }, 100);
            
            // Auto-remove after 5 seconds
            setTimeout(() => {
                if (notification.parentElement) {
                    notification.style.opacity = '0';
                    notification.style.transform = 'translateX(100%)';
                    setTimeout(() => {
                        if (notification.parentElement) {
                            notification.remove();
                        }
                    }, 300);
                }
            }, 5000);
        }
    }

    getCSRFToken() {
        const token = document.querySelector('[name=csrfmiddlewaretoken]');
        return token ? token.value : '';
    }

    // Utility methods
    getTimezoneInfo() {
        return {
            timezone: this.timezone,
            offset: this.offset,
            detected: this.isDetected,
            currentTime: new Date().toISOString(),
            localTime: new Date().toString()
        };
    }

    getCurrentTimeForUser() {
        const now = new Date();
        return now.toLocaleString('en-US', {
            timeZone: this.timezone || 'UTC',
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        });
    }
}

// Auto-initialize on DOM ready
document.addEventListener('DOMContentLoaded', function() {
    // Small delay to ensure other scripts are loaded
    setTimeout(() => {
        window.autoTimezoneDetector = new AutoTimezoneDetector();
    }, 1000);
});

// Also initialize immediately if DOM is already ready
if (document.readyState === 'complete' || document.readyState === 'interactive') {
    setTimeout(() => {
        if (!window.autoTimezoneDetector) {
            window.autoTimezoneDetector = new AutoTimezoneDetector();
        }
    }, 1000);
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = AutoTimezoneDetector;
}
