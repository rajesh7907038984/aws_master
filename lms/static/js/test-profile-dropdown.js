// Test Profile Dropdown - Debug script
document.addEventListener('DOMContentLoaded', function() {
    console.log('🧪 Testing profile dropdown...');
    
    const profileButton = document.getElementById('profile-button');
    const profileDropdown = document.getElementById('profile-dropdown');
    const profileContainer = document.getElementById('profile-container');
    
    console.log('Profile button found:', !!profileButton);
    console.log('Profile dropdown found:', !!profileDropdown);
    console.log('Profile container found:', !!profileContainer);
    
    if (profileButton) {
        console.log('Profile button styles:', {
            display: window.getComputedStyle(profileButton).display,
            visibility: window.getComputedStyle(profileButton).visibility,
            opacity: window.getComputedStyle(profileButton).opacity,
            zIndex: window.getComputedStyle(profileButton).zIndex
        });
    }
    
    if (profileDropdown) {
        console.log('Profile dropdown styles:', {
            display: window.getComputedStyle(profileDropdown).display,
            visibility: window.getComputedStyle(profileDropdown).visibility,
            opacity: window.getComputedStyle(profileDropdown).opacity,
            position: window.getComputedStyle(profileDropdown).position,
            top: window.getComputedStyle(profileDropdown).top,
            right: window.getComputedStyle(profileDropdown).right,
            zIndex: window.getComputedStyle(profileDropdown).zIndex
        });
    }
    
    // Test click
    if (profileButton) {
        profileButton.addEventListener('click', function() {
            console.log('✅ Profile button clicked - dropdown should toggle');
        });
    }
});
