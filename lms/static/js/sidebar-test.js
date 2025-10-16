/**
 * Sidebar Test Script
 * Tests sidebar functionality and reports any issues
 */

(function() {
    'use strict';
    
    function testSidebar() {
        console.log('=== SIDEBAR TEST START ===');
        
        // Test 1: Check if sidebar element exists
        const sidebar = document.getElementById('sidebar');
        if (!sidebar) {
            console.error('❌ Sidebar element not found');
            return false;
        }
        console.log('✅ Sidebar element found');
        
        // Test 2: Check sidebar visibility
        const computedStyle = window.getComputedStyle(sidebar);
        const isVisible = computedStyle.display !== 'none' && 
                          computedStyle.visibility !== 'hidden' && 
                          computedStyle.opacity !== '0';
        
        if (!isVisible && window.innerWidth >= 768) {
            console.error('❌ Sidebar not visible on desktop');
            return false;
        }
        console.log('✅ Sidebar visibility check passed');
        
        // Test 3: Check submenu buttons
        const submenuButtons = document.querySelectorAll('.menu-item.has-submenu, [data-submenu]');
        if (submenuButtons.length === 0) {
            console.warn('⚠️ No submenu buttons found');
        } else {
            console.log(`✅ Found ${submenuButtons.length} submenu buttons`);
        }
        
        // Test 4: Check arrow icons
        const arrowIcons = document.querySelectorAll('.arrow-icon');
        let visibleArrows = 0;
        arrowIcons.forEach(arrow => {
            const style = window.getComputedStyle(arrow);
            if (style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0') {
                visibleArrows++;
            }
        });
        
        if (visibleArrows === 0 && submenuButtons.length > 0) {
            console.error('❌ No arrow icons visible');
            return false;
        }
        console.log(`✅ ${visibleArrows} arrow icons visible`);
        
        // Test 5: Check toggle button
        const toggleButton = document.getElementById('mobile-menu-toggle');
        if (!toggleButton) {
            console.error('❌ Toggle button not found');
            return false;
        }
        console.log('✅ Toggle button found');
        
        // Test 6: Check main content positioning
        const mainContent = document.getElementById('main-content');
        if (!mainContent) {
            console.error('❌ Main content not found');
            return false;
        }
        console.log('✅ Main content found');
        
        // Test 7: Check responsive behavior
        const isMobile = window.innerWidth < 768;
        const isDesktop = window.innerWidth >= 768;
        
        if (isDesktop) {
            const sidebarWidth = sidebar.offsetWidth;
            const mainMarginLeft = parseInt(computedStyle.marginLeft) || 0;
            
            if (sidebarWidth === 0) {
                console.error('❌ Sidebar has no width on desktop');
                return false;
            }
            
            if (mainMarginLeft < 200) { // Should be at least 16rem (256px) or 3.5rem (56px) if collapsed
                console.warn('⚠️ Main content margin might be incorrect');
            }
        }
        
        console.log('✅ Responsive behavior check passed');
        
        // Test 8: Check for JavaScript errors
        const originalError = window.onerror;
        let hasErrors = false;
        
        window.onerror = function(msg, url, line, col, error) {
            if (msg.includes('sidebar') || msg.includes('SidebarManager')) {
                hasErrors = true;
                console.error('❌ JavaScript error detected:', msg);
            }
            if (originalError) {
                originalError.apply(this, arguments);
            }
        };
        
        // Reset error handler after a short delay
        setTimeout(() => {
            window.onerror = originalError;
            if (!hasErrors) {
                console.log('✅ No JavaScript errors detected');
            }
        }, 1000);
        
        console.log('=== SIDEBAR TEST COMPLETE ===');
        return true;
    }
    
    // Run test when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', testSidebar);
    } else {
        testSidebar();
    }
    
    // Also run test after a delay to catch any dynamic loading
    setTimeout(testSidebar, 2000);
    
    // Export test function globally
    window.testSidebar = testSidebar;
    
})();
