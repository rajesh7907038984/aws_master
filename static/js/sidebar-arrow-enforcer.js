/**
 * Sidebar Arrow Icon Enforcer
 * Ensures all submenu arrow icons are visible and properly styled
 */

(function() {
    'use strict';

    // Configuration
    const CONFIG = {
        selectors: {
            sidebar: '#sidebar',
            mobileMenu: '#nexsy-mobile-menu',
            submenuButtons: '.menu-item.has-submenu, [data-submenu]',
            arrowIcons: '.arrow-icon'
        },
        styles: {
            display: 'inline-block',
            visibility: 'visible',
            opacity: '1',
            color: 'white',
            stroke: 'white',
            fill: 'none',
            position: 'absolute',
            right: '1rem',
            width: '0.75rem',
            height: '0.75rem',
            zIndex: '10',
            transition: 'transform 0.3s ease'
        }
    };

    /**
     * Create arrow icon SVG element
     */
    function createArrowIcon() {
        const svg = document.createElement('svg');
        svg.className = 'arrow-icon';
        svg.setAttribute('fill', 'none');
        svg.setAttribute('stroke', 'currentColor');
        svg.setAttribute('viewBox', '0 0 24 24');
        svg.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>';
        return svg;
    }

    /**
     * Apply styles to arrow icon
     */
    function styleArrowIcon(arrow) {
        if (!arrow) return;
        
        Object.keys(CONFIG.styles).forEach(property => {
            arrow.style[property] = CONFIG.styles[property];
        });
        
        // Ensure class is present
        arrow.classList.add('arrow-icon');
    }

    /**
     * Ensure arrow icon exists and is visible
     */
    function ensureArrowIcon(button) {
        if (!button) return;
        
        let arrow = button.querySelector('.arrow-icon');
        
        // Create arrow if it doesn't exist
        if (!arrow) {
            arrow = createArrowIcon();
            button.appendChild(arrow);
        }
        
        // Style the arrow
        styleArrowIcon(arrow);
        
        return arrow;
    }

    /**
     * Process all submenu buttons in a container
     */
    function processSubmenuButtons(container) {
        if (!container) return;
        
        const buttons = container.querySelectorAll(CONFIG.selectors.submenuButtons);
        buttons.forEach(button => {
            ensureArrowIcon(button);
        });
    }

    /**
     * Main enforcement function
     */
    function enforceArrowIcons() {
        console.log('Enforcing sidebar arrow icons...');
        
        // Process sidebar
        const sidebar = document.querySelector(CONFIG.selectors.sidebar);
        if (sidebar) {
            processSubmenuButtons(sidebar);
        }
        
        // Process mobile menu
        const mobileMenu = document.querySelector(CONFIG.selectors.mobileMenu);
        if (mobileMenu) {
            processSubmenuButtons(mobileMenu);
        }
        
        // Process any dynamically loaded content
        const allContainers = document.querySelectorAll('#sidebar, #nexsy-mobile-menu');
        allContainers.forEach(container => {
            processSubmenuButtons(container);
        });
        
        console.log('Arrow icon enforcement completed');
    }

    /**
     * Initialize the enforcer
     */
    function init() {
        // Run immediately if DOM is ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', enforceArrowIcons);
        } else {
            enforceArrowIcons();
        }
        
        // Run on window load as fallback
        window.addEventListener('load', enforceArrowIcons);
        
        // Run when sidebar content changes
        const observer = new MutationObserver(function(mutations) {
            let shouldEnforce = false;
            mutations.forEach(function(mutation) {
                if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                    // Check if any added nodes contain submenu buttons
                    mutation.addedNodes.forEach(function(node) {
                        if (node.nodeType === 1) { // Element node
                            if (node.matches && node.matches(CONFIG.selectors.submenuButtons)) {
                                shouldEnforce = true;
                            } else if (node.querySelector && node.querySelector(CONFIG.selectors.submenuButtons)) {
                                shouldEnforce = true;
                            }
                        }
                    });
                }
            });
            
            if (shouldEnforce) {
                setTimeout(enforceArrowIcons, 100);
            }
        });
        
        // Observe sidebar and mobile menu for changes
        const sidebar = document.querySelector(CONFIG.selectors.sidebar);
        const mobileMenu = document.querySelector(CONFIG.selectors.mobileMenu);
        
        if (sidebar) {
            observer.observe(sidebar, { childList: true, subtree: true });
        }
        
        if (mobileMenu) {
            observer.observe(mobileMenu, { childList: true, subtree: true });
        }
    }

    // Public API
    window.SidebarArrowEnforcer = {
        enforce: enforceArrowIcons,
        init: init
    };

    // Auto-initialize
    init();

})();
