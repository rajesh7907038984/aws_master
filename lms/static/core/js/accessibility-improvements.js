/**
 * Accessibility Improvements for LMS
 * Enhances ARIA support and keyboard navigation
 */

(function() {
    'use strict';

    // Initialize accessibility improvements when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAccessibility);
    } else {
        initAccessibility();
    }

    function initAccessibility() {
        enhanceFormAccessibility();
        improveNavigationAccessibility();
        addKeyboardSupport();
        enhanceModalAccessibility();
        improveTableAccessibility();
        addSkipLinks();
        announceDynamicContent();
    }

    /**
     * Enhance form accessibility
     */
    function enhanceFormAccessibility() {
        // Associate labels with form controls
        const formControls = document.querySelectorAll('input, select, textarea');
        formControls.forEach(control => {
            const id = control.id || generateId('form-control');
            control.id = id;

            // Find associated label
            let label = document.querySelector(`label[for="${id}"]`);
            if (!label) {
                label = control.closest('.form-group, .field-wrapper')?.querySelector('label');
                if (label) {
                    label.setAttribute('for', id);
                }
            }

            // Add ARIA attributes
            if (!control.getAttribute('aria-describedby')) {
                const helpText = control.closest('.form-group, .field-wrapper')?.querySelector('.form-help, .field-help');
                if (helpText) {
                    const helpId = helpText.id || generateId('help-text');
                    helpText.id = helpId;
                    control.setAttribute('aria-describedby', helpId);
                }
            }

            // Mark required fields
            if (control.required && !control.getAttribute('aria-required')) {
                control.setAttribute('aria-required', 'true');
            }

            // Handle validation states
            if (control.classList.contains('is-invalid') || control.classList.contains('error')) {
                control.setAttribute('aria-invalid', 'true');
                const errorMessage = control.closest('.form-group, .field-wrapper')?.querySelector('.form-error, .field-error, .validation-error');
                if (errorMessage) {
                    const errorId = errorMessage.id || generateId('error-message');
                    errorMessage.id = errorId;
                    const describedBy = control.getAttribute('aria-describedby');
                    control.setAttribute('aria-describedby', describedBy ? `${describedBy} ${errorId}` : errorId);
                }
            }
        });
    }

    /**
     * Improve navigation accessibility
     */
    function improveNavigationAccessibility() {
        // Add proper ARIA roles to navigation
        const navElements = document.querySelectorAll('nav:not([role])');
        navElements.forEach(nav => {
            nav.setAttribute('role', 'navigation');
            if (!nav.getAttribute('aria-label')) {
                nav.setAttribute('aria-label', 'Main navigation');
            }
        });

        // Enhance breadcrumbs
        const breadcrumbs = document.querySelectorAll('.breadcrumb, [role="navigation"] ol');
        breadcrumbs.forEach(breadcrumb => {
            breadcrumb.setAttribute('role', 'navigation');
            breadcrumb.setAttribute('aria-label', 'Breadcrumb');
        });

        // Add current page indication
        const currentLinks = document.querySelectorAll('.nav-link.active, .breadcrumb-item.active a, .current');
        currentLinks.forEach(link => {
            link.setAttribute('aria-current', 'page');
        });
    }

    /**
     * Add keyboard navigation support
     */
    function addKeyboardSupport() {
        // Tab navigation for custom interactive elements
        const interactiveElements = document.querySelectorAll('[onclick]:not(button):not(a):not([tabindex])');
        interactiveElements.forEach(element => {
            element.setAttribute('tabindex', '0');
            element.setAttribute('role', 'button');
            
            element.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    element.click();
                }
            });
        });

        // Escape key to close modals and dropdowns
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                // Close modals
                const openModals = document.querySelectorAll('.modal.show, .modal.open, [role="dialog"][aria-hidden="false"]');
                openModals.forEach(modal => {
                    const closeBtn = modal.querySelector('.modal-close, .btn-close, [data-dismiss="modal"]');
                    if (closeBtn) {
                        closeBtn.click();
                    }
                });

                // Close dropdowns
                const openDropdowns = document.querySelectorAll('.dropdown.open, .dropdown.show');
                openDropdowns.forEach(dropdown => {
                    dropdown.classList.remove('open', 'show');
                });
            }
        });

        // Arrow key navigation for tabs
        const tabLists = document.querySelectorAll('[role="tablist"], .tab-list');
        tabLists.forEach(tabList => {
            const tabs = tabList.querySelectorAll('[role="tab"], .tab-btn');
            tabs.forEach((tab, index) => {
                tab.addEventListener('keydown', function(e) {
                    let targetIndex;
                    
                    switch(e.key) {
                        case 'ArrowLeft':
                        case 'ArrowUp':
                            e.preventDefault();
                            targetIndex = index > 0 ? index - 1 : tabs.length - 1;
                            break;
                        case 'ArrowRight':
                        case 'ArrowDown':
                            e.preventDefault();
                            targetIndex = index < tabs.length - 1 ? index + 1 : 0;
                            break;
                        case 'Home':
                            e.preventDefault();
                            targetIndex = 0;
                            break;
                        case 'End':
                            e.preventDefault();
                            targetIndex = tabs.length - 1;
                            break;
                    }
                    
                    if (targetIndex !== undefined) {
                        tabs[targetIndex].focus();
                        tabs[targetIndex].click();
                    }
                });
            });
        });
    }

    /**
     * Enhance modal accessibility
     */
    function enhanceModalAccessibility() {
        const modals = document.querySelectorAll('.modal, [role="dialog"]');
        modals.forEach(modal => {
            // Ensure proper ARIA attributes
            if (!modal.getAttribute('role')) {
                modal.setAttribute('role', 'dialog');
            }
            if (!modal.getAttribute('aria-modal')) {
                modal.setAttribute('aria-modal', 'true');
            }
            
            // Add aria-labelledby if there's a title
            const title = modal.querySelector('.modal-title, h1, h2, h3');
            if (title && !modal.getAttribute('aria-labelledby')) {
                const titleId = title.id || generateId('modal-title');
                title.id = titleId;
                modal.setAttribute('aria-labelledby', titleId);
            }

            // Focus management
            const focusableElements = modal.querySelectorAll(
                'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
            );

            if (focusableElements.length > 0) {
                // Focus first element when modal opens
                const observer = new MutationObserver(function(mutations) {
                    mutations.forEach(function(mutation) {
                        if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                            if (modal.classList.contains('show') || modal.classList.contains('open')) {
                                setTimeout(() => focusableElements[0].focus(), 100);
                            }
                        }
                    });
                });
                observer.observe(modal, { attributes: true });

                // Trap focus within modal
                modal.addEventListener('keydown', function(e) {
                    if (e.key === 'Tab') {
                        const firstFocusable = focusableElements[0];
                        const lastFocusable = focusableElements[focusableElements.length - 1];

                        if (e.shiftKey) {
                            if (document.activeElement === firstFocusable) {
                                e.preventDefault();
                                lastFocusable.focus();
                            }
                        } else {
                            if (document.activeElement === lastFocusable) {
                                e.preventDefault();
                                firstFocusable.focus();
                            }
                        }
                    }
                });
            }
        });
    }

    /**
     * Improve table accessibility
     */
    function improveTableAccessibility() {
        const tables = document.querySelectorAll('table');
        tables.forEach(table => {
            // Add table role if not present
            if (!table.getAttribute('role')) {
                table.setAttribute('role', 'table');
            }

            // Add caption if missing but title exists
            if (!table.querySelector('caption')) {
                const title = table.closest('.table-container, .table-wrapper')?.querySelector('h1, h2, h3, h4, h5, h6');
                if (title) {
                    const caption = document.createElement('caption');
                    caption.textContent = title.textContent;
                    caption.className = 'sr-only'; // Hide visually but keep for screen readers
                    table.insertBefore(caption, table.firstChild);
                }
            }

            // Ensure proper header associations
            const headers = table.querySelectorAll('th');
            headers.forEach((header, index) => {
                if (!header.getAttribute('scope')) {
                    header.setAttribute('scope', header.closest('thead') ? 'col' : 'row');
                }
                
                if (!header.id) {
                    header.id = generateId('table-header');
                }
            });

            // Add sortable indicators
            const sortableHeaders = table.querySelectorAll('th[data-sort], th.sortable');
            sortableHeaders.forEach(header => {
                header.setAttribute('role', 'columnheader');
                header.setAttribute('tabindex', '0');
                
                if (!header.getAttribute('aria-sort')) {
                    header.setAttribute('aria-sort', 'none');
                }
                
                // Add keyboard support for sorting
                header.addEventListener('keydown', function(e) {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        header.click();
                    }
                });
            });
        });
    }

    /**
     * Add skip links for navigation
     */
    function addSkipLinks() {
        const mainContent = document.querySelector('main, #main, .main-content');
        if (mainContent && !document.querySelector('.skip-link')) {
            const skipLink = document.createElement('a');
            skipLink.href = '#main-content';
            skipLink.className = 'skip-link';
            skipLink.textContent = 'Skip to main content';
            
            if (!mainContent.id) {
                mainContent.id = 'main-content';
            }
            
            document.body.insertBefore(skipLink, document.body.firstChild);
        }
    }

    /**
     * Announce dynamic content changes
     */
    function announceDynamicContent() {
        // Create live region for announcements
        const liveRegion = document.createElement('div');
        liveRegion.id = 'live-region';
        liveRegion.setAttribute('aria-live', 'polite');
        liveRegion.setAttribute('aria-atomic', 'true');
        liveRegion.style.position = 'absolute';
        liveRegion.style.left = '-10000px';
        liveRegion.style.width = '1px';
        liveRegion.style.height = '1px';
        liveRegion.style.overflow = 'hidden';
        document.body.appendChild(liveRegion);

        // Watch for success/error messages
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                mutation.addedNodes.forEach(function(node) {
                    if (node.nodeType === 1) { // Element node
                        const messages = node.matches && node.matches('.alert, .message, .notification, .toast') 
                            ? [node] 
                            : node.querySelectorAll('.alert, .message, .notification, .toast');
                        
                        messages.forEach(message => {
                            const text = message.textContent.trim();
                            if (text) {
                                setTimeout(() => {
                                    liveRegion.textContent = text;
                                    setTimeout(() => liveRegion.textContent = '', 1000);
                                }, 100);
                            }
                        });
                    }
                });
            });
        });
        
        observer.observe(document.body, { childList: true, subtree: true });
    }

    /**
     * Generate unique ID
     */
    function generateId(prefix = 'element') {
        return `${prefix}-${Math.random().toString(36).substr(2, 9)}`;
    }

    // Expose function to manually announce content
    window.announceToScreenReader = function(message) {
        const liveRegion = document.getElementById('live-region');
        if (liveRegion) {
            liveRegion.textContent = message;
            setTimeout(() => liveRegion.textContent = '', 1000);
        }
    };

})();
