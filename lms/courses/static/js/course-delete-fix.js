/**
 * Course Delete Functionality Fix
 * Version: 2025-09-26
 * Author: LMS Support Team
 * 
 * This script fixes the course grid box delete option that was not working properly.
 * 
 * Issues Fixed:
 * 1. Form submission failures due to inline onsubmit handlers
 * 2. CSRF token access issues
 * 3. Button positioning and clickability problems
 * 4. Double-click prevention
 * 5. User feedback during deletion process
 */

console.log('🔧 Loading Course Delete Fix...');

/**
 * Enhanced Course Delete Handler
 */
window.handleCourseDelete = function(button) {
    console.log('🗑️ Course delete handler called');
    
    const courseId = button.getAttribute('data-course-id');
    const courseTitle = button.getAttribute('data-course-title');
    
    console.log(`Deleting course: ${courseTitle} (ID: ${courseId})`);
    
    // Show confirmation dialog
    if (!confirm(`Are you sure you want to delete the course "${courseTitle}"? This action cannot be undone.`)) {
        console.log('❌ User cancelled deletion');
        return;
    }
    
    // Disable the button to prevent double-clicks
    button.disabled = true;
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    button.setAttribute('title', 'Deleting...');
    
    // Get CSRF token with multiple fallback methods
    const csrfToken = getCsrfToken();
    
    if (!csrfToken) {
        alert('Security token not found. Please refresh the page and try again.');
        resetDeleteButton(button);
        return;
    }
    
    console.log('✅ CSRF token found');
    
    // Create and submit form dynamically
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = `/courses/${courseId}/delete/`;
    form.style.display = 'none';
    
    const csrfInput = document.createElement('input');
    csrfInput.type = 'hidden';
    csrfInput.name = 'csrfmiddlewaretoken';
    csrfInput.value = csrfToken;
    
    form.appendChild(csrfInput);
    document.body.appendChild(form);
    
    console.log('📤 Submitting delete form');
    
    // Add error handling for form submission
    try {
        form.submit();
    } catch (error) {
        console.error('❌ Form submission error:', error);
        alert('An error occurred while deleting the course. Please try again.');
        resetDeleteButton(button);
        document.body.removeChild(form);
    }
}

/**
 * Get CSRF Token with multiple fallback methods
 */
function getCsrfToken() {
    console.log('🔍 Retrieving CSRF token...');
    
    // Method 1: Hidden form
    const csrfForm = document.querySelector('#csrf-form [name=csrfmiddlewaretoken]');
    if (csrfForm && csrfForm.value) {
        console.log('✅ CSRF token found in hidden form');
        return csrfForm.value;
    }
    
    // Method 2: Any form on the page
    const csrfInput = document.querySelector('[name=csrfmiddlewaretoken]');
    if (csrfInput && csrfInput.value) {
        console.log('✅ CSRF token found in form input');
        return csrfInput.value;
    }
    
    // Method 3: Meta tag
    const csrfMeta = document.querySelector('meta[name=csrf-token]');
    if (csrfMeta && csrfMeta.content) {
        console.log('✅ CSRF token found in meta tag');
        return csrfMeta.content;
    }
    
    // Method 4: Cookie
    const cookieToken = getCookie('csrftoken');
    if (cookieToken) {
        console.log('✅ CSRF token found in cookie');
        return cookieToken;
    }
    
    // Method 5: Window object (if set)
    if (window.CSRF_TOKEN) {
        console.log('✅ CSRF token found in window object');
        return window.CSRF_TOKEN;
    }
    
    console.error('❌ CSRF token not found with any method');
    return null;
}

/**
 * Helper function to get cookie value
 */
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

/**
 * Reset delete button to original state
 */
function resetDeleteButton(button) {
    button.disabled = false;
    button.innerHTML = '<i class="fas fa-trash"></i>';
    button.removeAttribute('title');
}

/**
 * Initialize delete button handlers on page load
 */
document.addEventListener('DOMContentLoaded', function() {
    console.log('🎯 Course Delete Fix initialized');
    
    // Add click handlers to any existing delete buttons that might not have onclick
    const deleteButtons = document.querySelectorAll('.course-delete-btn');
    deleteButtons.forEach(button => {
        if (!button.hasAttribute('onclick')) {
            button.addEventListener('click', function() {
                handleCourseDelete(this);
            });
        }
    });
    
    console.log(`✅ Found ${deleteButtons.length} delete buttons`);
});

console.log('✅ Course Delete Fix loaded successfully');
