/**
 * Session Timeout Handler - Manages session expiration
 */
(function() {
    'use strict';
    
    var SessionTimeout = {
        timeoutDuration: 7 * 24 * 60 * 60 * 1000, // 7 days (matches Django settings)
        warningDuration: 60 * 60 * 1000,  // 1 hour warning
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
            var self = this;
            
            // Set warning timer
            this.warningId = setTimeout(function() {
                try {
                    self.showWarning();
                } catch (error) {
                    console.error('Error showing session warning:', error);
                }
            }, this.timeoutDuration - this.warningDuration);
            
            // Set timeout timer
            this.timeoutId = setTimeout(function() {
                try {
                    self.handleTimeout();
                } catch (error) {
                    console.error('Error handling session timeout:', error);
                    // Fallback: redirect to login
                    window.location.href = '/login/?timeout=1';
                }
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
            var self = this;
            var activities = ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart'];
            
            activities.forEach(function(activity) {
                document.addEventListener(activity, function() {
                    self.resetTimer();
                }, true);
            });
        },
        
        showWarning: function() {
            // You can implement a modal or notification here
        },
        
        handleTimeout: function() {
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
