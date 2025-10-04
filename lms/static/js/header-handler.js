/**
 * Header Handler - Manages all header functionality
 * Consolidated from inline scripts to improve maintainability
 */

(function() {
    'use strict';
    
    // Mobile menu content loaded flag
    let mobileMenuContentLoaded = false;
    
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
                console.error('Error loading mobile menu content:', error);
            }
        }
    }
    
    /**
     * Initialize submenu toggles in mobile menu
     */
    function initializeMobileSubmenus(container) {
        const submenuButtons = container.querySelectorAll('.menu-item.has-submenu');
        
        submenuButtons.forEach((button) => {
            button.removeAttribute('onclick');
            
            let submenuId = button.getAttribute('data-submenu');
            if (!submenuId && button.getAttribute('onclick')) {
                const onclickMatch = button.getAttribute('onclick').match(/'([^']+)'/);
                submenuId = onclickMatch ? onclickMatch[1] : null;
            }
            
            if (submenuId) {
                button.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    
                    const submenu = document.getElementById(submenuId);
                    if (!submenu) return;
                    
                    submenu.classList.toggle('hidden');
                    this.classList.toggle('expanded');
                    this.classList.toggle('active');
                    
                    const arrow = this.querySelector('.arrow-icon');
                    if (arrow) {
                        arrow.style.transform = submenu.classList.contains('hidden') ? '' : 'rotate(180deg)';
                    }
                    
                    // Close other submenus
                    if (!submenu.classList.contains('hidden')) {
                        container.querySelectorAll('.submenu').forEach(menu => {
                            if (menu.id !== submenuId && !menu.classList.contains('hidden')) {
                                menu.classList.add('hidden');
                                const menuButton = container.querySelector(`[data-submenu="${menu.id}"]`);
                                if (menuButton) {
                                    menuButton.classList.remove('active', 'expanded');
                                    const menuArrow = menuButton.querySelector('.arrow-icon');
                                    if (menuArrow) menuArrow.style.transform = '';
                                }
                            }
                        });
                    }
                });
            }
        });
    }
    
    /**
     * Initialize mobile menu toggle
     */
    function initializeMobileMenu() {
        const mobileMenuToggle = document.getElementById('mobile-menu-toggle');
        const mobileMenu = document.getElementById('mobile-menu');
        const closeMobileMenu = document.getElementById('close-mobile-menu');
        const mobileMenuOverlay = document.getElementById('mobile-menu-overlay');
        
        if (mobileMenuToggle && mobileMenu) {
            mobileMenuToggle.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                
                if (window.innerWidth < 768) {
                    const wasOpen = mobileMenu.classList.contains('open');
                    mobileMenu.classList.toggle('open');
                    
                    if (!wasOpen) {
                        document.body.classList.add('overflow-hidden');
                        loadSidebarContentToMobileMenu();
                    } else {
                        document.body.classList.remove('overflow-hidden');
                    }
                } else {
                    // Desktop: toggle sidebar
                    if (typeof window.toggleSidebar === 'function') {
                        window.toggleSidebar();
                    }
                }
            });
            
            // Close menu handlers
            const closeMenu = () => {
                mobileMenu.classList.remove('open');
                document.body.classList.remove('overflow-hidden');
            };
            
            if (closeMobileMenu) closeMobileMenu.addEventListener('click', closeMenu);
            if (mobileMenuOverlay) mobileMenuOverlay.addEventListener('click', closeMenu);
        }
    }
    
    /**
     * Initialize mobile search toggle
     */
    function initializeMobileSearch() {
        const searchToggle = document.getElementById('mobile-search-toggle');
        const searchContainer = document.getElementById('mobile-search-container');
        
        if (searchToggle && searchContainer) {
            searchToggle.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                
                searchContainer.classList.toggle('hidden');
                this.classList.toggle('active');
                
                if (!searchContainer.classList.contains('hidden')) {
                    const searchInput = searchContainer.querySelector('input[name="q"]');
                    if (searchInput) {
                        setTimeout(() => searchInput.focus(), 100);
                    }
                }
            });
            
            // Close on outside click
            document.addEventListener('click', function(e) {
                if (!searchContainer.classList.contains('hidden') && 
                    !searchContainer.contains(e.target) && 
                    !searchToggle.contains(e.target)) {
                    searchContainer.classList.add('hidden');
                    searchToggle.classList.remove('active');
                }
            });
            
            // Close on escape
            document.addEventListener('keydown', function(e) {
                if (e.key === 'Escape' && !searchContainer.classList.contains('hidden')) {
                    searchContainer.classList.add('hidden');
                    searchToggle.classList.remove('active');
                }
            });
        }
    }
    
    /**
     * Handle window resize
     */
    function handleResize() {
        const mobileMenu = document.getElementById('mobile-menu');
        const mobileSearchContainer = document.getElementById('mobile-search-container');
        const searchToggle = document.getElementById('mobile-search-toggle');
        
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
                    'Cache-Control': 'no-cache'
                },
                credentials: 'same-origin',
                signal: AbortSignal.timeout(30000)
            })
            .then(response => {
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
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
                const icon = document.querySelector('.discussion-icon');
                const badge = document.getElementById('messages-count-badge');
                const indicator = icon?.querySelector('span:first-of-type');
                
                if (icon) {
                    icon.title = `Messages (${data.unread_count || 0} unread)`;
                    
                    if (indicator) {
                        indicator.style.display = data.unread_count > 0 ? 'block' : 'none';
                    }
                    
                    if (badge) {
                        badge.textContent = data.unread_count > 9 ? '9+' : data.unread_count;
                        badge.style.display = data.unread_count > 0 ? 'flex' : 'none';
                    }
                }
            })
            .catch(() => {
                // Silent fail - DO NOT hide icons on API errors
                // Icons should remain visible regardless of API status
                console.log('API failed but keeping icons visible');
            });
        
        // Update notification counts
        makeApiCall('/notifications/api/count/')
            .then(data => {
                const icon = document.querySelector('.notification-icon');
                const badge = document.getElementById('notification-count-badge');
                const indicator = document.getElementById('notification-indicator');
                
                if (icon) {
                    const urgentText = data.urgent_count > 0 ? `, ${data.urgent_count} urgent` : '';
                    icon.title = `Notifications (${data.unread_count || 0} unread${urgentText})`;
                    
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
            })
            .catch(() => {
                // Silent fail - DO NOT hide icons on API errors
                // Icons should remain visible regardless of API status
                console.log('API failed but keeping icons visible');
            });
    }
    
    /**
     * Initialize header
     */
    function initializeHeader() {
        initializeMobileMenu();
        initializeMobileSearch();
        
        // Setup resize handler
        let resizeTimeout;
        window.addEventListener('resize', function() {
            clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(handleResize, 250);
        });
        
        // Update counts every 5 minutes
        updateHeaderCounts();
        setInterval(updateHeaderCounts, 300000);
    }
    
    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeHeader);
    } else {
        initializeHeader();
    }
    
    // Expose functions globally if needed
    window.HeaderHandler = {
        updateCounts: updateHeaderCounts,
        loadMobileMenu: loadSidebarContentToMobileMenu
    };
})();

