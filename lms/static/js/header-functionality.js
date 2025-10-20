/**
 * Header Functionality JavaScript
 * Simplified header functionality extracted from template
 */

document.addEventListener('DOMContentLoaded', function() {
    // Branch Switcher JavaScript
    let branchData = null;
    let isLoading = false;
    
    // Load branch data when dropdown is opened
    const branchMenuButton = document.querySelector('#branch-switcher-button');
    if (branchMenuButton) {
        branchMenuButton.addEventListener('click', function(e) {
            if (!isLoading && !branchData) {
                loadUserBranches();
            }
        });
    }
    
    async function loadUserBranches() {
        if (isLoading) return;
        isLoading = true;
        
        try {
            const response = await fetch(window.branchApiUrl || '/branches/api/user-branches/', {
                method: 'GET',
                headers: {
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || '',
                    'Accept': 'application/json',
                }
            });
            
            if (!response.ok) {
                throw new Error('Failed to load branches');
            }
            
            branchData = await response.json();
            renderBranchOptions();
            updateCurrentBranchDisplay();
            
        } catch (error) {
            renderBranchError();
        } finally {
            isLoading = false;
        }
    }
    
    function renderBranchOptions() {
        const container = document.getElementById('branch-options');
        if (!container || !branchData) return;
        
        let html = '';
        
        branchData.branches.forEach(branch => {
            const isCurrentClass = branch.is_current ? 'bg-blue-50 text-blue-700' : 'text-gray-700 hover:bg-gray-50';
            const currentIndicator = branch.is_current ? 
                '<svg class="w-4 h-4 ml-auto text-blue-600" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>' : 
                '';
            
            html += `
                <button 
                    data-branch-id="${branch.id}" data-branch-name="${branch.name.replace(/'/g, "\\'")}" class="branch-switch-btn"
                    class="flex items-center w-full px-4 py-2 text-sm ${isCurrentClass} transition-colors"
                    ${branch.is_current ? 'disabled' : ''}
                >
                    <div class="flex-1 text-left">
                        <div class="font-medium">${branch.name}</div>
                        ${branch.business_name ? `<div class="text-xs text-gray-500">${branch.business_name}</div>` : ''}
                        ${branch.is_primary ? '<div class="text-xs text-blue-600 mt-1">Primary Branch</div>' : ''}
                    </div>
                    ${currentIndicator}
                </button>
            `;
        });

        container.innerHTML = html;
    }
    
    function renderBranchError() {
        const container = document.getElementById('branch-options');
        if (!container) return;
        
        container.innerHTML = `
            <div class="flex items-center justify-center py-4 text-red-600">
                <svg class="w-4 h-4 mr-2" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span class="text-sm">Error loading branches</span>
            </div>
        `;
    }
    
    function updateCurrentBranchDisplay() {
        const display = document.getElementById('current-branch-display');
        if (display && branchData) {
            const currentBranch = branchData.branches.find(b => b.is_current);
            if (currentBranch) {
                display.textContent = currentBranch.name;
            }
        }
    }
    
    // Global functions for button clicks
    window.switchToBranch = async function(branchId, branchName) {
        try {
            const formData = new FormData();
            formData.append('branch_id', branchId);
            formData.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]')?.value || '');
            
            const response = await fetch(window.branchSwitchUrl || '/branches/api/switch/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || '',
                    'Accept': 'application/json',
                }
            });
            
            const data = await response.json();
            
            if (data.success) {
                showBranchMessage(data.message, 'success');
                branchData = null;
                loadUserBranches();
                setTimeout(() => {
                    window.location.reload();
                }, 1000);
            } else {
                showBranchMessage(data.error || 'Failed to switch branch', 'error');
            }
            
        } catch (error) {
            showBranchMessage('Error switching branch', 'error');
        }
    };

    function showBranchMessage(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `fixed top-20 right-4 z-50 px-4 py-2 rounded-lg shadow-lg text-white text-sm max-w-sm ${
            type === 'success' ? 'bg-green-600' : type === 'error' ? 'bg-red-600' : 'bg-blue-600'
        }`;
        toast.textContent = message;
        
        document.body.appendChild(toast);
        
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 3000);
    }
    
    // Mobile menu functionality
    const mobileMenuToggle = document.getElementById('nexsy-mobile-menu-toggle');
    const mobileMenu = document.getElementById('nexsy-mobile-menu');
    const mobileMenuOverlay = document.getElementById('nexsy-mobile-menu-overlay');
    const closeMobileMenu = document.getElementById('nexsy-close-mobile-menu');
    
    let mobileMenuContentLoaded = false;
    
    function loadSidebarContentToMobileMenu() {
        if (mobileMenuContentLoaded) return;
        
        const sidebarContent = document.querySelector('#sidebar nav .flex.flex-col');
        const mobileMenuContent = document.querySelector('#nexsy-mobile-menu-body');
        
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
                
                const submenuButtons = mobileMenuContent.querySelectorAll('.menu-item.has-submenu');
                submenuButtons.forEach(button => {
                    const submenuId = button.getAttribute('data-submenu');
                    if (submenuId) {
                        button.addEventListener('click', function(e) {
                            e.preventDefault();
                            e.stopPropagation();
                            const submenu = document.getElementById(submenuId);
                            if (submenu) {
                                submenu.classList.toggle('hidden');
                                this.classList.toggle('expanded');
                                this.classList.toggle('active');
                                
                                const arrow = this.querySelector('.arrow-icon');
                                if (arrow) {
                                    const isNowHidden = submenu.classList.contains('hidden');
                                    arrow.style.transform = isNowHidden ? '' : 'rotate(180deg)';
                                }
                            }
                        });
                    }
                });
            } catch (error) {
                // Error loading mobile menu content
            }
        }
    }
    
    if (mobileMenuToggle && mobileMenu) {
        const newButton = mobileMenuToggle.cloneNode(true);
        if (mobileMenuToggle.parentNode) {
            mobileMenuToggle.parentNode.replaceChild(newButton, mobileMenuToggle);
        }
        
        newButton.addEventListener('click', function(e) {
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
                const sidebar = document.getElementById('sidebar');
                const mainContent = document.getElementById('main-content');
                
                if (sidebar && mainContent) {
                    const wasCollapsed = sidebar.classList.contains('collapsed');
                    sidebar.classList.toggle('collapsed');
                    mainContent.classList.toggle('sidebar-collapsed');
                    
                    const isNowCollapsed = sidebar.classList.contains('collapsed');
                    localStorage.setItem('sidebar_collapsed', isNowCollapsed);
                    
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
                    if (typeof window.toggleSidebar === 'function') {
                        window.toggleSidebar();
                    }
                }
            }
        });
        
        const closeMenu = () => {
            mobileMenu.classList.remove('open');
            document.body.classList.remove('overflow-hidden');
        };
        
        if (closeMobileMenu) closeMobileMenu.addEventListener('click', closeMenu);
        if (mobileMenuOverlay) mobileMenuOverlay.addEventListener('click', closeMenu);
    }
    
    // Handle resize events
    let resizeDebounceTimer;
    window.addEventListener('resize', function() {
        clearTimeout(resizeDebounceTimer);
        resizeDebounceTimer = setTimeout(function() {
            if (window.innerWidth >= 768) {
                if (mobileMenu && mobileMenu.classList.contains('open')) {
                    mobileMenu.classList.remove('open');
                    document.body.classList.remove('overflow-hidden');
                }
            }
        }, 100);
    });

    // Profile dropdown functionality
    function initializeProfileDropdown() {
        const profileButton = document.getElementById('nexsy-profile-button');
        const profileDropdown = document.getElementById('nexsy-profile-dropdown');
        const profileContainer = document.getElementById('nexsy-profile-container');
        
        if (!profileButton || !profileDropdown || !profileContainer) {
            return false;
        }
        
        let isProfileOpen = false;
        
        function toggleProfileDropdown() {
            isProfileOpen = !isProfileOpen;
            
            if (isProfileOpen) {
                profileDropdown.classList.remove('hidden');
                profileDropdown.style.display = 'block';
                profileDropdown.style.visibility = 'visible';
                profileDropdown.style.opacity = '1';
                profileDropdown.style.transform = 'translateY(0)';
            } else {
                profileDropdown.classList.add('hidden');
                profileDropdown.style.display = 'none';
                profileDropdown.style.visibility = 'hidden';
                profileDropdown.style.opacity = '0';
                profileDropdown.style.transform = 'translateY(-5px)';
            }
        }
        
        function closeProfileDropdown() {
            isProfileOpen = false;
            profileDropdown.classList.add('hidden');
            profileDropdown.style.display = 'none';
            profileDropdown.style.visibility = 'hidden';
            profileDropdown.style.opacity = '0';
            profileDropdown.style.transform = 'translateY(-5px)';
        }
        
        const newProfileButton = profileButton.cloneNode(true);
        profileButton.parentNode.replaceChild(newProfileButton, profileButton);
        
        newProfileButton.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            toggleProfileDropdown();
        });
        
        document.addEventListener('click', function(e) {
            if (isProfileOpen && !profileContainer.contains(e.target)) {
                closeProfileDropdown();
            }
        });
        
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && isProfileOpen) {
                closeProfileDropdown();
            }
        });
        
        return true;
    }
    
    function initProfileDropdownWithRetry() {
        let attempts = 0;
        const maxAttempts = 5;
        
        function tryInit() {
            attempts++;
            
            if (initializeProfileDropdown()) {
                return;
            }
            
            if (attempts < maxAttempts) {
                setTimeout(tryInit, 100);
            }
        }
        
        tryInit();
    }
    
    initProfileDropdownWithRetry();
    
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initProfileDropdownWithRetry);
    }
    
    // Branch switcher functionality
    const branchSwitcherButton = document.getElementById('branch-switcher-button');
    const branchSwitcherMenu = document.getElementById('branch-switcher-menu');
    const branchArrow = document.getElementById('branch-arrow');
    
    if (branchSwitcherButton && branchSwitcherMenu && branchArrow) {
        let isBranchMenuOpen = false;
        
        function toggleBranchMenu() {
            isBranchMenuOpen = !isBranchMenuOpen;
            if (isBranchMenuOpen) {
                branchSwitcherMenu.classList.remove('hidden');
                branchSwitcherMenu.style.display = 'block';
                branchSwitcherMenu.style.visibility = 'visible';
                branchSwitcherMenu.style.opacity = '1';
                branchArrow.style.transform = 'rotate(180deg)';
            } else {
                branchSwitcherMenu.classList.add('hidden');
                branchSwitcherMenu.style.display = 'none';
                branchSwitcherMenu.style.visibility = 'hidden';
                branchSwitcherMenu.style.opacity = '0';
                branchArrow.style.transform = 'rotate(0deg)';
            }
        }
        
        function closeBranchMenu() {
            isBranchMenuOpen = false;
            branchSwitcherMenu.classList.add('hidden');
            branchSwitcherMenu.style.display = 'none';
            branchSwitcherMenu.style.visibility = 'hidden';
            branchSwitcherMenu.style.opacity = '0';
            branchArrow.style.transform = 'rotate(0deg)';
        }
        
        branchSwitcherButton.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            toggleBranchMenu();
        });
        
        document.addEventListener('click', function(e) {
            if (isBranchMenuOpen && !branchSwitcherButton.contains(e.target) && !branchSwitcherMenu.contains(e.target)) {
                closeBranchMenu();
            }
        });
    }
    
    // Handle window resize
    let resizeTimer;
    window.addEventListener('resize', function() {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function() {
            if (window.innerWidth <= 768) {
                const profileButton = document.getElementById('nexsy-profile-button');
                if (profileButton) {
                    profileButton.style.touchAction = 'manipulation';
                }
            }
        }, 250);
    });
});
