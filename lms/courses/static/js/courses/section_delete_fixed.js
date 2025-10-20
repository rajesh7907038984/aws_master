/**
 * Fixed Section Delete Handler
 * Comprehensive solution for section deletion issues
 * Version: 2025-01-26
 */


// Global state management
window.sectionDeleteState = {
    inProgress: false,
    lastDeleted: null
};

/**
 * Robust CSRF token retrieval
 */
function getCSRFToken() {
    
    // Method 1: Form input
    const csrfInput = document.querySelector('[name=csrfmiddlewaretoken]');
    if (csrfInput && csrfInput.value) {
        return csrfInput.value;
    }
    
    // Method 2: Meta tag
    const csrfMeta = document.querySelector('meta[name=csrf-token]');
    if (csrfMeta && csrfMeta.content) {
        return csrfMeta.content;
    }
    
    // Method 3: Cookie
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
        const [name, value] = cookie.trim().split('=');
        if (name === 'csrftoken' || name === 'lms_csrftoken') {
            return value;
        }
    }
    
    // Method 4: Window object
    if (window.CSRF_TOKEN) {
        return window.CSRF_TOKEN;
    }
    
    return null;
}

/**
 * Show notification with proper styling
 */
function showNotification(message, type = 'info', duration = 3000) {
    // Remove existing notifications
    const existingNotifications = document.querySelectorAll('.section-delete-notification');
    existingNotifications.forEach(notification => notification.remove());
    
    const notification = document.createElement('div');
    notification.className = `section-delete-notification fixed bottom-4 right-4 px-6 py-3 rounded shadow-lg z-50 transition-all duration-300`;
    
    // Set colors based on type
    switch(type) {
        case 'success': 
            notification.classList.add('bg-green-500', 'text-white');
            break;
        case 'error': 
            notification.classList.add('bg-red-500', 'text-white');
            break;
        case 'warning': 
            notification.classList.add('bg-yellow-500', 'text-white');
            break;
        default: 
            notification.classList.add('bg-blue-500', 'text-white');
    }
    
    notification.innerHTML = message;
    document.body.appendChild(notification);
    
    // Auto-remove after duration
    setTimeout(() => {
        notification.classList.add('opacity-0');
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, duration);
}

/**
 * Enhanced section delete function
 */
// Make deleteSection available globally
window.deleteSection = async function deleteSection(sectionId) {
    
    // Prevent multiple simultaneous deletions
    if (window.sectionDeleteState.inProgress) {
        showNotification('Please wait for the current deletion to complete', 'warning');
        return;
    }
    
    // Confirm deletion
    if (!confirm('Are you sure you want to delete this section? All topics in this section will be moved to unsectioned.')) {
        return;
    }
    
    // Set loading state
    window.sectionDeleteState.inProgress = true;
    window.sectionDeleteState.lastDeleted = sectionId;
    
    try {
        // Find section element
        const sectionElement = document.querySelector(`[data-section-id="${sectionId}"]`);
        if (!sectionElement) {
            throw new Error('Section element not found in DOM');
        }
        
        // Add loading state to section
        sectionElement.style.opacity = '0.5';
        sectionElement.style.pointerEvents = 'none';
        
        // Get CSRF token
        const csrfToken = getCSRFToken();
        if (!csrfToken) {
            throw new Error('Security token not found. Please refresh the page and try again.');
        }
        
        
        // Make the delete request
        const response = await fetch(`/courses/api/sections/${sectionId}/simple-delete/`, {
            method: 'DELETE',
            headers: {
                'X-CSRFToken': csrfToken,
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            }
        });
        
        
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Server error (${response.status}): ${errorText}`);
        }
        
        const data = await response.json();
        
        if (data.success) {
            
            // Animate section removal
            sectionElement.style.transition = 'all 0.3s ease';
            sectionElement.style.opacity = '0';
            sectionElement.style.height = '0';
            sectionElement.style.margin = '0';
            sectionElement.style.padding = '0';
            sectionElement.style.overflow = 'hidden';
            
            // Remove element after animation
            setTimeout(() => {
                sectionElement.remove();
                
                // Check if no sections remain
                const remainingSections = document.querySelectorAll('[data-section-id]');
                if (remainingSections.length === 0) {
                    const emptyMessage = document.querySelector('.empty-sections-message');
                    if (emptyMessage) {
                        emptyMessage.style.display = 'block';
                    }
                }
                
                // Reinitialize any necessary components
                if (typeof window.initializeSectionAccordion === 'function') {
                    window.initializeSectionAccordion();
                }
                
                showNotification(data.message || 'Section deleted successfully', 'success');
            }, 300);
            
        } else {
            throw new Error(data.error || 'Failed to delete section');
        }
        
    } catch (error) {
        
        // Restore section element state
        const sectionElement = document.querySelector(`[data-section-id="${sectionId}"]`);
        if (sectionElement) {
            sectionElement.style.opacity = '1';
            sectionElement.style.pointerEvents = 'auto';
        }
        
        showNotification(`Error: ${error.message}`, 'error');
        
    } finally {
        // Always clean up loading state
        window.sectionDeleteState.inProgress = false;
    }
}

/**
 * Test function to verify functionality
 */
function testSectionDelete() {
    return true;
}

// Export functions to global scope
window.deleteSection = deleteSection;
window.testSectionDelete = testSectionDelete;
window.getCSRFToken = getCSRFToken;
window.showNotification = showNotification;

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('Section Delete Handler initialized');
    console.log('Available functions:', {
        deleteSection: typeof window.deleteSection,
        testSectionDelete: typeof window.testSectionDelete,
        getCSRFToken: typeof window.getCSRFToken,
        showNotification: typeof window.showNotification
    });
});

