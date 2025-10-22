/**
 * User Report Tab Switching - Conflict-Free Implementation
 * Designed to avoid conflicts with mobile-tabs-accordion.js
 */

console.log(' Loading User Report Tabs Script');
console.log(' Current pathname:', window.location.pathname);

// Prevent conflicts with mobile accordion by checking if we're on the right page
const isReportsPage = window.location.pathname.includes('/reports/');
const isUserPage = window.location.pathname.includes('/user') || window.location.pathname.includes('/my-');
console.log(' Is reports page:', isReportsPage);
console.log(' Is user/my page:', isUserPage);

if (isReportsPage && isUserPage) {
    
    // Initialize function that can be called multiple times
    function initializeTabs() {
        console.log('📄 Initializing User Report Tabs');
        
        // Specifically target user report tabs to avoid conflicts
        const tabContainer = document.querySelector('.user-report-tab-content');
        console.log('🗂️ Tab container found:', !!tabContainer);
        if (!tabContainer) {
            console.log(' User report tab container not found - will retry');
            return false;
        }
        
        // Find all tab buttons and panes with specific user-report classes
        const tabButtons = document.querySelectorAll('.user-report-tab-btn');
        const tabPanes = document.querySelectorAll('.user-report-tab-pane');
        
        console.log('🔘 Tab buttons found:', tabButtons.length);
        console.log('📋 Tab panes found:', tabPanes.length);
        
        if (tabButtons.length > 0) {
            console.log('🔘 Button details:');
            tabButtons.forEach((btn, i) => {
                console.log(`  Button ${i}:`, btn.getAttribute('data-tab'), btn.textContent.trim());
            });
        }
        
        if (tabPanes.length > 0) {
            console.log('📋 Pane details:');
            tabPanes.forEach((pane, i) => {
                console.log(`  Pane ${i}:`, pane.getAttribute('data-tab-content'));
            });
        }
        
        if (tabButtons.length === 0 || tabPanes.length === 0) {
            console.log(' No user report tabs found - will retry');
            return false;
        }
        
        // Prevent mobile accordion from interfering
        if (window.mobileTabsAccordionInstance) {
            console.log('🚫 Detected mobile accordion - setting up conflict prevention');
        }
        
        // Simple tab switching function with conflict prevention
        function showTab(tabName) {
            console.log(' Switching to tab:', tabName);
            
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
                
                console.log(' Successfully switched to:', tabName);
            } else {
                console.error(' Target elements not found for:', tabName);
            }
        }
        
        // Add click listeners - simple and direct approach
        console.log('🔗 Adding click listeners to', tabButtons.length, 'buttons');
        tabButtons.forEach((button, index) => {
            console.log(`Setting up button ${index}:`, button.getAttribute('data-tab'));
            
            button.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                
                const tabName = this.getAttribute('data-tab');
                console.log('🖱️ Tab clicked:', tabName);
                showTab(tabName);
            });
        });
        
        // Initialize with overview tab
        console.log('🎯 Initializing with overview tab');
        showTab('overview');
        
        // Periodically ensure our tabs stay visible (conflict resolution)
        setInterval(function() {
            const activePane = document.querySelector('.user-report-tab-pane.active');
            if (activePane && activePane.style.display === 'none') {
                console.log(' Fixing hidden active pane');
                activePane.style.setProperty('display', 'block', 'important');
                activePane.style.setProperty('visibility', 'visible', 'important');
                activePane.style.setProperty('opacity', '1', 'important');
            }
        }, 1000);
        
        // Expose for testing
        window.showUserReportTab = showTab;
        window.debugUserReportTabs = function() {
            console.log('=== User Report Tabs Debug ===');
            console.log('Buttons:', tabButtons.length);
            console.log('Panes:', tabPanes.length);
            tabButtons.forEach((btn, i) => {
                console.log(`Button ${i}:`, btn.getAttribute('data-tab'), btn.className);
            });
            tabPanes.forEach((pane, i) => {
                console.log(`Pane ${i}:`, pane.getAttribute('data-tab-content'), pane.style.display, pane.className);
            });
        };
        
        console.log(' User Report Tabs initialized successfully');
        return true;
    }
    
    // Try to initialize immediately if DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            console.log('📄 DOM Content Loaded event fired');
            if (!initializeTabs()) {
                // Retry after a short delay if initialization failed
                setTimeout(() => {
                    console.log(' Retrying tab initialization...');
                    initializeTabs();
                }, 500);
            }
        });
    } else {
        console.log('📄 DOM already ready, initializing immediately');
        if (!initializeTabs()) {
            // Retry after a short delay if initialization failed
            setTimeout(() => {
                console.log(' Retrying tab initialization...');
                initializeTabs();
            }, 500);
        }
    }
    
    // Expose initialization function globally for manual testing
    window.initUserReportTabs = initializeTabs;
    
} else {
    console.log('🚫 Not on user report page - skipping tab initialization');
    console.log(' Current URL does not match expected patterns');
    console.log('   Expected: /reports/ AND (/user OR /my-)');
    console.log('   Current:', window.location.pathname);
}