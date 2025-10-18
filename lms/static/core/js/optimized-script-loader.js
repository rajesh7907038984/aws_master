/**
 * Optimized Script Loader for LMS
 * Loads scripts efficiently with dependency management
 */

(function() {
    'use strict';

    const OptimizedScriptLoader = {
        loadedScripts: new Set(),
        loadingPromises: new Map(),
        
        init: function() {
            this.setupScriptLoading();
        },
        
        setupScriptLoading: function() {
            // Load critical scripts first
            this.loadCriticalScripts();
            
            // Load non-critical scripts after page load
            window.addEventListener('load', () => {
                this.loadNonCriticalScripts();
            });
        },
        
        loadCriticalScripts: function() {
            const criticalScripts = [
                '/static/js/csrf-token-manager.js',
                '/static/core/js/unified-csrf-handler.js'
            ];
            
            criticalScripts.forEach(script => {
                this.loadScript(script, { async: false });
            });
        },
        
        loadNonCriticalScripts: function() {
            const nonCriticalScripts = [
                '/static/js/performance-optimizer.js',
                '/static/js/unified-validation-system.js',
                '/static/core/js/version-manager.js'
            ];
            
            nonCriticalScripts.forEach(script => {
                this.loadScript(script, { async: true });
            });
        },
        
        loadScript: function(src, options = {}) {
            if (this.loadedScripts.has(src)) {
                return Promise.resolve();
            }
            
            if (this.loadingPromises.has(src)) {
                return this.loadingPromises.get(src);
            }
            
            const promise = new Promise((resolve, reject) => {
                const script = document.createElement('script');
                script.src = src;
                script.async = options.async !== false;
                script.defer = options.defer || false;
                
                script.onload = () => {
                    this.loadedScripts.add(src);
                    this.loadingPromises.delete(src);
                    resolve();
                };
                
                script.onerror = () => {
                    this.loadingPromises.delete(src);
                    reject(new Error(`Failed to load script: ${src}`));
                };
                
                document.head.appendChild(script);
            });
            
            this.loadingPromises.set(src, promise);
            return promise;
        },
        
        loadScripts: function(scripts) {
            return Promise.all(scripts.map(script => this.loadScript(script)));
        },
        
        isLoaded: function(src) {
            return this.loadedScripts.has(src);
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            OptimizedScriptLoader.init();
        });
    } else {
        OptimizedScriptLoader.init();
    }

    // Export to global scope
    window.OptimizedScriptLoader = OptimizedScriptLoader;
})();
