/**
 * Header Handler - Clean and Conflict-Free
 * Manages all header functionality without conflicts
 */

(function() {
    'use strict';
    
    // State management
    let mobileMenuContentLoaded = false;
    let isInitialized = false;
    
    /**
     * Load sidebar content to mobile menu (runs once)
     */
    function loadSidebarContentToMobileMenu() {
        if (mobileMenuContentLoaded) return;
        
        const sidebarContent = document.querySelector('#sidebar nav .flex.flex-col');
        const mobileMenuContent = document.querySelector('#mobile-menu .py-4');
        
        if (sidebarContent && mobileMenuContent) {
            if (mobileMenuContent.children.length > 0) {
                mobileMenuContentLoaded = true;
                return;
            }
            
            try {
                const clone = sidebarContent.cloneNode(true);
                mobileMenuContent.innerHTML = '';
                mobileMenuContent.appendChild(clone);
                mobileMenuContentLoaded = true;
                
                // Reinitialize submenu toggles
                initializeMobileSubmenus(mobileMenuContent);
            } catch (error) {
                console.warn('Failed to clone sidebar content to mobile menu:', error);
            }
        }
    }
    
    /**
     * Initialize submenu toggles in mobile menu - Enhanced to prevent conflicts
     */
    function initializeMobileSubmenus(container) {
        console.log('Initializing mobile submenus...');
        
        const submenuButtons = container.querySelectorAll('.menu-item.has-submenu');
        console.log('Found mobile submenu buttons:', submenuButtons.length);
        
        submenuButtons.forEach((button, index) => {
            // Remove any existing onclick handlers
            button.removeAttribute('onclick');
            
            let submenuId = button.getAttribute('data-submenu');
            if (!submenuId && button.getAttribute('onclick')) {
                const onclickMatch = button.getAttribute('onclick').match(/'([^']+)'/);
                submenuId = onclickMatch ? onclickMatch[1] : null;
            }
            
            if (submenuId) {
                console.log('Setting up mobile submenu ' + (index + 1) + ':', submenuId);
                
                // Ensure arrow icon is visible
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
                    if (!submenu) {
                        console.error('Mobile submenu not found:', submenuId);
                        return;
                    }
                    
                    const wasHidden = submenu.classList.contains('hidden');
                    submenu.classList.toggle('hidden');
                    this.classList.toggle('expanded');
                    this.classList.toggle('active');
                    
                    const arrow = this.querySelector('.arrow-icon');
                    if (arrow) {
                        const isNowHidden = submenu.classList.contains('hidden');
                        arrow.style.transform = isNowHidden ? '' : 'rotate(180deg)';
                        console.log('Mobile arrow rotated for:', submenuId, 'hidden:', isNowHidden);
                    }
                    
                    // Close other submenus
                    if (!submenu.classList.contains('hidden')) {
                        console.log('Opening mobile submenu, closing others');
                        container.querySelectorAll('.submenu').forEach(menu => {
                            if (menu.id !== submenuId && !menu.classList.contains('hidden')) {
                                menu.classList.add('hidden');
                                const menuButton = container.querySelector('[data-submenu="' + menu.id + '"]');
                                if (menuButton) {
                                    menuButton.classList.remove('active', 'expanded');
                                    const menuArrow = menuButton.querySelector('.arrow-icon');
                                    if (menuArrow) menuArrow.style.transform = '';
                                }
                            }
                        });
                    }
                    
                    console.log('Mobile submenu toggle completed for:', submenuId);
                });
            } else {
                console.warn('Mobile submenu button without ID:', button);
            }
        });
        
        console.log('Mobile submenus initialization completed');
    }
    
    /**
     * Initialize mobile menu toggle - Clean version
     */
    function initializeMobileMenu() {
        const mobileMenuToggle = document.getElementById('nexsy-mobile-menu-toggle');
        const mobileMenu = document.getElementById('nexsy-mobile-menu');
        const closeMobileMenu = document.getElementById('nexsy-close-mobile-menu');
        const mobileMenuOverlay = document.getElementById('nexsy-mobile-menu-overlay');
        
        if (!mobileMenuToggle || !mobileMenu) return;
        
        // Clean event listener setup
        function handleMenuToggle(e) {
            e.preventDefault();
            e.stopPropagation();
            
            if (window.innerWidth < 768) {
                // Mobile behavior
                const wasOpen = mobileMenu.classList.contains('open');
                mobileMenu.classList.toggle('open');
                
                if (!wasOpen) {
                    document.body.classList.add('overflow-hidden');
                    loadSidebarContentToMobileMenu();
                } else {
                    document.body.classList.remove('overflow-hidden');
                }
            } else {
                // Desktop behavior - toggle sidebar
                const sidebar = document.getElementById('sidebar');
                const mainContent = document.getElementById('main-content');
                
                if (sidebar && mainContent) {
                    const wasCollapsed = sidebar.classList.contains('collapsed');
                    sidebar.classList.toggle('collapsed');
                    mainContent.classList.toggle('sidebar-collapsed');
                    
                    // Store state in localStorage
                    const isNowCollapsed = sidebar.classList.contains('collapsed');
                    localStorage.setItem('sidebar_collapsed', isNowCollapsed);
                    
                    // Update layout immediately
                    if (isNowCollapsed) {
                        mainContent.style.marginLeft = '3.5rem';
                        mainContent.style.width = 'calc(100% - 3.5rem)';
                        mainContent.style.maxWidth = 'calc(100% - 3.5rem)';
                    } else {
                        mainContent.style.marginLeft = '16rem';
                        mainContent.style.width = 'calc(100% - 16rem)';
                        mainContent.style.maxWidth = 'calc(100% - 16rem)';
                    }
                } else {
                    // Fallback: try to call global toggleSidebar function if it exists
                    if (typeof window.toggleSidebar === 'function') {
                        window.toggleSidebar();
                    }
                }
            }
        }
        
        // Remove existing listeners and add new one
        mobileMenuToggle.removeEventListener('click', handleMenuToggle);
        mobileMenuToggle.addEventListener('click', handleMenuToggle);
        
        // Close menu handlers
        function closeMenu() {
            mobileMenu.classList.remove('open');
            document.body.classList.remove('overflow-hidden');
        }
        
        if (closeMobileMenu) {
            closeMobileMenu.removeEventListener('click', closeMenu);
            closeMobileMenu.addEventListener('click', closeMenu);
        }
        if (mobileMenuOverlay) {
            mobileMenuOverlay.removeEventListener('click', closeMenu);
            mobileMenuOverlay.addEventListener('click', closeMenu);
        }
    }
    
    /**
     * Initialize mobile search toggle - Clean version
     */
    function initializeMobileSearch() {
        const searchToggle = document.getElementById('mobile-search-toggle');
        const searchContainer = document.getElementById('mobile-search-container');
        
        if (!searchToggle || !searchContainer) return;
        
        function handleSearchToggle(e) {
            e.preventDefault();
            e.stopPropagation();
            
            searchContainer.classList.toggle('hidden');
            searchToggle.classList.toggle('active');
            
            if (!searchContainer.classList.contains('hidden')) {
                const searchInput = searchContainer.querySelector('input[name="q"]');
                if (searchInput) {
                    setTimeout(() => searchInput.focus(), 100);
                }
            }
        }
        
        function handleOutsideClick(e) {
            if (!searchContainer.classList.contains('hidden') && 
                !searchContainer.contains(e.target) && 
                !searchToggle.contains(e.target)) {
                searchContainer.classList.add('hidden');
                searchToggle.classList.remove('active');
            }
        }
        
        function handleEscapeKey(e) {
            if (e.key === 'Escape' && !searchContainer.classList.contains('hidden')) {
                searchContainer.classList.add('hidden');
                searchToggle.classList.remove('active');
            }
        }
        
        // Clean event listener setup
        searchToggle.removeEventListener('click', handleSearchToggle);
        searchToggle.addEventListener('click', handleSearchToggle);
        
        document.removeEventListener('click', handleOutsideClick);
        document.addEventListener('click', handleOutsideClick);
        
        document.removeEventListener('keydown', handleEscapeKey);
        document.addEventListener('keydown', handleEscapeKey);
    }
    
    /**
     * Handle window resize
     */
    function handleResize() {
        const mobileMenu = document.getElementById('nexsy-mobile-menu');
        const mobileSearchContainer = document.getElementById('nexsy-mobile-search-container');
        const searchToggle = document.getElementById('nexsy-mobile-search-toggle');
        
        if (window.innerWidth >= 768) {
            if (mobileMenu && mobileMenu.classList.contains('open')) {
                mobileMenu.classList.remove('open');
                document.body.classList.remove('overflow-hidden');
            }
            
            if (mobileSearchContainer && !mobileSearchContainer.classList.contains('hidden')) {
                mobileSearchContainer.classList.add('hidden');
                if (searchToggle) searchToggle.classList.remove('active');
            }
        }
        
        // Fix header responsive issues
        fixHeaderResponsiveIssues();
    }
    
    /**
     * Fix header responsive issues dynamically
     */
    function fixHeaderResponsiveIssues() {
        const header = document.querySelector('header');
        const logo = header?.querySelector('img');
        const logoContainer = header?.querySelector('.flex.items-center:first-child');
        const headerContainer = header?.querySelector('.flex.items-center');
        
        if (!header || !logo || !logoContainer || !headerContainer) return;
        
        const screenWidth = window.innerWidth;
        
        // Apply responsive fixes based on screen size
        if (screenWidth <= 479) {
            // Extra small screens (320px - 479px)
            logo.style.maxWidth = '120px';
            logoContainer.style.maxWidth = '140px';
            logoContainer.style.flexShrink = '0';
            logoContainer.style.marginRight = '0.5rem';
            headerContainer.style.gap = '0.5rem';
        } else if (screenWidth <= 767) {
            // Small screens (480px - 767px)
            logo.style.maxWidth = '140px';
            logoContainer.style.maxWidth = '160px';
            logoContainer.style.flexShrink = '0';
            logoContainer.style.marginRight = '0.75rem';
            headerContainer.style.gap = '0.75rem';
        } else if (screenWidth <= 1023) {
            // Medium screens (768px - 1023px)
            logo.style.maxWidth = '160px';
            logoContainer.style.maxWidth = '200px';
            logoContainer.style.flexShrink = '0';
            logoContainer.style.marginRight = '0.75rem';
            headerContainer.style.gap = '1rem';
        } else {
            // Large screens (1024px+)
            logo.style.maxWidth = '200px';
            logoContainer.style.maxWidth = '250px';
            logoContainer.style.flexShrink = '0';
            logoContainer.style.marginRight = '1rem';
            headerContainer.style.gap = '1.5rem';
        }
        
        // Ensure logo is always visible
        logo.style.objectFit = 'contain';
        logo.style.height = 'auto';
        logo.style.flexShrink = '0';
        
        // Prevent sidebar overlap
        logoContainer.style.zIndex = '10';
        logoContainer.style.position = 'relative';
        
        // Ensure header layout doesn't break
        headerContainer.style.overflow = 'visible';
        headerContainer.style.flexWrap = 'nowrap';
        
        // Fix icon sizing for different screen sizes
        const icons = header.querySelectorAll('.header-icon, .discussion-icon, .notification-icon, #mobile-menu-toggle, #profile-button');
        icons.forEach(icon => {
            if (screenWidth <= 479) {
                icon.style.width = '2rem';
                icon.style.height = '2rem';
                icon.style.minWidth = '2rem';
                icon.style.minHeight = '2rem';
            } else if (screenWidth <= 767) {
                icon.style.width = '2.25rem';
                icon.style.height = '2.25rem';
                icon.style.minWidth = '2.25rem';
                icon.style.minHeight = '2.25rem';
            } else if (screenWidth <= 1023) {
                icon.style.width = '2.75rem';
                icon.style.height = '2.75rem';
                icon.style.minWidth = '2.75rem';
                icon.style.minHeight = '2.75rem';
            } else {
                icon.style.width = '3rem';
                icon.style.height = '3rem';
                icon.style.minWidth = '3rem';
                icon.style.minHeight = '3rem';
            }
        });
    }
    
    /**
     * Update header notification counts
     */
    function updateHeaderCounts() {
        if (!document.body) return;
        
        // Skip for unauthenticated users
        if (typeof window.unifiedAuthHandler !== 'undefined') {
            if (!window.unifiedAuthHandler.isUserAuthenticated() || window.unifiedAuthHandler.isFirstVisit()) {
                return;
            }
        }
        
        // Helper function for API calls with retry
        function makeApiCall(url, retryCount = 0) {
            const maxRetries = 3;
            const baseDelay = 1000;
            const maxDelay = 8000;
            const delay = Math.min(baseDelay * Math.pow(2, retryCount) + Math.random() * 1000, maxDelay);
            
            return fetch(url, {
                method: 'GET',
                headers: {
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || '',
                    'Content-Type': 'application/json',
                },
                credentials: 'same-origin',
                signal: AbortSignal.timeout(30000)
            })
            .then(response => {
                if (!response.ok) throw new Error('HTTP error! status: ' + response.status);
                return response.json();
            })
            .catch(error => {
                const isRetryable = error.name === 'TypeError' || error.message.includes('Failed to fetch');
                
                if (retryCount < maxRetries && isRetryable) {
                    return new Promise(resolve => {
                        setTimeout(() => resolve(makeApiCall(url, retryCount + 1)), delay);
                    });
                }
                throw error;
            });
        }
        
        // Update message counts
        makeApiCall('/messages/api/count/')
            .then(data => {
                try {
                    const icon = document.querySelector('.discussion-icon');
                    const badge = document.getElementById('messages-count-badge');
                    const indicator = icon?.querySelector('span:first-of-type');
                    
                    if (icon) {
                        icon.title = 'Messages (' + (data.unread_count || 0) + ' unread)';
                        
                        if (indicator) {
                            indicator.style.display = data.unread_count > 0 ? 'block' : 'none';
                        }
                        
                        if (badge) {
                            badge.textContent = data.unread_count > 9 ? '9+' : data.unread_count;
                            badge.style.display = data.unread_count > 0 ? 'flex' : 'none';
                        }
                    }
                } catch (error) {
                    console.error('Error updating message counts:', error);
                }
            })
            .catch((error) => {
                console.error('API error fetching message counts:', error);
                // Silent fail - DO NOT hide icons on API errors
                // Icons should remain visible regardless of API status
            });
        
        // Update notification counts
        makeApiCall('/notifications/api/count/')
            .then(data => {
                try {
                    const icon = document.querySelector('.notification-icon');
                    const badge = document.getElementById('notification-count-badge');
                    const indicator = document.getElementById('notification-indicator');
                    
                    if (icon) {
                        const urgentText = data.urgent_count > 0 ? ', ' + data.urgent_count + ' urgent' : '';
                        icon.title = 'Notifications (' + (data.unread_count || 0) + ' unread' + urgentText + ')';
                        
                        if (indicator) {
                            if (data.unread_count > 0) {
                                indicator.classList.remove('hidden');
                                indicator.classList.toggle('bg-red-500', data.urgent_count > 0);
                                indicator.classList.toggle('bg-orange-500', data.urgent_count === 0);
                                indicator.classList.toggle('animate-pulse', data.urgent_count > 0);
                            } else {
                                indicator.classList.add('hidden');
                            }
                        }
                        
                        if (badge) {
                            if (data.unread_count > 0) {
                                badge.textContent = data.unread_count > 9 ? '9+' : data.unread_count;
                                badge.classList.remove('hidden');
                                badge.classList.toggle('bg-red-500', data.urgent_count > 0);
                                badge.classList.toggle('bg-orange-500', data.urgent_count === 0);
                                badge.classList.toggle('animate-pulse', data.urgent_count > 0);
                            } else {
                                badge.classList.add('hidden');
                            }
                        }
                    }
                } catch (error) {
                    console.error('Error updating notification counts:', error);
                }
            })
            .catch((error) => {
                console.error('API error fetching notification counts:', error);
                // Silent fail - DO NOT hide icons on API errors
                // Icons should remain visible regardless of API status
            });
    }
    
    /**
     * Initialize header - Clean version
     */
    function initializeHeader() {
        if (isInitialized) return;
        isInitialized = true;
        
        // Initialize components
        initializeMobileMenu();
        initializeMobileSearch();
        
        // Apply responsive fixes
        handleResponsiveBreakpoints();
        
        // Setup resize handler
        let resizeTimeout;
        function handleWindowResize() {
            clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(() => {
                handleResize();
                handleResponsiveBreakpoints();
            }, 250);
        }
        
        window.removeEventListener('resize', handleWindowResize);
        window.addEventListener('resize', handleWindowResize);
        
        // Update counts
        updateHeaderCounts();
        setInterval(updateHeaderCounts, 300000);
        
        console.log('Header system initialized successfully');
    }
    
    // Clean initialization
    function safeInitialize() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initializeHeader);
        } else {
            initializeHeader();
        }
    }
    
    safeInitialize();
    
    
    /**
     * Enhanced responsive behavior with better breakpoint handling
     */
    function handleResponsiveBreakpoints() {
        const screenWidth = window.innerWidth;
        const header = document.querySelector('header');
        
        if (!header) return;
        
        // Apply specific fixes for different breakpoints
        if (screenWidth <= 320) {
            // Very small screens - minimal layout
            header.classList.add('header-extra-small');
            header.classList.remove('header-small', 'header-medium', 'header-large');
        } else if (screenWidth <= 480) {
            // Small screens - compact layout
            header.classList.add('header-small');
            header.classList.remove('header-extra-small', 'header-medium', 'header-large');
        } else if (screenWidth <= 768) {
            // Medium screens - balanced layout
            header.classList.add('header-medium');
            header.classList.remove('header-extra-small', 'header-small', 'header-large');
        } else {
            // Large screens - full layout
            header.classList.add('header-large');
            header.classList.remove('header-extra-small', 'header-small', 'header-medium');
        }
        
        // Apply responsive fixes
        fixHeaderResponsiveIssues();
    }
    
    // Expose essential functions globally
    window.HeaderHandler = {
        updateCounts: updateHeaderCounts,
        loadMobileMenu: loadSidebarContentToMobileMenu,
        initializeMobileSubmenus: initializeMobileSubmenus,
        fixResponsiveIssues: fixHeaderResponsiveIssues,
        handleBreakpoints: handleResponsiveBreakpoints,
        reinitialize: function() {
            isInitialized = false;
            initializeHeader();
        }
    };
})();

