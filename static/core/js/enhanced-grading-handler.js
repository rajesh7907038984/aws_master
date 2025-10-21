/**
 * Enhanced Grading Handler - Manages grading interface functionality
 */
(function() {
    'use strict';
    
    const EnhancedGradingHandler = {
        init: function() {
            this.setupGradeInputs();
            this.setupBulkActions();
            this.setupGradeValidation();
        },
        
        setupGradeInputs: function() {
            const gradeInputs = document.querySelectorAll('input[data-grade-input]');
            
            gradeInputs.forEach(input => {
                input.addEventListener('change', this.handleGradeChange.bind(this));
                input.addEventListener('blur', this.validateGrade.bind(this));
            });
        },
        
        setupBulkActions: function() {
            const bulkGradeButton = document.getElementById('bulk-grade-btn');
            if (bulkGradeButton) {
                bulkGradeButton.addEventListener('click', this.handleBulkGrade.bind(this));
            }
            
            const selectAllCheckbox = document.getElementById('select-all-submissions');
            if (selectAllCheckbox) {
                selectAllCheckbox.addEventListener('change', this.handleSelectAll.bind(this));
            }
        },
        
        setupGradeValidation: function() {
            const gradeForm = document.querySelector('[data-grade-form]');
            if (gradeForm) {
                gradeForm.addEventListener('submit', this.validateGradeForm.bind(this));
            }
        },
        
        handleGradeChange: function(event) {
            const input = event.target;
            const grade = parseFloat(input.value);
            const maxGrade = parseFloat(input.dataset.maxGrade) || 100;
            
            if (grade > maxGrade) {
                input.classList.add('error');
                this.showGradeError(input, `Grade cannot exceed ${maxGrade}`);
            } else if (grade < 0) {
                input.classList.add('error');
                this.showGradeError(input, 'Grade cannot be negative');
            } else {
                input.classList.remove('error');
                this.hideGradeError(input);
                this.updateGradePreview(input);
            }
        },
        
        validateGrade: function(event) {
            const input = event.target;
            const value = input.value.trim();
            
            if (value && !this.isValidGrade(value)) {
                input.classList.add('error');
                this.showGradeError(input, 'Please enter a valid grade');
            }
        },
        
        isValidGrade: function(value) {
            const grade = parseFloat(value);
            return !isNaN(grade) && grade >= 0 && grade <= 100;
        },
        
        showGradeError: function(input, message) {
            let errorElement = input.nextElementSibling;
            if (!errorElement || !errorElement.classList.contains('grade-error')) {
                errorElement = document.createElement('div');
                errorElement.className = 'grade-error text-red-500 text-sm';
                input.parentNode.insertBefore(errorElement, input.nextSibling);
            }
            errorElement.textContent = message;
        },
        
        hideGradeError: function(input) {
            const errorElement = input.nextElementSibling;
            if (errorElement && errorElement.classList.contains('grade-error')) {
                errorElement.remove();
            }
        },
        
        updateGradePreview: function(input) {
            const preview = document.querySelector(`[data-grade-preview="${input.dataset.submissionId}"]`);
            if (preview) {
                preview.textContent = input.value;
            }
        },
        
        handleSelectAll: function(event) {
            const checkboxes = document.querySelectorAll('input[data-submission-checkbox]');
            checkboxes.forEach(checkbox => {
                checkbox.checked = event.target.checked;
            });
        },
        
        handleBulkGrade: function(event) {
            const selectedCheckboxes = document.querySelectorAll('input[data-submission-checkbox]:checked');
            if (selectedCheckboxes.length === 0) {
                alert('Please select submissions to grade');
                return;
            }
            
            const bulkGrade = prompt('Enter grade for all selected submissions:');
            if (bulkGrade && this.isValidGrade(bulkGrade)) {
                selectedCheckboxes.forEach(checkbox => {
                    const gradeInput = document.querySelector(`input[data-submission-id="${checkbox.value}"]`);
                    if (gradeInput) {
                        gradeInput.value = bulkGrade;
                        this.updateGradePreview(gradeInput);
                    }
                });
            }
        },
        
        validateGradeForm: function(event) {
            const form = event.target;
            const gradeInputs = form.querySelectorAll('input[data-grade-input]');
            let isValid = true;
            
            gradeInputs.forEach(input => {
                if (input.value && !this.isValidGrade(input.value)) {
                    input.classList.add('error');
                    this.showGradeError(input, 'Invalid grade');
                    isValid = false;
                }
            });
            
            if (!isValid) {
                event.preventDefault();
            }
        }
    };
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            EnhancedGradingHandler.init();
        });
    } else {
        EnhancedGradingHandler.init();
    }
    
    // Export to global scope
    window.EnhancedGradingHandler = EnhancedGradingHandler;
})();
