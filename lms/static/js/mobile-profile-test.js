// Mobile Profile Dropdown Test Script
// This script helps test and debug the mobile profile dropdown functionality

(function() {
    'use strict';
    
    console.log('Mobile Profile Dropdown Test Script loaded');
    
    // Test function to check if profile dropdown is working
    function testProfileDropdown() {
        const profileContainer = document.querySelector('[x-data*="isOpen"]');
        const profileButton = profileContainer ? profileContainer.querySelector('button') : null;
        const profileDropdown = profileContainer ? profileContainer.querySelector('[x-show]') : null;
        
        console.log('Profile dropdown test results:');
        console.log('- Profile container found:', !!profileContainer);
        console.log('- Profile button found:', !!profileButton);
        console.log('- Profile dropdown found:', !!profileDropdown);
        
        if (profileContainer) {
            console.log('- Container has x-data:', profileContainer.hasAttribute('x-data'));
            console.log('- Container x-data value:', profileContainer.getAttribute('x-data'));
        }
        
        if (profileButton) {
            console.log('- Button has @click:', profileButton.hasAttribute('@click'));
            console.log('- Button @click value:', profileButton.getAttribute('@click'));
            console.log('- Button z-index:', profileButton.style.zIndex);
        }
        
        if (profileDropdown) {
            console.log('- Dropdown has x-show:', profileDropdown.hasAttribute('x-show'));
            console.log('- Dropdown z-index:', profileDropdown.style.zIndex);
            console.log('- Dropdown display:', profileDropdown.style.display);
            console.log('- Dropdown classes:', profileDropdown.className);
        }
        
        // Test Alpine.js availability
        console.log('- Alpine.js available:', typeof Alpine !== 'undefined');
        if (typeof Alpine !== 'undefined') {
            console.log('- Alpine.js version:', Alpine.version || 'unknown');
        }
        
        // Test mobile detection
        console.log('- Screen width:', window.innerWidth);
        console.log('- Is mobile:', window.innerWidth <= 768);
        
        return {
            container: !!profileContainer,
            button: !!profileButton,
            dropdown: !!profileDropdown,
            alpine: typeof Alpine !== 'undefined',
            mobile: window.innerWidth <= 768
        };
    }
    
    // Run test when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', testProfileDropdown);
    } else {
        testProfileDropdown();
    }
    
    // Make test function globally available
    window.testProfileDropdown = testProfileDropdown;
    
    // Add click event listener to profile button for debugging
    document.addEventListener('click', function(e) {
        const profileButton = e.target.closest('[x-data*="isOpen"] button');
        if (profileButton) {
            console.log('Profile button clicked - debugging info:');
            console.log('- Event target:', e.target);
            console.log('- Event type:', e.type);
            console.log('- Event bubbles:', e.bubbles);
            console.log('- Event cancelable:', e.cancelable);
            console.log('- Event defaultPrevented:', e.defaultPrevented);
            console.log('- Event stopPropagation called:', e.cancelBubble);
        }
    });
    
})();
