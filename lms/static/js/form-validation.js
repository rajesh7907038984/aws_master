/**
 * Enhanced Form Validation System
 * Provides comprehensive client-side validation for all forms in the LMS
 */

(function() {
    'use strict';

    window.FormValidator = {
        init: function() {
            this.setupFormValidation();
            this.setupRequiredFieldValidation();
            this.setupCustomValidation();
            console.log('Form Validator initialized');
        },

        // Setup validation for all forms
        setupFormValidation: function() {
            document.addEventListener('DOMContentLoaded', () => {
                // Find all forms
                const forms = document.querySelectorAll('form');
                forms.forEach(form => {
                    this.enhanceForm(form);
                });
            });

            // Handle dynamically added forms
            const observer = new MutationObserver((mutations) => {
                mutations.forEach((mutation) => {
                    mutation.addedNodes.forEach((node) => {
                        if (node.nodeType === 1) { // Element node
                            if (node.tagName === 'FORM') {
                                this.enhanceForm(node);
                            }
                            // Check for forms within added nodes
                            const forms = node.querySelectorAll ? node.querySelectorAll('form') : [];
                            forms.forEach(form => this.enhanceForm(form));
                        }
                    });
                });
            });

            observer.observe(document.body, {
                childList: true,
                subtree: true
            });
        },

        // Enhance individual form
        enhanceForm: function(form) {
            if (form.hasAttribute('data-validation-enhanced')) return;
            form.setAttribute('data-validation-enhanced', 'true');

            // Add required attributes to fields
            this.addRequiredAttributes(form);

            // Add validation event listeners
            this.addValidationListeners(form);

            // Handle form submission
            form.addEventListener('submit', (e) => {
                if (!this.validateForm(form)) {
                    e.preventDefault();
                    e.stopPropagation();
                    return false;
                }
            });
        },

        // Add required attributes to form fields
        addRequiredAttributes: function(form) {
            const requiredFields = form.querySelectorAll('input, select, textarea');
            
            requiredFields.forEach(field => {
                // Check if field should be required based on Django form
                if (this.shouldBeRequired(field)) {
                    field.setAttribute('required', 'required');
                    field.setAttribute('aria-required', 'true');
                    
                    // Add visual indicator
                    this.addRequiredIndicator(field);
                }
            });
        },

        // Determine if field should be required
        shouldBeRequired: function(field) {
            // Check for explicit required attribute
            if (field.hasAttribute('required')) return true;
            
            // Check for Django form required field indicators
            const fieldName = field.name;
            const form = field.closest('form');
            
            // Check if field has required class or data attribute
            if (field.classList.contains('required') || field.hasAttribute('data-required')) {
                return true;
            }
            
            // Check for required field patterns in field names
            const requiredPatterns = [
                'title', 'name', 'email', 'username', 'password', 'description', 
                'instructions', 'content', 'text_content', 'question_text'
            ];
            
            if (requiredPatterns.some(pattern => fieldName.includes(pattern))) {
                return true;
            }
            
            // Check if field is in a required section
            const fieldContainer = field.closest('.form-group, .field-container, .required-field');
            if (fieldContainer && (
                fieldContainer.classList.contains('required') ||
                fieldContainer.querySelector('.required-indicator') ||
                fieldContainer.textContent.includes('*') ||
                fieldContainer.textContent.includes('Required')
            )) {
                return true;
            }
            
            return false;
        },

        // Add visual indicator for required fields
        addRequiredIndicator: function(field) {
            const label = field.closest('.form-group, .field-container')?.querySelector('label');
            if (label && !label.querySelector('.required-indicator')) {
                const indicator = document.createElement('span');
                indicator.className = 'required-indicator text-red-500 ml-1';
                indicator.textContent = '*';
                indicator.setAttribute('aria-label', 'Required field');
                label.appendChild(indicator);
            }
        },

        // Add validation event listeners
        addValidationListeners: function(form) {
            const fields = form.querySelectorAll('input, select, textarea');
            
            fields.forEach(field => {
                // Real-time validation on blur
                field.addEventListener('blur', () => {
                    this.validateField(field);
                });
                
                // Clear errors on input
                field.addEventListener('input', () => {
                    this.clearFieldError(field);
                });
                
                // Handle special field types
                this.setupFieldSpecificValidation(field);
            });
        },

        // Setup field-specific validation
        setupFieldSpecificValidation: function(field) {
            const fieldType = field.type || field.tagName.toLowerCase();
            
            switch (fieldType) {
                case 'email':
                    field.addEventListener('blur', () => {
                        if (field.value && !this.isValidEmail(field.value)) {
                            this.showFieldError(field, 'Please enter a valid email address');
                        }
                    });
                    break;
                    
                case 'number':
                    field.addEventListener('blur', () => {
                        if (field.value && !this.isValidNumber(field.value, field)) {
                            this.showFieldError(field, 'Please enter a valid number');
                        }
                    });
                    break;
                    
                case 'url':
                    field.addEventListener('blur', () => {
                        if (field.value && !this.isValidUrl(field.value)) {
                            this.showFieldError(field, 'Please enter a valid URL');
                        }
                    });
                    break;
            }
        },

        // Validate entire form
        validateForm: function(form) {
            let isValid = true;
            const errors = [];
            
            // Clear previous errors
            this.clearFormErrors(form);
            
            // Validate all required fields
            const requiredFields = form.querySelectorAll('[required]');
            requiredFields.forEach(field => {
                if (!this.validateField(field)) {
                    isValid = false;
                }
            });
            
            // Validate field-specific rules
            const allFields = form.querySelectorAll('input, select, textarea');
            allFields.forEach(field => {
                if (field.value && !this.validateField(field)) {
                    isValid = false;
                }
            });
            
            // Show general error message if validation fails
            if (!isValid) {
                this.showFormError(form, 'Please correct the errors below and try again.');
                this.scrollToFirstError(form);
            }
            
            return isValid;
        },

        // Validate individual field
        validateField: function(field) {
            const value = field.value.trim();
            let isValid = true;
            let errorMessage = '';
            
            // Check if required field is empty
            if (field.hasAttribute('required') && !value) {
                errorMessage = this.getRequiredFieldMessage(field);
                isValid = false;
            }
            
            // Check field-specific validation
            if (value && isValid) {
                const fieldType = field.type || field.tagName.toLowerCase();
                
                switch (fieldType) {
                    case 'email':
                        if (!this.isValidEmail(value)) {
                            errorMessage = 'Please enter a valid email address';
                            isValid = false;
                        }
                        break;
                        
                    case 'number':
                        if (!this.isValidNumber(value, field)) {
                            errorMessage = 'Please enter a valid number';
                            isValid = false;
                        }
                        break;
                        
                    case 'url':
                        if (!this.isValidUrl(value)) {
                            errorMessage = 'Please enter a valid URL';
                            isValid = false;
                        }
                        break;
                }
            }
            
            // Show or clear error
            if (!isValid) {
                this.showFieldError(field, errorMessage);
            } else {
                this.clearFieldError(field);
            }
            
            return isValid;
        },

        // Get appropriate required field message
        getRequiredFieldMessage: function(field) {
            const fieldName = field.name || 'This field';
            const label = field.closest('.form-group, .field-container')?.querySelector('label');
            const labelText = label ? label.textContent.replace('*', '').trim() : fieldName;
            
            return `${labelText} is required`;
        },

        // Validation helper functions
        isValidEmail: function(email) {
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            return emailRegex.test(email);
        },

        isValidNumber: function(value, field) {
            const num = parseFloat(value);
            if (isNaN(num)) return false;
            
            const min = field.getAttribute('min');
            const max = field.getAttribute('max');
            
            if (min && num < parseFloat(min)) return false;
            if (max && num > parseFloat(max)) return false;
            
            return true;
        },

        isValidUrl: function(url) {
            try {
                new URL(url);
                return true;
            } catch {
                return false;
            }
        },

        // Error display functions
        showFieldError: function(field, message) {
            this.clearFieldError(field);
            
            // Add error styling
            field.classList.add('border-red-500', 'bg-red-50');
            field.setAttribute('aria-invalid', 'true');
            
            // Create error message
            const errorDiv = document.createElement('div');
            errorDiv.className = 'field-error text-red-600 text-sm mt-1 flex items-center';
            errorDiv.innerHTML = `
                <svg class="w-4 h-4 mr-1 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
                </svg>
                ${message}
            `;
            
            // Insert error message
            const container = field.closest('.form-group, .field-container') || field.parentNode;
            container.appendChild(errorDiv);
        },

        clearFieldError: function(field) {
            // Remove error styling
            field.classList.remove('border-red-500', 'bg-red-50');
            field.removeAttribute('aria-invalid');
            
            // Remove error message
            const container = field.closest('.form-group, .field-container') || field.parentNode;
            const errorDiv = container.querySelector('.field-error');
            if (errorDiv) {
                errorDiv.remove();
            }
        },

        clearFormErrors: function(form) {
            // Clear all field errors
            const fields = form.querySelectorAll('input, select, textarea');
            fields.forEach(field => this.clearFieldError(field));
            
            // Clear form-level errors
            const formErrors = form.querySelectorAll('.form-error, .lms-form-error');
            formErrors.forEach(error => error.remove());
        },

        showFormError: function(form, message) {
            // Remove existing form errors
            this.clearFormErrors(form);
            
            // Create form error message
            const errorDiv = document.createElement('div');
            errorDiv.className = 'form-error bg-red-100 border border-red-300 text-red-700 px-4 py-3 rounded mb-4 flex items-center';
            errorDiv.innerHTML = `
                <svg class="w-5 h-5 mr-2 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
                </svg>
                <span>${message}</span>
            `;
            
            // Insert at top of form
            form.insertBefore(errorDiv, form.firstChild);
        },

        scrollToFirstError: function(form) {
            const firstError = form.querySelector('.field-error');
            if (firstError) {
                firstError.scrollIntoView({ 
                    behavior: 'smooth', 
                    block: 'center' 
                });
                
                // Focus the field
                const field = firstError.closest('.form-group, .field-container')?.querySelector('input, select, textarea');
                if (field) {
                    field.focus();
                }
            }
        },

        // Setup required field validation for specific forms
        setupRequiredFieldValidation: function() {
            // Assignment form validation
            this.setupAssignmentFormValidation();
            
            // Course form validation
            this.setupCourseFormValidation();
            
            // User form validation
            this.setupUserFormValidation();
        },

        setupAssignmentFormValidation: function() {
            const assignmentForms = document.querySelectorAll('form[id*="assignment"], form[action*="assignment"]');
            assignmentForms.forEach(form => {
                // Mark specific fields as required
                const requiredFields = [
                    'title', 'description', 'instructions'
                ];
                
                requiredFields.forEach(fieldName => {
                    const field = form.querySelector(`[name="${fieldName}"]`);
                    if (field) {
                        field.setAttribute('required', 'required');
                    }
                });
            });
        },

        setupCourseFormValidation: function() {
            const courseForms = document.querySelectorAll('form[id*="course"], form[action*="course"]');
            courseForms.forEach(form => {
                // Mark specific fields as required
                const requiredFields = [
                    'title', 'description'
                ];
                
                requiredFields.forEach(fieldName => {
                    const field = form.querySelector(`[name="${fieldName}"]`);
                    if (field) {
                        field.setAttribute('required', 'required');
                    }
                });
            });
        },

        setupUserFormValidation: function() {
            const userForms = document.querySelectorAll('form[id*="user"], form[action*="user"], form[id*="register"]');
            userForms.forEach(form => {
                // Mark specific fields as required
                const requiredFields = [
                    'username', 'email', 'password1', 'password2'
                ];
                
                requiredFields.forEach(fieldName => {
                    const field = form.querySelector(`[name="${fieldName}"]`);
                    if (field) {
                        field.setAttribute('required', 'required');
                    }
                });
            });
        },

        // Setup custom validation rules
        setupCustomValidation: function() {
            // TinyMCE validation
            this.setupTinyMCEValidation();
            
            // File upload validation
            this.setupFileUploadValidation();
        },

        setupTinyMCEValidation: function() {
            // Handle TinyMCE fields
            if (typeof tinymce !== 'undefined') {
                tinymce.on('AddEditor', (e) => {
                    const editor = e.editor;
                    const textarea = editor.getElement();
                    
                    if (textarea.hasAttribute('required')) {
                        editor.on('change', () => {
                            const content = editor.getContent();
                            if (!content || content.trim() === '' || content === '<p></p>') {
                                this.showFieldError(textarea, 'This field is required');
                            } else {
                                this.clearFieldError(textarea);
                            }
                        });
                    }
                });
            }
        },

        setupFileUploadValidation: function() {
            const fileInputs = document.querySelectorAll('input[type="file"]');
            fileInputs.forEach(input => {
                input.addEventListener('change', () => {
                    if (input.hasAttribute('required') && input.files.length === 0) {
                        this.showFieldError(input, 'Please select a file');
                    } else {
                        this.clearFieldError(input);
                    }
                });
            });
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            FormValidator.init();
        });
    } else {
        FormValidator.init();
    }

})();
