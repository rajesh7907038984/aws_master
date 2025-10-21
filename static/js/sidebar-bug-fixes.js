/**
 * Sidebar Bug Fixes - Comprehensive Solution
 * Addresses common sidebar issues and conflicts
 */

(function() {
    'use strict';

    console.log('🔧 Loading Sidebar Bug Fixes...');

    // Configuration
    const CONFIG = {
        selectors: {
            sidebar: '#sidebar',
            mainContent: '#main-content',
            mobileMenu: '#nexsy-mobile-menu',
            mobileToggle: '#nexsy-mobile-menu-toggle',
            submenuButtons: '.menu-item.has-submenu, [data-submenu]',
            arrowIcons: '.arrow-icon'
        },
        classes: {
            collapsed: 'collapsed',
            hidden: 'hidden',
            active: 'active',
            expanded: 'expanded'
        },
        breakpoints: {
            mobile: 768
        }
    };

    // State tracking
    let isInitialized = false;
    let isMobile = window.innerWidth < CONFIG.breakpoints.mobile;

    /**
     * Fix 1: Prevent duplicate event listeners
     */
    function fixDuplicateEventListeners() {
        console.log('🔧 Fixing duplicate event listeners...');
        
        const submenuButtons = document.querySelectorAll(CONFIG.selectors.submenuButtons);
        submenuButtons.forEach(button => {
            // Remove all existing event listeners by cloning
            const newButton = button.cloneNode(true);
            if (button.parentNode) {
                button.parentNode.replaceChild(newButton, button);
            }
        });
        
        console.log('✅ Duplicate event listeners removed');
    }

    /**
     * Fix 2: Ensure proper arrow icon visibility
     */
    function fixArrowIconVisibility() {
        console.log('🔧 Fixing arrow icon visibility...');
        
        const arrowIcons = document.querySelectorAll(CONFIG.selectors.arrowIcons);
        arrowIcons.forEach(arrow => {
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
        });
        
        console.log('✅ Arrow icons visibility fixed');
    }

    /**
     * Fix 3: Resolve CSS variable conflicts
     */
    function fixCSSVariableConflicts() {
        console.log('🔧 Fixing CSS variable conflicts...');
        
        const root = document.documentElement;
        const computedStyle = getComputedStyle(root);
        
        // Ensure critical variables are set
        const variables = {
            '--sidebar-width': '16rem',
            '--sidebar-collapsed-width': '3.5rem',
            '--sidebar-bg': '#1C2260',
            '--sidebar-text': 'white',
            '--sidebar-transition': 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
            '--z-sidebar': '30'
        };
        
        Object.entries(variables).forEach(([property, value]) => {
            const currentValue = computedStyle.getPropertyValue(property);
            if (!currentValue || currentValue.trim() === '') {
                root.style.setProperty(property, value);
                console.log(`✅ Set ${property}: ${value}`);
            }
        });
        
        console.log('✅ CSS variables conflicts resolved');
    }

    /**
     * Fix 4: Mobile menu synchronization
     */
    function fixMobileMenuSync() {
        console.log('🔧 Fixing mobile menu synchronization...');
        
        const sidebar = document.querySelector(CONFIG.selectors.sidebar);
        const mobileMenu = document.querySelector(CONFIG.selectors.mobileMenu);
        
        if (sidebar && mobileMenu) {
            const sidebarContent = sidebar.querySelector('nav .flex.flex-col');
            const mobileMenuContent = mobileMenu.querySelector('.py-4');
            
            if (sidebarContent && mobileMenuContent) {
                // Sync content when mobile menu opens
                const syncContent = () => {
                    const clone = sidebarContent.cloneNode(true);
                    mobileMenuContent.innerHTML = '';
                    mobileMenuContent.appendChild(clone);
                    
                    // Reinitialize submenu toggles in mobile menu
                    setupMobileMenuSubmenus(mobileMenuContent);
                };
                
                // Listen for mobile menu open
                const observer = new MutationObserver((mutations) => {
                    mutations.forEach((mutation) => {
                        if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                            if (mobileMenu.classList.contains('open')) {
                                syncContent();
                            }
                        }
                    });
                });
                
                observer.observe(mobileMenu, { attributes: true });
                console.log('✅ Mobile menu synchronization fixed');
            }
        }
    }

    /**
     * Fix 5: Submenu toggle functionality
     */
    function fixSubmenuToggles() {
        console.log('🔧 Fixing submenu toggle functionality...');
        
        const submenuButtons = document.querySelectorAll(CONFIG.selectors.submenuButtons);
        submenuButtons.forEach(button => {
            const submenuId = button.getAttribute('data-submenu');
            if (!submenuId) return;
            
            button.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                
                const submenu = document.getElementById(submenuId);
                if (!submenu) return;
                
                const arrow = button.querySelector('.arrow-icon');
                const wasHidden = submenu.classList.contains(CONFIG.classes.hidden);
                
                // Toggle submenu
                submenu.classList.toggle(CONFIG.classes.hidden);
                button.classList.toggle(CONFIG.classes.active);
                button.classList.toggle(CONFIG.classes.expanded);
                
                // Rotate arrow
                if (arrow) {
                    const isNowHidden = submenu.classList.contains(CONFIG.classes.hidden);
                    arrow.style.transform = isNowHidden ? '' : 'rotate(180deg)';
                }
                
                // Close other submenus if opening this one
                if (!submenu.classList.contains(CONFIG.classes.hidden)) {
                    closeOtherSubmenus(submenuId);
                }
            });
        });
        
        console.log('✅ Submenu toggle functionality fixed');
    }

    /**
     * Fix 6: Mobile menu submenu setup
     */
    function setupMobileMenuSubmenus(container) {
        const submenuButtons = container.querySelectorAll(CONFIG.selectors.submenuButtons);
        submenuButtons.forEach(button => {
            const submenuId = button.getAttribute('data-submenu');
            if (!submenuId) return;
            
            button.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                
                const submenu = document.getElementById(submenuId);
                if (!submenu) return;
                
                const arrow = button.querySelector('.arrow-icon');
                submenu.classList.toggle(CONFIG.classes.hidden);
                button.classList.toggle(CONFIG.classes.expanded);
                button.classList.toggle(CONFIG.classes.active);
                
                if (arrow) {
                    const isNowHidden = submenu.classList.contains(CONFIG.classes.hidden);
                    arrow.style.transform = isNowHidden ? '' : 'rotate(180deg)';
                }
                
                if (!submenu.classList.contains(CONFIG.classes.hidden)) {
                    closeOtherSubmenus(submenuId);
                }
            });
        });
    }

    /**
     * Close other submenus
     */
    function closeOtherSubmenus(currentSubmenuId) {
        const allSubmenus = document.querySelectorAll('.submenu');
        allSubmenus.forEach(menu => {
            if (menu.id !== currentSubmenuId && !menu.classList.contains(CONFIG.classes.hidden)) {
                const hasActiveItem = menu.querySelector('.menu-item.active');
                if (!hasActiveItem) {
                    menu.classList.add(CONFIG.classes.hidden);
                    
                    const menuButton = document.querySelector('[data-submenu="' + menu.id + '"]');
                    if (menuButton) {
                        menuButton.classList.remove(CONFIG.classes.active, CONFIG.classes.expanded);
                        
                        const menuArrow = menuButton.querySelector('.arrow-icon');
                        if (menuArrow) {
                            menuArrow.style.transform = '';
                        }
                    }
                }
            }
        });
    }

    /**
     * Fix 7: Responsive behavior
     */
    function fixResponsiveBehavior() {
        console.log('🔧 Fixing responsive behavior...');
        
        const sidebar = document.querySelector(CONFIG.selectors.sidebar);
        const mainContent = document.querySelector(CONFIG.selectors.mainContent);
        
        if (!sidebar || !mainContent) return;
        
        const handleResize = () => {
            const wasMobile = isMobile;
            isMobile = window.innerWidth < CONFIG.breakpoints.mobile;
            
            if (isMobile !== wasMobile) {
                if (isMobile) {
                    // Mobile behavior
                    sidebar.classList.add(CONFIG.classes.hidden);
                    mainContent.style.marginLeft = '0';
                    mainContent.style.width = '100%';
                } else {
                    // Desktop behavior
                    sidebar.classList.remove(CONFIG.classes.hidden);
                    const sidebarWidth = getComputedStyle(document.documentElement).getPropertyValue('--sidebar-width') || '16rem';
                    mainContent.style.marginLeft = sidebarWidth;
                    mainContent.style.width = `calc(100% - ${sidebarWidth})`;
                }
            }
        };
        
        window.addEventListener('resize', handleResize);
        handleResize(); // Initial call
        
        console.log('✅ Responsive behavior fixed');
    }

    /**
     * Fix 8: Layout calculations
     */
    function fixLayoutCalculations() {
        console.log('🔧 Fixing layout calculations...');
        
        const sidebar = document.querySelector(CONFIG.selectors.sidebar);
        const mainContent = document.querySelector(CONFIG.selectors.mainContent);
        
        if (!sidebar || !mainContent) return;
        
        const updateLayout = () => {
            if (isMobile) {
                mainContent.style.marginLeft = '0';
                mainContent.style.width = '100%';
            } else {
                const isCollapsed = sidebar.classList.contains(CONFIG.classes.collapsed);
                if (isCollapsed) {
                    const collapsedWidth = getComputedStyle(document.documentElement).getPropertyValue('--sidebar-collapsed-width') || '3.5rem';
                    mainContent.style.marginLeft = collapsedWidth;
                    mainContent.style.width = `calc(100% - ${collapsedWidth})`;
                } else {
                    const sidebarWidth = getComputedStyle(document.documentElement).getPropertyValue('--sidebar-width') || '16rem';
                    mainContent.style.marginLeft = sidebarWidth;
                    mainContent.style.width = `calc(100% - ${sidebarWidth})`;
                }
            }
        };
        
        // Update layout on sidebar toggle
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                    updateLayout();
                }
            });
        });
        
        observer.observe(sidebar, { attributes: true });
        updateLayout(); // Initial call
        
        console.log('✅ Layout calculations fixed');
    }

    /**
     * Initialize all fixes
     */
    function initializeFixes() {
        if (isInitialized) return;
        
        console.log('🚀 Initializing sidebar bug fixes...');
        
        try {
            fixDuplicateEventListeners();
            fixArrowIconVisibility();
            fixCSSVariableConflicts();
            fixMobileMenuSync();
            fixSubmenuToggles();
            fixResponsiveBehavior();
            fixLayoutCalculations();
            
            isInitialized = true;
            console.log('✅ All sidebar bug fixes applied successfully');
        } catch (error) {
            console.error('❌ Error applying sidebar fixes:', error);
        }
    }

    // Auto-initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeFixes);
    } else {
        initializeFixes();
    }

    // Export for manual testing
    window.SidebarBugFixes = {
        init: initializeFixes,
        fixDuplicateEventListeners,
        fixArrowIconVisibility,
        fixCSSVariableConflicts,
        fixMobileMenuSync,
        fixSubmenuToggles,
        fixResponsiveBehavior,
        fixLayoutCalculations
    };

})();
