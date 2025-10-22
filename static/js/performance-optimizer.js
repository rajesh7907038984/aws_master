/**
 * Performance Optimizer for LMS
 * Provides optimized DOM manipulation and performance improvements
 */

(function() {
    'use strict';

    // Performance optimization utilities
    window.LMSPerformance = {
        
        // Debounce function to limit function calls
        debounce: function(func, wait, immediate) {
            let timeout;
            return function executedFunction() {
                const context = this;
                const args = arguments;
                const later = function() {
                    timeout = null;
                    if (!immediate) func.apply(context, args);
                };
                const callNow = immediate && !timeout;
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
                if (callNow) func.apply(context, args);
            };
        },

        // Throttle function to limit function calls
        throttle: function(func, limit) {
            let inThrottle;
            return function() {
                const args = arguments;
                const context = this;
                if (!inThrottle) {
                    func.apply(context, args);
                    inThrottle = true;
                    setTimeout(() => inThrottle = false, limit);
                }
            };
        },

        // Optimized DOM query with caching
        queryCache: new Map(),
        
        query: function(selector, context = document) {
            const cacheKey = `${selector}_${context === document ? 'document' : context.tagName}`;
            
            if (this.queryCache.has(cacheKey)) {
                return this.queryCache.get(cacheKey);
            }
            
            const elements = context.querySelectorAll(selector);
            this.queryCache.set(cacheKey, elements);
            
            // Clear cache after 5 seconds
            setTimeout(() => {
                this.queryCache.delete(cacheKey);
            }, 5000);
            
            return elements;
        },

        // Batch DOM updates to prevent reflow
        batchDOMUpdates: function(updates) {
            // Use DocumentFragment for batch updates
            const fragment = document.createDocumentFragment();
            
            updates.forEach(update => {
                if (typeof update === 'function') {
                    update(fragment);
                }
            });
            
            return fragment;
        },

        // Optimized event delegation
        delegate: function(container, event, selector, handler) {
            if (!container._delegatedEvents) {
                container._delegatedEvents = new Map();
            }
            
            const key = `${event}_${selector}`;
            if (container._delegatedEvents.has(key)) {
                return; // Already delegated
            }
            
            const delegatedHandler = function(e) {
                const target = e.target.closest(selector);
                if (target) {
                    handler.call(target, e);
                }
            };
            
            container.addEventListener(event, delegatedHandler);
            container._delegatedEvents.set(key, delegatedHandler);
        },

        // Remove event delegation
        undelegate: function(container, event, selector) {
            if (!container._delegatedEvents) return;
            
            const key = `${event}_${selector}`;
            const handler = container._delegatedEvents.get(key);
            if (handler) {
                container.removeEventListener(event, handler);
                container._delegatedEvents.delete(key);
            }
        },

        // Optimized scroll handler
        optimizedScroll: function(handler, delay = 16) {
            let ticking = false;
            
            return function() {
                if (!ticking) {
                    requestAnimationFrame(() => {
                        handler();
                        ticking = false;
                    });
                    ticking = true;
                }
            };
        },

        // Lazy loading for images
        lazyLoadImages: function() {
            const images = document.querySelectorAll('img[data-src]');
            const imageObserver = new IntersectionObserver((entries, observer) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const img = entry.target;
                        img.src = img.dataset.src;
                        img.removeAttribute('data-src');
                        observer.unobserve(img);
                    }
                });
            });
            
            images.forEach(img => imageObserver.observe(img));
        },

        // Optimized form validation
        validateForm: function(form) {
            const errors = [];
            const inputs = form.querySelectorAll('input, textarea, select');
            
            inputs.forEach(input => {
                // Remove previous error styling
                input.classList.remove('error');
                
                // Validate required fields
                if (input.hasAttribute('required') && !input.value.trim()) {
                    errors.push(`${input.name || input.id} is required`);
                    input.classList.add('error');
                }
                
                // Validate email fields
                if (input.type === 'email' && input.value) {
                    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
                    if (!emailRegex.test(input.value)) {
                        errors.push(`${input.name || input.id} must be a valid email`);
                        input.classList.add('error');
                    }
                }
                
                // Validate number fields
                if (input.type === 'number' && input.value) {
                    if (isNaN(input.value)) {
                        errors.push(`${input.name || input.id} must be a valid number`);
                        input.classList.add('error');
                    }
                }
            });
            
            return errors;
        },

        // Memory cleanup
        cleanup: function() {
            // Clear query cache
            this.queryCache.clear();
            
            // Remove all delegated events
            document.querySelectorAll('*').forEach(element => {
                if (element._delegatedEvents) {
                    element._delegatedEvents.clear();
                }
            });
        }
    };

    // Initialize performance optimizations
    document.addEventListener('DOMContentLoaded', function() {
        // Lazy load images
        window.LMSPerformance.lazyLoadImages();
        
        // Optimize scroll events
        const scrollHandler = window.LMSPerformance.optimizedScroll(() => {
            // Handle scroll events here
        });
        window.addEventListener('scroll', scrollHandler);
        
        // Cleanup on page unload
        window.addEventListener('beforeunload', function() {
            window.LMSPerformance.cleanup();
        });
    });

})();
