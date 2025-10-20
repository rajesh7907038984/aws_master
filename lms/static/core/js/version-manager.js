/**
 * Version Manager for LMS
 * Handles file versioning and cache busting
 */

(function() {
    'use strict';

    const VersionManager = {
        version: '1.0.0',
        cacheBuster: Date.now(),
        
        init: function() {
            this.setupCacheBusting();
            this.setupVersionHeaders();
        },
        
        setupCacheBusting: function() {
            // Add cache busting to all static resources
            const links = document.querySelectorAll('link[href*="static/"]');
            links.forEach(link => {
                const href = link.getAttribute('href');
                if (href && !href.includes('?')) {
                    link.setAttribute('href', href + '?v=' + this.cacheBuster);
                }
            });
            
            const scripts = document.querySelectorAll('script[src*="static/"]');
            scripts.forEach(script => {
                const src = script.getAttribute('src');
                if (src && !src.includes('?')) {
                    script.setAttribute('src', src + '?v=' + this.cacheBuster);
                }
            });
        },
        
        setupVersionHeaders: function() {
            // Add version header to all fetch requests
            const originalFetch = window.fetch;
            window.fetch = function(url, options = {}) {
                options.headers = options.headers || {};
                options.headers['X-LMS-Version'] = VersionManager.version;
                return originalFetch(url, options);
            };
        },
        
        getVersion: function() {
            return this.version;
        },
        
        getCacheBuster: function() {
            return this.cacheBuster;
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