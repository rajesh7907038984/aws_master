/**
 * Unified Sidebar JavaScript - Clean and Optimized v5.0
 * Handles all sidebar functionality including responsive behavior, 
 * submenu toggles, hover tooltips, and mobile menu integration
 */

(function() {
    'use strict';

    // Configuration
    const CONFIG = {
        breakpoints: {
            mobile: 768
        },
        animations: {
            duration: 300,
            easing: 'cubic-bezier(0.4, 0, 0.2, 1)'
        },
        storage: {
            collapsedKey: 'sidebar_collapsed'
        }
    };

    // State management
    let state = {
        isInitialized: false,
        isCollapsed: false,
        isMobile: false,
        hoverTooltip: null,
        hoverTimeout: null,
        currentMenuItem: null,
        submenuSetupTimeout: null,
        isSettingUpSubmenus: false
    };

    // DOM elements cache
    let elements = {};

    /**
     * Initialize the sidebar system
     */
    function init() {
        if (state.isInitialized) return;
        
        try {
            cacheElements();
            setupEventListeners();
            handleResponsiveBehavior();
            restoreSidebarState();
            setupSubmenuToggles();
            setupHoverTooltips();
            
            state.isInitialized = true;
            console.log('Sidebar system initialized successfully');
        } catch (error) {
            console.error('Error initializing sidebar system:', error);
            // Try to set up basic functionality even if full initialization fails
            setupBasicToggle();
        }
    }
    
    /**
     * Setup basic toggle functionality as fallback
     */
    function setupBasicToggle() {
        const toggleButton = document.getElementById('mobile-menu-toggle');
        const sidebar = document.getElementById('sidebar');
        const mainContent = document.getElementById('main-content');
        
        if (toggleButton && sidebar) {
            // Remove any existing event listeners by cloning the button
            const newButton = toggleButton.cloneNode(true);
            if (toggleButton.parentNode) {
                toggleButton.parentNode.replaceChild(newButton, toggleButton);
            }
            
            newButton.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                
                console.log('Toggle button clicked, window width:', window.innerWidth);
                
                if (window.innerWidth < 768) {
                    // Mobile behavior
                    const mobileMenu = document.getElementById('mobile-menu');
                    if (mobileMenu) {
                        const wasOpen = mobileMenu.classList.contains('open');
                        mobileMenu.classList.toggle('open');
                        
                        if (!wasOpen) {
                            document.body.classList.add('overflow-hidden');
                            // Load sidebar content to mobile menu if not already loaded
                            loadSidebarContentToMobileMenu();
                        } else {
                            document.body.classList.remove('overflow-hidden');
                        }
                        console.log('Mobile menu toggled, now open:', !wasOpen);
                    }
                } else {
                    // Desktop behavior - toggle sidebar
                    const wasCollapsed = sidebar.classList.contains('collapsed');
                    sidebar.classList.toggle('collapsed');
                    
                    if (mainContent) {
                        mainContent.classList.toggle('sidebar-collapsed');
                    }
                    
                    // Store state
                    const isNowCollapsed = sidebar.classList.contains('collapsed');
                    localStorage.setItem('sidebar_collapsed', isNowCollapsed);
                    
                    console.log('Desktop sidebar toggled, now collapsed:', isNowCollapsed);
                }
            });
            
            console.log('Basic sidebar toggle functionality initialized');
        }
    }

    /**
     * Load sidebar content to mobile menu
     */
    function loadSidebarContentToMobileMenu() {
        const sidebarContent = document.querySelector('#sidebar nav .flex.flex-col');
        const mobileMenuContent = document.querySelector('#mobile-menu .py-4');
        
        if (sidebarContent && mobileMenuContent && mobileMenuContent.children.length === 0) {
            try {
                // Clone the content to avoid duplicate IDs
                const clone = sidebarContent.cloneNode(true);
                mobileMenuContent.innerHTML = '';
                mobileMenuContent.appendChild(clone);
                console.log('Sidebar content loaded to mobile menu');
            } catch (error) {
                console.error('Error loading mobile menu content:', error);
            }
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
            // Clone the button to remove all existing event listeners
            const newButton = elements.mobileMenuToggle.cloneNode(true);
            if (elements.mobileMenuToggle.parentNode) {
                elements.mobileMenuToggle.parentNode.replaceChild(newButton, elements.mobileMenuToggle);
                elements.mobileMenuToggle = newButton;
            }
            
            // Add new event listener
            elements.mobileMenuToggle.addEventListener('click', handleMobileMenuToggle);
            console.log('Toggle button event listener added');
        }
        
        // Window resize handler
        window.removeEventListener('resize', handleResponsiveBehavior);
        window.addEventListener('resize', debounce(handleResponsiveBehavior, 150));
        
        if (elements.closeMobileMenu && elements.mobileMenuOverlay) {
            elements.closeMobileMenu.removeEventListener('click', closeMobileMenu);
            elements.mobileMenuOverlay.removeEventListener('click', closeMobileMenu);
            elements.closeMobileMenu.addEventListener('click', closeMobileMenu);
            elements.mobileMenuOverlay.addEventListener('click', closeMobileMenu);
        }

        // Keyboard navigation
        document.removeEventListener('keydown', handleKeyboardNavigation);
        document.addEventListener('keydown', handleKeyboardNavigation);
        
        // Page visibility change
        document.removeEventListener('visibilitychange', handleVisibilityChange);
        document.addEventListener('visibilitychange', handleVisibilityChange);
    }

    /**
     * Handle responsive behavior
     */
    function handleResponsiveBehavior() {
        const wasMobile = state.isMobile;
        state.isMobile = window.innerWidth < CONFIG.breakpoints.mobile;
        
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
        if (wasMobile !== state.isMobile) {
            setTimeout(() => {
                setupSubmenuToggles();
            }, 100);
        }
    }

    /**
     * Handle mobile menu toggle
     */
    function handleMobileMenuToggle(e) {
        e.preventDefault();
        e.stopPropagation();
        
        console.log('Toggle button clicked, isMobile:', state.isMobile, 'window width:', window.innerWidth);
        
        if (state.isMobile) {
            console.log('Mobile mode: toggling mobile menu');
            toggleMobileMenu();
        } else {
            console.log('Desktop mode: toggling sidebar');
            toggleSidebar();
        }
    }

    /**
     * Toggle mobile menu
     */
    function toggleMobileMenu() {
        if (!elements.mobileMenu) return;
        
        const wasOpen = elements.mobileMenu.classList.contains('open');
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
        if (!elements.sidebar) {
            console.error('Sidebar element not found');
            return;
        }
        
        if (state.isMobile) {
            console.log('Toggle called on mobile, switching to mobile menu');
            toggleMobileMenu();
            return;
        }
        
        console.log('Toggling sidebar, current state:', state.isCollapsed);
        console.log('Sidebar element:', elements.sidebar);
        console.log('Main content element:', elements.mainContent);
        
        state.isCollapsed = !state.isCollapsed;
        
        // Toggle collapsed class
        elements.sidebar.classList.toggle('collapsed');
        console.log('Sidebar collapsed class toggled, now has collapsed:', elements.sidebar.classList.contains('collapsed'));
        
        // Update main content
        if (elements.mainContent) {
            elements.mainContent.classList.toggle('sidebar-collapsed');
            console.log('Main content sidebar-collapsed class toggled, now has sidebar-collapsed:', elements.mainContent.classList.contains('sidebar-collapsed'));
        }
        
        // If collapsing, close all submenus
        if (state.isCollapsed) {
            closeAllSubmenus();
        }
        
        // Store state in localStorage
        localStorage.setItem(CONFIG.storage.collapsedKey, state.isCollapsed);
        console.log('Sidebar state saved to localStorage:', state.isCollapsed);
        
        // Hide tooltip when toggling
        hideHoverTooltip();
        
        // Reinitialize hover tooltips based on new state
        setTimeout(() => {
            setupHoverTooltips();
            console.log('Sidebar toggled successfully. Collapsed:', state.isCollapsed);
        }, 150);
        
        // Force a reflow to ensure changes are applied
        elements.sidebar.offsetHeight;
    }

    /**
     * Restore sidebar state from localStorage
     */
    function restoreSidebarState() {
        if (state.isMobile) return;
        
        const savedState = localStorage.getItem(CONFIG.storage.collapsedKey);
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
     * Setup submenu toggle functionality (debounced)
     */
    function setupSubmenuToggles() {
        // Prevent excessive re-initialization
        if (state.isSettingUpSubmenus) {
            return;
        }
        
        // Debounce rapid setup calls
        if (state.submenuSetupTimeout) {
            clearTimeout(state.submenuSetupTimeout);
        }
        
        state.submenuSetupTimeout = setTimeout(() => {
            setupSubmenutogglesInternal();
        }, 300);
    }
    
    /**
     * Internal submenu setup function
     */
    function setupSubmenutogglesInternal() {
        if (!elements.sidebar || state.isSettingUpSubmenus) return;
        
        state.isSettingUpSubmenus = true;
        console.log(' Setting up submenu toggles...');
        
        try {
            // Remove existing event listeners and reinitialize
            document.querySelectorAll('.menu-item.has-submenu, [data-submenu]').forEach(button => {
            const submenuId = button.getAttribute('data-submenu');
            if (!submenuId) return;
            
            console.log('🔍 Found submenu button:', submenuId);
            
            // Remove any existing onclick handlers
            button.removeAttribute('onclick');
            
            // Remove existing event listeners by cloning the element
            const newButton = button.cloneNode(true);
            if (button.parentNode) {
                button.parentNode.replaceChild(newButton, button);
                
                // Ensure arrow icon is visible with enhanced styling
                const arrow = newButton.querySelector('.arrow-icon');
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
                    console.log(' Arrow icon styled for:', submenuId);
                }
                
                // Add new event listener with enhanced error handling
                newButton.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    console.log('🖱️ Submenu button clicked:', submenuId);
                    
                    // Don't allow submenu toggling when sidebar is collapsed
                    if (state.isCollapsed) {
                        console.log('Submenu toggle blocked - sidebar is collapsed');
                        return;
                    }
                    
                    // Direct toggle implementation
                    const submenu = document.getElementById(submenuId);
                    if (!submenu) {
                        console.error(' Submenu not found:', submenuId);
                        return;
                    }
                    
                    const wasHidden = submenu.classList.contains('hidden');
                    console.log('📋 Submenu was hidden:', wasHidden);
                    
                    // Toggle submenu
                    submenu.classList.toggle('hidden');
                    newButton.classList.toggle('active');
                    newButton.classList.toggle('expanded');
                    
                    // Rotate arrow
                    if (arrow) {
                        const isNowHidden = submenu.classList.contains('hidden');
                        arrow.style.transform = isNowHidden ? '' : 'rotate(180deg)';
                        console.log(' Arrow rotated:', !isNowHidden);
                    }
                    
                    // Close other submenus if opening this one
                    if (!submenu.classList.contains('hidden')) {
                        document.querySelectorAll('.submenu').forEach(menu => {
                            if (menu.id !== submenuId && !menu.classList.contains('hidden')) {
                                menu.classList.add('hidden');
                                
                                const menuButton = document.querySelector(`[data-submenu="${menu.id}"]`);
                                if (menuButton) {
                                    menuButton.classList.remove('active', 'expanded');
                                    
                                    const menuArrow = menuButton.querySelector('.arrow-icon');
                                    if (menuArrow) {
                                        menuArrow.style.transform = '';
                                    }
                                }
                            }
                        });
                    }
                    
                    console.log(' Submenu toggled successfully');
                });
                
                console.log(' Submenu toggle setup for:', submenuId);
            }
        });
        
        // Check for active items in submenus and expand them
        checkActiveSubmenus();
        } catch (error) {
            console.error('Error setting up submenu toggles:', error);
        } finally {
            state.isSettingUpSubmenus = false;
        }
    }

    /**
     * Toggle submenu visibility
     */
    function toggleSubmenu(submenuId, event) {
        // Don't allow submenu toggling when sidebar is collapsed
        if (state.isCollapsed) {
            console.log('Submenu toggle blocked - sidebar is collapsed');
            return;
        }
        
        console.log('Submenu toggle allowed - sidebar is expanded');
        
        const submenu = document.getElementById(submenuId);
        if (!submenu) {
            console.warn('Submenu not found:', submenuId);
            return;
        }
        
        // Find the button that triggered this
        let button = event.currentTarget;
        if (!button) {
            button = document.querySelector(`[data-submenu="${submenuId}"]`);
        }
        
        if (!button) {
            console.warn('Button not found for submenu:', submenuId);
            return;
        }
        
        const arrow = button.querySelector('.arrow-icon');
        const wasHidden = submenu.classList.contains('hidden');
        
        console.log('Toggling submenu:', submenuId, 'was hidden:', wasHidden);
        
        // Toggle submenu
        submenu.classList.toggle('hidden');
        button.classList.toggle('active');
        button.classList.toggle('expanded');
        
        // Rotate arrow with enhanced visibility and styling
        if (arrow) {
            const isNowHidden = submenu.classList.contains('hidden');
            arrow.style.transform = isNowHidden ? '' : 'rotate(180deg)';
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
            console.log('Arrow rotated:', !isNowHidden);
        }
        
        // Close other submenus if opening this one
        if (!submenu.classList.contains('hidden')) {
            closeOtherSubmenus(submenuId);
        }
        
        // Scroll submenu into view if needed
        if (!submenu.classList.contains('hidden')) {
            scrollSubmenuIntoView(submenu);
        }
    }

    /**
     * Close other open submenus
     */
    function closeOtherSubmenus(currentSubmenuId) {
        const allSubmenus = document.querySelectorAll('.submenu');
        allSubmenus.forEach(menu => {
            if (menu.id !== currentSubmenuId && !menu.classList.contains('hidden')) {
                const hasActiveItem = menu.querySelector('.menu-item.active');
                if (!hasActiveItem) {
                    menu.classList.add('hidden');
                    
                    const menuButton = document.querySelector(`[data-submenu="${menu.id}"]`);
                    if (menuButton) {
                        menuButton.classList.remove('active', 'expanded');
                        
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
     * Close all submenus
     */
    function closeAllSubmenus() {
        const allSubmenus = document.querySelectorAll('.submenu');
        allSubmenus.forEach(menu => {
            menu.classList.add('hidden');
            
            const menuButton = document.querySelector(`[data-submenu="${menu.id}"]`);
            if (menuButton) {
                menuButton.classList.remove('active', 'expanded');
                
                const menuArrow = menuButton.querySelector('.arrow-icon');
                if (menuArrow) {
                    menuArrow.style.transform = '';
                }
            }
        });
        console.log('All submenus closed');
    }

    /**
     * Scroll submenu into view
     */
    function scrollSubmenuIntoView(submenu) {
        if (!elements.sidebar) return;
        
        const submenuRect = submenu.getBoundingClientRect();
        const sidebarRect = elements.sidebar.getBoundingClientRect();
        
        if (submenuRect.bottom > sidebarRect.bottom) {
            const flexContainer = elements.sidebar.querySelector('.flex.flex-col');
            if (flexContainer) {
                flexContainer.scrollTo({
                    top: flexContainer.scrollTop + (submenuRect.bottom - sidebarRect.bottom),
                    behavior: 'smooth'
                });
            }
        }
    }

    /**
     * Check for active items in submenus and expand them
     */
    function checkActiveSubmenus() {
        const currentPath = window.location.pathname;
        const currentUrl = window.location.href;
        
        document.querySelectorAll('#sidebar .submenu').forEach(submenu => {
            let hasActiveItem = false;
            
            submenu.querySelectorAll('a.menu-item').forEach(item => {
                const href = item.getAttribute('href');
                if (!href) return;
                
                if (isCurrentPage(href, currentPath, currentUrl)) {
                    item.classList.add('active');
                    hasActiveItem = true;
                }
            });
            
            if (hasActiveItem) {
                submenu.classList.remove('hidden');
                
                const menuButton = document.querySelector(`[data-submenu="${submenu.id}"]`);
                if (menuButton) {
                    menuButton.classList.add('active', 'expanded');
                    
                    const arrow = menuButton.querySelector('.arrow-icon');
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
            const hrefPath = href.split('?')[0];
            const hrefParams = href.split('?')[1];
            return currentPath.includes(hrefPath) && currentUrl.includes(hrefParams);
        } else {
            return currentPath.includes(href) && href !== '/';
        }
    }

    /**
     * Setup hover tooltips for collapsed sidebar
     */
    function setupHoverTooltips() {
        if (!elements.sidebar) return;
        
        // Remove existing listeners first
        const existingHandler = elements.sidebar._tooltipHandler;
        if (existingHandler) {
            elements.sidebar.removeEventListener('mouseenter', existingHandler, true);
            elements.sidebar.removeEventListener('mouseleave', existingHandler);
        }
        
        // Only setup tooltips if sidebar is collapsed
        if (!state.isCollapsed) {
            hideHoverTooltip(); // Hide any existing tooltips
            return;
        }
        
        const mouseEnterHandler = function(e) {
            const menuItem = e.target.closest('.menu-item');
            if (menuItem && state.isCollapsed) {
                clearTimeout(state.hoverTimeout);
                state.hoverTimeout = setTimeout(() => {
                    if (menuItem.matches(':hover') && state.isCollapsed) {
                        showHoverTooltip(menuItem, e);
                    }
                }, 200); // Increased delay for better UX
            }
        };
        
        const mouseLeaveHandler = function(e) {
            if (state.isCollapsed) {
                const tooltip = document.querySelector('.sidebar-hover-tooltip.show');
                const isGoingToTooltip = e.relatedTarget?.closest('.sidebar-hover-tooltip');
                const isGoingToMenuItem = e.relatedTarget?.closest('.menu-item');
                
                if (!isGoingToTooltip && !isGoingToMenuItem) {
                    state.hoverTimeout = setTimeout(() => {
                        const currentTooltip = document.querySelector('.sidebar-hover-tooltip.show');
                        if (!currentTooltip || !currentTooltip.matches(':hover')) {
                            hideHoverTooltip();
                        }
                    }, 200);
                }
            }
        };
        
        elements.sidebar.addEventListener('mouseenter', mouseEnterHandler, true);
        elements.sidebar.addEventListener('mouseleave', mouseLeaveHandler);
        
        elements.sidebar._tooltipHandler = mouseEnterHandler;
        
        console.log('Hover tooltips setup for collapsed sidebar');
    }

    /**
     * Show hover tooltip
     */
    function showHoverTooltip(menuItem, event) {
        if (!state.isCollapsed) return;
        
        clearTimeout(state.hoverTimeout);
        state.currentMenuItem = menuItem;
        
        // Hide any existing tooltip first
        hideHoverTooltip();
        
        const tooltip = createHoverTooltip();
        const menuText = menuItem.querySelector('.menu-text');
        const menuIcon = menuItem.querySelector('.icon-container svg');
        const hasSubmenu = menuItem.classList.contains('has-submenu');
        
        if (!menuText) {
            console.warn('No menu text found for tooltip');
            return;
        }
        
        let submenu = null;
        if (hasSubmenu) {
            const submenuId = menuItem.getAttribute('data-submenu');
            if (submenuId) {
                submenu = document.getElementById(submenuId);
                console.log('Submenu element found:', submenu);
                if (submenu) {
                    console.log('Submenu children count:', submenu.children.length);
                    console.log('Submenu HTML:', submenu.innerHTML);
                }
            }
        }
        
        let tooltipContent = `
            <div class="tooltip-header">
                ${menuIcon ? menuIcon.outerHTML : ''}
                <span>${menuText.textContent.trim()}</span>
            </div>
        `;
        
        if (submenu && submenu.children.length > 0) {
            console.log('Adding submenu to tooltip, items found:', submenu.children.length);
            tooltipContent += '<div class="tooltip-submenu">';
            const submenuItems = submenu.querySelectorAll('a.menu-item');
            console.log('Submenu items found:', submenuItems.length);
            
            if (submenuItems.length > 0) {
                submenuItems.forEach(item => {
                    const itemText = item.querySelector('.menu-text');
                    const itemHref = item.getAttribute('href') || '#';
                    if (itemText) {
                        console.log('Adding submenu item:', itemText.textContent.trim());
                        tooltipContent += `
                            <a href="${itemHref}" class="tooltip-submenu-item">
                                ${itemText.textContent.trim()}
                            </a>
                        `;
                    }
                });
            } else {
                // Fallback: look for any child elements with menu-text
                const allChildren = submenu.querySelectorAll('[class*="menu-text"]');
                console.log('Fallback: Found menu-text elements:', allChildren.length);
                allChildren.forEach(child => {
                    const parent = child.closest('a');
                    if (parent) {
                        const itemHref = parent.getAttribute('href') || '#';
                        console.log('Adding fallback submenu item:', child.textContent.trim());
                        tooltipContent += `
                            <a href="${itemHref}" class="tooltip-submenu-item">
                                ${child.textContent.trim()}
                            </a>
                        `;
                    }
                });
            }
            tooltipContent += '</div>';
        } else {
            console.log('No submenu found or submenu is empty');
        }
        
        tooltip.innerHTML = tooltipContent;
        
        // Position tooltip
        const rect = menuItem.getBoundingClientRect();
        const sidebarRect = elements.sidebar.getBoundingClientRect();
        
        let topPosition = rect.top;
        let leftPosition = sidebarRect.right + 12;
        
        const tooltipHeight = submenu && submenu.children.length > 0 ? 300 : 80;
        const tooltipWidth = 280;
        
        // Adjust position if tooltip would go off screen
        if (topPosition + tooltipHeight > window.innerHeight) {
            topPosition = window.innerHeight - tooltipHeight - 20;
        }
        
        if (leftPosition + tooltipWidth > window.innerWidth) {
            leftPosition = sidebarRect.left - tooltipWidth - 12;
        }
        
        tooltip.style.top = `${Math.max(20, topPosition)}px`;
        tooltip.style.left = `${leftPosition}px`;
        
        // Show tooltip with animation
        requestAnimationFrame(() => {
            tooltip.classList.add('show');
            console.log('Tooltip shown for:', menuText.textContent.trim());
            console.log('Tooltip content:', tooltip.innerHTML);
            console.log('Tooltip position:', tooltip.style.top, tooltip.style.left);
        });
    }

    /**
     * Hide hover tooltip
     */
    function hideHoverTooltip() {
        clearTimeout(state.hoverTimeout);
        
        // Hide all existing tooltips
        const existingTooltips = document.querySelectorAll('.sidebar-hover-tooltip');
        existingTooltips.forEach(tooltip => {
            tooltip.classList.remove('show');
            setTimeout(() => {
                if (tooltip.parentNode) {
                    tooltip.parentNode.removeChild(tooltip);
                }
            }, 200);
        });
        
        // Clear state
        if (state.hoverTooltip) {
            state.hoverTooltip = null;
        }
        state.currentMenuItem = null;
    }

    /**
     * Create hover tooltip element
     */
    function createHoverTooltip() {
        // Always create a new tooltip to avoid conflicts
        const tooltip = document.createElement('div');
        tooltip.className = 'sidebar-hover-tooltip';
        tooltip.setAttribute('role', 'tooltip');
        tooltip.setAttribute('aria-live', 'polite');
        document.body.appendChild(tooltip);
        
        setupTooltipEvents(tooltip);
        state.hoverTooltip = tooltip;
        return tooltip;
    }

    /**
     * Setup tooltip event handlers
     */
    function setupTooltipEvents(tooltip) {
        tooltip.addEventListener('mouseenter', function() {
            clearTimeout(state.hoverTimeout);
        });
        
        tooltip.addEventListener('mouseleave', function(e) {
            const isGoingToSidebar = e.relatedTarget?.closest('#sidebar');
            const isGoingToMenuItem = e.relatedTarget?.closest('.menu-item') === state.currentMenuItem;
            
            if (!isGoingToSidebar && !isGoingToMenuItem) {
                hideHoverTooltip();
            }
        });
        
        tooltip.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                hideHoverTooltip();
            }
        });
    }

    /**
     * Load sidebar content to mobile menu
     */
    function loadSidebarContentToMobileMenu() {
        if (!elements.mobileMenu) return;
        
        const sidebarContent = document.querySelector('#sidebar nav .flex.flex-col');
        const mobileMenuContent = document.querySelector('#mobile-menu .py-4');
        
        if (sidebarContent && mobileMenuContent) {
            // Always update content to ensure it's current
            const clone = sidebarContent.cloneNode(true);
            mobileMenuContent.innerHTML = '';
            mobileMenuContent.appendChild(clone);
            
            // Reinitialize submenu toggles in mobile menu
            setupMobileMenuSubmenus(mobileMenuContent);
            
            console.log('Mobile menu content loaded and submenus initialized');
        }
    }

    /**
     * Setup mobile menu submenus
     */
    function setupMobileMenuSubmenus(container) {
        console.log('Setting up mobile menu submenus...');
        
        const submenuToggleButtons = container.querySelectorAll('.menu-item.has-submenu');
        submenuToggleButtons.forEach(button => {
            button.removeAttribute('onclick');
            
            const submenuId = button.getAttribute('data-submenu');
            if (submenuId) {
                // Ensure arrow icon is visible in mobile menu
                const arrow = button.querySelector('.arrow-icon');
                if (arrow) {
                    arrow.style.display = 'inline-block';
                    arrow.style.visibility = 'visible';
                    arrow.style.opacity = '1';
                    arrow.style.color = 'white';
                    arrow.style.stroke = 'white';
                }
                
                button.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    
                    console.log('Mobile submenu button clicked:', submenuId);
                    
                    const submenu = document.getElementById(submenuId);
                    if (submenu) {
                        const wasHidden = submenu.classList.contains('hidden');
                        submenu.classList.toggle('hidden');
                        this.classList.toggle('expanded');
                        this.classList.toggle('active');
                        
                        const arrow = this.querySelector('.arrow-icon');
                        if (arrow) {
                            const isNowHidden = submenu.classList.contains('hidden');
                            arrow.style.transform = isNowHidden ? '' : 'rotate(180deg)';
                            arrow.style.display = 'inline-block';
                            arrow.style.visibility = 'visible';
                            arrow.style.opacity = '1';
                        }
                        
                        if (!submenu.classList.contains('hidden')) {
                            closeOtherSubmenus(submenuId);
                        }
                        
                        console.log('Mobile submenu toggled:', submenuId, 'now hidden:', submenu.classList.contains('hidden'));
                    }
                });
                
                console.log('Mobile submenu toggle setup for:', submenuId);
            }
        });
    }

    /**
     * Handle keyboard navigation
     */
    function handleKeyboardNavigation(e) {
        if (e.key === 'Escape') {
            hideHoverTooltip();
            closeMobileMenu();
        }
    }

    /**
     * Handle page visibility changes
     */
    function handleVisibilityChange() {
        if (document.hidden) {
            hideHoverTooltip();
        }
    }

    /**
     * Debounce utility function
     */
    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    // Public API
    window.SidebarManager = {
        init: init,
        toggle: toggleSidebar,
        toggleSubmenu: toggleSubmenu,
        hideTooltip: hideHoverTooltip,
        setupSubmenuToggles: setupSubmenuToggles,
        isCollapsed: () => state.isCollapsed,
        isMobile: () => state.isMobile,
        isInitialized: () => state.isInitialized
    };

    // Global function for backward compatibility
    window.toggleSubmenu = toggleSubmenu;
    
    // Global function for sidebar toggle (fallback)
    window.toggleSidebar = toggleSidebar;
    
    // Global function for mobile menu toggle (fallback)
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
