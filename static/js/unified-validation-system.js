/**
 * Unified Validation System for LMS
 * Client-side validation system
 */

(function() {
    'use strict';

    const UnifiedValidation = {
        rules: {
            username: {
                required: true,
                minLength: 3,
                maxLength: 30,
                pattern: /^[a-zA-Z0-9_]+$/,
                message: 'Username must be 3-30 characters, letters, numbers, and underscores only'
            },
            email: {
                required: true,
                pattern: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
                message: 'Please enter a valid email address'
            },
            password: {
                required: true,
                minLength: 8,
                pattern: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/,
                message: 'Password must be at least 8 characters with uppercase, lowercase, and number'
            }
        },
        
        init: function() {
            this.setupFormValidation();
        },
        
        setupFormValidation: function() {
            try {
                document.addEventListener('DOMContentLoaded', () => {
                    try {
                        const forms = document.querySelectorAll('form');
                        forms.forEach(form => {
                            try {
                                this.setupForm(form);
                            } catch (error) {
                                console.error('Error setting up form:', error);
                            }
                        });
                    } catch (error) {
                        console.error('Error in DOMContentLoaded form validation:', error);
                    }
                });
            } catch (error) {
                console.error('Error setting up form validation:', error);
            }
        },
        
        setupForm: function(form) {
            try {
                const inputs = form.querySelectorAll('input, textarea, select');
                inputs.forEach(input => {
                    try {
                        this.setupInput(input);
                    } catch (error) {
                        console.error('Error setting up input:', error);
                    }
                });
                
                form.addEventListener('submit', (e) => {
                    try {
                        if (!this.validateForm(form)) {
                            e.preventDefault();
                        }
                    } catch (error) {
                        console.error('Error validating form on submit:', error);
                    }
                });
            } catch (error) {
                console.error('Error setting up form:', error);
            }
        },
        
        setupInput: function(input) {
            try {
                input.addEventListener('blur', () => {
                    try {
                        this.validateField(input);
                    } catch (error) {
                        console.error('Error validating field on blur:', error);
                    }
                });
                
                input.addEventListener('input', () => {
                    try {
                        this.clearErrors(input);
                    } catch (error) {
                        console.error('Error clearing errors on input:', error);
                    }
                });
            } catch (error) {
                console.error('Error setting up input:', error);
            }
        },
        
        validateField: function(input) {
            const rules = this.getRules(input);
            if (!rules) return true;
            
            const value = input.value.trim();
            const errors = [];
            
            if (rules.required && !value) {
                errors.push(rules.message || 'This field is required');
            }
            
            if (value && rules.minLength && value.length < rules.minLength) {
                errors.push(`Must be at least ${rules.minLength} characters`);
            }
            
            if (value && rules.maxLength && value.length > rules.maxLength) {
                errors.push(`Must be no more than ${rules.maxLength} characters`);
            }
            
            if (value && rules.pattern && !rules.pattern.test(value)) {
                errors.push(rules.message || 'Invalid format');
            }
            
            if (errors.length > 0) {
                this.showErrors(input, errors);
                return false;
            } else {
                this.clearErrors(input);
                return true;
            }
        },
        
        validateForm: function(form) {
            const inputs = form.querySelectorAll('input, textarea, select');
            let isValid = true;
            
            inputs.forEach(input => {
                if (!this.validateField(input)) {
                    isValid = false;
                }
            });
            
            return isValid;
        },
        
        getRules: function(input) {
            const name = input.name;
            if (this.rules[name]) {
                return this.rules[name];
            }
            
            if (name.includes('email')) return this.rules.email;
            if (name.includes('password')) return this.rules.password;
            if (name.includes('username')) return this.rules.username;
            
            if (input.hasAttribute('required')) {
                return { required: true, message: 'This field is required' };
            }
            
            return null;
        },
        
        showErrors: function(input, errors) {
            this.clearErrors(input);
            
            input.classList.add('error');
            
            const errorContainer = document.createElement('div');
            errorContainer.className = 'field-errors';
            
            errors.forEach(error => {
                const errorElement = document.createElement('div');
                errorElement.className = 'field-error text-red-500 text-sm mt-1';
                errorElement.textContent = error;
                errorContainer.appendChild(errorElement);
            });
            
            input.parentNode.appendChild(errorContainer);
        },
        
        clearErrors: function(input) {
            input.classList.remove('error');
            
            const errorContainer = input.parentNode.querySelector('.field-errors');
            if (errorContainer) {
                errorContainer.remove();
            }
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            UnifiedValidation.init();
        });
    } else {
        UnifiedValidation.init();
    }

    // Export to global scope
    window.UnifiedValidation = UnifiedValidation;
})();