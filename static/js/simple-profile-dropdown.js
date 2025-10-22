/**
 * Simple Profile Dropdown Handler
 * Handles the profile dropdown menu functionality without Alpine.js
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log(' Simple Profile Dropdown Handler Loading...');
    
    // Get profile elements
    const profileButton = document.getElementById('profile-button');
    const profileDropdown = document.getElementById('profile-dropdown');
    const profileContainer = document.getElementById('profile-container');
    
    // Check if elements exist
    if (!profileButton || !profileDropdown || !profileContainer) {
        console.error(' Profile dropdown elements not found:', {
            profileButton: !!profileButton,
            profileDropdown: !!profileDropdown,
            profileContainer: !!profileContainer
        });
        return;
    }
    
    console.log(' Profile dropdown elements found');
    
    // Track dropdown state
    let isDropdownOpen = false;
    
    // Function to show dropdown
    function showDropdown() {
        if (!profileDropdown) return;
        
        profileDropdown.style.display = 'block';
        profileDropdown.style.visibility = 'visible';
        profileDropdown.style.opacity = '1';
        profileDropdown.classList.remove('hidden');
        isDropdownOpen = true;
        
        console.log('📂 Profile dropdown opened');
    }
    
    // Function to hide dropdown
    function hideDropdown() {
        if (!profileDropdown) return;
        
        profileDropdown.style.display = 'none';
        profileDropdown.style.visibility = 'hidden';
        profileDropdown.style.opacity = '0';
        profileDropdown.classList.add('hidden');
        isDropdownOpen = false;
        
        console.log('📁 Profile dropdown closed');
    }
    
    // Function to toggle dropdown
    function toggleDropdown() {
        if (isDropdownOpen) {
            hideDropdown();
        } else {
            showDropdown();
        }
    }
    
    // Add click event listener to profile button
    profileButton.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        
        console.log('🖱️ Profile button clicked');
        toggleDropdown();
    });
    
    // Add touch event listener for mobile devices
    profileButton.addEventListener('touchend', function(e) {
        e.preventDefault();
        e.stopPropagation();
        
        console.log('📱 Profile button touched');
        toggleDropdown();
    });
    
    // Close dropdown when clicking outside
    document.addEventListener('click', function(e) {
        if (isDropdownOpen && profileContainer && !profileContainer.contains(e.target)) {
            hideDropdown();
        }
    });
    
    // Close dropdown on escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && isDropdownOpen) {
            hideDropdown();
        }
    });
    
    // Handle window resize
    window.addEventListener('resize', function() {
        if (isDropdownOpen) {
            // Reposition dropdown if needed
            setTimeout(function() {
                if (isDropdownOpen) {
                    // Ensure dropdown is still visible and properly positioned
                    const rect = profileButton.getBoundingClientRect();
                    const dropdownRect = profileDropdown.getBoundingClientRect();
                    
                    // Check if dropdown goes off screen
                    if (dropdownRect.right > window.innerWidth) {
                        profileDropdown.style.right = '0';
                        profileDropdown.style.left = 'auto';
                    }
                    
                    if (dropdownRect.bottom > window.innerHeight) {
                        profileDropdown.style.top = 'auto';
                        profileDropdown.style.bottom = '100%';
                        profileDropdown.style.marginBottom = '0.5rem';
                    }
                }
            }, 100);
        }
    });
    
    // Handle dropdown menu item clicks
    const dropdownItems = profileDropdown.querySelectorAll('a, button');
    dropdownItems.forEach(function(item) {
        item.addEventListener('click', function(e) {
            // Don't prevent default for form submissions or links
            if (item.tagName === 'BUTTON' && item.type === 'submit') {
                // Allow form submission
                return;
            }
            
            if (item.tagName === 'A' && item.href) {
                // Allow navigation
                return;
            }
            
            // For other buttons, close dropdown after a short delay
            setTimeout(function() {
                hideDropdown();
            }, 150);
        });
    });
    
    // Mobile-specific improvements
    if (window.innerWidth <= 768) {
        // Add touch-friendly styles
        profileButton.style.minHeight = '44px';
        profileButton.style.minWidth = '44px';
        
        // Improve dropdown positioning on mobile
        profileDropdown.style.maxWidth = 'calc(100vw - 2rem)';
        profileDropdown.style.right = '0';
    }
    
    // Handle orientation change
    window.addEventListener('orientationchange', function() {
        setTimeout(function() {
            if (isDropdownOpen) {
                hideDropdown();
            }
        }, 100);
    });
    
    console.log(' Simple Profile Dropdown Handler Loaded Successfully');
});

// Export functions for external use
window.ProfileDropdown = {
    show: function() {
        const dropdown = document.getElementById('profile-dropdown');
        if (dropdown) {
            dropdown.style.display = 'block';
            dropdown.style.visibility = 'visible';
            dropdown.style.opacity = '1';
            dropdown.classList.remove('hidden');
        }
    },
    hide: function() {
        const dropdown = document.getElementById('profile-dropdown');
        if (dropdown) {
            dropdown.style.display = 'none';
            dropdown.style.visibility = 'hidden';
            dropdown.style.opacity = '0';
            dropdown.classList.add('hidden');
        }
    },
    toggle: function() {
        const dropdown = document.getElementById('profile-dropdown');
        if (dropdown) {
            if (dropdown.classList.contains('hidden')) {
                this.show();
            } else {
                this.hide();
            }
        }
    }
};
