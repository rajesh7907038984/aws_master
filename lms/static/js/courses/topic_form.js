// Register quill-better-table module
window.onload = function() {
    if (window.Quill && window.QuillBetterTable) {
        Quill.register({
            'modules/better-table': QuillBetterTable
        }, true);
        console.log('QuillBetterTable module registered');
    } else {
        console.warn('Quill or QuillBetterTable not loaded yet');
    }
};

document.addEventListener('DOMContentLoaded', function() {
    // Form data recovery from localStorage on page load
    const topicForm = document.getElementById('topicForm');
    const formId = topicForm ? topicForm.getAttribute('data-form-id') || window.location.pathname : window.location.pathname;
    
    // Enhanced detection for create vs edit mode
    const isCreateMode = detectCreateMode();
    
    function detectCreateMode() {
        // Multiple ways to detect if this is a create operation
        const topicIdField = document.querySelector('input[name="topic_id"]');
        const hasTopicId = topicIdField && topicIdField.value && topicIdField.value.trim() !== '';
        
        const currentPath = window.location.pathname;
        const isCreateURL = currentPath.includes('/create') || currentPath.includes('/add') || currentPath.includes('/topic/create/');
        
        // Check form action URL as well
        const formAction = topicForm ? topicForm.action : '';
        const isCreateAction = formAction.includes('/create') || formAction.includes('/add');
        
        // Check page title or header text
        const pageHeader = document.querySelector('h1');
        const isCreateHeader = pageHeader && (pageHeader.textContent.includes('Create') || pageHeader.textContent.includes('Add'));
        
        console.log('Create mode detection:', {
            hasTopicId: hasTopicId,
            isCreateURL: isCreateURL,
            isCreateAction: isCreateAction,
            isCreateHeader: isCreateHeader,
            currentPath: currentPath,
            formAction: formAction
        });
        
        // For edit mode, we must have a topic ID. Only consider other indicators if we don't have one.
        if (hasTopicId) {
            return false; // This is edit mode - we have a topic ID
        }
        
        // If no topic ID, check other indicators for create mode
        return isCreateURL || isCreateAction || isCreateHeader;
    }
    
    // For create mode, ensure clean form especially for title field
    if (isCreateMode) {
        console.log('CREATE MODE DETECTED - Ensuring clean form with blank title field');
        
        // Only clear localStorage if the form is truly empty (no user input yet)
        const titleField = document.querySelector('input[name="title"], #topic_title');
        const hasUserInput = titleField && titleField.value.trim() !== '';
        
        if (!hasUserInput) {
            // Clear localStorage for create operations only if no user input
            try {
                localStorage.removeItem('topicForm_' + formId);
                
                // Clear any old entries with different patterns
                const keysToRemove = [];
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    if (key && key.indexOf('topicForm_') !== -1) {
                        keysToRemove.push(key);
                    }
                }
                keysToRemove.forEach(key => localStorage.removeItem(key));
                
                console.log('Cleared localStorage entries for clean form:', keysToRemove);
            } catch (e) {
                console.warn('Could not clear saved form data:', e);
            }
            
            // Only clear fields if no user input detected
            if (titleField && !titleField.value.trim()) {
                titleField.value = '';
                console.log('Title field cleared for new topic creation');
            }
            
            // Clear other key fields that users expect to be blank for new topics
            const descriptionField = document.querySelector('[name="description"]');
            if (descriptionField && !descriptionField.value.trim()) {
                descriptionField.value = '';
            }
            
            // Clear text content if TinyMCE is available
            setTimeout(() => {
                if (typeof tinyMCE !== 'undefined') {
                    const textEditor = tinyMCE.get('id_text_content');
                    if (textEditor && !textEditor.getContent().trim()) {
                        textEditor.setContent('');
                        console.log('TinyMCE text content cleared for new topic');
                    }
                }
            }, 1000);
        } else {
            console.log('User input detected - preserving form data');
        }
        
    } else {
        console.log('EDIT MODE DETECTED - Loading saved form data if available');
        // Load saved form data if available (only for edit mode)
        if (topicForm) {
            loadSavedFormData(formId);
        }
    }
    
    // Setup auto-save timer to preserve form data (but respect create/edit mode)
    if (topicForm) {
        setInterval(function() {
            // Only auto-save if not in create mode or if user has started typing
            if (!isCreateMode || hasUserStartedEditing()) {
                saveFormData(formId);
            }
        }, 5000); // Save every 5 seconds
        
        // Save when user is leaving the page (but respect create/edit mode)
        window.addEventListener('beforeunload', function() {
            if (!isCreateMode || hasUserStartedEditing()) {
                saveFormData(formId);
            }
        });
    }
    
    function hasUserStartedEditing() {
        const titleField = document.querySelector('input[name="title"], #topic_title');
        const descriptionField = document.querySelector('[name="description"]');
        
        return (titleField && titleField.value.trim() !== '') || 
               (descriptionField && descriptionField.value.trim() !== '');
    }
    
    // Content type selection
    const contentTypeInputs = document.querySelectorAll('input[name="content_type"]');
    
    // Initial setup
    const initialSelectedType = document.querySelector('input[name="content_type"]:checked')?.value;
    if (initialSelectedType) {
        toggleContentFields(initialSelectedType.toLowerCase());
    }
    
    // Add event listeners to all content type radio buttons
    contentTypeInputs.forEach(input => {
        input.addEventListener('change', function() {
            // Preserve title field value before switching content types
            const titleField = document.querySelector('input[name="title"], #topic_title');
            const titleValue = titleField ? titleField.value : '';
            
            toggleContentFields(this.value.toLowerCase());
            
            // Restore title field value if it was cleared
            if (titleField && titleValue && !titleField.value) {
                titleField.value = titleValue;
                console.log('Restored title field value after content type change');
            }
            
            // Save form data when content type changes
            saveFormData(formId);
        });
    });
    
    // Toggle visibility of content type specific fields
    function toggleContentFields(selectedType) {
        // Define content types that should hide the Instructions field
        const hideInstructionsTypes = ['video', 'document', 'text', 'audio', 'web', 'embedvideo', 'scorm', 'quiz', 'assignment', 'conference', 'discussion'];
        
        // Handle Instructions field visibility
        const instructionsField = document.querySelector('label[for*="instructions"]').closest('div');
        if (instructionsField) {
            if (hideInstructionsTypes.includes(selectedType)) {
                instructionsField.style.display = 'none';
                console.log('Hiding Instructions field for content type:', selectedType);
            } else {
                instructionsField.style.display = 'block';
                console.log('Showing Instructions field for content type:', selectedType);
            }
        }
        
        // Hide all content type fields
        document.querySelectorAll('.content-type-field').forEach(field => {
            field.classList.add('hidden');
            field.classList.remove('active');
        });
        
        // Show the selected content type field
        const selectedField = document.getElementById(selectedType + '-content');
        if (selectedField) {
            selectedField.classList.remove('hidden');
            selectedField.classList.add('active');
            
            // Force visibility for better compatibility
            selectedField.style.display = 'block';
            selectedField.style.visibility = 'visible';
            selectedField.style.opacity = '1';
            
            // Special handling for text content
            if (selectedType === 'text') {
                console.log('Text content type selected');
                // Ensure TinyMCE is properly initialized for text content
                setTimeout(function() {
                    const textArea = selectedField.querySelector('textarea');
                    if (textArea && typeof tinymce !== 'undefined') {
                        const editorId = textArea.id || 'id_text_content';
                        if (tinymce.get(editorId)) {
                            console.log('TinyMCE already initialized for:', editorId);
                            // Make sure the editor container is visible
                            const editorContainer = tinymce.get(editorId).getContainer();
                            if (editorContainer) {
                                editorContainer.style.display = 'block';
                                editorContainer.style.visibility = 'visible';
                                editorContainer.style.opacity = '1';
                            }
                        } else {
                            console.log('Initializing TinyMCE for text content field...');
                            // Initialize TinyMCE if not already done
                            if (typeof window.TinyMCEWidget !== 'undefined' && window.TinyMCEWidget.initialize) {
                                window.TinyMCEWidget.initialize(textArea);
                            }
                        }
                    }
                }, 100);
            }
            
            // Log for debugging
            console.log(`Showing ${selectedType} content field`);
        }
        
        // Hide/show quiz, assignment, conference, discussion dropdowns
        const dropdownTypes = ['quiz', 'assignment', 'conference', 'discussion'];
        
        dropdownTypes.forEach(type => {
            const button = document.getElementById(`${type}-dropdown-button`);
            const dropdown = document.getElementById(`${type}-dropdown`);
            
            if (button && dropdown) {
                if (selectedType === type) {
                    button.classList.remove('hidden');
                    // Don't show dropdown automatically, wait for button click
                } else {
                    button.classList.add('hidden');
                    dropdown.classList.add('hidden');
                }
            }
        });
    }

    // Setup dropdown toggle buttons
    const dropdownTypes = ['quiz', 'assignment', 'conference', 'discussion'];
    
    dropdownTypes.forEach(type => {
        const button = document.getElementById(`${type}-dropdown-button`);
        const dropdown = document.getElementById(`${type}-dropdown`);
        
        if (button && dropdown) {
            button.addEventListener('click', function(e) {
                e.preventDefault();
                dropdown.classList.toggle('hidden');
            });
            
            // Close dropdown when clicking outside
            document.addEventListener('click', function(e) {
                if (!button.contains(e.target) && !dropdown.contains(e.target)) {
                    dropdown.classList.add('hidden');
                }
            });
        }
    });

    // Setup content type radio button change handlers
    document.querySelectorAll('input[name="content_type"]').forEach(radio => {
        radio.addEventListener('change', function() {
            if (this.checked) {
                console.log('Content type changed to:', this.value);
                toggleContentFields(this.value.toLowerCase());
            }
        });
    });
    
    // Initial setup - show the correct field if a content type is already selected
    const selectedContentType = document.querySelector('input[name="content_type"]:checked');
    if (selectedContentType) {
        console.log('Initial content type:', selectedContentType.value);
        toggleContentFields(selectedContentType.value.toLowerCase());
    }

    // Additional debugging and fix for web content
    
    // Monitor for web content type selection specifically - check both cases
    const webRadio = document.querySelector('input[name="content_type"][value="Web"]') || 
                     document.querySelector('input[name="content_type"][value="web"]');
    if (webRadio) {
        console.log('Web radio button found:', webRadio);
        webRadio.addEventListener('change', function() {
            if (this.checked) {
                console.log('Web content type selected!');
                const webContentDiv = document.getElementById('web-content');
                const webUrlField = document.querySelector('[name="web_url"]');
                
                console.log('Web content div:', webContentDiv);
                console.log('Web URL field:', webUrlField);
                
                if (webContentDiv) {
                    // Remove all possible hiding mechanisms
                    webContentDiv.style.display = 'block';
                    webContentDiv.style.visibility = 'visible';
                    webContentDiv.style.height = 'auto';
                    webContentDiv.style.overflow = 'visible';
                    webContentDiv.style.opacity = '1';
                    webContentDiv.classList.remove('hidden');
                    webContentDiv.classList.add('active');
                }
                
                if (webUrlField) {
                    webUrlField.focus();
                    console.log('Web URL field focused');
                }
            }
        });
    } else {
        console.error('Web radio button not found!');
    }

    // Handle endless access checkbox
    const endlessAccessCheckbox = document.getElementById('topic_endless_access');
    const endDateInput = document.getElementById('topic_end_date');
    
    if (endlessAccessCheckbox && endDateInput) {
        endlessAccessCheckbox.addEventListener('change', function() {
            endDateInput.disabled = this.checked;
            if (this.checked) {
                endDateInput.value = '';
            }
            // Save form data when this changes
            saveFormData(formId);
        });
    }
    
    // Function to display validation errors next to fields
    function displayFieldError(fieldName, errorMessage) {
        const field = document.querySelector(`[name="${fieldName}"]`);
        if (field) {
            // Remove any existing error for this field
            const existingError = field.parentNode.querySelector('.validation-error');
            if (existingError) existingError.remove();
            
            // Create and insert error message
            const errorElement = document.createElement('div');
            errorElement.className = 'validation-error text-red-500 mt-1 text-sm';
            errorElement.textContent = errorMessage;
            field.parentNode.appendChild(errorElement);
            
            // Highlight the field
            field.classList.add('border-red-500');
            
            // Focus the field
            field.focus();
        } else {
            // If field not found, add to global errors
            displayGlobalError(fieldName + ': ' + errorMessage);
        }
    }
    
    // Function to display global errors
    function displayGlobalError(errorMessage) {
        const form = document.getElementById('topicForm');
        if (!form) return;
        
        // Remove any existing global errors
        const existingErrors = form.querySelectorAll('.global-form-error');
        existingErrors.forEach(error => error.remove());
        
        const errorElement = document.createElement('div');
        errorElement.className = 'global-form-error bg-red-100 border-l-4 border-red-500 text-red-700 p-4 mb-4';
        errorElement.innerHTML = `<p>${errorMessage}</p>`;
        form.prepend(errorElement);
        
        // Scroll to error
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
    
    // Clear validation errors on input
    document.querySelectorAll('input, textarea, select').forEach(element => {
        element.addEventListener('input', function() {
            // Remove validation styling
            this.classList.remove('border-red-500');
            
            // Remove error message if it exists
            const error = this.parentNode.querySelector('.validation-error');
            if (error) error.remove();
            
            // Save form data on input
            saveFormData(formId);
        });
        
        // Also save on change events (for dropdowns, checkboxes, etc.)
        element.addEventListener('change', function() {
            saveFormData(formId);
        });
    });
    
    // Handle section dropdown change
    const sectionSelect = document.getElementById('section');
    const newSectionInput = document.getElementById('new-section-input');
    
    if (sectionSelect && newSectionInput) {
        // Toggle visibility of the new section name input based on selection
        sectionSelect.addEventListener('change', function() {
            if (this.value === 'new_section') {
                newSectionInput.style.display = 'block';
                
                // Focus the input field
                const nameInput = document.getElementById('new_section_name');
                if (nameInput) {
                    setTimeout(() => nameInput.focus(), 100);
                }
            } else {
                newSectionInput.style.display = 'none';
            }
            
            // Save form data when section changes
            saveFormData(formId);
        });
        
        // Initial state check
        if (sectionSelect.value === 'new_section') {
            newSectionInput.style.display = 'block';
        }
    }
    
    // Form submission handler
    if (topicForm) {
        topicForm.addEventListener('submit', function(event) {
            // Save the original submit event to use later
            event.preventDefault();
            
            // Clear any existing error messages
            document.querySelectorAll('.validation-error, .global-form-error').forEach(el => el.remove());
            
            // Handle new section creation if needed
            const sectionSelect = document.getElementById('section');
            const newSectionNameInput = document.getElementById('new_section_name');
            
            if (sectionSelect && sectionSelect.value === 'new_section' && newSectionNameInput) {
                const newSectionName = newSectionNameInput.value.trim();
                
                if (!newSectionName) {
                    // Show error if new section name is empty
                    displayFieldError('new_section_name', 'Please enter a name for the new section');
                    return;
                }
                
                // Create a new section via AJAX
                const formData = new FormData();
                formData.append('name', newSectionName);
                formData.append('csrfmiddlewaretoken', document.querySelector('input[name="csrfmiddlewaretoken"]').value);
                
                // Get course ID from URL
                const urlParts = window.location.pathname.split('/');
                const courseId = urlParts[2]; // Assuming URL pattern: /courses/{courseId}/topic/create/
                
                fetch(`/courses/section/${courseId}/create/`, {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                })
                .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
                .then(data => {
                    if (data.success) {
                        // Add the new section to the dropdown
                        const newOption = document.createElement('option');
                        newOption.value = data.section_id;
                        newOption.text = data.section_name;
                        
                        // Insert before the "Create New Section" option
                        const createNewOption = sectionSelect.querySelector('option[value="new_section"]');
                        if (createNewOption) {
                            sectionSelect.insertBefore(newOption, createNewOption);
                        } else {
                            sectionSelect.appendChild(newOption);
                        }
                        
                        // Select the new section
                        newOption.selected = true;
                        
                        // Hide the new section input
                        newSectionInput.style.display = 'none';
                        
                        // Continue with the form submission
                        continueFormSubmission();
                    } else {
                        // Show error message
                        displayGlobalError(data.error || 'Error creating section');
                    }
                })
                .catch(error => {
                    console.error('Error creating section:', error);
                    displayGlobalError('Error creating section. Please try again.');
                });
            } else {
                // No new section needed, continue with form submission
                continueFormSubmission();
            }
            
            // Function to continue with the regular form validation and submission
            function continueFormSubmission() {
                // Get the selected content type - either from visible radio or hidden field
                let selectedType;
                const radioButton = document.querySelector('input[name="content_type"]:checked');
                const hiddenField = document.querySelector('input[type="hidden"][name="content_type"]');
                
                if (radioButton) {
                    selectedType = radioButton.value;
                } else if (hiddenField) {
                    selectedType = hiddenField.value;
                }
                
                if (!selectedType) {
                    // Use enhanced error handler if available
                    if (window.LMS && window.LMS.ErrorHandler) {
                        window.LMS.ErrorHandler.showError('Please select a content type');
                    } else {
                        displayGlobalError('Please select a content type');
                    }
                    return;
                }
                
                const contentTypeLower = selectedType.toLowerCase();
                
                // Validate fields based on content type
                let validationPassed = true;
                
                // Validate title
                const titleField = document.querySelector('[name="title"]');
                if (!titleField || !titleField.value.trim()) {
                    displayFieldError('title', 'Title is required');
                    validationPassed = false;
                }
                
                // Validate content fields based on type
                if (contentTypeLower === 'text') {
                    // Make sure TinyMCE content is included in the form data
                    if (typeof tinyMCE !== 'undefined') {
                        const textEditor = tinyMCE.get('id_text_content');
                        if (textEditor) {
                            // Get the content from TinyMCE editor
                            const content = textEditor.getContent();
                            if (!content.trim() || content === '<p></p>' || content === '<p>&nbsp;</p>') {
                                displayFieldError('text_content', 'Text content is required');
                                validationPassed = false;
                            }
                            
                            // Update the hidden input field
                            const textContentField = document.querySelector('[name="text_content"]');
                            if (textContentField) {
                                textContentField.value = content;
                            } else {
                                // Create a hidden field if it doesn't exist
                                const hiddenField = document.createElement('input');
                                hiddenField.type = 'hidden';
                                hiddenField.name = 'text_content';
                                hiddenField.value = content;
                                topicForm.appendChild(hiddenField);
                            }
                        }
                    }
                } else if (contentTypeLower === 'web') {
                    const webUrlField = document.querySelector('[name="web_url"]');
                    
                    // Make absolutely sure the web-content div is visible
                    const webContentDiv = document.getElementById('web-content');
                    if (webContentDiv) {
                        // Remove all possible hiding mechanisms
                        webContentDiv.style.display = 'block';
                        webContentDiv.style.visibility = 'visible';
                        webContentDiv.style.height = 'auto';
                        webContentDiv.style.overflow = 'visible';
                        webContentDiv.style.opacity = '1';
                        webContentDiv.classList.remove('hidden');
                        webContentDiv.classList.add('active');
                    }
                    
                    if (!webUrlField || !webUrlField.value.trim()) {
                        displayFieldError('web_url', 'URL is required for web content');
                        validationPassed = false;
                    } else if (!isValidURL(webUrlField.value.trim())) {
                        displayFieldError('web_url', 'Please enter a valid URL (e.g., https://example.com)');
                        validationPassed = false;
                    }
                } else if (contentTypeLower === 'embedvideo') {
                    const embedCodeField = document.querySelector('[name="embed_code"]');
                    if (!embedCodeField || !embedCodeField.value.trim()) {
                        displayFieldError('embed_code', 'Embed code is required');
                        validationPassed = false;
                    }
                } else if (['video', 'audio', 'document', 'scorm'].includes(contentTypeLower)) {
                    const fileInput = document.querySelector('#' + contentTypeLower + '-content input[type="file"]');
                    
                    // Check if editing existing topic
                    const isEdit = !!document.getElementById('edit_topic_id')?.value;
                    const hasExistingFile = document.querySelector('#' + contentTypeLower + '-content .selected-filename')?.textContent.includes('Current file:');
                    
                    // Special handling for SCORM - prevent file replacement and support direct upload
                    if (contentTypeLower === 'scorm') {
                        if (isEdit && hasExistingFile && fileInput && fileInput.files.length > 0) {
                            displayFieldError('content_file', 'SCORM packages cannot be replaced once uploaded. Please create a new topic if you need to upload a different SCORM package.');
                            validationPassed = false;
                        }
                        // For SCORM, file is optional (direct upload to cloud is supported)
                    } else {
                        // For other content types, file is required
                        if (!isEdit || (fileInput && fileInput.files.length > 0)) {
                            if (!fileInput || fileInput.files.length === 0) {
                                displayFieldError('content_file', 'Please select a file to upload');
                                validationPassed = false;
                            }
                        }
                    }
                } else if (contentTypeLower === 'quiz') {
                    const quizField = document.querySelector('[name="quiz"]');
                    if (!quizField || !quizField.value) {
                        displayFieldError('quiz', 'Please select a quiz');
                        validationPassed = false;
                    }
                } else if (contentTypeLower === 'assignment') {
                    const assignmentField = document.querySelector('[name="assignment"]');
                    if (!assignmentField || !assignmentField.value) {
                        displayFieldError('assignment', 'Please select an assignment');
                        validationPassed = false;
                    }
                } else if (contentTypeLower === 'conference') {
                    const conferenceField = document.querySelector('[name="conference"]');
                    if (!conferenceField || !conferenceField.value) {
                        displayFieldError('conference', 'Please select a conference');
                        validationPassed = false;
                    }
                } else if (contentTypeLower === 'discussion') {
                    const discussionField = document.querySelector('[name="discussion"]');
                    if (!discussionField || !discussionField.value) {
                        displayFieldError('discussion', 'Please select a discussion');
                        validationPassed = false;
                    }
                }
                
                // If validation fails, stop the submission
                if (!validationPassed) {
                    return;
                }
                
                // Clear saved form data on successful submission
                clearSavedFormData(formId);
                
                // Check if this is an AJAX submission or regular form
                const useAjax = topicForm.getAttribute('data-ajax') === 'true';
                
                if (useAjax) {
                    // Submit via AJAX
                    const formData = new FormData(topicForm);
                    
                    // Ensure TinyMCE content is included for text-type topics
                    if (contentTypeLower === 'text' && typeof tinyMCE !== 'undefined') {
                        const textEditor = tinyMCE.get('id_text_content');
                        if (textEditor) {
                            const content = textEditor.getContent();
                            console.log('TinyMCE content:', content);
                            formData.set('text_content', content);
                        }
                    }
                    
                    // Special handling for SCORM uploads
                    let uploadUrl = topicForm.action;
                    if (contentTypeLower === 'scorm') {
                        // Use the SCORM upload endpoint for SCORM content
                        uploadUrl = '/scorm/upload/topic/';
                        console.log('Using SCORM upload endpoint:', uploadUrl);
                    }
                    
                    // Show loading state
                    const submitButton = topicForm.querySelector('button[type="submit"]');
                    const originalButtonText = submitButton.innerHTML;
                    submitButton.disabled = true;
                    submitButton.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Submitting...';
                    
                    // Add progress tracking
                    const progressContainer = document.createElement('div');
                    progressContainer.id = 'progress-container';
                    progressContainer.className = 'fixed top-4 right-4 bg-white p-4 rounded-lg shadow-lg z-50';
                    progressContainer.innerHTML = `
                        <div class="text-sm font-medium mb-2">Uploading content...</div>
                        <div class="w-64 bg-gray-200 rounded-full h-2.5">
                            <div id="progress-bar" class="bg-blue-600 h-2.5 rounded-full" style="width: 0%"></div>
                        </div>
                        <div class="text-xs text-gray-500 mt-1"><span id="progress-percent">0%</span> complete</div>
                    `;
                    
                    // Only show progress for file uploads
                    if (['video', 'audio', 'document', 'scorm'].includes(contentTypeLower)) {
                        document.body.appendChild(progressContainer);
                    }
                    
                    // Create XHR request with progress monitoring
                    const xhr = new XMLHttpRequest();
                    
                    xhr.upload.addEventListener('progress', function(e) {
                        if (e.lengthComputable) {
                            const percent = Math.round((e.loaded / e.total) * 100);
                            const progressBar = document.getElementById('progress-bar');
                            const progressText = document.getElementById('progress-percent');
                            
                            if (progressBar && progressText) {
                                progressBar.style.width = percent + '%';
                                progressText.textContent = percent + '%';
                            }
                        }
                    });
                    
                    xhr.addEventListener('load', function() {
                        // Remove progress indicator
                        const progressContainer = document.getElementById('progress-container');
                        if (progressContainer) {
                            progressContainer.remove();
                        }
                        
                        // Reset button state
                        submitButton.disabled = false;
                        submitButton.innerHTML = originalButtonText;
                        
                        // Parse response
                        try {
                            const response = JSON.parse(xhr.responseText);
                            
                            if (xhr.status >= 200 && xhr.status < 300) {
                                // Success
                                displayGlobalSuccess(response.message || 'Topic saved successfully.');
                                
                                // Clear saved form data on success
                                clearSavedFormData(formId);
                                
                                // Redirect if a redirect URL is provided
                                if (response.redirect_url) {
                                    window.location.href = response.redirect_url;
                                }
                            } else {
                                // Error
                                if (response.field_errors) {
                                    // Display field-specific errors with user-friendly messages
                                    for (const field in response.field_errors) {
                                        let errorMessage = response.field_errors[field];
                                        
                                        // Enhance error messages for common storage issues
                                        if (typeof errorMessage === 'string') {
                                            if (errorMessage.includes('disk space') || errorMessage.includes('storage')) {
                                                errorMessage = 'Server storage is full. Please try again later or contact support.';
                                            } else if (errorMessage.includes('No space left')) {
                                                errorMessage = 'Server storage is full. Please try uploading a smaller file or contact support.';
                                            }
                                        }
                                        
                                        displayFieldError(field, errorMessage);
                                    }
                                } else {
                                    // Display global error with enhanced messaging
                                    let globalError = response.error || 'Unable to save topic. Please check your input and try again.';
                                    if (globalError.includes('disk space') || globalError.includes('storage') || globalError.includes('No space left')) {
                                        globalError = 'Server storage is full. Please try again later or contact support.';
                                    }
                                    displayGlobalError(globalError);
                                }
                            }
                        } catch (e) {
                            // If response isn't JSON, likely a 500 error
                            displayGlobalError('Unable to save topic. Please check your input and try again, or contact support if the problem persists.');
                            console.error('Error parsing response:', e);
                        }
                    });
                    
                    xhr.addEventListener('error', function() {
                        // Remove progress indicator
                        const progressContainer = document.getElementById('progress-container');
                        if (progressContainer) {
                            progressContainer.remove();
                        }
                        
                        // Reset button state
                        submitButton.disabled = false;
                        submitButton.innerHTML = originalButtonText;
                        
                        // Display error using enhanced handler
                        if (window.LMS && window.LMS.ErrorHandler) {
                            window.LMS.ErrorHandler.showError('Network error occurred. Please check your connection and try again.');
                        } else {
                            displayGlobalError('Network error occurred. Please check your connection and try again.');
                        }
                    });
                    
                    // Open and send the request
                    xhr.open('POST', uploadUrl);
                    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
                    xhr.send(formData);
                } else {
                    // Regular form submission
                    // Make sure TinyMCE content is included in the form data
                    if (contentTypeLower === 'text' && typeof tinyMCE !== 'undefined') {
                        const textEditor = tinyMCE.get('id_text_content');
                        if (textEditor) {
                            // Get the content from TinyMCE editor
                            const content = textEditor.getContent();
                            
                            // Update the hidden input field
                            const textContentField = document.querySelector('[name="text_content"]');
                            if (textContentField) {
                                textContentField.value = content;
                            } else {
                                // Create a hidden field if it doesn't exist
                                const hiddenField = document.createElement('input');
                                hiddenField.type = 'hidden';
                                hiddenField.name = 'text_content';
                                hiddenField.value = content;
                                topicForm.appendChild(hiddenField);
                            }
                        }
                    }
                    
                    // Submit the form
                    topicForm.submit();
                }
            }
            
            // Helper function to validate URLs
            function isValidURL(url) {
                try {
                    new URL(url);
                    return true;
                } catch (e) {
                    return false;
                }
            }
        });
    }
    
    // Function to display a success message
    function displayGlobalSuccess(message) {
        const form = document.getElementById('topicForm');
        if (!form) return;
        
        const successElement = document.createElement('div');
        successElement.className = 'global-form-success bg-green-100 border-l-4 border-green-500 text-green-700 p-4 mb-4';
        successElement.innerHTML = `<p>${message}</p>`;
        form.prepend(successElement);
        
        // Scroll to success message
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
    
    // Functions to save and load form data
    function saveFormData(formId) {
        if (!topicForm || !formId) return;
        
        const formData = {};
        
        // Save all input values
        topicForm.querySelectorAll('input, textarea, select').forEach(element => {
            // Skip password fields and file inputs
            if (element.type === 'password' || element.type === 'file') return;
            
            // Handle different input types
            if (element.type === 'radio' || element.type === 'checkbox') {
                formData[element.name] = element.checked;
            } else {
                formData[element.name] = element.value;
            }
        });
        
        // Save TinyMCE content if available
        if (typeof tinyMCE !== 'undefined') {
            const textEditor = tinyMCE.get('id_text_content');
            if (textEditor) {
                formData['text_content'] = textEditor.getContent();
            }
        }
        
        // Save to localStorage
        try {
            localStorage.setItem('topicForm_' + formId, JSON.stringify(formData));
        } catch (e) {
            console.warn('Could not save form data to localStorage:', e);
        }
    }
    
    function loadSavedFormData(formId) {
        if (!topicForm || !formId) return;
        
        // Enhanced create vs edit detection with multiple failsafes
        const topicIdField = document.querySelector('input[name="topic_id"]');
        const hasTopicId = topicIdField && topicIdField.value && topicIdField.value.trim() !== '';
        
        const currentPath = window.location.pathname;
        const isCreatePage = currentPath.includes('/create') || currentPath.includes('/add') || currentPath.includes('/topic/create/');
        
        // Check form action URL as well
        const formAction = topicForm ? topicForm.action : '';
        const isCreateAction = formAction.includes('/create') || formAction.includes('/add');
        
        // Check page header for create indicators
        const pageHeader = document.querySelector('h1');
        const isCreateHeader = pageHeader && (pageHeader.textContent.includes('Create') || pageHeader.textContent.includes('Add'));
        
        // Enhanced create mode detection - if ANY indicator suggests create mode, treat as create
        const isCreateMode = !hasTopicId || isCreatePage || isCreateAction || isCreateHeader;
        
        // For create operations, absolutely ensure clean form - users expect fresh forms for new topics
        if (isCreateMode) {
            console.log('FAILSAFE: Create mode detected in loadSavedFormData - ensuring clean form without prefilled data');
            console.log('Detection details:', {
                hasTopicId: hasTopicId,
                isCreatePage: isCreatePage,
                isCreateAction: isCreateAction,
                isCreateHeader: isCreateHeader,
                currentPath: currentPath,
                formAction: formAction
            });
            
            // Clear any existing localStorage data for create operations to prevent confusion
            try {
                localStorage.removeItem('topicForm_' + formId);
                
                // Also clear any old entries with different formKey patterns
                const keysToRemove = [];
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    if (key && key.indexOf('topicForm_') !== -1) {
                        keysToRemove.push(key);
                    }
                }
                keysToRemove.forEach(key => localStorage.removeItem(key));
                
                console.log('FAILSAFE: Cleared localStorage entries for clean form:', keysToRemove);
                
            } catch (e) {
                console.warn('Could not clear saved form data:', e);
            }
            
            // Only clear title field if it's empty (preserve user input)
            const titleField = document.querySelector('input[name="title"], #topic_title');
            if (titleField && !titleField.value.trim()) {
                titleField.value = '';
                console.log('FAILSAFE: Title field cleared (was empty)');
            } else if (titleField && titleField.value.trim()) {
                console.log('FAILSAFE: Preserving user input in title field');
            }
            
            return;
        }
        
        try {
            const savedData = localStorage.getItem('topicForm_' + formId);
            if (!savedData) return;
            
            const formData = JSON.parse(savedData);
            
            // Populate form fields
            for (const fieldName in formData) {
                const elements = topicForm.querySelectorAll(`[name="${fieldName}"]`);
                if (!elements.length) continue;
                
                elements.forEach(element => {
                    if (element.type === 'radio' || element.type === 'checkbox') {
                        element.checked = formData[fieldName];
                    } else {
                        element.value = formData[fieldName];
                    }
                });
            }
            
            // Restore TinyMCE content if available
            if (typeof tinyMCE !== 'undefined' && formData['text_content']) {
                const initEditor = function() {
                    const textEditor = tinyMCE.get('id_text_content');
                    if (textEditor) {
                        textEditor.setContent(formData['text_content']);
                    } else {
                        // If editor isn't ready yet, try again shortly
                        setTimeout(initEditor, 500);
                    }
                };
                
                // Start trying to set content
                initEditor();
            }
            
            // Update any dependent fields
            // For example, show/hide new section input
            const sectionSelect = document.getElementById('section');
            const newSectionInput = document.getElementById('new-section-input');
            if (sectionSelect && newSectionInput && sectionSelect.value === 'new_section') {
                newSectionInput.style.display = 'block';
            }
            
            // Toggle content type fields
            const selectedType = document.querySelector('input[name="content_type"]:checked')?.value;
            if (selectedType) {
                toggleContentFields(selectedType.toLowerCase());
            }
            
            console.log('Edit mode detected - Form data restored from localStorage');
        } catch (e) {
            console.warn('Could not load saved form data:', e);
        }
    }
    
    function clearSavedFormData(formId) {
        if (!formId) return;
        
        try {
            localStorage.removeItem('topicForm_' + formId);
            console.log('Saved form data cleared');
        } catch (e) {
            console.warn('Could not clear saved form data:', e);
        }
    }

    // Simple fix: Ensure form includes all fields even if hidden
    if (topicForm) {
        topicForm.addEventListener('submit', function(e) {
            // Check if web content is selected
            const selectedType = document.querySelector('input[name="content_type"]:checked');
            if (selectedType && selectedType.value.toLowerCase() === 'web') {
                const webUrlField = document.querySelector('[name="web_url"]');
                const webContentDiv = document.getElementById('web-content');
                
                if (webUrlField) {
                    // Ensure the field is not disabled
                    webUrlField.disabled = false;
                    console.log('Web URL field value on submit:', webUrlField.value);
                    
                    // If field has value but parent is hidden, create a hidden input
                    if (webUrlField.value.trim() && webContentDiv && window.getComputedStyle(webContentDiv).display === 'none') {
                        console.log('Web content div appears hidden, creating backup field');
                        let hiddenInput = document.createElement('input');
                        hiddenInput.type = 'hidden';
                        hiddenInput.name = 'web_url';
                        hiddenInput.value = webUrlField.value;
                        topicForm.appendChild(hiddenInput);
                        
                        // Temporarily rename original field to prevent conflict
                        webUrlField.name = 'web_url_original';
                    }
                }
            }
        });
    }
}); 