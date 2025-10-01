/**
 * Simple Category JavaScript - Simplified version for course editing
 * This file provides basic category functionality needed by the Topic Section
 */

console.log('Simple Category JS loaded');

// Basic category management functions
function initializeSimpleCategory() {
    console.log('Initializing simple category functionality');
    
    // Handle category dropdown changes if present
    const categoryDropdowns = document.querySelectorAll('select[name*="category"], #id_category, .category-select');
    categoryDropdowns.forEach(dropdown => {
        dropdown.addEventListener('change', function() {
            console.log('Category changed to:', this.value);
            // Basic change handler - can be extended if needed
        });
    });
    
    // Handle add category buttons if present
    const addCategoryButtons = document.querySelectorAll('.add-category-btn, #add-category-btn');
    addCategoryButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            console.log('Add category button clicked');
            // Call modal function if available
            if (typeof showCategoryModal === 'function') {
                showCategoryModal();
            } else {
                console.warn('showCategoryModal function not available');
            }
        });
    });
}

// Simple validation function for category fields
function validateCategoryField(field) {
    if (!field.value || field.value.trim() === '') {
        return false;
    }
    return true;
}

// Utility function to refresh category dropdown
function refreshCategoryDropdown(newCategoryData) {
    const dropdowns = document.querySelectorAll('select[name*="category"], #id_category, .category-select');
    dropdowns.forEach(dropdown => {
        if (newCategoryData) {
            const option = new Option(newCategoryData.name, newCategoryData.id);
            dropdown.add(option);
            dropdown.value = newCategoryData.id;
        }
    });
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('✅ Simple category script initialized');
    initializeSimpleCategory();
});

// Export to global scope for compatibility
window.initializeSimpleCategory = initializeSimpleCategory;
window.validateCategoryField = validateCategoryField;
window.refreshCategoryDropdown = refreshCategoryDropdown;
