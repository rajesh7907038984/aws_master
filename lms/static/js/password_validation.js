/**
 * Password Validation JavaScript
 * Provides real-time password validation and strength checking
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('Password validation script loaded');
    
    // Initialize password validation for all password forms
    initializePasswordValidation();
});

function initializePasswordValidation() {
    // Find all password forms
    const passwordForms = document.querySelectorAll('form');
    
    passwordForms.forEach(form => {
        const password1Field = form.querySelector('input[name="password1"], input[name="new_password1"]');
        const password2Field = form.querySelector('input[name="password2"], input[name="new_password2"]');
        
        if (password1Field && password2Field) {
            setupPasswordValidation(form, password1Field, password2Field);
        }
    });
}

function setupPasswordValidation(form, password1Field, password2Field) {
    // Create password strength indicator
    const strengthIndicator = createPasswordStrengthIndicator();
    const passwordContainer = password1Field.closest('.form-group, .field-container') || password1Field.parentNode;
    passwordContainer.appendChild(strengthIndicator);
    
    // Create password match indicator
    const matchIndicator = createPasswordMatchIndicator();
    const password2Container = password2Field.closest('.form-group, .field-container') || password2Field.parentNode;
    password2Container.appendChild(matchIndicator);
    
    // Add event listeners
    password1Field.addEventListener('input', function() {
        validatePasswordStrength(this.value, strengthIndicator);
        validatePasswordMatch(password1Field.value, password2Field.value, matchIndicator);
    });
    
    password2Field.addEventListener('input', function() {
        validatePasswordMatch(password1Field.value, this.value, matchIndicator);
    });
    
    // Add form submission validation
    form.addEventListener('submit', function(e) {
        if (!validatePasswordSubmission(password1Field, password2Field)) {
            e.preventDefault();
            return false;
        }
    });
}

function createPasswordStrengthIndicator() {
    const indicator = document.createElement('div');
    indicator.className = 'password-strength-indicator mt-2';
    indicator.innerHTML = `
        <div class="strength-bar-container">
            <div class="strength-bar bg-gray-200 rounded-full h-2">
                <div class="strength-bar-fill h-2 rounded-full transition-all duration-300" style="width: 0%"></div>
            </div>
            <div class="strength-text text-sm mt-1"></div>
        </div>
        <div class="strength-requirements text-xs mt-2 space-y-1">
            <div class="requirement" data-requirement="length">
                <span class="requirement-icon">❌</span>
                <span class="requirement-text">At least 8 characters</span>
            </div>
            <div class="requirement" data-requirement="uppercase">
                <span class="requirement-icon">❌</span>
                <span class="requirement-text">One uppercase letter</span>
            </div>
            <div class="requirement" data-requirement="lowercase">
                <span class="requirement-icon">❌</span>
                <span class="requirement-text">One lowercase letter</span>
            </div>
            <div class="requirement" data-requirement="number">
                <span class="requirement-icon">❌</span>
                <span class="requirement-text">One number</span>
            </div>
            <div class="requirement" data-requirement="special">
                <span class="requirement-icon">❌</span>
                <span class="requirement-text">One special character</span>
            </div>
        </div>
    `;
    return indicator;
}

function createPasswordMatchIndicator() {
    const indicator = document.createElement('div');
    indicator.className = 'password-match-indicator mt-2 text-sm';
    indicator.innerHTML = `
        <div class="match-status flex items-center">
            <span class="match-icon mr-1">❌</span>
            <span class="match-text">Passwords must match</span>
        </div>
    `;
    return indicator;
}

function validatePasswordStrength(password, indicator) {
    const requirements = {
        length: password.length >= 8,
        uppercase: /[A-Z]/.test(password),
        lowercase: /[a-z]/.test(password),
        number: /\d/.test(password),
        special: /[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/.test(password)
    };
    
    const passedRequirements = Object.values(requirements).filter(Boolean).length;
    const strengthPercentage = (passedRequirements / 5) * 100;
    
    // Update strength bar
    const strengthBar = indicator.querySelector('.strength-bar-fill');
    const strengthText = indicator.querySelector('.strength-text');
    
    strengthBar.style.width = strengthPercentage + '%';
    
    // Update strength text and color
    if (strengthPercentage < 40) {
        strengthBar.className = 'strength-bar-fill h-2 rounded-full transition-all duration-300 bg-red-500';
        strengthText.textContent = 'Weak';
        strengthText.className = 'strength-text text-sm mt-1 text-red-600';
    } else if (strengthPercentage < 80) {
        strengthBar.className = 'strength-bar-fill h-2 rounded-full transition-all duration-300 bg-yellow-500';
        strengthText.textContent = 'Medium';
        strengthText.className = 'strength-text text-sm mt-1 text-yellow-600';
    } else {
        strengthBar.className = 'strength-bar-fill h-2 rounded-full transition-all duration-300 bg-green-500';
        strengthText.textContent = 'Strong';
        strengthText.className = 'strength-text text-sm mt-1 text-green-600';
    }
    
    // Update individual requirements
    Object.keys(requirements).forEach(requirement => {
        const requirementElement = indicator.querySelector(`[data-requirement="${requirement}"]`);
        const icon = requirementElement.querySelector('.requirement-icon');
        const text = requirementElement.querySelector('.requirement-text');
        
        if (requirements[requirement]) {
            icon.textContent = '✅';
            icon.className = 'requirement-icon text-green-600';
            text.className = 'requirement-text text-green-600';
        } else {
            icon.textContent = '❌';
            icon.className = 'requirement-icon text-red-600';
            text.className = 'requirement-text text-red-600';
        }
    });
    
    return passedRequirements === 5;
}

function validatePasswordMatch(password1, password2, indicator) {
    const matchStatus = indicator.querySelector('.match-status');
    const matchIcon = indicator.querySelector('.match-icon');
    const matchText = indicator.querySelector('.match-text');
    
    if (!password1 || !password2) {
        matchIcon.textContent = '❌';
        matchIcon.className = 'match-icon mr-1 text-red-600';
        matchText.textContent = 'Passwords must match';
        matchText.className = 'match-text text-red-600';
        indicator.className = 'password-match-indicator mt-2 text-sm';
        return false;
    }
    
    if (password1 === password2) {
        matchIcon.textContent = '✅';
        matchIcon.className = 'match-icon mr-1 text-green-600';
        matchText.textContent = 'Passwords match';
        matchText.className = 'match-text text-green-600';
        indicator.className = 'password-match-indicator mt-2 text-sm';
        return true;
    } else {
        matchIcon.textContent = '❌';
        matchIcon.className = 'match-icon mr-1 text-red-600';
        matchText.textContent = 'Passwords do not match';
        matchText.className = 'match-text text-red-600';
        indicator.className = 'password-match-indicator mt-2 text-sm';
        return false;
    }
}

function validatePasswordSubmission(password1Field, password2Field) {
    const password1 = password1Field.value;
    const password2 = password2Field.value;
    
    // Check if user is trying to change password (both fields must be empty or whitespace-only)
    if ((!password1 || !password1.trim()) && (!password2 || !password2.trim())) {
        return true; // No password change attempted
    }
    
    // If only one field has content, that's an error - both must be provided for password change
    const hasPassword1 = password1 && password1.trim();
    const hasPassword2 = password2 && password2.trim();
    
    if (hasPassword1 && !hasPassword2) {
        showFieldError(password2Field, 'Please confirm your new password.');
        return false;
    }
    
    if (hasPassword2 && !hasPassword1) {
        showFieldError(password1Field, 'Please enter a new password.');
        return false;
    }
    
    // Only validate if both fields have content (user is changing password)
    if (hasPassword1 && hasPassword2) {
        // Validate password strength
        const strengthValid = validatePasswordStrength(password1, password1Field.parentNode.querySelector('.password-strength-indicator'));
        if (!strengthValid) {
            showFieldError(password1Field, 'Password does not meet strength requirements.');
            return false;
        }
        
        // Validate password match
        if (password1 !== password2) {
            showFieldError(password2Field, 'Passwords do not match.');
            return false;
        }
    }
    
    return true;
}

function showFieldError(field, message) {
    // Remove existing error
    clearFieldError(field);
    
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
}

function clearFieldError(field) {
    // Remove error styling
    field.classList.remove('border-red-500', 'bg-red-50');
    field.removeAttribute('aria-invalid');
    
    // Remove error message
    const container = field.closest('.form-group, .field-container') || field.parentNode;
    const errorDiv = container.querySelector('.field-error');
    if (errorDiv) {
        errorDiv.remove();
    }
}
