/**
 * Unified Validation System for 100% Frontend-Backend Alignment
 * This system ensures validation rules are identical on frontend and backend
 */

class UnifiedValidationSystem {
    constructor() {
        this.validationRules = {
            // User validation rules
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
                minLength: 14,
                pattern: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]/,
                message: 'Password must be at least 14 characters with uppercase, lowercase, number, and special character'
            },
            first_name: {
                required: true,
                maxLength: 50,
                pattern: /^[a-zA-Z\s]+$/,
                message: 'First name must contain only letters and spaces'
            },
            last_name: {
                required: true,
                maxLength: 50,
                pattern: /^[a-zA-Z\s]+$/,
                message: 'Last name must contain only letters and spaces'
            },
            
            // Course validation rules
            title: {
                required: true,
                minLength: 3,
                maxLength: 200,
                message: 'Title must be 3-200 characters'
            },
            description: {
                required: false,
                maxLength: 2000,
                message: 'Description must be less than 2000 characters'
            },
            
            // File validation rules
            file: {
                maxSize: 50 * 1024 * 1024, // 50MB
                allowedTypes: ['image/jpeg', 'image/png', 'image/gif', 'application/pdf', 'video/mp4'],
                message: 'File must be less than 50MB and be an image, PDF, or video'
            },
            
            // Generic validation rules
            required: {
                required: true,
                message: 'This field is required'
            },
            optional: {
                required: false
            }
        };
        
        this.setupValidation();
    }
    
    /**
     * Setup validation for all forms
     */
    setupValidation() {
        document.addEventListener('DOMContentLoaded', () => {
            this.initializeFormValidation();
        });
    }
    
    /**
     * Initialize validation for all forms
     */
    initializeFormValidation() {
        const forms = document.querySelectorAll('form');
        forms.forEach(form => {
            this.setupFormValidation(form);
        });
    }
    
    /**
     * Setup validation for a specific form
     */
    setupFormValidation(form) {
        // Add validation to form inputs
        const inputs = form.querySelectorAll('input, textarea, select');
        inputs.forEach(input => {
            this.setupInputValidation(input);
        });
        
        // Add form submission validation
        form.addEventListener('submit', (event) => {
            if (!this.validateForm(form)) {
                event.preventDefault();
                return false;
            }
        });
    }
    
    /**
     * Setup validation for a specific input
     */
    setupInputValidation(input) {
        const fieldName = input.name;
        const rules = this.getValidationRules(fieldName);
        
        if (!rules) return;
        
        // Add event listeners for real-time validation
        input.addEventListener('blur', () => {
            this.validateField(input, rules);
        });
        
        input.addEventListener('input', () => {
            this.clearFieldError(input);
        });
    }
    
    /**
     * Get validation rules for a field
     */
    getValidationRules(fieldName) {
        // Direct rule lookup
        if (this.validationRules[fieldName]) {
            return this.validationRules[fieldName];
        }
        
        // Pattern-based rule lookup
        if (fieldName.includes('email')) {
            return this.validationRules.email;
        }
        if (fieldName.includes('password')) {
            return this.validationRules.password;
        }
        if (fieldName.includes('username')) {
            return this.validationRules.username;
        }
        if (fieldName.includes('title')) {
            return this.validationRules.title;
        }
        if (fieldName.includes('description')) {
            return this.validationRules.description;
        }
        if (fieldName.includes('file') || input.type === 'file') {
            return this.validationRules.file;
        }
        
        // Check for required attribute
        if (input.hasAttribute('required')) {
            return this.validationRules.required;
        }
        
        return this.validationRules.optional;
    }
    
    /**
     * Validate a single field
     */
    validateField(input, rules) {
        const value = input.value.trim();
        const errors = [];
        
        // Required validation
        if (rules.required && !value) {
            errors.push(rules.message || 'This field is required');
        }
        
        // Skip other validations if field is empty and not required
        if (!value && !rules.required) {
            this.clearFieldError(input);
            return true;
        }
        
        // Length validations
        if (value && rules.minLength && value.length < rules.minLength) {
            errors.push(`Must be at least ${rules.minLength} characters`);
        }
        if (value && rules.maxLength && value.length > rules.maxLength) {
            errors.push(`Must be no more than ${rules.maxLength} characters`);
        }
        
        // Pattern validation
        if (value && rules.pattern && !rules.pattern.test(value)) {
            errors.push(rules.message || 'Invalid format');
        }
        
        // File validation
        if (input.type === 'file' && input.files.length > 0) {
            const file = input.files[0];
            if (rules.maxSize && file.size > rules.maxSize) {
                errors.push(`File must be less than ${this.formatFileSize(rules.maxSize)}`);
            }
            if (rules.allowedTypes && !rules.allowedTypes.includes(file.type)) {
                errors.push(`File type not allowed. Allowed types: ${rules.allowedTypes.join(', ')}`);
            }
        }
        
        // Show errors or clear them
        if (errors.length > 0) {
            this.showFieldErrors(input, errors);
            return false;
        } else {
            this.clearFieldError(input);
            return true;
        }
    }
    
    /**
     * Validate entire form
     */
    validateForm(form) {
        const inputs = form.querySelectorAll('input, textarea, select');
        let isValid = true;
        
        inputs.forEach(input => {
            const rules = this.getValidationRules(input.name);
            if (rules && !this.validateField(input, rules)) {
                isValid = false;
            }
        });
        
        return isValid;
    }
    
    /**
     * Show field errors
     */
    showFieldErrors(input, errors) {
        this.clearFieldError(input);
        
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
    }
    
    /**
     * Clear field error
     */
    clearFieldError(input) {
        input.classList.remove('error');
        
        const errorContainer = input.parentNode.querySelector('.field-errors');
        if (errorContainer) {
            errorContainer.remove();
        }
    }
    
    /**
     * Format file size for display
     */
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    /**
     * Validate API response errors and map to form fields
     */
    handleAPIValidationErrors(errors) {
        Object.keys(errors).forEach(fieldName => {
            const field = document.querySelector(`[name="${fieldName}"]`);
            if (field) {
                const fieldErrors = Array.isArray(errors[fieldName]) ? errors[fieldName] : [errors[fieldName]];
                this.showFieldErrors(field, fieldErrors);
            }
        });
    }
    
    /**
     * Add custom validation rule
     */
    addValidationRule(fieldName, rules) {
        this.validationRules[fieldName] = rules;
    }
    
    /**
     * Get all validation rules
     */
    getValidationRules() {
        return this.validationRules;
    }
}

// Create global instance
window.UnifiedValidationSystem = UnifiedValidationSystem;
window.unifiedValidation = new UnifiedValidationSystem();

// Make validation functions globally available
window.validateForm = (form) => window.unifiedValidation.validateForm(form);
window.validateField = (input) => {
    const rules = window.unifiedValidation.getValidationRules(input.name);
    return window.unifiedValidation.validateField(input, rules);
};
window.handleAPIValidationErrors = (errors) => window.unifiedValidation.handleAPIValidationErrors(errors);

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('✅ Unified Validation System initialized');
});
