/**
 * Sidebar Layout Fix - Prevents sidebar overlap issues
 * Ensures proper spacing and responsive behavior
 */
(function() {
    'use strict';
    
    const SidebarLayoutFix = {
        init: function() {
            this.setupLayoutHandlers();
            this.handleInitialLayout();
            this.setupResizeHandler();
            this.setupSidebarToggleHandler();
        },
        
        setupLayoutHandlers: function() {
            // Ensure layout is correct on page load
            document.addEventListener('DOMContentLoaded', () => {
                this.fixLayout();
            });
            
            // Fix layout when window loads
            window.addEventListener('load', () => {
                this.fixLayout();
            });
        },
        
        handleInitialLayout: function() {
            // Fix layout immediately if DOM is already loaded
            if (document.readyState === 'complete' || document.readyState === 'interactive') {
                this.fixLayout();
            }
        },
        
        setupResizeHandler: function() {
            let resizeTimeout;
            window.addEventListener('resize', () => {
                clearTimeout(resizeTimeout);
                resizeTimeout = setTimeout(() => {
                    this.fixLayout();
                }, 150);
            });
        },
        
        setupSidebarToggleHandler: function() {
            // Listen for sidebar toggle events
            document.addEventListener('click', (e) => {
                if (e.target.closest('[data-sidebar-toggle]') || 
                    e.target.closest('#sidebar-toggle') ||
                    e.target.closest('.sidebar-toggle')) {
                    setTimeout(() => {
                        this.fixLayout();
                    }, 300); // Wait for animation to complete
                }
            });
        },
        
        fixLayout: function() {
            const sidebar = document.getElementById('sidebar');
            const mainContent = document.getElementById('main-content');
            
            if (!sidebar || !mainContent) {
                console.warn('Sidebar or main content element not found');
                return;
            }
            
            const isMobile = window.innerWidth < 768;
            const isCollapsed = sidebar.classList.contains('collapsed');
            
            // Reset classes first
            mainContent.classList.remove('sidebar-collapsed');
            
            if (isMobile) {
                // Mobile layout
                mainContent.style.marginLeft = '0';
                mainContent.style.width = '100%';
                mainContent.style.maxWidth = '100%';
                mainContent.classList.remove('md:ml-[16rem]', 'md:w-[calc(100%-16rem)]');
            } else {
                // Desktop layout
                if (isCollapsed) {
                    mainContent.style.marginLeft = '3.5rem';
                    mainContent.style.width = 'calc(100% - 3.5rem)';
                    mainContent.style.maxWidth = 'calc(100% - 3.5rem)';
                    mainContent.classList.add('sidebar-collapsed');
                } else {
                    mainContent.style.marginLeft = '16rem';
                    mainContent.style.width = 'calc(100% - 16rem)';
                    mainContent.style.maxWidth = 'calc(100% - 16rem)';
                    mainContent.classList.remove('sidebar-collapsed');
                }
            }
            
            // Fix table containers
            this.fixTableContainers();
        },
        
        fixTableContainers: function() {
            const tableContainers = document.querySelectorAll('.responsive-table-wrapper, .responsive-table-wrapper.full-width');
            
            tableContainers.forEach(container => {
                // Reset any problematic styles
                container.style.marginLeft = '0';
                container.style.marginRight = '0';
                container.style.width = '100%';
                container.style.maxWidth = '100%';
                
                // Ensure proper overflow handling
                const table = container.querySelector('table');
                if (table) {
                    const wrapper = container.querySelector('.table-scroll-wrapper, .overflow-x-auto');
                    if (wrapper) {
                        wrapper.style.overflowX = 'auto';
                        wrapper.style.width = '100%';
                    }
                }
            });
        }
    };
    
    // Initialize immediately
    SidebarLayoutFix.init();
    
    // Export to global scope
    window.SidebarLayoutFix = SidebarLayoutFix;
})();
