/**
 * Centralized Observer Manager
 * Prevents multiple MutationObservers and manages memory efficiently
 */

(function() {
    'use strict';
    
    // Global observer registry
    const observerRegistry = new Map();
    const observerCleanup = new Set();
    
    /**
     * Create or get existing observer for a target
     * @param {string} key Unique key for the observer
     * @param {Element} target Target element
     * @param {function} callback Mutation callback
     * @param {object} options Observer options
     * @returns {object|null} Observer instance or null
     */
    function getOrCreateObserver(key, target, callback, options = {}) {
        // Check if observer already exists
        if (observerRegistry.has(key)) {
            const existing = observerRegistry.get(key);
            if (existing.target === target && existing.observer) {
                return existing.observer;
            } else {
                // Clean up old observer
                cleanupObserver(key);
            }
        }
        
        // Validate target
        if (!target || target.nodeType !== 1) {
            ProductionLogger.warn('ObserverManager: Invalid target for observer', key);
            return null;
        }
        
        // Create new observer
        const observer = window.BrowserCompatibility ? 
            window.BrowserCompatibility.createObserver(callback) : 
            new MutationObserver(callback);
            
        if (!observer) {
            ProductionLogger.warn('ObserverManager: Failed to create observer for', key);
            return null;
        }
        
        try {
            observer.observe(target, {
                childList: true,
                subtree: true,
                attributes: true,
                attributeOldValue: true,
                ...options
            });
            
            // Register observer
            observerRegistry.set(key, {
                observer: observer,
                target: target,
                callback: callback,
                options: options,
                createdAt: Date.now()
            });
            
            ProductionLogger.log('ObserverManager: Created observer for', key);
            return observer;
            
        } catch (error) {
            ProductionLogger.error('ObserverManager: Failed to observe target for', key, error);
            return null;
        }
    }
    
    /**
     * Clean up specific observer
     * @param {string} key Observer key
     */
    function cleanupObserver(key) {
        if (observerRegistry.has(key)) {
            const entry = observerRegistry.get(key);
            if (entry.observer) {
                try {
                    entry.observer.disconnect();
                } catch (error) {
                    ProductionLogger.warn('ObserverManager: Error disconnecting observer', key, error);
                }
            }
            observerRegistry.delete(key);
            ProductionLogger.log('ObserverManager: Cleaned up observer for', key);
        }
    }
    
    /**
     * Clean up all observers
     */
    function cleanupAllObservers() {
        for (const key of observerRegistry.keys()) {
            cleanupObserver(key);
        }
        ProductionLogger.log('ObserverManager: Cleaned up all observers');
    }
    
    /**
     * Clean up old observers (older than specified time)
     * @param {number} maxAge Maximum age in milliseconds
     */
    function cleanupOldObservers(maxAge = 300000) { // 5 minutes default
        const now = Date.now();
        const toCleanup = [];
        
        for (const [key, entry] of observerRegistry.entries()) {
            if (now - entry.createdAt > maxAge) {
                toCleanup.push(key);
            }
        }
        
        toCleanup.forEach(key => cleanupObserver(key));
        
        if (toCleanup.length > 0) {
            ProductionLogger.log('ObserverManager: Cleaned up', toCleanup.length, 'old observers');
        }
    }
    
    /**
     * Get observer statistics
     * @returns {object} Observer statistics
     */
    function getObserverStats() {
        return {
            total: observerRegistry.size,
            keys: Array.from(observerRegistry.keys()),
            memoryUsage: observerRegistry.size * 1024 // Rough estimate
        };
    }
    
    /**
     * Enhanced observer with automatic cleanup
     * @param {string} key Unique key
     * @param {Element} target Target element
     * @param {function} callback Mutation callback
     * @param {object} options Observer options
     * @returns {object|null} Observer instance with cleanup methods
     */
    function createManagedObserver(key, target, callback, options = {}) {
        const observer = getOrCreateObserver(key, target, callback, options);
        
        if (!observer) {
            return null;
        }
        
        return {
            observer: observer,
            disconnect: function() {
                cleanupObserver(key);
            },
            reconnect: function(newTarget, newCallback, newOptions) {
                this.disconnect();
                return createManagedObserver(key, newTarget || target, newCallback || callback, newOptions || options);
            },
            isActive: function() {
                return observerRegistry.has(key);
            }
        };
    }
    
    /**
     * Debounced observer creation to prevent rapid creation/destruction
     * @param {string} key Unique key
     * @param {Element} target Target element
     * @param {function} callback Mutation callback
     * @param {object} options Observer options
     * @param {number} debounceMs Debounce time in milliseconds
     * @returns {object|null} Managed observer
     */
    function createDebouncedObserver(key, target, callback, options = {}, debounceMs = 100) {
        // Clear any existing timeout for this key
        const timeoutKey = key + '_debounce';
        if (window[timeoutKey]) {
            clearTimeout(window[timeoutKey]);
        }
        
        return new Promise((resolve) => {
            window[timeoutKey] = setTimeout(() => {
                const managedObserver = createManagedObserver(key, target, callback, options);
                resolve(managedObserver);
            }, debounceMs);
        });
    }
    
    // Auto-cleanup on page unload
    window.addEventListener('beforeunload', function() {
        cleanupAllObservers();
    });
    
    // Periodic cleanup of old observers
    setInterval(function() {
        cleanupOldObservers();
    }, 60000); // Clean up every minute
    
    // Expose global API
    window.ObserverManager = {
        create: createManagedObserver,
        createDebounced: createDebouncedObserver,
        cleanup: cleanupObserver,
        cleanupAll: cleanupAllObservers,
        stats: getObserverStats,
        registry: observerRegistry
    };
    
    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            ProductionLogger.log('✅ Observer Manager initialized');
        });
    } else {
        ProductionLogger.log('✅ Observer Manager initialized');
    }
    
})();
