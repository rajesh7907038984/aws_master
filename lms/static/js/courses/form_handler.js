// Form validation
function validateForm() {
    const title = document.getElementById('title').value.trim();
    const courseStatus = document.querySelector('input[name="course_status"]:checked');
    
    if (!title) {
        alert('Please enter a course title');
        return false;
    }
    
    if (!courseStatus) {
        alert('Please select a course status');
        return false;
    }
    
    // Course code validation if provided
    if (courseCode) {
        // Pattern: 2-4 letters followed by 3-4 numbers (e.g., CS101, MATH201, ENG1001)
        const courseCodePattern = /^[A-Za-z]{2,4}\d{3,4}$/;
        if (!courseCodePattern.test(courseCode)) {
            alert('Course code must follow the format: 2-4 letters followed by 3-4 numbers (e.g., CS101, MATH201)');
            return false;
        }
    }
    
    return true;
}

// Function to check if slug exists
async function checkSlugExists(slug) {
    if (!slug) return false;
    
    try {
        const response = await fetch(`/categories/check-slug/?slug=${encodeURIComponent(slug)}`, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            }
        });
        
        const data = await response.json();
        return data.exists;
    } catch (error) {
        console.error('Error checking slug:', error);
        return false;
    }
}

// Category form submission handler
const categoryForm = document.getElementById('categoryForm');
if (categoryForm) {
    // Add event listener for name input to auto-generate slug
    const nameInput = categoryForm.querySelector('[name="name"]');
    const slugInput = categoryForm.querySelector('[name="slug"]');
    
    if (nameInput && slugInput) {
        nameInput.addEventListener('input', function() {
            // Only generate slug if slug field is empty or matches the previous name
            if (!slugInput.value || slugInput.value === nameInput.value) {
                // Convert to lowercase and replace spaces with hyphens
                const slug = this.value.toLowerCase()
                    .replace(/[^a-z0-9]+/g, '-') // Replace non-alphanumeric chars with hyphens
                    .replace(/^-+|-+$/g, ''); // Remove leading/trailing hyphens
                slugInput.value = slug;
            }
        });
        
        // Add blur event to slug input to check if slug exists
        slugInput.addEventListener('blur', async function() {
            const slug = this.value.trim();
            if (slug) {
                // Remove the alerts about existing slugs
                // Let the backend handle the unique slug generation
                const exists = await checkSlugExists(slug);
                // No need to show an alert or clear the field
            }
        });
    }

    categoryForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const submitBtn = this.querySelector('button[type="submit"]');
        const slug = this.querySelector('[name="slug"]').value.trim();
        
        // Remove the check for existing slug before submitting
        // Let the backend handle the unique slug generation
        
        // Show loading state
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = 'Creating...';
        }
        
        try {
            // Get form data
            const formData = new FormData(this);
            
            const response = await fetch('/categories/ajax-create/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                }
            });
            
            const responseData = await response.json();
            
            if (responseData.status === 'success') {
                // Add new category to the select dropdown
                const categorySelect = document.getElementById('category');
                if (categorySelect) {
                    const option = document.createElement('option');
                    option.value = responseData.id;
                    option.textContent = responseData.name;
                    categorySelect.appendChild(option);
                    categorySelect.value = responseData.id;
                }
                
                // Close popup and reset form
                const modal = document.getElementById('popup-container');
                if (modal) {
                    modal.style.display = 'none';
                    modal.classList.remove('active');
                    document.body.style.overflow = 'auto';
                }
                this.reset();
                
                // Suppress any duplicate slug errors that might appear
                // Add a flag to window to indicate successful category creation
                window.categoryCreatedSuccessfully = true;
                setTimeout(() => {
                    window.categoryCreatedSuccessfully = false;
                }, 2000); // Reset after 2 seconds
            } else {
                throw new Error(responseData.message || 'Failed to create category');
            }
            
        } catch (error) {
            console.error('Error:', error);
            if (!window.categoryCreatedSuccessfully) {
                alert(error.message || 'An error occurred while creating the category. Please try again.');
            }
        } finally {
            // Reset button state
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Create Category';
            }
        }
    });
}

// Section form submission handler
const sectionForm = document.getElementById('sectionForm');
if (sectionForm) {
    sectionForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const submitBtn = this.querySelector('.btn-submit');
        const submitText = submitBtn.querySelector('.submit-text');
        const spinner = submitBtn.querySelector('.spinner');
        
        // Show loading state
        submitBtn.disabled = true;
        submitText.classList.add('hidden');
        spinner.classList.remove('hidden');
        
        try {
            // Get form data
            const formData = new FormData(this);
            formData.append('course_id', document.querySelector('[name=course_id]').value);
            formData.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);

            const response = await fetch('/courses/api/sections/create/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                }
            });
            
            const responseData = await response.json();
            
            if (responseData.status === 'success') {
                // Add new section to the topics container
                const topicsContainer = document.getElementById('topics-container');
                if (topicsContainer) {
                    const sectionHtml = `
                        <div class="bg-white rounded-lg shadow-sm p-4 mb-4 section-item" data-section-id="${responseData.id}">
                            <div class="flex items-start justify-between">
                                <div class="flex items-start space-x-3">
                                    <div class="flex-shrink-0">
                                        <span class="inline-flex items-center justify-center w-8 h-8 rounded-full bg-gray-100 text-gray-600">
                                            <i class="fas fa-folder"></i>
                                        </span>
                                    </div>
                                    <div>
                                        <h3 class="text-lg font-medium text-gray-900">${responseData.title}</h3>
                                        <div class="mt-2 flex items-center space-x-2">
                                            <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                                                Section
                                            </span>
                                        </div>
                                    </div>
                                </div>
                                <div class="flex items-center space-x-2">
                                    <button type="button" class="text-blue-600 hover:text-blue-700 edit-section-btn" data-section-id="${responseData.id}">
                                        <i class="fas fa-edit"></i>
                                    </button>
                                    <button type="button" class="text-red-600 hover:text-red-700" onclick="deleteSection(${responseData.id})">
                                        <i class="fas fa-trash"></i>
                                    </button>
                                </div>
                            </div>
                        </div>
                    `;
                    topicsContainer.insertAdjacentHTML('beforeend', sectionHtml);
                }
                
                // Close popup and reset form
                sectionPopup.hide();
            } else {
                throw new Error(responseData.message || 'Failed to create section');
            }
            
        } catch (error) {
            console.error('Error:', error);
            alert(error.message || 'An error occurred while creating the section. Please try again.');
        } finally {
            // Reset button state
            submitBtn.disabled = false;
            submitText.classList.remove('hidden');
            spinner.classList.add('hidden');
        }
    });
} 