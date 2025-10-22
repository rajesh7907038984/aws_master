document.addEventListener('DOMContentLoaded', function() {
    const topicForm = document.getElementById('topicForm');
    const contentTypeRadios = document.querySelectorAll('input[name="content_type"]');
    const contentTypeSections = document.querySelectorAll('.content-type-section');
    
    // Function to show/hide content type sections
    function updateContentTypeSections(selectedType) {
        console.log('Updating content type sections for:', selectedType);
        
        // Normalize selected type (lowercase first)
        const normalizedType = selectedType.toLowerCase();
        
        // Define content types that should hide the Instructions field
        const hideInstructionsTypes = ['video', 'document', 'text', 'audio', 'web', 'embedvideo', 'scorm', 'quiz', 'assignment', 'conference', 'discussion'];
        
        // Handle Instructions field visibility
        const instructionsField = document.querySelector('label[for*="instructions"]').closest('div');
        if (instructionsField) {
            if (hideInstructionsTypes.includes(normalizedType)) {
                instructionsField.style.display = 'none';
                console.log('Hiding Instructions field for content type:', normalizedType);
            } else {
                instructionsField.style.display = 'block';
                console.log('Showing Instructions field for content type:', normalizedType);
            }
        }
        
        // First hide all content fields
        document.querySelectorAll('.content-type-field').forEach(field => {
            field.style.display = 'none';
            field.style.visibility = 'hidden';
            field.classList.remove('active');
        });
        
        // Then show the selected content field
        const selectedField = document.getElementById(`${normalizedType}-content`);
        if (selectedField) {
            console.log(`Showing content field for ${normalizedType}`);
            selectedField.style.display = 'block';
            selectedField.style.visibility = 'visible';
            selectedField.classList.add('active');
            
            // Special handling for assignment content
            if (normalizedType === 'assignment') {
                console.log('Handling assignment content type specifically');
                const assignmentSelect = selectedField.querySelector('select[name="assignment"]');
                if (assignmentSelect) {
                    // Make sure it's visible
                    assignmentSelect.style.display = 'block';
                    assignmentSelect.style.visibility = 'visible';
                    
                    // Check if there's a selected option
                    const selectedOption = assignmentSelect.querySelector('option:checked[value]:not([value=""])');
                    if (selectedOption) {
                        console.log('Assignment already selected:', selectedOption.value);
                    }
                } else {
                    console.warn('Assignment select not found');
                }
            }
            
            // Also handle legacy content sections if they exist
            contentTypeSections.forEach(section => {
                if (section.id === `${selectedType}-content`) {
                    section.classList.remove('hidden');
                } else {
                    section.classList.add('hidden');
                }
            });
        } else {
            console.warn(`Content field with ID ${normalizedType}-content not found`);
            
            // Fall back to legacy content sections
            contentTypeSections.forEach(section => {
                if (section.id === `${selectedType}-content`) {
                    section.classList.remove('hidden');
                } else {
                    section.classList.add('hidden');
                }
            });
        }
    }

    // Handle content type selection
    contentTypeRadios.forEach(radio => {
        radio.addEventListener('change', (e) => {
            updateContentTypeSections(e.target.value);
        });
    });

    // Handle file input changes
    const fileInputs = document.querySelectorAll('input[type="file"]');
    fileInputs.forEach(input => {
        input.addEventListener('change', function() {
            const filenameDiv = this.closest('.file-upload-container').querySelector('.selected-filename');
            const previewDiv = this.closest('.file-upload-container').querySelector('.file-preview');
            
            if (this.files && this.files[0]) {
                filenameDiv.textContent = this.files[0].name;
                filenameDiv.classList.remove('hidden');
                
                // Show preview for video/audio files
                if (this.files[0].type.startsWith('video/') || this.files[0].type.startsWith('audio/')) {
                    const url = URL.createObjectURL(this.files[0]);
                    const element = this.files[0].type.startsWith('video/') ? 'video' : 'audio';
                    previewDiv.innerHTML = `<${element} controls><source src="${url}"></${element}>`;
                    previewDiv.classList.remove('hidden');
                }
            } else {
                filenameDiv.textContent = '';
                filenameDiv.classList.add('hidden');
                previewDiv.innerHTML = '';
                previewDiv.classList.add('hidden');
            }
        });
    });

    // Handle endless access checkbox
    const endlessAccessCheckbox = document.getElementById('topic_endless_access');
    const endDateInput = document.getElementById('topic_end_date');
    
    if (endlessAccessCheckbox && endDateInput) {
        endlessAccessCheckbox.addEventListener('change', function() {
            endDateInput.disabled = this.checked;
            if (this.checked) {
                endDateInput.value = '';
            }
        });
    }

    // Handle form submission
    if (topicForm) {
        topicForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const submitBtn = this.querySelector('.btn-submit');
            const submitText = submitBtn.querySelector('.submit-text');
            const spinner = submitBtn.querySelector('.spinner');
            
            // Show loading state
            submitBtn.disabled = true;
            submitText.classList.add('hidden');
            spinner.classList.remove('hidden');
            
            try {
                const formData = new FormData(this);
                
                // Get course ID from the hidden input or URL parameter
                let courseId = formData.get('course');
                if (!courseId) {
                    courseId = new URLSearchParams(window.location.search).get('course');
                }
                
                if (!courseId) {
                    throw new Error('Could not determine course ID');
                }

                const topicId = formData.get('topic_id');
                
                // Determine the endpoint based on whether we're creating or editing
                const endpoint = topicId 
                    ? `/courses/topic/${topicId}/edit/`
                    : `/courses/${courseId}/topic/create/`;
                
                const response = await fetch(endpoint, {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });
                
                const data = await response.json();
                
                if (data.success) {
                    // Redirect to course edit page
                    window.location.href = data.redirect_url || `/courses/${courseId}/edit/`;
                } else if (data.errors) {
                    // Show error messages
                    Object.entries(data.errors).forEach(([field, errors]) => {
                        const errorDiv = document.createElement('div');
                        errorDiv.className = 'text-red-500 text-sm mt-1';
                        errorDiv.textContent = errors[0];
                        
                        const input = this.querySelector(`[name="${field}"]`);
                        if (input) {
                            const parent = input.closest('div');
                            const existingError = parent.querySelector('.text-red-500');
                            if (existingError) {
                                existingError.remove();
                            }
                            parent.appendChild(errorDiv);
                        }
                    });
                } else {
                    throw new Error(data.error || 'An error occurred while saving the topic');
                }
            } catch (error) {
                console.error('Error:', error);
                alert('An error occurred while saving the topic. Please try again.');
            } finally {
                // Reset button state
                submitBtn.disabled = false;
                submitText.classList.remove('hidden');
                spinner.classList.add('hidden');
            }
        });
    }

    // Initialize with default content type
    const defaultContentType = document.querySelector('input[name="content_type"]:checked');
    if (defaultContentType) {
        updateContentTypeSections(defaultContentType.value);
    }
});

// On window load, ensure the assignment field is properly displayed
window.onload = function() {
    // Check for assignment content type
    const assignmentRadio = document.querySelector('input[name="content_type"][value="Assignment"]:checked');
    if (assignmentRadio) {
        console.log('Assignment content type detected on window load');
        
        // Check if field is visible
        const assignmentField = document.getElementById('assignment-content');
        if (assignmentField) {
            // Force it to be visible
            assignmentField.style.display = 'block';
            assignmentField.style.visibility = 'visible';
            assignmentField.style.opacity = '1';
            assignmentField.classList.add('active');
            console.log('Assignment field made visible on window load');
            
            // Also ensure assignment select is visible
            const assignmentSelect = assignmentField.querySelector('select[name="assignment"]');
            if (assignmentSelect) {
                assignmentSelect.style.display = 'block';
                assignmentSelect.style.visibility = 'visible';
                assignmentSelect.style.opacity = '1';
                
                // Get assignment ID from hidden field if it exists
                const assignmentIdField = document.querySelector('[name="assignment_id"]');
                if (assignmentIdField && assignmentIdField.value) {
                    // Select the option
                    const option = assignmentSelect.querySelector(`option[value="${assignmentIdField.value}"]`);
                    if (option) {
                        option.selected = true;
                        console.log('Selected assignment option from hidden field:', assignmentIdField.value);
                    }
                }
            }
        }
    }
    
    // Original code for Quill/BetterTable initialization
    if (typeof Quill === 'undefined' || typeof QuillBetterTable === 'undefined') {
        console.log('Quill or QuillBetterTable not loaded yet');
        return;
    }
}; 