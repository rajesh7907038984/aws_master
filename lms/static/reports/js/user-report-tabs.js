/**
 * User Report Tab Switching - Conflict-Free Implementation
 * Designed to avoid conflicts with mobile-tabs-accordion.js
 */


// Prevent conflicts with mobile accordion by checking if we're on the right page
const isReportsPage = window.location.pathname.includes('/reports/');
const isUserPage = window.location.pathname.includes('/user') || window.location.pathname.includes('/my-');

if (isReportsPage && isUserPage) {
    
    // Initialize function that can be called multiple times
    function initializeTabs() {
        
        // Specifically target user report tabs to avoid conflicts
        const tabContainer = document.querySelector('.user-report-tab-content');
        if (!tabContainer) {
            return false;
        }
        
        // Find all tab buttons and panes with specific user-report classes
        const tabButtons = document.querySelectorAll('.user-report-tab-btn');
        const tabPanes = document.querySelectorAll('.user-report-tab-pane');
        
        
        if (tabButtons.length > 0) {
            tabButtons.forEach((btn, i) => {
                // Initialize tab buttons
            });
        }
        
        if (tabPanes.length > 0) {
            tabPanes.forEach((pane, i) => {
                // Initialize tab panes
            });
        }
        
        if (tabButtons.length === 0 || tabPanes.length === 0) {
            return false;
        }
        
        // Prevent mobile accordion from interfering
        if (window.mobileTabsAccordionInstance) {
            // Mobile accordion instance exists
        }
        
        // Simple tab switching function with conflict prevention
        function showTab(tabName) {
            
            // Hide all user report panes only
            tabPanes.forEach(pane => {
                pane.style.setProperty('display', 'none', 'important');
                pane.classList.remove('active');
            });
            
            // Remove active from all user report buttons only
            tabButtons.forEach(btn => {
                btn.classList.remove('active', 'border-blue-500', 'text-blue-600');
                btn.classList.add('border-transparent', 'text-gray-500');
            });
            
            // Show target pane
            const targetPane = document.querySelector(`.user-report-tab-pane[data-tab-content="${tabName}"]`);
            const targetButton = document.querySelector(`.user-report-tab-btn[data-tab="${tabName}"]`);
            
            if (targetPane && targetButton) {
                targetPane.style.setProperty('display', 'block', 'important');
                targetPane.style.setProperty('visibility', 'visible', 'important');
                targetPane.style.setProperty('opacity', '1', 'important');
                targetPane.classList.add('active');
                
                targetButton.classList.add('active', 'border-blue-500', 'text-blue-600');
                targetButton.classList.remove('border-transparent', 'text-gray-500');
                
            } else {
                console.log('Target pane or button not found for tab:', tabName);
            }
        }
        
        // Add click listeners - simple and direct approach
        tabButtons.forEach((button, index) => {
            button.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                
                const tabName = this.getAttribute('data-tab');
                showTab(tabName);
            });
        });
        
        // Initialize with overview tab
        showTab('overview');
        
        // Periodically ensure our tabs stay visible (conflict resolution)
        setInterval(function() {
            const activePane = document.querySelector('.user-report-tab-pane.active');
            if (activePane && activePane.style.display === 'none') {
                activePane.style.setProperty('display', 'block', 'important');
                activePane.style.setProperty('visibility', 'visible', 'important');
                activePane.style.setProperty('opacity', '1', 'important');
            }
        }, 1000);
        
        // Expose for testing
        window.showUserReportTab = showTab;
        window.debugUserReportTabs = function() {
            tabButtons.forEach((btn, i) => {
                console.log('Tab button', i, btn);
            });
            tabPanes.forEach((pane, i) => {
                console.log('Tab pane', i, pane);
            });
        };
        
        return true;
    }
    
    // Try to initialize immediately if DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            if (!initializeTabs()) {
                // Retry after a short delay if initialization failed
                setTimeout(() => {
                    initializeTabs();
                }, 500);
            }
        });
    } else {
        if (!initializeTabs()) {
            // Retry after a short delay if initialization failed
            setTimeout(() => {
                initializeTabs();
            }, 500);
        }
    }
    
    // Expose initialization function globally for manual testing
    window.initUserReportTabs = initializeTabs;
    
} else {
    // Not on reports page or user page
}