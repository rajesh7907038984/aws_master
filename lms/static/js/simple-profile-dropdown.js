// Simple Profile Dropdown - Fixed positioning and visibility
document.addEventListener('DOMContentLoaded', function() {
    const profileButton = document.getElementById('profile-button');
    const profileDropdown = document.getElementById('profile-dropdown');
    
    if (!profileButton || !profileDropdown) {
        console.log('Profile elements not found');
        return;
    }
    
    console.log('Profile dropdown script loaded');
    
    // Ensure dropdown is properly positioned
    function fixDropdownPosition() {
        profileDropdown.style.position = 'absolute';
        profileDropdown.style.top = '3rem';
        profileDropdown.style.right = '0';
        profileDropdown.style.zIndex = '9999';
        profileDropdown.style.minWidth = '12rem';
        profileDropdown.style.maxWidth = 'calc(100vw - 2rem)';
        profileDropdown.style.boxShadow = '0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)';
        profileDropdown.style.backgroundColor = 'white';
        profileDropdown.style.borderRadius = '0.75rem';
        profileDropdown.style.border = '1px solid #e5e7eb';
    }
    
    // Fix positioning on load
    fixDropdownPosition();
    
    // Toggle dropdown on button click
    profileButton.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        
        console.log('Profile button clicked');
        
        // Fix positioning before showing
        fixDropdownPosition();
        
        if (profileDropdown.classList.contains('hidden')) {
            // Show dropdown
            profileDropdown.classList.remove('hidden');
            profileDropdown.style.display = 'block';
            profileDropdown.style.visibility = 'visible';
            profileDropdown.style.opacity = '1';
            console.log('Dropdown shown');
        } else {
            // Hide dropdown
            profileDropdown.classList.add('hidden');
            profileDropdown.style.display = 'none';
            profileDropdown.style.visibility = 'hidden';
            profileDropdown.style.opacity = '0';
            console.log('Dropdown hidden');
        }
    });
    
    // Close dropdown when clicking outside
    document.addEventListener('click', function(e) {
        if (!profileButton.contains(e.target) && !profileDropdown.contains(e.target)) {
            profileDropdown.classList.add('hidden');
            profileDropdown.style.display = 'none';
            profileDropdown.style.visibility = 'hidden';
            profileDropdown.style.opacity = '0';
            console.log('Dropdown closed via click outside');
        }
    });
    
    // Close dropdown on escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            profileDropdown.classList.add('hidden');
            profileDropdown.style.display = 'none';
            profileDropdown.style.visibility = 'hidden';
            profileDropdown.style.opacity = '0';
            console.log('Dropdown closed via escape key');
        }
    });
    
    // Fix positioning on window resize
    window.addEventListener('resize', function() {
        fixDropdownPosition();
    });
});
