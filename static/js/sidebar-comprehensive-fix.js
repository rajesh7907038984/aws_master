/**
 * Enhanced Sidebar Fix v2.1
 * Optimized for performance, accessibility, and responsive behavior
 * Includes improved error handling and mobile support
 */

(function() {
    'use strict';

    // Enhanced Configuration
    var CONFIG = {
        breakpoints: {
            mobile: 768,
            tabvar: 1024
        },
        animations: {
            duration: 300,
            easing: 'cubic-bezier(0.4, 0, 0.2, 1)'
        },
        storage: {
            collapsedKey: 'sidebar_collapsed',
            mobileOpenKey: 'sidebar_mobile_open'
        },
        performance: {
            debounceDelay: 150,
            throttleDelay: 16,
            maxRetries: 3
        },
        accessibility: {
            focusVisible: true,
            keyboardNavigation: true,
            screenReaderSupport: true
        }
    };

    // State management
    var state = {
        isInitialized: false,
        isCollapsed: false,
        isMobile: false,
        isTabvar: false,
        currentSubmenu: null
    };

    // DOM elements cache
    var elements = {};

    /**
     * Initialize the comprehensive sidebar fix
     */
    function init() {
        if (state.isInitialized) return;
        
        try {
            console.log('Initializing comprehensive sidebar fix...');
            cacheElements();
            setupEventListeners();
            handleResponsiveBehavior();
            restoreSidebarState();
            setupSubmenuToggles();
            fixLayout();
            
            state.isInitialized = true;
            console.log('Sidebar fix initialized successfully');
        } catch (error) {
            console.error('Error initializing sidebar fix:', error);
            // Try to set up basic functionality even if full initialization fails
            setupBasicFunctionality();
        }
    }

    /**
     * Setup basic functionality as fallback
     */
    function setupBasicFunctionality() {
        console.log('Setting up basic sidebar functionality...');
        
        var toggleButton = document.getElementById('mobile-menu-toggle');
        var sidebar = document.getElementById('sidebar');
        var mainContent = document.getElementById('main-content');
        
        if (toggleButton && sidebar) {
            // Remove existing event listeners
            var newButton = toggleButton.cloneNode(true);
            if (toggleButton.parentNode) {
                toggleButton.parentNode.replaceChild(newButton, toggleButton);
            }
            
            newButton.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                
                if (window.innerWidth < CONFIG.breakpoints.mobile) {
                    // Mobile behavior - toggle mobile menu
                    var mobileMenu = document.getElementById('mobile-menu');
                    if (mobileMenu) {
                        mobileMenu.classList.toggle('open');
                        document.body.classList.toggle('overflow-hidden');
                    }
                } else {
                    // Desktop behavior - toggle sidebar collapse
                    sidebar.classList.toggle('collapsed');
                    if (mainContent) {
                        mainContent.classList.toggle('sidebar-collapsed');
                    }
                    
                    // Store state
                    var isCollapsed = sidebar.classList.contains('collapsed');
                    localStorage.setItem(CONFIG.storage.collapsedKey, isCollapsed);
                }
            });
        }
    }

    /**
     * Cache DOM elements for performance
     */
    function cacheElements() {
        elements = {
            sidebar: document.getElementById('sidebar'),
            mainContent: document.getElementById('main-content'),
            mobileMenuToggle: document.getElementById('mobile-menu-toggle'),
            mobileMenu: document.getElementById('mobile-menu'),
            mobileMenuOverlay: document.getElementById('mobile-menu-overlay'),
            closeMobileMenu: document.getElementById('close-mobile-menu')
        };
    }

    /**
     * Setup all event listeners
     */
    function setupEventListeners() {
        // Remove existing listeners to prevent duplicates
        if (elements.mobileMenuToggle) {
            var newButton = elements.mobileMenuToggle.cloneNode(true);
            if (elements.mobileMenuToggle.parentNode) {
                elements.mobileMenuToggle.parentNode.replaceChild(newButton, elements.mobileMenuToggle);
                elements.mobileMenuToggle = newButton;
            }
            
            elements.mobileMenuToggle.addEventListener('click', handleToggleClick);
        }
        
        // Window resize handler
        window.removeEventListener('resize', handleResize);
        window.addEventListener('resize', debounce(handleResize, 150));
        
        // Mobile menu close handlers
        if (elements.closeMobileMenu && elements.mobileMenuOverlay) {
            elements.closeMobileMenu.removeEventListener('click', closeMobileMenu);
            elements.mobileMenuOverlay.removeEventListener('click', closeMobileMenu);
            elements.closeMobileMenu.addEventListener('click', closeMobileMenu);
            elements.mobileMenuOverlay.addEventListener('click', closeMobileMenu);
        }

        // Keyboard navigation
        document.removeEventListener('keydown', handleKeyboardNavigation);
        document.addEventListener('keydown', handleKeyboardNavigation);
    }

    /**
     * Handle toggle button click
     */
    function handleToggleClick(e) {
        e.preventDefault();
        e.stopPropagation();
        
        if (state.isMobile) {
            toggleMobileMenu();
        } else {
            toggleSidebar();
        }
    }

    /**
     * Handle responsive behavior
     */
    function handleResponsiveBehavior() {
        var wasMobile = state.isMobile;
        var wasTabvar = state.isTabvar;
        
        state.isMobile = window.innerWidth < CONFIG.breakpoints.mobile;
        state.isTabvar = window.innerWidth >= CONFIG.breakpoints.mobile && window.innerWidth < CONFIG.breakpoints.tabvar;
        
        if (elements.sidebar && elements.mainContent) {
            if (state.isMobile) {
                // Mobile behavior
                elements.sidebar.classList.add('hidden');
                elements.sidebar.classList.remove('md:block');
                elements.mainContent.style.marginLeft = '0';
                elements.mainContent.style.width = '100%';
                
                // Reset collapsed state on mobile
                elements.sidebar.classList.remove('collapsed');
                elements.mainContent.classList.remove('sidebar-collapsed');
                state.isCollapsed = false;
                
                // Close mobile menu if open
                if (elements.mobileMenu) {
                    elements.mobileMenu.classList.remove('open');
                    document.body.classList.remove('overflow-hidden');
                }
            } else {
                // Desktop behavior
                elements.sidebar.classList.remove('hidden');
                elements.sidebar.classList.add('md:block');
                
                // Restore collapsed state if it was collapsed
                if (state.isCollapsed) {
                    elements.sidebar.classList.add('collapsed');
                    elements.mainContent.classList.add('sidebar-collapsed');
                }
                
                // Close mobile menu if open
                if (elements.mobileMenu) {
                    elements.mobileMenu.classList.remove('open');
                    document.body.classList.remove('overflow-hidden');
                }
            }
        }
        
        // Update mobile menu toggle visibility
        if (elements.mobileMenuToggle) {
            if (state.isMobile) {
                elements.mobileMenuToggle.classList.add('md:hidden');
                elements.mobileMenuToggle.classList.remove('md:flex');
            } else {
                elements.mobileMenuToggle.classList.remove('md:hidden');
                elements.mobileMenuToggle.classList.add('md:flex');
            }
        }
        
        // Reinitialize submenu toggles after responsive change
        if (wasMobile !== state.isMobile || wasTabvar !== state.isTabvar) {
            setTimeout(() => {
                setupSubmenuToggles();
            }, 100);
        }
    }

    /**
     * Handle window resize
     */
    function handleResize() {
        handleResponsiveBehavior();
        fixLayout();
    }

    /**
     * Toggle mobile menu
     */
    function toggleMobileMenu() {
        if (!elements.mobileMenu) return;
        
        var wasOpen = elements.mobileMenu.classList.contains('open');
        elements.mobileMenu.classList.toggle('open');
        
        if (!wasOpen) {
            document.body.classList.add('overflow-hidden');
            loadSidebarContentToMobileMenu();
        } else {
            document.body.classList.remove('overflow-hidden');
        }
    }

    /**
     * Close mobile menu
     */
    function closeMobileMenu() {
        if (elements.mobileMenu) {
            elements.mobileMenu.classList.remove('open');
            document.body.classList.remove('overflow-hidden');
        }
    }

    /**
     * Toggle sidebar collapsed state
     */
    function toggleSidebar() {
        try {
            if (!elements.sidebar) return;
            
            if (state.isMobile) {
                toggleMobileMenu();
                return;
            }
            
            state.isCollapsed = !state.isCollapsed;
            
            // Toggle collapsed class
            elements.sidebar.classList.toggle('collapsed');
            
            // Update main content
            if (elements.mainContent) {
                elements.mainContent.classList.toggle('sidebar-collapsed');
            }
            
            // If collapsing, close all submenus
            if (state.isCollapsed) {
                closeAllSubmenus();
            }
            
            // Store state in localStorage
            localStorage.setItem(CONFIG.storage.collapsedKey, state.isCollapsed);
            
            // Fix layout after toggle
            setTimeout(() => {
                fixLayout();
            }, CONFIG.animations.duration);
        } catch (error) {
            console.error('Error toggling sidebar:', error);
        }
    }

    /**
     * Restore sidebar state from localStorage
     */
    function restoreSidebarState() {
        if (state.isMobile) return;
        
        var savedState = localStorage.getItem(CONFIG.storage.collapsedKey);
        if (savedState === 'true') {
            state.isCollapsed = true;
            if (elements.sidebar) {
                elements.sidebar.classList.add('collapsed');
            }
            if (elements.mainContent) {
                elements.mainContent.classList.add('sidebar-collapsed');
            }
        }
    }

    /**
     * Setup submenu toggle functionality
     */
    function setupSubmenuToggles() {
        if (!elements.sidebar) return;
        
        // Remove existing event listeners and reinitialize
        document.querySelectorAll('.menu-item.has-submenu, [data-submenu]').forEach(button => {
            var submenuId = button.getAttribute('data-submenu');
            if (!submenuId) return;
            
            // Remove any existing onclick handlers
            button.removeAttribute('onclick');
            
            // Remove existing event listeners by cloning the element
            var newButton = button.cloneNode(true);
            if (button.parentNode) {
                button.parentNode.replaceChild(newButton, button);
                
                // Ensure arrow icon is visible with enhanced styling
                var arrow = newButton.querySelector('.arrow-icon');
                if (arrow) {
                    arrow.style.display = 'inline-block';
                    arrow.style.visibility = 'visible';
                    arrow.style.opacity = '1';
                    arrow.style.color = 'white';
                    arrow.style.stroke = 'white';
                    arrow.style.fill = 'none';
                    arrow.style.position = 'absolute';
                    arrow.style.right = '1rem';
                    arrow.style.width = '0.75rem';
                    arrow.style.height = '0.75rem';
                    arrow.style.zIndex = '10';
                    arrow.style.transition = 'transform 0.3s ease';
                }
                
                // Add new event listener with enhanced error handling
                newButton.addEventListener('click', function(e) {
                    try {
                        e.preventDefault();
                        e.stopPropagation();
                        
                        // Don't allow submenu toggling when sidebar is collapsed
                        if (state.isCollapsed) {
                            return;
                        }
                        
                        toggleSubmenu(submenuId, this, arrow);
                    } catch (error) {
                        console.error('Error handling submenu toggle:', error);
                    }
                });
            }
        });
        
        // Check for active items in submenus and expand them
        checkActiveSubmenus();
    }

    /**
     * Toggle submenu visibility
     */
    function toggleSubmenu(submenuId, button, arrow) {
        try {
            var submenu = document.getElementById(submenuId);
            if (!submenu) return;
            
            var wasHidden = submenu.classList.contains('hidden');
            
            // Toggle submenu
            submenu.classList.toggle('hidden');
            button.classList.toggle('active');
            button.classList.toggle('expanded');
            
            // Rotate arrow
            if (arrow) {
                var isNowHidden = submenu.classList.contains('hidden');
                arrow.style.transform = isNowHidden ? '' : 'rotate(180deg)';
            }
            
            // Close other submenus if opening this one
            if (!submenu.classList.contains('hidden')) {
                closeOtherSubmenus(submenuId);
                state.currentSubmenu = submenuId;
            } else {
                state.currentSubmenu = null;
            }
        } catch (error) {
            console.error('Error toggling submenu:', error);
        }
    }

    /**
     * Close other open submenus
     */
    function closeOtherSubmenus(currentSubmenuId) {
        var allSubmenus = document.querySelectorAll('.submenu');
        allSubmenus.forEach(menu => {
            if (menu.id !== currentSubmenuId && !menu.classList.contains('hidden')) {
                var hasActiveItem = menu.querySelector('.menu-item.active');
                if (!hasActiveItem) {
                    menu.classList.add('hidden');
                    
                    var menuButton = document.querySelector('[data-submenu="' + menu.id + '"]');
                    if (menuButton) {
                        menuButton.classList.remove('active', 'expanded');
                        
                        var menuArrow = menuButton.querySelector('.arrow-icon');
                        if (menuArrow) {
                            menuArrow.style.transform = '';
                        }
                    }
                }
            }
        });
    }

    /**
     * Close all submenus
     */
    function closeAllSubmenus() {
        var allSubmenus = document.querySelectorAll('.submenu');
        allSubmenus.forEach(menu => {
            menu.classList.add('hidden');
            
            var menuButton = document.querySelector('[data-submenu="' + menu.id + '"]');
            if (menuButton) {
                menuButton.classList.remove('active', 'expanded');
                
                var menuArrow = menuButton.querySelector('.arrow-icon');
                if (menuArrow) {
                    menuArrow.style.transform = '';
                }
            }
        });
        state.currentSubmenu = null;
    }

    /**
     * Check for active items in submenus and expand them
     */
    function checkActiveSubmenus() {
        var currentPath = window.location.pathname;
        var currentUrl = window.location.href;
        
        document.querySelectorAll('#sidebar .submenu').forEach(submenu => {
            var hasActiveItem = false;
            
            submenu.querySelectorAll('a.menu-item').forEach(item => {
                var href = item.getAttribute('href');
                if (!href) return;
                
                if (isCurrentPage(href, currentPath, currentUrl)) {
                    item.classList.add('active');
                    hasActiveItem = true;
                }
            });
            
            if (hasActiveItem) {
                submenu.classList.remove('hidden');
                
                var menuButton = document.querySelector('[data-submenu="' + submenu.id + '"]');
                if (menuButton) {
                    menuButton.classList.add('active', 'expanded');
                    
                    var arrow = menuButton.querySelector('.arrow-icon');
                    if (arrow) {
                        arrow.style.transform = 'rotate(180deg)';
                    }
                }
            }
        });
    }

    /**
     * Check if a URL matches the current page
     */
    function isCurrentPage(href, currentPath, currentUrl) {
        if (href.includes('?')) {
            var hrefPath = href.split('?')[0];
            var hrefParams = href.split('?')[1];
            return currentPath.includes(hrefPath) && currentUrl.includes(hrefParams);
        } else {
            return currentPath.includes(href) && href !== '/';
        }
    }

    /**
     * Load sidebar content to mobile menu
     */
    function loadSidebarContentToMobileMenu() {
        if (!elements.mobileMenu) return;
        
        var sidebarContent = document.querySelector('#sidebar nav .flex.flex-col');
        var mobileMenuContent = document.querySelector('#mobile-menu .py-4');
        
        if (sidebarContent && mobileMenuContent) {
            // Always update content to ensure it's current
            var clone = sidebarContent.cloneNode(true);
            mobileMenuContent.innerHTML = '';
            mobileMenuContent.appendChild(clone);
            
            // Reinitialize submenu toggles in mobile menu
            setupMobileMenuSubmenus(mobileMenuContent);
        }
    }

    /**
     * Setup mobile menu submenus
     */
    function setupMobileMenuSubmenus(container) {
        var submenuToggleButtons = container.querySelectorAll('.menu-item.has-submenu');
        submenuToggleButtons.forEach(button => {
            button.removeAttribute('onclick');
            
            var submenuId = button.getAttribute('data-submenu');
            if (submenuId) {
                // Ensure arrow icon is visible in mobile menu
                var arrow = button.querySelector('.arrow-icon');
                if (arrow) {
                    arrow.style.display = 'inline-block';
                    arrow.style.visibility = 'visible';
                    arrow.style.opacity = '1';
                    arrow.style.color = 'white';
                    arrow.style.stroke = 'white';
                }
                
                button.addEventListener('click', function(e) {
                    try {
                        e.preventDefault();
                        e.stopPropagation();
                        
                        var submenu = document.getElementById(submenuId);
                        if (submenu) {
                            var wasHidden = submenu.classList.contains('hidden');
                            submenu.classList.toggle('hidden');
                            this.classList.toggle('expanded');
                            this.classList.toggle('active');
                            
                            var arrow = this.querySelector('.arrow-icon');
                            if (arrow) {
                                var isNowHidden = submenu.classList.contains('hidden');
                                arrow.style.transform = isNowHidden ? '' : 'rotate(180deg)';
                                arrow.style.display = 'inline-block';
                                arrow.style.visibility = 'visible';
                                arrow.style.opacity = '1';
                            }
                            
                            if (!submenu.classList.contains('hidden')) {
                                closeOtherSubmenus(submenuId);
                            }
                        }
                    } catch (error) {
                        console.error('Error handling mobile submenu toggle:', error);
                    }
                });
            }
        });
    }

    /**
     * Fix layout issues
     */
    function fixLayout() {
        if (!elements.sidebar || !elements.mainContent) return;
        
        var isMobile = window.innerWidth < CONFIG.breakpoints.mobile;
        var isCollapsed = elements.sidebar.classList.contains('collapsed');
        
        // Reset classes first
        elements.mainContent.classList.remove('sidebar-collapsed');
        
        if (isMobile) {
            // Mobile layout
            elements.mainContent.style.marginLeft = '0';
            elements.mainContent.style.width = '100%';
            elements.mainContent.style.maxWidth = '100%';
        } else {
            // Desktop layout
            if (isCollapsed) {
                elements.mainContent.style.marginLeft = '3.5rem';
                elements.mainContent.style.width = 'calc(100% - 3.5rem)';
                elements.mainContent.style.maxWidth = 'calc(100% - 3.5rem)';
                elements.mainContent.classList.add('sidebar-collapsed');
            } else {
                elements.mainContent.style.marginLeft = '16rem';
                elements.mainContent.style.width = 'calc(100% - 16rem)';
                elements.mainContent.style.maxWidth = 'calc(100% - 16rem)';
                elements.mainContent.classList.remove('sidebar-collapsed');
            }
        }
    }

    /**
     * Handle keyboard navigation
     */
    function handleKeyboardNavigation(e) {
        if (e.key === 'Escape') {
            closeMobileMenu();
            closeAllSubmenus();
        }
    }

    /**
     * Debounce utility function
     */
    function debounce(func, wait) {
        var timeout;
        return function executedFunction(...args) {
            var later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    // Public API
    window.SidebarComprehensiveFix = {
        init: init,
        toggle: toggleSidebar,
        toggleSubmenu: toggleSubmenu,
        closeAllSubmenus: closeAllSubmenus,
        fixLayout: fixLayout,
        isCollapsed: () => state.isCollapsed,
        isMobile: () => state.isMobile,
        isInitialized: () => state.isInitialized
    };

    // Global functions for backward compatibility
    window.toggleSubmenu = toggleSubmenu;
    window.toggleSidebar = toggleSidebar;
    window.toggleMobileMenu = toggleMobileMenu;

    // Auto-initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Also initialize on window load as fallback
    window.addEventListener('load', init);

})();
