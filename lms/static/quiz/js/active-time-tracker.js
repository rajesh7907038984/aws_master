/**
 * Active Time Tracker for Quiz Attempts
 * Provides 100% accurate tracking of time spent on quiz pages
 */

class ActiveTimeTracker {
    constructor(attemptId, options = {}) {
        this.attemptId = attemptId;
        this.options = {
            pingInterval: options.pingInterval || 10000, // Send ping every 10 seconds
            idleThreshold: options.idleThreshold || 30000, // Consider idle after 30 seconds
            activityEvents: options.activityEvents || ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart', 'click'],
            ...options
        };
        
        // State tracking
        this.isActive = false;
        this.isPageVisible = true;
        this.lastActivity = Date.now();
        this.sessionStartTime = null;
        this.totalActiveTime = 0;
        
        // Timers
        this.pingTimer = null;
        this.idleCheckTimer = null;
        
        // Bindings
        this.handleActivity = this.handleActivity.bind(this);
        this.handleVisibilityChange = this.handleVisibilityChange.bind(this);
        this.handlePageFocus = this.handlePageFocus.bind(this);
        this.handlePageBlur = this.handlePageBlur.bind(this);
        this.handleBeforeUnload = this.handleBeforeUnload.bind(this);
        
        this.init();
    }
    
    init() {
        console.log('ActiveTimeTracker: Initializing for attempt', this.attemptId);
        
        // Set up activity event listeners
        this.options.activityEvents.forEach(event => {
            document.addEventListener(event, this.handleActivity, { passive: true });
        });
        
        // Set up page visibility tracking
        document.addEventListener('visibilitychange', this.handleVisibilityChange);
        
        // Set up focus/blur tracking
        window.addEventListener('focus', this.handlePageFocus);
        window.addEventListener('blur', this.handlePageBlur);
        
        // Handle page unload
        window.addEventListener('beforeunload', this.handleBeforeUnload);
        window.addEventListener('unload', this.handleBeforeUnload);
        
        // Start tracking
        this.startSession();
        this.startPingTimer();
        this.startIdleCheckTimer();
        
        // Send initial focus event
        this.sendFocusUpdate(true);
    }
    
    handleActivity(event) {
        this.lastActivity = Date.now();
        
        if (!this.isActive && this.isPageVisible) {
            this.startSession();
        }
    }
    
    handleVisibilityChange() {
        this.isPageVisible = !document.hidden;
        
        if (this.isPageVisible) {
            console.log('ActiveTimeTracker: Page became visible');
            this.handlePageFocus();
        } else {
            console.log('ActiveTimeTracker: Page became hidden');
            this.handlePageBlur();
        }
    }
    
    handlePageFocus() {
        console.log('ActiveTimeTracker: Page gained focus');
        this.isPageVisible = true;
        this.startSession();
        this.sendFocusUpdate(true);
    }
    
    handlePageBlur() {
        console.log('ActiveTimeTracker: Page lost focus');
        this.endSession();
        this.sendFocusUpdate(false);
    }
    
    handleBeforeUnload() {
        console.log('ActiveTimeTracker: Page unloading, sending final update');
        this.endSession();
        this.sendPingUpdate(true); // Send synchronous final update
    }
    
    startSession() {
        if (!this.isActive && this.isPageVisible) {
            this.isActive = true;
            this.sessionStartTime = Date.now();
            this.lastActivity = Date.now();
            console.log('ActiveTimeTracker: Session started');
        }
    }
    
    endSession() {
        if (this.isActive && this.sessionStartTime) {
            const sessionDuration = Date.now() - this.sessionStartTime;
            this.totalActiveTime += sessionDuration;
            this.isActive = false;
            this.sessionStartTime = null;
            console.log('ActiveTimeTracker: Session ended, duration:', sessionDuration / 1000, 'seconds');
            
            // Send ping with accumulated time
            this.sendPingUpdate();
        }
    }
    
    startPingTimer() {
        this.pingTimer = setInterval(() => {
            if (this.isActive) {
                this.sendPingUpdate();
            }
        }, this.options.pingInterval);
    }
    
    startIdleCheckTimer() {
        this.idleCheckTimer = setInterval(() => {
            const timeSinceActivity = Date.now() - this.lastActivity;
            
            if (this.isActive && timeSinceActivity > this.options.idleThreshold) {
                console.log('ActiveTimeTracker: User idle, ending session');
                this.endSession();
            }
        }, 5000); // Check every 5 seconds
    }
    
    sendPingUpdate(synchronous = false) {
        let additionalSeconds = 0;
        
        if (this.isActive && this.sessionStartTime) {
            const currentSessionTime = Date.now() - this.sessionStartTime;
            additionalSeconds = Math.floor((this.totalActiveTime + currentSessionTime) / 1000);
            
            // Reset accumulated time since we're sending it
            this.totalActiveTime = 0;
            this.sessionStartTime = Date.now();
        }
        
        const data = {
            action: 'ping',
            additional_seconds: additionalSeconds
        };
        
        this.sendRequest(data, synchronous);
    }
    
    sendFocusUpdate(focused) {
        const data = {
            action: focused ? 'focus' : 'blur'
        };
        
        this.sendRequest(data);
    }
    
    sendRequest(data, synchronous = false) {
        const url = `/quiz/attempt/${this.attemptId}/update-active-time/`;
        
        const requestOptions = {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken()
            },
            body: JSON.stringify(data)
        };
        
        if (synchronous) {
            // Use sendBeacon for synchronous requests (more reliable on page unload)
            if ('sendBeacon' in navigator) {
                const formData = new FormData();
                formData.append('data', JSON.stringify(data));
                formData.append('csrfmiddlewaretoken', this.getCSRFToken());
                
                navigator.sendBeacon(url, formData);
                return;
            }
            
            // Fallback to synchronous fetch
            requestOptions.keepalive = true;
        }
        
        fetch(url, requestOptions)
            .then(response => {
                if (!response.ok) {
                    if (response.status === 401) {
                        console.warn('ActiveTimeTracker: Session expired, stopping tracker');
                        this.destroy();
                        // Optionally redirect to login or refresh page
                        if (this.options.onSessionExpired) {
                            this.options.onSessionExpired();
                        }
                        return;
                    }
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(result => {
                if (result && result.success) {
                    console.log('ActiveTimeTracker: Update successful', result);
                    
                    // Update UI if callback provided
                    if (this.options.onUpdate) {
                        this.options.onUpdate(result);
                    }
                } else if (result) {
                    console.error('ActiveTimeTracker: Update failed', result.error);
                    
                    // Handle specific error types
                    if (result.error_type === 'authentication_required') {
                        console.warn('ActiveTimeTracker: Authentication required, stopping tracker');
                        this.destroy();
                        if (this.options.onSessionExpired) {
                            this.options.onSessionExpired();
                        }
                    }
                }
            })
            .catch(error => {
                console.error('ActiveTimeTracker: Request failed', error);
                
                // Stop tracker on network errors to prevent spam
                if (error.name === 'NetworkError' || error.message.includes('Failed to fetch')) {
                    console.warn('ActiveTimeTracker: Network error detected, reducing ping frequency');
                    // Reduce ping frequency on network errors
                    if (this.pingTimer) {
                        clearInterval(this.pingTimer);
                        this.pingTimer = setInterval(() => this.sendPing(), this.options.pingInterval * 2);
                    }
                }
            });
    }
    
    getCSRFToken() {
        const token = document.querySelector('[name=csrfmiddlewaretoken]');
        return token ? token.value : '';
    }
    
    getCurrentActiveTime() {
        let currentTime = this.totalActiveTime;
        
        if (this.isActive && this.sessionStartTime) {
            currentTime += Date.now() - this.sessionStartTime;
        }
        
        return Math.floor(currentTime / 1000); // Return in seconds
    }
    
    getFormattedTime(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;
        
        if (hours > 0) {
            return `${hours}h ${minutes}m ${secs}s`;
        } else if (minutes > 0) {
            return `${minutes}m ${secs}s`;
        } else {
            return `${secs}s`;
        }
    }
    
    destroy() {
        console.log('ActiveTimeTracker: Destroying tracker');
        
        // End current session
        this.endSession();
        
        // Clear timers
        if (this.pingTimer) {
            clearInterval(this.pingTimer);
        }
        if (this.idleCheckTimer) {
            clearInterval(this.idleCheckTimer);
        }
        
        // Remove event listeners
        this.options.activityEvents.forEach(event => {
            document.removeEventListener(event, this.handleActivity);
        });
        
        document.removeEventListener('visibilitychange', this.handleVisibilityChange);
        window.removeEventListener('focus', this.handlePageFocus);
        window.removeEventListener('blur', this.handlePageBlur);
        window.removeEventListener('beforeunload', this.handleBeforeUnload);
        window.removeEventListener('unload', this.handleBeforeUnload);
    }
}

// Export for global use
window.ActiveTimeTracker = ActiveTimeTracker;
