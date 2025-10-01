// Question types are loaded globally via window object
// No imports needed - using window.TrueFalseQuestion, etc.

class QuestionManager {
    constructor(formElement) {
        this.form = formElement;
        this.questionType = this.form.querySelector('#id_question_type');
        this.answerFields = this.form.querySelector('#answerFields');
        this.currentHandler = null;
        this.setupEventListeners();
    }

    setupEventListeners() {
        // Listen for question type changes
        this.questionType.addEventListener('change', () => this.updateQuestionType());
        
        // Form validation
        this.form.addEventListener('submit', (e) => this.validateForm(e));
    }

    updateQuestionType() {
        const type = this.questionType.value;
        const container = this.answerFields;
        
        // Remove previous container classes
        container.className = '';
        
        // Initialize the appropriate handler based on question type
        switch (type) {
            case 'true_false':
                container.classList.add('true-false-container');
                this.currentHandler = window.TrueFalseQuestion;
                break;
            case 'multiple_choice':
                container.classList.add('multiple-choice-container');
                this.currentHandler = window.MultipleChoiceQuestion;
                break;
            case 'multiple_select':
                container.classList.add('multiple-select-container');
                this.currentHandler = window.MultipleSelectQuestion;
                break;
            case 'fill_blank':
                container.classList.add('fill-blank-container');
                this.currentHandler = window.FillBlankQuestion;
                break;
            case 'multi_blank':
                container.classList.add('multi-blank-container');
                this.currentHandler = window.MultiBlankQuestion;
                break;
            case 'matching':
                container.classList.add('matching-container');
                this.currentHandler = window.MatchingQuestion;
                break;
            default:
                container.innerHTML = '';
                this.currentHandler = null;
                return;
        }

        // Get initial data from the page
        const initialData = this.getInitialData();
        
        // Render the question fields
        container.innerHTML = this.currentHandler.getAnswerFields();
        
        // Initialize the handler with the form and initial data
        this.currentHandler.init(this.form, initialData);
    }

    getInitialData() {
        // Get data from the page based on question type
        const type = this.questionType.value;
        const data = {};

        try {
            switch (type) {
                case 'true_false':
                    data.correctAnswer = window.initialData?.correctAnswer || '';
                    break;
                case 'multiple_choice':
                case 'multiple_select':
                    data.options = JSON.parse(window.initialData?.options || '[]');
                    data.correctAnswers = JSON.parse(window.initialData?.correctAnswers || '[]');
                    break;
                case 'fill_blank':
                    data.answer = window.initialData?.blankAnswer || '';
                    break;
                case 'multi_blank':
                    data.answers = JSON.parse(window.initialData?.multipleBlankAnswers || '[]');
                    break;
                case 'matching':
                    data.pairs = JSON.parse(window.initialData?.matchingPairs || '{"left":[],"right":[]}');
                    break;
            }
        } catch (e) {
            console.error('Error parsing initial data:', e);
        }

        return data;
    }

    validateForm(e) {
        if (!this.currentHandler) return true;

        const isValid = this.currentHandler.validateAnswer();
        if (!isValid) {
            e.preventDefault();
            alert('Please fill in all required fields correctly.');
            return false;
        }

        return true;
    }
}

// Initialize the question manager when the DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('questionForm');
    if (form) {
        window.questionManager = new QuestionManager(form);
        window.questionManager.updateQuestionType();
    }
}); 