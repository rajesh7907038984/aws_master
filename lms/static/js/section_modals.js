/**
 * Section Modal Handler
 * Manages section creation and editing
 */
document.addEventListener('DOMContentLoaded', function() {
    const createSectionForm = document.getElementById('newSectionForm');
    const sectionModal = document.getElementById('add-section-modal');
    
    if (createSectionForm) {
        createSectionForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            // Get form data
            const formData = new FormData(this);
            const sectionName = formData.get('name');
            
            // Validate section name
            if (!sectionName || !sectionName.trim()) {
                showFormError(this, 'name', 'Section name is required');
                return;
            }
            
            // Get CSRF token
            const csrfToken = getCsrfToken();
            if (!csrfToken) {
                alert('CSRF token not found. Please refresh the page and try again.');
                return;
            }
            
            // Show loading state
            const submitBtn = this.querySelector('button[type="submit"]');
            const originalBtnText = submitBtn.textContent;
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner"></span> Creating...';
            
            // Submit form data
            fetch('/courses/api/sections/create/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': csrfToken
                }
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Server responded with ${response.status}: ${response.statusText}`);
                }
                return response.json();
            })
            .then(data => {
                if (data && data.success) {
                    // Section created successfully
                    console.log('Section created successfully', data);
                    
                    // Create new section element
                    const sectionId = data.section.id;
                    const sectionName = data.section.name;
                    
                    // Create section in the DOM
                    createSectionElement(sectionId, sectionName);
                    
                    // Close modal
                    closeModal();
                    
                    // Show success message
                    showToast('Section created successfully', 'success');
                } else {
                    // Error creating section
                    throw new Error((data && data.error) || 'Failed to create section');
                }
            })
            .catch(error => {
                console.error('Error creating section:', error);
                showFormError(createSectionForm, 'general', error.message || 'An error occurred while creating the section');
            })
            .finally(() => {
                // Reset button state
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalBtnText;
            });
        });
    }
    
    // Helper function to create a new section element in the DOM
    function createSectionElement(sectionId, sectionName) {
        // Ensure sectionId is a number for consistency
        sectionId = parseInt(sectionId, 10);
        
        const sectionsContainer = document.getElementById('sections-container');
        if (!sectionsContainer) return;
        
        // Create the new section HTML
        const sectionTemplate = document.createElement('div');
        sectionTemplate.className = 'section-container mb-3';
        sectionTemplate.setAttribute('data-id', sectionId.toString());
        sectionTemplate.id = `section-${sectionId}`;
        
        sectionTemplate.innerHTML = `
            <div class="flex items-center justify-between p-2 bg-gray-100 rounded-t-md border border-gray-200">
                <div class="flex items-center">
                    <span class="section-drag-handle mr-2 cursor-grab opacity-70 hover:opacity-100">
                        <svg class="h-4 w-4 text-gray-500" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M8 6a2 2 0 1 0 0-4 2 2 0 0 0 0 4zm0 8a2 2 0 1 0 0-4 2 2 0 0 0 0 4zm0 8a2 2 0 1 0 0-4 2 2 0 0 0 0 4zm8-16a2 2 0 1 0 0-4 2 2 0 0 0 0 4zm0 8a2 2 0 1 0 0-4 2 2 0 0 0 0 4zm0 8a2 2 0 1 0 0-4 2 2 0 0 0 0 4z"></path>
                        </svg>
                    </span>
                    <svg class="section-toggle h-4 w-4 mr-1 cursor-pointer" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                    </svg>
                    <span class="font-semibold text-sm">${sectionName}</span>
                </div>
                <div class="flex items-center space-x-1">
                    <button type="button" onclick="renameSection('${sectionId}', '${sectionName.replace(/'/g, "\\'")}')" class="text-xs px-2 py-1 bg-white border border-gray-300 rounded-md hover:bg-gray-50" title="Rename section">
                        <svg class="h-3.5 w-3.5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"></path>
                        </svg>
                    </button>
                    <button type="button" onclick="deleteSectionConfirm('${sectionId}')" class="text-xs px-2 py-1 bg-white border border-gray-300 rounded-md hover:bg-gray-50" title="Delete section">
                        <svg class="h-3.5 w-3.5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                        </svg>
                    </button>
                </div>
            </div>
            <div class="section-topics px-3 py-2 bg-gray-50">
                <div class="topic-list" data-section-id="${sectionId}">
                    <!-- Topics will be added here -->
                    <div class="empty-section-message text-center py-4 text-gray-500 italic text-sm">
                        No topics in this section yet. Add a topic to get started.
                    </div>
                </div>
                <div class="mt-2 flex justify-end">
                    <a href="${window.TOPIC_CREATE_URL_TEMPLATE ? window.TOPIC_CREATE_URL_TEMPLATE.replace('0', courseId) + '?section_id=' + sectionId : '/courses/' + courseId + '/topic/create/?section_id=' + sectionId}" class="inline-flex items-center px-2 py-1 text-xs font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none">
                        <svg class="-ml-0.5 mr-1 h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path>
                        </svg>
                        Add Topic
                    </a>
                </div>
            </div>
        `;
        
        // Add the new section to the container
        sectionsContainer.appendChild(sectionTemplate);
        
        // Re-initialize sortable for the new section
        if (typeof initializeTopicsSortable === 'function') {
            initializeTopicsSortable();
        }
        
        // No need to add individual event listeners - 
        // They're handled by the delegated event handlers in course_edit.js
        
        // Trigger event to notify that a section was added
        document.dispatchEvent(new CustomEvent('section:added', {
            detail: { sectionId: sectionId }
        }));
    }
    
    // Fallback delete function if global one is not available
    function deleteSectionAjax(sectionId) {
        const csrfToken = getCsrfToken();
        
        fetch(`/courses/api/sections/${sectionId}/delete/`, {
            method: 'DELETE',
            headers: {
                'X-CSRFToken': csrfToken,
                'Content-Type': 'application/json'
            }
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`Server responded with ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data && data.success) {
                const sectionElement = document.getElementById(`section-${sectionId}`);
                if (sectionElement) {
                    sectionElement.remove();
                    showToast('Section deleted successfully', 'success');
                }
            } else {
                throw new Error((data && data.error) || 'Failed to delete section');
            }
        })
        .catch(error => {
            console.error('Error deleting section:', error);
            showToast('Error deleting section: ' + error.message, 'error');
        });
    }
    
    // Helper function to get CSRF token
    function getCsrfToken() {
        const tokenElement = document.querySelector('[name=csrfmiddlewaretoken]');
        if (tokenElement) {
            return tokenElement.value;
        }
        
        // Try to get from cookie
        return getCookie('csrftoken');
    }
    
    // Helper function to show form errors
    function showFormError(form, fieldName, message) {
        let errorContainer;
        
        if (fieldName === 'general') {
            // Create or find general error container
            errorContainer = form.querySelector('.general-error');
            if (!errorContainer) {
                errorContainer = document.createElement('div');
                errorContainer.className = 'general-error text-red-500 text-sm mt-2 p-2 bg-red-50 rounded';
                form.prepend(errorContainer);
            }
        } else {
            // Find the field
            const field = form.querySelector(`[name="${fieldName}"]`);
            if (!field) return;
            
            // Find or create error container
            errorContainer = field.parentNode.querySelector('.field-error');
            if (!errorContainer) {
                errorContainer = document.createElement('div');
                errorContainer.className = 'field-error text-red-500 text-sm mt-1';
                field.parentNode.appendChild(errorContainer);
            }
        }
        
        errorContainer.textContent = message;
    }
    
    // Helper function to show toast notification
    function showToast(message, type = 'info', duration = 3000) {
        // Check if toast container exists, create if not
        let toastContainer = document.getElementById('toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.id = 'toast-container';
            toastContainer.className = 'fixed bottom-4 right-4 z-50';
            document.body.appendChild(toastContainer);
        }
        
        // Create toast element
        const toast = document.createElement('div');
        toast.className = 'bg-white rounded-lg shadow-md p-4 mb-3 flex items-center';
        
        // Add color based on type
        switch (type) {
            case 'success':
                toast.classList.add('border-l-4', 'border-green-500');
                break;
            case 'error':
                toast.classList.add('border-l-4', 'border-red-500');
                break;
            case 'warning':
                toast.classList.add('border-l-4', 'border-yellow-500');
                break;
            default:
                toast.classList.add('border-l-4', 'border-blue-500');
        }
        
        toast.innerHTML = message;
        toastContainer.appendChild(toast);
        
        // Animation
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(20px)';
        toast.style.transition = 'opacity 0.3s, transform 0.3s';
        
        setTimeout(() => {
            toast.style.opacity = '1';
            toast.style.transform = 'translateY(0)';
        }, 50);
        
        // Auto remove after duration
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(20px)';
            
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }, duration);
    }
    
    // Helper function to close modal
    function closeModal() {
        if (sectionModal) {
            sectionModal.classList.add('hidden');
            document.body.classList.remove('modal-open');
            
            // Reset form
            if (createSectionForm) {
                createSectionForm.reset();
                
                // Clear any error messages
                const errorMessages = createSectionForm.querySelectorAll('.field-error, .general-error');
                errorMessages.forEach(msg => msg.textContent = '');
            }
        }
    }
    
    // Helper function to get cookie value
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
}); 