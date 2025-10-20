// Admin Sidebar Functionality
document.addEventListener('DOMContentLoaded', function() {
    // Elements
    var sidebarToggle = document.getElementById('sidebar-toggle');
    var sidebarToggleHeader = document.getElementById('sidebar-toggle-header');
    var mobileSidebarToggle = document.getElementById('mobile-sidebar-toggle');
    var sidebar = document.getElementById('sidebar');
    var mainContent = document.getElementById('main-content');
    
    // Toggle sidebar function
    function toggleSidebar() {
        sidebar.classList.toggle('sidebar-collapsed');
        mainContent.classList.toggle('main-content-expanded');
        
        // Toggle visibility of text in sidebar items
        var sidebarTextElements = document.querySelectorAll('.sidebar-text');
        for (var i = 0; i < sidebarTextElements.length; i++) {
            sidebarTextElements[i].classList.toggle('hidden');
        }
        
        // Adjust icon containers
        var sidebarIconElements = document.querySelectorAll('.sidebar-icon');
        for (var i = 0; i < sidebarIconElements.length; i++) {
            var el = sidebarIconElements[i];
            el.classList.toggle('w-full');
            el.classList.toggle('justify-center');
        }
        
        // Update toggle icon
        var icon = sidebarToggle.querySelector('i');
        if (icon) {
            if (sidebar.classList.contains('sidebar-collapsed')) {
                icon.classList.remove('fa-chevron-left');
                icon.classList.add('fa-chevron-right');
            } else {
                icon.classList.remove('fa-chevron-right');
                icon.classList.add('fa-chevron-left');
            }
        }
        
        // Store sidebar state in localStorage
        localStorage.setItem('admin_sidebar_collapsed', sidebar.classList.contains('sidebar-collapsed'));
    }
    
    // Toggle sidebar on desktop
    if (sidebarToggle && sidebar && mainContent) {
        sidebarToggle.addEventListener('click', function(e) {
            e.preventDefault();
            toggleSidebar();
        });
    }
    
    // Toggle sidebar from header button
    if (sidebarToggleHeader && sidebar && mainContent) {
        sidebarToggleHeader.addEventListener('click', toggleSidebar);
    }
    
    // Toggle sidebar on mobile
    if (mobileSidebarToggle && sidebar) {
        mobileSidebarToggle.addEventListener('click', function() {
            sidebar.classList.toggle('mobile-open');
            document.body.classList.toggle('overflow-hidden');
            
            // Add overlay when sidebar is open on mobile
            let overlay = document.getElementById('mobile-sidebar-overlay');
            if (sidebar.classList.contains('mobile-open')) {
                if (!overlay) {
                    overlay = document.createElement('div');
                    overlay.id = 'mobile-sidebar-overlay';
                    overlay.className = 'fixed inset-0 bg-black bg-opacity-50 z-20 md:hidden';
                    document.body.appendChild(overlay);
                    
                    // Close sidebar when clicking on overlay
                    overlay.addEventListener('click', function() {
                        sidebar.classList.remove('mobile-open');
                        document.body.classList.remove('overflow-hidden');
                        overlay.remove();
                    });
                }
            } else if (overlay) {
                overlay.remove();
            }
        });
    }
    
    // Close sidebar when clicking outside on mobile
    document.addEventListener('click', function(event) {
        if (window.innerWidth <= 768 && 
            sidebar && 
            sidebar.classList.contains('mobile-open') && 
            !sidebar.contains(event.target) && 
            event.target !== mobileSidebarToggle) {
            sidebar.classList.remove('mobile-open');
            document.body.classList.remove('overflow-hidden');
            
            // Remove overlay
            const overlay = document.getElementById('mobile-sidebar-overlay');
            if (overlay) {
                overlay.remove();
            }
        }
    });
    
    // Restore sidebar state from localStorage
    var savedState = localStorage.getItem('admin_sidebar_collapsed');
    if (savedState === 'true' && window.innerWidth > 768) {
        toggleSidebar();
    }
    
    // Handle window resize
    window.addEventListener('resize', function() {
        if (window.innerWidth <= 768) {
            sidebar.classList.add('mobile-sidebar');
            sidebar.classList.remove('sidebar-collapsed');
            mainContent.classList.remove('main-content-expanded');
        } else {
            sidebar.classList.remove('mobile-sidebar', 'mobile-open');
            var overlay = document.getElementById('mobile-sidebar-overlay');
            if (overlay) overlay.remove();
            
            // Restore desktop collapsed state
            var savedState = localStorage.getItem('admin_sidebar_collapsed');
            if (savedState === 'true') {
                sidebar.classList.add('sidebar-collapsed');
                mainContent.classList.add('main-content-expanded');
            }
        }
    });
    
    // Submenu toggles
    var submenuToggles = document.querySelectorAll('.submenu-toggle');
    for (var i = 0; i < submenuToggles.length; i++) {
        var toggle = submenuToggles[i];
        toggle.addEventListener('click', function(e) {
            e.preventDefault();
            var submenuId = this.getAttribute('data-submenu');
            var submenu = document.getElementById(submenuId);
            if (submenu) {
                submenu.classList.toggle('open');
                
                // Toggle icon
                var icon = this.querySelector('.toggle-icon');
                if (icon) {
                    icon.classList.toggle('fa-chevron-down');
                    icon.classList.toggle('fa-chevron-up');
                }
            }
        });
    }
    
    // Get current URL path
    var currentPath = window.location.pathname;
    
    // Get user's role from the dashboard link
    var dashboardLink = document.querySelector('[data-role]');
    var userRole = dashboardLink ? dashboardLink.getAttribute('data-role') : null;
    
    // Find all sidebar menu items
    var menuItems = document.querySelectorAll('.sidebar-menu-item, a[href]');
    
    for (var i = 0; i < menuItems.length; i++) {
        var item = menuItems[i];
        // Get the href attribute
        var link = item.getAttribute('href');
        
        // Add click handler to prevent unnecessary reloading
        item.addEventListener('click', function(e) {
            if (link === currentPath) {
                e.preventDefault(); // Prevent reload if already on the page
                return;
            }
            
            // Check if it's a dashboard link and matches the user's role
            if (link && link.includes('dashboard') && userRole) {
                var isDashboardMatch = (
                    (userRole === 'superadmin' && link.includes('dashboard_superadmin')) ||
                    (userRole === 'admin' && link.includes('dashboard_admin')) ||
                    (userRole === 'instructor' && link.includes('dashboard_instructor')) ||
                    (userRole === 'learner' && link === '/dashboard/')
                );
                
                if (isDashboardMatch && link === currentPath) {
                    e.preventDefault(); // Prevent reload if already on the correct dashboard
                }
            }
        });
        
        // Add active class based on current path
        if (link && currentPath === link) {
            item.classList.add('active');
            // Also add active class to parent li if it exists
            var parentLi = item.closest('li');
            if (parentLi) {
                parentLi.classList.add('active');
            }
        }
        // Special case for dashboard
        else if (currentPath.includes('/dashboard/') && link && link.includes('dashboard')) {
            var isDashboardMatch = (
                (userRole === 'superadmin' && currentPath.includes('superadmin')) ||
                (userRole === 'admin' && currentPath.includes('admin')) ||
                (userRole === 'instructor' && currentPath.includes('instructor')) ||
                (userRole === 'learner' && currentPath === '/dashboard/')
            );
            
            if (isDashboardMatch) {
                item.classList.add('active');
                var parentLi = item.closest('li');
                if (parentLi) {
                    parentLi.classList.add('active');
                }
            }
        }
    }
    
    // Auto-hide messages after 5 seconds
    var messages = document.querySelectorAll('.animate-fade-in-down');
    if (messages.length > 0) {
        setTimeout(function() {
            for (var i = 0; i < messages.length; i++) {
                var message = messages[i];
                message.style.opacity = '0';
                message.style.transform = 'translateY(-10px)';
                message.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
                
                setTimeout(function() {
                    message.remove();
                }, 500);
            }
        }, 5000);
    }
}); 