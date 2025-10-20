/**
 * Form Validation - Provides client-side form validation
 */
(function() {
    'use strict';
    
    const FormValidation = {
        init: function() {
            this.setupValidation();
            this.setupRealTimeValidation();
        },
        
        setupValidation: function() {
            const forms = document.querySelectorAll('[data-validate]');
            
            forms.forEach(form => {
                form.addEventListener('submit', this.handleFormSubmit.bind(this));
            });
        },
        
        setupRealTimeValidation: function() {
            const inputs = document.querySelectorAll('[data-required], [data-email], [data-min-length], [data-max-length]');
            
            inputs.forEach(input => {
                input.addEventListener('blur', this.validateInput.bind(this));
                input.addEventListener('input', this.clearErrors.bind(this));
            });
        },
        
        handleFormSubmit: function(event) {
            const form = event.target;
            const isValid = this.validateForm(form);
            
            if (!isValid) {
                event.preventDefault();
                this.focusFirstError(form);
            }
        },
        
        validateForm: function(form) {
            let isValid = true;
            const inputs = form.querySelectorAll('[data-required], [data-email], [data-min-length], [data-max-length]');
            
            inputs.forEach(input => {
                if (!this.validateInput({ target: input })) {
                    isValid = false;
                }
            });
            
            return isValid;
        },
        
        validateInput: function(event) {
            const input = event.target;
            const value = input.value.trim();
            let isValid = true;
            
            // Clear previous errors
            this.clearInputErrors(input);
            
            // Required validation
            if (input.hasAttribute('data-required') && !value) {
                this.showError(input, 'This field is required');
                isValid = false;
            }
            
            // Email validation
            if (value && input.hasAttribute('data-email') && !this.isValidEmail(value)) {
                this.showError(input, 'Please enter a valid email address');
                isValid = false;
            }
            
            // Min length validation
            const minLength = input.getAttribute('data-min-length');
            if (value && minLength && value.length < parseInt(minLength)) {
                this.showError(input, `Minimum ${minLength} characters required`);
                isValid = false;
            }
            
            // Max length validation
            const maxLength = input.getAttribute('data-max-length');
            if (value && maxLength && value.length > parseInt(maxLength)) {
                this.showError(input, `Maximum ${maxLength} characters allowed`);
                isValid = false;
            }
            
            // Password confirmation
            if (input.hasAttribute('data-confirm-password')) {
                const passwordField = document.getElementById(input.getAttribute('data-confirm-password'));
                if (passwordField && value !== passwordField.value) {
                    this.showError(input, 'Passwords do not match');
                    isValid = false;
                }
            }
            
            return isValid;
        },
        
        isValidEmail: function(email) {
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            return emailRegex.test(email);
        },
        
        showError: function(input, message) {
            input.classList.add('error', 'border-red-500');
            
            let errorElement = input.parentNode.querySelector('.validation-error');
            if (!errorElement) {
                errorElement = document.createElement('div');
                errorElement.className = 'validation-error text-red-500 text-sm mt-1';
                input.parentNode.appendChild(errorElement);
            }
            
            errorElement.textContent = message;
        },
        
        clearErrors: function(event) {
            const input = event.target;
            this.clearInputErrors(input);
        },
        
        clearInputErrors: function(input) {
            input.classList.remove('error', 'border-red-500');
            
            const errorElement = input.parentNode.querySelector('.validation-error');
            if (errorElement) {
                errorElement.remove();
            }
        },
        
        focusFirstError: function(form) {
            const firstError = form.querySelector('.error');
            if (firstError) {
                firstError.focus();
                firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }
    };
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            FormValidation.init();
        });
    } else {
        FormValidation.init();
    }
    
    // Export to global scope
    window.FormValidation = FormValidation;
})();
