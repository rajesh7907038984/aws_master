/**
 * Sidebar Submenu Fix Script v1.0
 * Fixes submenu not showing issues
 */

(function() {
    'use strict';
    
    
    // Wait for DOM to be ready
    function waitForDOM() {
        return new Promise((resolve) => {
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', resolve);
            } else {
                resolve();
            }
        });
    }
    
    // Fix submenu functionality - only run if SidebarManager is not available
    async function fixSubmenuFunctionality() {
        await waitForDOM();
        
        // Check if SidebarManager is available and initialized
        if (window.SidebarManager && window.SidebarManager.isInitialized) {
            return;
        }
        
        
        // Find all submenu buttons
        const submenuButtons = document.querySelectorAll('.menu-item.has-submenu, [data-submenu]');
        
        submenuButtons.forEach((button, index) => {
            const submenuId = button.getAttribute('data-submenu');
            
            if (!submenuId) return;
            
            // Skip if already has proper event handling
            if (button.hasAttribute('data-sidebar-manager-initialized')) {
                return;
            }
            
            // Remove existing event listeners
            const newButton = button.cloneNode(true);
            if (button.parentNode) {
                button.parentNode.replaceChild(newButton, button);
                
                // Ensure arrow icon is visible
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
                }
                
                // Add click event listener
                newButton.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    
                    
                    const submenu = document.getElementById(submenuId);
                    if (!submenu) {
                        return;
                    }
                    
                    const wasHidden = submenu.classList.contains('hidden');
                    
                    // Toggle submenu
                    submenu.classList.toggle('hidden');
                    newButton.classList.toggle('active');
                    newButton.classList.toggle('expanded');
                    
                    // Rotate arrow
                    if (arrow) {
                        const isNowHidden = submenu.classList.contains('hidden');
                        arrow.style.transform = isNowHidden ? '' : 'rotate(180deg)';
                    }
                    
                    // Close other submenus if opening this one
                    if (!submenu.classList.contains('hidden')) {
                        closeOtherSubmenus(submenuId);
                    }
                    
                });
                
            }
        });
        
    }
    
    // Close other submenus
    function closeOtherSubmenus(currentSubmenuId) {
        const allSubmenus = document.querySelectorAll('.submenu');
        allSubmenus.forEach(menu => {
            if (menu.id !== currentSubmenuId && !menu.classList.contains('hidden')) {
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
    
    // Initialize fix
    fixSubmenuFunctionality();
    
    // Re-run fix after a delay to catch dynamically loaded content
    setTimeout(fixSubmenuFunctionality, 1000);
    
    // Export functions for global access
    window.SidebarSubmenuFix = {
        fixSubmenuFunctionality,
        closeOtherSubmenus
    };
    
})();
