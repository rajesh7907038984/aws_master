/**
 * Session Timeout Handler - Manages session expiration
 */
(function() {
    'use strict';
    
    const SessionTimeout = {
        timeoutDuration: 30 * 60 * 1000, // 30 minutes
        warningDuration: 5 * 60 * 1000,  // 5 minutes warning
        timeoutId: null,
        warningId: null,
        
        init: function() {
            this.resetTimer();
            this.setupActivityListeners();
        },
        
        resetTimer: function() {
            this.clearTimers();
            this.startTimer();
        },
        
        startTimer: function() {
            const self = this;
            
            // Set warning timer
            this.warningId = setTimeout(function() {
                self.showWarning();
            }, this.timeoutDuration - this.warningDuration);
            
            // Set timeout timer
            this.timeoutId = setTimeout(function() {
                self.handleTimeout();
            }, this.timeoutDuration);
        },
        
        clearTimers: function() {
            if (this.timeoutId) {
                clearTimeout(this.timeoutId);
                this.timeoutId = null;
            }
            if (this.warningId) {
                clearTimeout(this.warningId);
                this.warningId = null;
            }
        },
        
        setupActivityListeners: function() {
            const self = this;
            const activities = ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart'];
            
            activities.forEach(function(activity) {
                document.addEventListener(activity, function() {
                    self.resetTimer();
                }, true);
            });
        },
        
        showWarning: function() {
            console.log('Session will expire soon. Please save your work.');
            // You can implement a modal or notification here
        },
        
        handleTimeout: function() {
            console.log('Session expired. Redirecting to login...');
            window.location.href = '/login/?timeout=1';
        }
    };
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            SessionTimeout.init();
        });
    } else {
        SessionTimeout.init();
    }
    
    // Export to global scope
    window.SessionTimeout = SessionTimeout;
})();
