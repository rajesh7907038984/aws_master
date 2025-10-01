// Question Form Module
const QuestionForm = {
    init() {
        this.form = document.getElementById('inlineQuestionForm');
        this.addQuestionBtn = document.getElementById('addQuestionBtn');
        this.formContainer = document.getElementById('questionFormContainer');
        this.questionType = document.getElementById('question_type');
        
        this.bindEvents();
        this.initializeFormState();
    },

    bindEvents() {
        if (this.addQuestionBtn) {
            this.addQuestionBtn.addEventListener('click', (e) => {
                e.preventDefault();
                console.log('Add Question button clicked');
                this.toggleForm();
            });
        }

        if (this.questionType) {
            this.questionType.addEventListener('change', () => {
                console.log('Question type changed to:', this.questionType.value);
                window.QuestionTypeFields.toggle(this.questionType.value);
            });
        }

        if (this.form) {
            this.form.addEventListener('submit', this.handleSubmit.bind(this));
        }
    },

    toggleForm() {
        try {
            if (!this.formContainer) {
                throw new Error('Form container not found');
            }

            const isVisible = !this.formContainer.classList.contains('hidden');
            console.log('Form is currently visible:', isVisible);

            if (isVisible) {
                this.hideForm();
            } else {
                this.showForm();
            }
            console.log('Form visibility toggled successfully');
        } catch (error) {
            console.error('Error in toggleForm:', error);
            alert('Error: ' + error.message);
        }
    },

    showForm() {
        this.formContainer.classList.remove('hidden');
        this.updateAddButton('Cancel', true);
        if (this.questionType) {
            this.questionType.value = '';
            window.QuestionTypeFields.toggle('');
        }
    },

    hideForm() {
        this.formContainer.classList.add('hidden');
        this.updateAddButton('Add Question', false);
        if (this.form) {
            this.form.reset();
            const dynamicFields = document.getElementById('dynamicFields');
            if (dynamicFields) {
                dynamicFields.innerHTML = '';
            }
        }
    },

    updateAddButton(text, isCancel) {
        const icon = isCancel ? 
            '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>' :
            '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"/>';

        this.addQuestionBtn.innerHTML = `
            <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                ${icon}
            </svg>
            ${text}
        `;

        if (isCancel) {
            this.addQuestionBtn.classList.remove('bg-green-600', 'hover:bg-green-700');
            this.addQuestionBtn.classList.add('bg-red-500', 'hover:bg-red-600');
        } else {
            this.addQuestionBtn.classList.remove('bg-red-500', 'hover:bg-red-600');
            this.addQuestionBtn.classList.add('bg-green-600', 'hover:bg-green-700');
        }
    },

    initializeFormState() {
        if (this.formContainer) {
            console.log('Initializing form container state');
            this.formContainer.classList.add('hidden');
        }

        if (this.questionType && this.questionType.value) {
            window.QuestionTypeFields.toggle(this.questionType.value);
        }
    },

    async handleSubmit(event) {
        event.preventDefault();
        console.log('Form submit event triggered');

        if (!window.QuestionValidator.validateForm()) {
            console.log('Form validation failed');
            return;
        }

        const formData = new FormData(this.form);
        const questionData = {
            question_type: formData.get('question_type'),
            text: formData.get('text'),
            points: formData.get('points'),
            options: window.QuestionOptions.collectOptions()
        };

        try {
            const response = await this.submitQuestion(questionData);
            if (response.success) {
                window.QuestionUI.showSuccess('Question added successfully!');
                this.form.reset();
                this.toggleForm();
                window.location.reload();
            } else {
                window.QuestionUI.showError(response.message || 'Error adding question');
            }
        } catch (error) {
            console.error('Error submitting question:', error);
            window.QuestionUI.showError('Error submitting question. Please try again.');
        }
    },

    async submitQuestion(questionData) {
        // Use the unified CSRF manager if available, fallback to QuestionUtils
        let csrfToken = null;
        
        if (window.csrfManager) {
            csrfToken = window.csrfManager.getToken();
        } else if (window.QuestionUtils && window.QuestionUtils.getCSRFToken) {
            csrfToken = window.QuestionUtils.getCSRFToken();
        } else if (window.getCsrfToken) {
            csrfToken = window.getCsrfToken();
        }
        
        if (!csrfToken) {
            // Last resort - try direct DOM lookup
            const csrfElement = document.querySelector('input[name="csrfmiddlewaretoken"]');
            if (csrfElement) {
                csrfToken = csrfElement.value;
            }
        }
        
        if (!csrfToken) {
            throw new Error('CSRF token not found. Please refresh the page and try again.');
        }

        const response = await fetch(this.form.action, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify(questionData)
        });

        if (!response.ok) {
            const text = await response.text();
            console.error('Server response:', text);
            
            // Provide more specific error messages
            if (response.status === 403) {
                throw new Error('Permission denied. Please refresh the page and try again.');
            } else if (response.status === 404) {
                throw new Error('The requested resource was not found.');
            } else if (response.status >= 500) {
                throw new Error('Server error occurred. Please try again later.');
            } else {
                throw new Error(`Request failed with status ${response.status}`);
            }
        }

        return response.json();
    }
};

// Make it globally available
window.QuestionForm = QuestionForm; 