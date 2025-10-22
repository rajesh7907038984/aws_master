// Admin Header Functionality
document.addEventListener('DOMContentLoaded', function() {
    // Mobile search toggle
    const mobileSearchToggle = document.getElementById('mobile-search-toggle');
    const mobileSearch = document.getElementById('mobile-search');
    
    if (mobileSearchToggle && mobileSearch) {
        mobileSearchToggle.addEventListener('click', function() {
            mobileSearch.classList.toggle('hidden');
        });
    }
    
    // Notification counter - Fetch from API
    const notificationIndicator = document.querySelector('.notification-indicator');
    
    // Fetch notification count from API
    async function fetchNotificationCount() {
        try {
            const response = await fetch('/api/notifications/count/');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            return data.count || 0;
        } catch (error) {
            console.warn('Failed to fetch notification count:', error);
            // Fallback to localStorage or default
            return 0;
        }
    }
    
    // Update notification indicator
    if (notificationIndicator) {
        fetchNotificationCount().then(notificationCount => {
            if (notificationCount > 0) {
                // Show count inside the indicator
                notificationIndicator.textContent = notificationCount > 9 ? '9+' : notificationCount;
                notificationIndicator.style.display = 'block';
            } else {
                // Hide the indicator if there are no notifications
                notificationIndicator.style.display = 'none';
            }
        });
    }
    
    // Notification dropdown animation
    const notificationIndicatorElement = document.querySelector('.notification-indicator');
    if (notificationIndicatorElement) {
        const notificationButton = notificationIndicatorElement.parentElement;
        const notificationDropdown = document.querySelector('.notification-dropdown');
        
        if (notificationButton && notificationDropdown) {
            // Using Alpine.js for toggle, this is just for additional effects
            notificationButton.addEventListener('click', function() {
                // Add animation classes if needed
                notificationDropdown.classList.add('animate-fade-in-down');
            });
        }
    }
    
    // Mark notifications as read
    const notificationItems = document.querySelectorAll('.notification-item');
    
    notificationItems.forEach(item => {
        item.addEventListener('click', function() {
            // Here you would typically call an API to mark the notification as read
            // For demo purposes, we're just adding a visual indicator
            this.classList.add('opacity-50');
        });
    });
}); 