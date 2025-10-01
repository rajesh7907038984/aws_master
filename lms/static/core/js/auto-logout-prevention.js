/**
 * Auto Logout Prevention - Keeps user session active
 */
(function() {
    'use strict';
    
    const AutoLogoutPrevention = {
        pingInterval: 15 * 60 * 1000, // 15 minutes
        warningTime: 5 * 60 * 1000,  // 5 minutes before logout
        intervalId: null,
        warningShown: false,
        
        init: function() {
            this.startPinging();
            this.setupUserActivityTracking();
        },
        
        startPinging: function() {
            const self = this;
            this.intervalId = setInterval(function() {
                self.pingServer();
            }, this.pingInterval);
        },
        
        pingServer: function() {
            fetch('/users/ping/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                credentials: 'same-origin'
            }).catch(function(error) {
                console.warn('Session ping failed:', error);
            });
        },
        
        setupUserActivityTracking: function() {
            const self = this;
            const activities = ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart'];
            
            activities.forEach(function(activity) {
                document.addEventListener(activity, function() {
                    self.resetWarning();
                }, true);
            });
        },
        
        resetWarning: function() {
            this.warningShown = false;
        },
        
        getCSRFToken: function() {
            const cookies = document.cookie.split(';');
            for (let cookie of cookies) {
                const [name, value] = cookie.trim().split('=');
                if (name === 'csrftoken') {
                    return value;
                }
            }
            return null;
        },
        
        destroy: function() {
            if (this.intervalId) {
                clearInterval(this.intervalId);
                this.intervalId = null;
            }
        }
    };
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            AutoLogoutPrevention.init();
        });
    } else {
        AutoLogoutPrevention.init();
    }
    
    // Export to global scope
    window.AutoLogoutPrevention = AutoLogoutPrevention;
})();
