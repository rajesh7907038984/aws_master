// Question Validator Module
const QuestionValidator = {
    validateForm() {
        const form = document.getElementById('inlineQuestionForm');
        if (!form) {
            console.error('Form not found');
            return false;
        }

        const questionType = form.querySelector('#question_type');
        const questionText = form.querySelector('#text');
        const points = form.querySelector('#points');

        if (!this.validateBasicFields(questionType, questionText, points)) {
            return false;
        }

        switch(questionType.value) {
            case 'multiple_choice':
                return this.validateMultipleChoice();
            case 'multiple_select':
                return this.validateMultipleSelect();
            case 'true_false':
                return this.validateTrueFalse();
            case 'fill_blank':
                return this.validateFillBlank();
            case 'multi_blank':
                return this.validateMultiBlank();
            case 'matching':
                return this.validateMatching();
            default:
                console.error('Invalid question type');
                return false;
        }
    },

    validateBasicFields(questionType, questionText, points) {
        if (!questionType || !questionType.value) {
            window.QuestionUI.showError('Please select a question type');
            return false;
        }

        const validTypes = ['multiple_choice', 'multiple_select', 'true_false', 'fill_blank', 'multi_blank', 'matching'];
        if (!validTypes.includes(questionType.value)) {
            window.QuestionUI.showError('Invalid question type selected');
            return false;
        }

        if (!questionText || !questionText.value.trim()) {
            window.QuestionUI.showError('Please enter the question text');
            return false;
        }

        if (!points || !points.value || isNaN(points.value) || points.value < 1) {
            window.QuestionUI.showError('Please enter valid points (must be at least 1)');
            return false;
        }

        return true;
    },

    validateMultipleChoice() {
        const options = document.querySelectorAll('.option-input');
        const correctAnswers = document.querySelectorAll('input[name="correct_answers[]"]:checked');
        
        // Check minimum number of options
        if (options.length < 2) {
            window.QuestionUI.showError('At least two options are required');
            return false;
        }

        // Check for empty options
        let hasEmptyOption = false;
        options.forEach(option => {
            if (!option.value.trim()) {
                hasEmptyOption = true;
            }
        });

        if (hasEmptyOption) {
            window.QuestionUI.showError('All options must have a value');
            return false;
        }

        // Check for correct answer selection
        if (correctAnswers.length !== 1) {
            window.QuestionUI.showError('Please select exactly one correct answer');
            return false;
        }

        return true;
    },

    validateMultipleSelect() {
        const options = document.querySelectorAll('.option-input');
        const correctAnswers = document.querySelectorAll('input[name="correct_answers[]"]:checked');
        
        // Check minimum number of options
        if (options.length < 2) {
            window.QuestionUI.showError('At least two options are required');
            return false;
        }

        // Check for empty options
        let hasEmptyOption = false;
        options.forEach(option => {
            if (!option.value.trim()) {
                hasEmptyOption = true;
            }
        });

        if (hasEmptyOption) {
            window.QuestionUI.showError('All options must have a value');
            return false;
        }

        // Check for correct answer selection
        if (correctAnswers.length < 1) {
            window.QuestionUI.showError('Please select at least one correct answer');
            return false;
        }

        return true;
    },

    validateTrueFalse() {
        const correctAnswer = document.querySelector('input[name="correct_answer"]:checked');
        if (!correctAnswer) {
            window.QuestionUI.showError('Please select either True or False as the correct answer');
            return false;
        }

        if (correctAnswer.value !== 'True' && correctAnswer.value !== 'False') {
            window.QuestionUI.showError('Invalid value for True/False question');
            return false;
        }

        return true;
    },

    validateFillBlank() {
        const container = document.getElementById('answersContainer');
        if (!container) {
            console.error('Answers container not found');
            return false;
        }

        const answers = container.querySelectorAll('input[type="text"]');
        if (answers.length === 0) {
            window.QuestionUI.showError('Please add at least one correct answer');
            return false;
        }

        for (const answer of answers) {
            if (!answer.value.trim()) {
                window.QuestionUI.showError('All answers must have text');
                return false;
            }
        }

        return true;
    },

    validateMultiBlank() {
        const container = document.getElementById('blanksContainer');
        if (!container) {
            console.error('Blanks container not found');
            return false;
        }

        const blanks = container.children;
        if (blanks.length === 0) {
            window.QuestionUI.showError('Please add at least one blank');
            return false;
        }

        for (const blank of blanks) {
            const label = blank.querySelector('input[name="blank_labels[]"]');
            if (!label || !label.value.trim()) {
                window.QuestionUI.showError('All blanks must have labels');
                return false;
            }

            const answers = blank.querySelectorAll('input[type="text"][name^="answers_"]');
            if (answers.length === 0) {
                window.QuestionUI.showError('Each blank must have at least one correct answer');
                return false;
            }

            for (const answer of answers) {
                if (!answer.value.trim()) {
                    window.QuestionUI.showError('All answers must have text');
                    return false;
                }
            }
        }

        return true;
    },

    validateMatching() {
        const container = document.getElementById('pairsContainer');
        if (!container) {
            console.error('Pairs container not found');
            return false;
        }

        const pairs = container.children;
        if (pairs.length < 2) {
            window.QuestionUI.showError('Matching questions must have at least 2 pairs');
            return false;
        }

        for (const pair of pairs) {
            const prompt = pair.querySelector('input[name="prompts[]"]');
            const match = pair.querySelector('input[name="matches[]"]');

            if (!prompt || !prompt.value.trim() || !match || !match.value.trim()) {
                window.QuestionUI.showError('All matching pairs must have both prompt and match filled out');
                return false;
            }
        }

        return true;
    }
};

// Make it globally available
window.QuestionValidator = QuestionValidator; 