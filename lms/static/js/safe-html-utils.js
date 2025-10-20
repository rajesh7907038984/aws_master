/**
 * Safe HTML Utilities for LMS
 * Provides XSS-safe HTML manipulation functions
 */

(function() {
    'use strict';

    // Global SafeHTMLUtils namespace
    window.SafeHTMLUtils = {
        
        /**
         * Safely set innerHTML with XSS protection
         * @param {HTMLElement} element - Target element
         * @param {string} html - HTML content to set
         */
        setSafeInnerHTML: function(element, html) {
            if (!element || !html) return;
            
            // Basic XSS protection - remove script tags and dangerous attributes
            const sanitized = this.sanitizeHTML(html);
            element.innerHTML = sanitized;
        },
        
        /**
         * Sanitize HTML to prevent XSS attacks
         * @param {string} html - HTML to sanitize
         * @returns {string} Sanitized HTML
         */
        sanitizeHTML: function(html) {
            if (!html) return '';
            
            // Create a temporary div to parse HTML
            const temp = document.createElement('div');
            temp.innerHTML = html;
            
            // Remove script tags and dangerous attributes
            const scripts = temp.querySelectorAll('script');
            scripts.forEach(script => script.remove());
            
            // Remove dangerous attributes
            const dangerousAttrs = ['onload', 'onerror', 'onclick', 'onmouseover', 'onfocus', 'onblur'];
            const allElements = temp.querySelectorAll('*');
            
            allElements.forEach(el => {
                dangerousAttrs.forEach(attr => {
                    if (el.hasAttribute(attr)) {
                        el.removeAttribute(attr);
                    }
                });
                
                // Remove javascript: protocols from href and src
                if (el.tagName === 'A' && el.href && el.href.startsWith('javascript:')) {
                    el.removeAttribute('href');
                }
                if (el.src && el.src.startsWith('javascript:')) {
                    el.removeAttribute('src');
                }
            });
            
            return temp.innerHTML;
        },
        
        /**
         * Safely create HTML element from string
         * @param {string} htmlString - HTML string
         * @returns {HTMLElement} Safe HTML element
         */
        createSafeElement: function(htmlString) {
            const temp = document.createElement('div');
            this.setSafeInnerHTML(temp, htmlString);
            return temp.firstElementChild || temp;
        },
        
        /**
         * Escape HTML entities
         * @param {string} text - Text to escape
         * @returns {string} Escaped text
         */
        escapeHTML: function(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        },
        
        /**
         * Safely set text content (preferred over innerHTML)
         * @param {HTMLElement} element - Target element
         * @param {string} text - Text content to set
         */
        setSafeTextContent: function(element, text) {
            if (!element) return;
            element.textContent = text;
        }
    };

    // Initialize on DOM ready
    document.addEventListener('DOMContentLoaded', function() {
        // Debug logging removed for production
    });

})();