/**
 * Simple Category Modal - Clean Implementation
 * Handles category creation from course edit page
 */

// Global functions for modal management
function showCategoryModal() {
    console.log('Opening category modal...');
    
    // Create modal if it doesn't exist
    let modal = document.getElementById('category-modal');
    if (!modal) {
        createCategoryModal();
        modal = document.getElementById('category-modal');
    }
    
    // Show modal
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
}

function hideCategoryModal() {
    console.log('Closing category modal...');
    const modal = document.getElementById('category-modal');
    if (modal) {
        modal.classList.add('hidden');
        document.body.style.overflow = 'auto';
        
        // Reset form
        const form = modal.querySelector('#categoryForm');
        if (form) {
            form.reset();
        }
    }
}

function createCategoryModal() {
    // Create modal HTML
    const modalHTML = `
    <div id="category-modal" class="fixed inset-0 bg-gray-900 bg-opacity-75 hidden overflow-y-auto h-full w-full z-50 flex items-center justify-center">
        <div class="relative mx-auto p-6 border border-gray-600 w-full max-w-md shadow-2xl rounded-lg bg-gray-800">
            <div class="flex justify-between items-center mb-4 border-b border-gray-700 pb-3">
                <h3 class="text-lg font-semibold text-white">Create New Category</h3>
                <button type="button" class="text-gray-400 hover:text-white transition focus:outline-none" onclick="hideCategoryModal()">
                    <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                </button>
            </div>
            
            <form id="categoryForm" class="space-y-4" method="POST" action="/categories/ajax-create/">
                <input type="hidden" name="csrfmiddlewaretoken" value="${getCSRFToken()}">
                
                <div>
                    <label for="category-name" class="block text-sm font-medium text-gray-300 mb-1">Category Name</label>
                    <input type="text" id="category-name" name="name" required 
                        class="w-full px-3 py-2 text-sm rounded-md border border-gray-600 bg-gray-700 text-white shadow-sm focus:border-blue-500 focus:ring-blue-500"
                        placeholder="Enter category name">
                </div>
                
                <div>
                    <label for="category-description" class="block text-sm font-medium text-gray-300 mb-1">Description (Optional)</label>
                    <textarea id="category-description" name="description" rows="3"
                        class="w-full px-3 py-2 text-sm rounded-md border border-gray-600 bg-gray-700 text-white shadow-sm focus:border-blue-500 focus:ring-blue-500"
                        placeholder="Enter category description"></textarea>
                </div>
                
                <div class="flex justify-end space-x-3 pt-4 border-t border-gray-700">
                    <button type="button" class="px-4 py-2 text-sm font-medium text-gray-300 bg-gray-600 border border-gray-500 rounded-md shadow-sm hover:bg-gray-500 focus:outline-none" onclick="hideCategoryModal()">
                        Cancel
                    </button>
                    <button type="submit" class="px-4 py-2 text-sm font-medium text-white bg-green-600 border border-transparent rounded-md shadow-sm hover:bg-green-700 focus:outline-none">
                        Create Category
                    </button>
                </div>
            </form>
        </div>
    </div>`;
    
    // Add to page
    document.body.insertAdjacentHTML('beforeend', modalHTML);
    
    // Add event listeners
    const modal = document.getElementById('category-modal');
    const form = document.getElementById('categoryForm');
    
    // Backdrop click to close
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            hideCategoryModal();
        }
    });
    
    // Form submission
    form.addEventListener('submit', handleCategoryFormSubmit);
    
    // Escape key to close
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && !modal.classList.contains('hidden')) {
            hideCategoryModal();
        }
    });
}

function getCSRFToken() {
    // Try to get CSRF token from form
    const input = document.querySelector('[name=csrfmiddlewaretoken]');
    if (input && input.value) {
        return input.value;
    }
    
    // Try to get from meta tag
    const meta = document.querySelector('meta[name=csrf-token]');
    if (meta) {
        return meta.getAttribute('content');
    }
    
    // Try to get from cookie
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
        const [name, value] = cookie.trim().split('=');
        if (name === 'csrftoken') {
            return value;
        }
    }
    
    return '';
}

function handleCategoryFormSubmit(e) {
    e.preventDefault();
    console.log('Category form submitted');
    
    const form = e.target;
    const submitButton = form.querySelector('button[type="submit"]');
    
    // Disable submit button
    submitButton.disabled = true;
    submitButton.textContent = 'Creating...';
    
    // Get form data
    const formData = new FormData(form);
    
    // Send request
    fetch('/categories/ajax-create/', {
        method: 'POST',
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRFToken': getCSRFToken()
        },
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        console.log('Response:', data);
        
        if (data.status === 'success') {
            // Update category dropdown
            updateCategoryDropdown(data);
            
            // Show success message
            showNotification('Category created successfully!', 'success');
            
            // Close modal
            hideCategoryModal();
        } else {
            showNotification(data.message || 'Failed to create category', 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showNotification('An error occurred. Please try again.', 'error');
    })
    .finally(() => {
        // Re-enable submit button
        submitButton.disabled = false;
        submitButton.textContent = 'Create Category';
    });
}

function updateCategoryDropdown(categoryData) {
    // Find category dropdown
    const categorySelect = document.getElementById('category') || 
                          document.getElementById('id_category') ||
                          document.querySelector('select[name="category"]');
    
    if (categorySelect) {
        // Add new option
        const newOption = new Option(categoryData.name, categoryData.id);
        categorySelect.add(newOption);
        
        // Select the new category
        categorySelect.value = categoryData.id;
        
        // Trigger change event
        const event = new Event('change', { bubbles: true });
        categorySelect.dispatchEvent(event);
        
        console.log('Category added to dropdown:', categoryData.name);
    } else {
        console.warn('Category dropdown not found');
        // Fallback: refresh page
        setTimeout(() => {
            window.location.reload();
        }, 1000);
    }
}

function showNotification(message, type) {
    // Create notification
    const notification = document.createElement('div');
    notification.className = `fixed top-4 right-4 z-50 px-6 py-3 rounded-md shadow-lg ${
        type === 'success' ? 'bg-green-500 text-white' : 
        type === 'error' ? 'bg-red-500 text-white' : 
        'bg-blue-500 text-white'
    }`;
    notification.textContent = message;
    
    document.body.appendChild(notification);
    
    // Remove after 3 seconds
    setTimeout(() => {
        notification.remove();
    }, 3000);
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', function() {
    console.log(' Simple category modal loaded - CLEAN VERSION');
    console.log('Available functions:', {
        showCategoryModal: typeof showCategoryModal,
        hideCategoryModal: typeof hideCategoryModal
    });
    
    // Add click handler for category add button
    document.addEventListener('click', function(e) {
        if (e.target.matches('#add-category-btn, button[onclick="showCategoryModal()"]')) {
            console.log('Category add button clicked');
            e.preventDefault();
            showCategoryModal();
        }
    });
});

// Export functions to global scope
window.showCategoryModal = showCategoryModal;
window.hideCategoryModal = hideCategoryModal;
