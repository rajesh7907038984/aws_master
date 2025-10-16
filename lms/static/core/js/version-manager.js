/**
 * Version Manager - Handles application version information
 */
(function() {
    'use strict';
    
    const VersionManager = {
        version: '1.0.0',
        build: Date.now(),
        
        init: function() {
        },
        
        getVersion: function() {
            return this.version;
        },
        
        getBuild: function() {
            return this.build;
        }
    };
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            VersionManager.init();
        });
    } else {
        VersionManager.init();
    }
    
    // Export to global scope
    window.VersionManager = VersionManager;
})();
