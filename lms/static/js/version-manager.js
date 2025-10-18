
// Console fallback for older browsers
if (typeof console === 'undefined') {
    window.console = {
        log: function() {},
        error: function() {},
        warn: function() {},
        info: function() {}
    };
}

// Browser compatibility checks
if (typeof document === 'undefined') {
    console.warn('Document object not available');
}

if (typeof window === 'undefined') {
    console.warn('Window object not available');
}

/**
 * LMS Version Manager
 * Displays version information and handles version-related functionality
 */

(function() {
    'use strict';
    
    const LMS_VERSION = '1.0.0';
    const BUILD_NUMBER = Date.now();
    
    
    // Export version info
    window.LMSVersion = {
        version: LMS_VERSION,
        build: BUILD_NUMBER,
        getVersionString: function() {
            return this.version + ' (Build: ' + this.build + ')';
        }
    };
    
})();
