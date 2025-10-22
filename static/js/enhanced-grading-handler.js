/**
 * Enhanced Grading Handler - Fix Instructor Grade Submission Errors
 * This script specifically addresses grading form submission issues
 */

(function() {
    'use strict';

    window.GradingHandler = {
        init: function() {
            this.setupGradingForms();
            this.setupRubricHandling();
            this.setupGradebookHandling();
            console.log('Enhanced Grading Handler initialized');
        },

        // Setup grading form handlers
        setupGradingForms: function() {
            // Handle assignment grading forms
            document.querySelectorAll('form#gradingForm, form[id*="grading"], form[action*="grade"]').forEach(form => {
                this.enhanceGradingForm(form);
            });

            // Handle AJAX grade submissions
            document.addEventListener('click', function(e) {
                if (e.target.matches('[data-action="save-grade"], .save-grade-btn, #save-grade')) {
                    e.preventDefault();
                    this.handleGradeSubmission(e.target);
                }
            }.bind(this));

            // Handle rubric grade submissions
            document.addEventListener('submit', function(e) {
                if (e.target.matches('form[id*="rubric"], form[action*="rubric"]')) {
                    this.handleRubricSubmission(e);
                }
            }.bind(this));
        },

        // Enhance individual grading forms
        enhanceGradingForm: function(form) {
            if (form.hasAttribute('data-enhanced')) return;
            form.setAttribute('data-enhanced', 'true');

            // Add grade validation
            const gradeInputs = form.querySelectorAll('input[name*="grade"], input[type="number"]');
            gradeInputs.forEach(input => {
                input.addEventListener('blur', function() {
                    this.validateGradeInput(input);
                }.bind(this));
            });

            // Handle form submission
            form.addEventListener('submit', function(e) {
                if (!this.validateGradingForm(form)) {
                    e.preventDefault();
                    return false;
                }
            }.bind(this));
        },

        // Handle AJAX grade submission
        handleGradeSubmission: function(trigger) {
            const form = trigger.closest('form') || document.querySelector('#gradingForm');
            if (!form) {
                this.showGradingError('Grading form not found');
                return;
            }

            const formData = new FormData(form);
            const gradingData = this.collectGradingData(form);

            // Show loading state
            this.setGradingLoadingState(trigger, true);

            // Prepare request
            const url = form.action || window.location.href;
            const csrfToken = window.getCSRFToken ? window.getCSRFToken() : 
                            form.querySelector('[name="csrfmiddlewaretoken"]')?.value;

            if (!csrfToken) {
                this.showGradingError('Security token missing. Please refresh the page.');
                this.setGradingLoadingState(trigger, false);
                return;
            }

            // Submit grade
            fetch(url, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': csrfToken,
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    this.showGradingSuccess(data.message || 'Grade saved successfully');
                    if (data.redirect_url) {
                        setTimeout(() => window.location.href = data.redirect_url, 1500);
                    }
                } else {
                    this.showGradingError(data.error || data.message || 'Failed to save grade');
                }
            })
            .catch(error => {
                console.error('Grading error:', error);
                this.showGradingError(`Error saving grade: ${error.message}`);
            })
            .finally(() => {
                this.setGradingLoadingState(trigger, false);
            });
        },

        // Handle rubric submissions
        handleRubricSubmission: function(e) {
            const form = e.target;
            
            // Validate rubric data
            if (!this.validateRubricForm(form)) {
                e.preventDefault();
                return false;
            }

            // Check for missing evaluations
            const criteria = form.querySelectorAll('[data-criterion-id]');
            let missingEvaluations = 0;
            
            criteria.forEach(criterion => {
                const criterionId = criterion.dataset.criterionId;
                const rating = form.querySelector(`input[name="rubric_data[${criterionId}][rating_id]"]:checked`);
                if (!rating) {
                    missingEvaluations++;
                }
            });

            if (missingEvaluations > 0) {
                if (!confirm(`${missingEvaluations} criteria have no ratings selected. Continue anyway?`)) {
                    e.preventDefault();
                    return false;
                }
            }
        },

        // Setup gradebook-specific handling
        setupGradebookHandling: function() {
            // Handle gradebook quick grading
            document.addEventListener('change', function(e) {
                if (e.target.matches('.grade-input, input[data-grade-type]')) {
                    this.handleQuickGradeChange(e.target);
                }
            }.bind(this));

            // Handle gradebook bulk operations
            document.addEventListener('click', function(e) {
                if (e.target.matches('.bulk-grade-btn, [data-action="bulk-grade"]')) {
                    e.preventDefault();
                    this.handleBulkGrading(e.target);
                }
            }.bind(this));
        },

        // Handle quick grade changes in gradebook
        handleQuickGradeChange: function(input) {
            const grade = parseFloat(input.value);
            
            // Validate grade value
            if (isNaN(grade) || grade < 0 || grade > 100) {
                this.showInputError(input, 'Grade must be between 0 and 100');
                return;
            }

            // Auto-save after short delay
            clearTimeout(input.saveTimeout);
            input.saveTimeout = setTimeout(() => {
                this.saveQuickGrade(input);
            }, 1000);
        },

        // Save quick grade
        saveQuickGrade: function(input) {
            const gradeData = {
                student_id: input.dataset.studentId,
                activity_id: input.dataset.activityId,
                activity_type: input.dataset.activityType,
                grade: input.value
            };

            const csrfToken = window.getCSRFToken();
            if (!csrfToken) {
                this.showInputError(input, 'Security token missing');
                return;
            }

            // Show saving state
            input.style.backgroundColor = '#fff3cd';

            fetch('/gradebook/ajax/save-grade/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken,
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify(gradeData)
            })
            .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
            .then(data => {
                if (data.success) {
                    input.style.backgroundColor = '#d4edda'; // Success green
                    setTimeout(() => input.style.backgroundColor = '', 2000);
                } else {
                    this.showInputError(input, data.error || 'Failed to save grade');
                }
            })
            .catch(error => {
                this.showInputError(input, 'Network error occurred');
            });
        },

        // Validation functions
        validateGradingForm: function(form) {
            let isValid = true;
            const errors = [];

            // Validate grade inputs
            const gradeInputs = form.querySelectorAll('input[name*="grade"]');
            gradeInputs.forEach(input => {
                if (input.value && !this.isValidGrade(input.value)) {
                    errors.push('Invalid grade value');
                    isValid = false;
                }
            });

            // Validate required fields
            const requiredFields = form.querySelectorAll('input[required], select[required], textarea[required]');
            requiredFields.forEach(field => {
                if (!field.value.trim()) {
                    errors.push(`${field.name || 'Field'} is required`);
                    isValid = false;
                }
            });

            if (!isValid) {
                this.showGradingError('Please fix the following errors:\n' + errors.join('\n'));
            }

            return isValid;
        },

        validateRubricForm: function(form) {
            // Basic rubric validation
            const rubricData = form.querySelector('textarea[name="rubric_data"]');
            if (rubricData) {
                try {
                    JSON.parse(rubricData.value);
                } catch (e) {
                    this.showGradingError('Invalid rubric data format');
                    return false;
                }
            }
            return true;
        },

        validateGradeInput: function(input) {
            const value = input.value.trim();
            if (!value) return true;

            if (!this.isValidGrade(value)) {
                this.showInputError(input, 'Grade must be between 0 and 100');
                return false;
            }

            this.clearInputError(input);
            return true;
        },

        isValidGrade: function(value) {
            const grade = parseFloat(value);
            return !isNaN(grade) && grade >= 0 && grade <= 100;
        },

        // Utility functions
        collectGradingData: function(form) {
            const data = {};
            new FormData(form).forEach((value, key) => {
                data[key] = value;
            });
            return data;
        },

        setGradingLoadingState: function(trigger, loading) {
            if (loading) {
                trigger.disabled = true;
                trigger.dataset.originalText = trigger.textContent;
                trigger.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
            } else {
                trigger.disabled = false;
                if (trigger.dataset.originalText) {
                    trigger.textContent = trigger.dataset.originalText;
                    delete trigger.dataset.originalText;
                }
            }
        },

        // Error and success display functions
        showGradingError: function(message) {
            this.showGradingMessage(message, 'error');
        },

        showGradingSuccess: function(message) {
            this.showGradingMessage(message, 'success');
        },

        showGradingMessage: function(message, type) {
            // Remove existing messages
            document.querySelectorAll('.grading-message').forEach(el => el.remove());

            const messageDiv = document.createElement('div');
            messageDiv.className = `grading-message alert alert-${type === 'error' ? 'danger' : 'success'}`;
            messageDiv.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 9999;
                max-width: 400px;
                padding: 10px 15px;
                border-radius: 4px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            `;

            const bgColor = type === 'error' ? '#f8d7da' : '#d1e7dd';
            const borderColor = type === 'error' ? '#f5c6cb' : '#badbcc';
            const textColor = type === 'error' ? '#721c24' : '#0f5132';
            const icon = type === 'error' ? 'fa-exclamation-triangle' : 'fa-check-circle';

            messageDiv.style.backgroundColor = bgColor;
            messageDiv.style.borderColor = borderColor;
            messageDiv.style.color = textColor;

            messageDiv.innerHTML = `
                <i class="fas ${icon}"></i> ${message}
                <button type="button" class="close" style="float: right; border: none; background: none; font-size: 18px; margin-left: 10px;">&times;</button>
            `;

            document.body.appendChild(messageDiv);

            // Close button
            messageDiv.querySelector('.close').addEventListener('click', () => messageDiv.remove());

            // Auto-remove
            setTimeout(() => {
                if (messageDiv.parentNode) messageDiv.remove();
            }, type === 'error' ? 8000 : 4000);
        },

        showInputError: function(input, message) {
            this.clearInputError(input);
            
            input.style.borderColor = '#dc3545';
            input.style.backgroundColor = '#f8d7da';
            
            const errorDiv = document.createElement('div');
            errorDiv.className = 'input-error text-danger';
            errorDiv.style.fontSize = '0.875em';
            errorDiv.textContent = message;
            
            input.parentNode.insertBefore(errorDiv, input.nextSibling);
            
            // Clear error after delay
            setTimeout(() => this.clearInputError(input), 5000);
        },

        clearInputError: function(input) {
            input.style.borderColor = '';
            input.style.backgroundColor = '';
            
            const errorDiv = input.parentNode.querySelector('.input-error');
            if (errorDiv) {
                errorDiv.remove();
            }
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            window.GradingHandler.init();
        });
    } else {
        window.GradingHandler.init();
    }

    // Setup rubric handling
    window.GradingHandler.setupRubricHandling = function() {
        // Handle rubric criterion changes
        document.addEventListener('change', function(e) {
            if (e.target.matches('input[name*="rubric_data"]')) {
                this.updateRubricTotal();
            }
        }.bind(this));

        // Auto-save rubric evaluations
        document.addEventListener('change', function(e) {
            if (e.target.matches('.rubric-rating-input')) {
                clearTimeout(e.target.autoSaveTimeout);
                e.target.autoSaveTimeout = setTimeout(() => {
                    this.autoSaveRubricEvaluation(e.target);
                }, 2000);
            }
        }.bind(this));
    };

    window.GradingHandler.updateRubricTotal = function() {
        const form = document.querySelector('form[id*="rubric"]');
        if (!form) return;

        let totalPoints = 0;
        const ratingInputs = form.querySelectorAll('input[name*="rubric_data"]:checked');
        
        ratingInputs.forEach(input => {
            const points = parseFloat(input.dataset.points || 0);
            totalPoints += points;
        });

        const totalDisplay = document.querySelector('.rubric-total-points');
        if (totalDisplay) {
            totalDisplay.textContent = totalPoints.toFixed(1);
        }
    };

    window.GradingHandler.autoSaveRubricEvaluation = function(input) {
        // Implementation for auto-saving rubric evaluations
        console.log('Auto-saving rubric evaluation:', input.name, input.value);
    };
})();
