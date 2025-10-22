// Category Handler JavaScript

// Function to handle category selection
function handleCategorySelection(categoryId) {
    const categorySelect = document.getElementById('category');
    if (categorySelect) {
        categorySelect.value = categoryId;
    }
}

// Function to refresh category dropdown
function refreshCategoryDropdown() {
    fetch('/categories/list/')
        .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
        .then(data => {
            if (data.status === 'success') {
                const categorySelect = document.getElementById('category');
                if (categorySelect) {
                    // Clear existing options except the first one
                    while (categorySelect.options.length > 1) {
                        categorySelect.remove(1);
                    }
                    
                    // Add new options
                    data.categories.forEach(category => {
                        const option = new Option(category.name, category.id);
                        categorySelect.add(option);
                    });
                }
            }
        })
        .catch(error => {
            console.error('Error refreshing categories:', error);
        });
}

// Function to show category creation modal
function showCategoryModal() {
    const modal = document.getElementById('popup-container');
    if (modal) {
        modal.style.display = 'flex';
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
}

// Function to hide category creation modal
function hideCategoryModal() {
    const modal = document.getElementById('popup-container');
    if (modal) {
        modal.style.display = 'none';
        modal.classList.remove('active');
        document.body.style.overflow = 'auto';
        // Reset form
        const form = document.getElementById('categoryForm');
        if (form) {
            form.reset();
        }
    }
}

// Function to generate slug from name
function generateSlug(name) {
    if (!name) return '';
    return name.toLowerCase()
        .replace(/[^a-z0-9]+/g, '-') // Replace any non-alphanumeric characters with hyphens
        .replace(/^-+|-+$/g, '')     // Remove leading and trailing hyphens
        .trim();                     // Remove any whitespace
}

// Function to handle category form submission
function handleCategorySubmit(event) {
    event.preventDefault();
    const form = event.target;
    const formData = new FormData(form);
    
    // Basic validation
    const name = formData.get('name').trim();
    if (!name) {
        showNotification('Category name is required', 'error');
        return;
    }
    
    // Show loading state
    const submitButton = form.querySelector('button[type="submit"]');
    const submitText = submitButton.querySelector('.submit-text');
    const spinner = submitButton.querySelector('.spinner');
    const originalText = submitText ? submitText.textContent : 'Create Category';
    
    if (submitText) submitText.textContent = 'Creating...';
    if (spinner) spinner.classList.remove('hidden');
    submitButton.disabled = true;

    // Get CSRF token
    const csrfToken = formData.get('csrfmiddlewaretoken');

    // Prepare the data
    const data = {
        name: name
    };
    
    // Add description if provided (optional field)
    const description = formData.get('description');
    if (description && description.trim()) {
        data.description = description.trim();
    }

    // Add slug if provided
    const slug = formData.get('slug').trim();
    if (slug) data.slug = slug;

    fetch('/categories/ajax-create/', {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrfToken,
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data)
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        if (data.status === 'success') {
            // Add new option to select dropdown
            const categorySelect = document.getElementById('category');
            if (categorySelect) {
                const newOption = new Option(data.name, data.id);
                categorySelect.add(newOption);
                categorySelect.value = data.id;
                categorySelect.dispatchEvent(new Event('change'));
            }
            
            // Close the modal
            hideCategoryModal();
            
            // Show success message
            showNotification(`Category "${data.name}" created successfully!`, 'success');
        } else {
            throw new Error(data.message || 'Failed to create category');
        }
    })
    .catch(error => {
        console.error('Category creation error:', error);
        const errorMessage = error.message || 'Failed to create category';
        showNotification(errorMessage, 'error');
    })
    .finally(() => {
        // Reset button state
        if (submitText) submitText.textContent = originalText;
        if (spinner) spinner.classList.add('hidden');
        submitButton.disabled = false;
    });
}

// Function to show notification
function showNotification(message, type = 'success') {
    // Try to use existing notification system first
    if (typeof showTopicNotification === 'function') {
        showTopicNotification(message, type);
        return;
    }
    
    // Fallback: Create simple notification
    const notification = document.createElement('div');
    notification.className = `fixed top-4 right-4 px-6 py-3 rounded-lg shadow-lg z-50 max-w-sm text-white ${
        type === 'success' ? 'bg-green-500' : 
        type === 'error' ? 'bg-red-500' : 
        type === 'warning' ? 'bg-yellow-500' : 'bg-blue-500'
    }`;
    notification.textContent = message;
    
    document.body.appendChild(notification);
    
    // Auto-remove after 4 seconds
    setTimeout(() => {
        if (notification.parentNode) {
            notification.parentNode.removeChild(notification);
        }
    }, 4000);
}

// Add event listeners when the document is ready
document.addEventListener('DOMContentLoaded', function() {
    // Add click event listener for the "Add New Category" button
    const addCategoryBtn = document.getElementById('add-category-btn');
    if (addCategoryBtn) {
        addCategoryBtn.addEventListener('click', showCategoryModal);
    }

    // Add click event listener for the close button
    const closeBtn = document.querySelector('.btn-cancel');
    if (closeBtn) {
        closeBtn.addEventListener('click', hideCategoryModal);
    }

    // Add click event listener for clicking outside the modal
    const modal = document.getElementById('popup-container');
    if (modal) {
        modal.addEventListener('click', function(event) {
            if (event.target === modal) {
                hideCategoryModal();
            }
        });
    }

    // Add form submission handler
    const categoryForm = document.getElementById('categoryForm');
    if (categoryForm) {
        categoryForm.addEventListener('submit', handleCategorySubmit);
    }

    // Add input event listener for auto-generating slug
    const nameInput = document.getElementById('id_name');
    const slugInput = document.getElementById('id_slug');
    if (nameInput && slugInput) {
        let isManualEdit = false;

        nameInput.addEventListener('input', function() {
            const name = this.value.trim();
            const currentSlug = slugInput.value.trim();
            const generatedSlug = generateSlug(name);
            
            // Only update slug if it's not being manually edited
            if (!isManualEdit && (!currentSlug || currentSlug === generateSlug(this.defaultValue))) {
                slugInput.value = generatedSlug;
            }
            
            // Store the current name for next comparison
            this.defaultValue = name;
        });

        // Handle manual slug editing
        slugInput.addEventListener('focus', function() {
            isManualEdit = true;
        });

        slugInput.addEventListener('blur', function() {
            if (this.value.trim()) {
                this.value = generateSlug(this.value);
            }
            isManualEdit = false;
        });

        slugInput.addEventListener('input', function() {
            if (this.value.trim()) {
                this.value = generateSlug(this.value);
            }
        });
    }
}); 