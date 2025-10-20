/**
 * Sidebar Tooltip Manager
 * Handles tooltip functionality for sidebar menu items
 */

(function() {
    'use strict';

    // Configuration
    const CONFIG = {
        selectors: {
            sidebar: '#sidebar',
            mobileMenu: '#nexsy-mobile-menu',
            menuItems: '.menu-item',
            submenuItems: '.submenu .menu-item',
            mainMenuItems: '.menu-item.has-submenu, .menu-item[data-submenu]'
        },
        classes: {
            collapsed: 'collapsed',
            hidden: 'hidden',
            active: 'active'
        },
        tooltip: {
            delay: 300,
            duration: 300,
            maxWidth: 200
        }
    };

    // State management
    let state = {
        isInitialized: false,
        tooltipTimeout: null,
        currentTooltip: null
    };

    /**
     * Initialize tooltip manager
     */
    function init() {
        if (state.isInitialized) return;
        
        console.log('Initializing sidebar tooltip manager...');
        
        // Wait for DOM to be ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', init);
            return;
        }
        
        setupTooltips();
        setupEventListeners();
        
        state.isInitialized = true;
        console.log('Sidebar tooltip manager initialized');
    }

    /**
     * Setup tooltips for all menu items
     */
    function setupTooltips() {
        // Process sidebar
        const sidebar = document.querySelector(CONFIG.selectors.sidebar);
        if (sidebar) {
            processMenuItems(sidebar);
        }
        
        // Process mobile menu
        const mobileMenu = document.querySelector(CONFIG.selectors.mobileMenu);
        if (mobileMenu) {
            processMenuItems(mobileMenu);
        }
    }

    /**
     * Process menu items and ensure they have tooltips
     */
    function processMenuItems(container) {
        if (!container) return;
        
        // Get all menu items
        const menuItems = container.querySelectorAll(CONFIG.selectors.menuItems);
        
        menuItems.forEach(item => {
            ensureTooltipAttribute(item);
            setupTooltipEvents(item);
        });
    }

    /**
     * Ensure menu item has tooltip attribute
     */
    function ensureTooltipAttribute(item) {
        if (!item) return;
        
        // Check if tooltip already exists
        if (item.getAttribute('data-tooltip')) return;
        
        // Get tooltip text from menu text or fallback
        let tooltipText = '';
        
        // Try to get text from .menu-text element
        const menuText = item.querySelector('.menu-text');
        if (menuText) {
            tooltipText = menuText.textContent.trim();
        } else {
            // Fallback to item text content
            tooltipText = item.textContent.trim();
        }
        
        // Clean up tooltip text
        tooltipText = tooltipText.replace(/\s+/g, ' ').trim();
        
        // Set tooltip attribute
        if (tooltipText) {
            item.setAttribute('data-tooltip', tooltipText);
        }
    }

    /**
     * Setup tooltip events for menu item
     */
    function setupTooltipEvents(item) {
        if (!item) return;
        
        // Remove existing event listeners
        item.removeEventListener('mouseenter', handleMouseEnter);
        item.removeEventListener('mouseleave', handleMouseLeave);
        
        // Add new event listeners
        item.addEventListener('mouseenter', handleMouseEnter);
        item.addEventListener('mouseleave', handleMouseLeave);
    }

    /**
     * Handle mouse enter event
     */
    function handleMouseEnter(event) {
        const item = event.currentTarget;
        const sidebar = document.querySelector(CONFIG.selectors.sidebar);
        
        // Only show tooltips when sidebar is collapsed
        if (!sidebar || !sidebar.classList.contains(CONFIG.classes.collapsed)) {
            return;
        }
        
        // Clear any existing timeout
        if (state.tooltipTimeout) {
            clearTimeout(state.tooltipTimeout);
        }
        
        // Set tooltip timeout
        state.tooltipTimeout = setTimeout(() => {
            showTooltip(item);
        }, CONFIG.tooltip.delay);
    }

    /**
     * Handle mouse leave event
     */
    function handleMouseLeave(event) {
        const item = event.currentTarget;
        
        // Clear timeout
        if (state.tooltipTimeout) {
            clearTimeout(state.tooltipTimeout);
            state.tooltipTimeout = null;
        }
        
        // Hide tooltip
        hideTooltip(item);
    }

    /**
     * Show tooltip for menu item
     */
    function showTooltip(item) {
        if (!item) return;
        
        const tooltipText = item.getAttribute('data-tooltip');
        if (!tooltipText) return;
        
        // Hide any existing tooltip
        hideTooltip();
        
        // Create tooltip element
        const tooltip = createTooltipElement(tooltipText);
        
        // Position tooltip
        positionTooltip(tooltip, item);
        
        // Add to DOM
        document.body.appendChild(tooltip);
        
        // Store reference
        state.currentTooltip = tooltip;
        
        // Animate in
        requestAnimationFrame(() => {
            tooltip.style.opacity = '1';
            tooltip.style.transform = 'translateY(-50%) translateX(0)';
        });
    }

    /**
     * Hide tooltip
     */
    function hideTooltip(item) {
        if (state.currentTooltip) {
            const tooltip = state.currentTooltip;
            
            // Animate out
            tooltip.style.opacity = '0';
            tooltip.style.transform = 'translateY(-50%) translateX(-10px)';
            
            // Remove after animation
            setTimeout(() => {
                if (tooltip.parentNode) {
                    tooltip.parentNode.removeChild(tooltip);
                }
            }, CONFIG.tooltip.duration);
            
            state.currentTooltip = null;
        }
    }

    /**
     * Create tooltip element
     */
    function createTooltipElement(text) {
        const tooltip = document.createElement('div');
        tooltip.className = 'sidebar-tooltip';
        tooltip.textContent = text;
        
        // Apply styles
        tooltip.style.cssText = `
            position: absolute;
            background-color: var(--sidebar-bg-hover, #02071e);
            color: white;
            padding: 0.75rem 1rem;
            border-radius: 0.5rem;
            white-space: nowrap;
            z-index: 1000;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
            pointer-events: none;
            opacity: 0;
            transform: translateY(-50%) translateX(-10px);
            transition: all ${CONFIG.tooltip.duration}ms ease-in-out;
            font-size: 0.875rem;
            font-weight: 500;
            max-width: ${CONFIG.tooltip.maxWidth}px;
            word-wrap: break-word;
            line-height: 1.25rem;
        `;
        
        return tooltip;
    }

    /**
     * Position tooltip relative to menu item
     */
    function positionTooltip(tooltip, item) {
        const itemRect = item.getBoundingClientRect();
        const sidebar = document.querySelector(CONFIG.selectors.sidebar);
        
        if (!sidebar) return;
        
        const sidebarRect = sidebar.getBoundingClientRect();
        
        // Position tooltip to the right of the sidebar
        const left = sidebarRect.right + 12; // 12px gap
        const top = itemRect.top + (itemRect.height / 2);
        
        tooltip.style.left = `${left}px`;
        tooltip.style.top = `${top}px`;
    }

    /**
     * Setup event listeners
     */
    function setupEventListeners() {
        // Listen for sidebar collapse/expand
        const sidebar = document.querySelector(CONFIG.selectors.sidebar);
        if (sidebar) {
            const observer = new MutationObserver(function(mutations) {
                mutations.forEach(function(mutation) {
                    if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                        // Sidebar class changed, hide any visible tooltips
                        if (!sidebar.classList.contains(CONFIG.classes.collapsed)) {
                            hideTooltip();
                        }
                    }
                });
            });
            
            observer.observe(sidebar, { attributes: true, attributeFilter: ['class'] });
        }
        
        // Listen for window resize
        window.addEventListener('resize', function() {
            hideTooltip();
        });
        
        // Listen for scroll
        window.addEventListener('scroll', function() {
            hideTooltip();
        });
    }

    /**
     * Public API
     */
    window.SidebarTooltipManager = {
        init: init,
        setupTooltips: setupTooltips,
        showTooltip: showTooltip,
        hideTooltip: hideTooltip
    };

    // Auto-initialize
    init();

})();
