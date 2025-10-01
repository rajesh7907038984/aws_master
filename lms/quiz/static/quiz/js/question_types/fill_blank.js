/**
 * FillBlankQuestion - Handler for Fill in the Blank question type
 */
class FillBlankQuestion {
    constructor(formElement) {
        this.form = formElement;
        this.answerFields = this.form.querySelector('#answerFields');
    }

    setupFields() {
        if (!this.answerFields) return;
        
        this.answerFields.innerHTML = `
            <div class="form-group">
                <label for="question_text_blank">Question with Blank:</label>
                <textarea id="question_text_blank" name="question_text_blank" rows="3" required
                         placeholder="Enter your question with ___ where the blank should be. Example: The capital of France is ___."></textarea>
                <small class="form-text text-muted">Use underscores (___) to indicate where the blank should appear.</small>
            </div>
            <div class="form-group">
                <label for="correct_answer">Correct Answer:</label>
                <input type="text" id="correct_answer" name="correct_answer" required
                       placeholder="Enter the correct answer to fill in the blank" class="form-control">
            </div>
            <div class="form-group">
                <label for="alternative_answers">Alternative Correct Answers (Optional):</label>
                <div id="alternatives-container">
                    <input type="text" name="alternative_1" placeholder="Alternative answer 1 (optional)" class="form-control mb-2">
                </div>
                <button type="button" id="addAlternative" class="btn btn-secondary btn-sm">Add Alternative Answer</button>
            </div>
            <div class="form-group">
                <div class="form-check">
                    <input type="checkbox" id="case_sensitive" name="case_sensitive" class="form-check-input">
                    <label for="case_sensitive" class="form-check-label">Case sensitive matching</label>
                </div>
            </div>
            <div class="form-group">
                <label for="explanation">Explanation (Optional):</label>
                <textarea id="explanation" name="explanation" rows="3" 
                         placeholder="Provide an explanation for the correct answer..."></textarea>
            </div>
        `;

        this.setupEventListeners();
    }

    setupEventListeners() {
        const addBtn = this.answerFields.querySelector('#addAlternative');
        if (addBtn) {
            addBtn.addEventListener('click', () => {
                this.addAlternativeField();
            });
        }
    }

    addAlternativeField() {
        const container = this.answerFields.querySelector('#alternatives-container');
        if (!container) return;

        const currentAlternatives = container.querySelectorAll('input[name^="alternative_"]').length;
        if (currentAlternatives >= 5) return; // Limit to 5 alternatives

        const newField = document.createElement('input');
        newField.type = 'text';
        newField.name = `alternative_${currentAlternatives + 1}`;
        newField.placeholder = `Alternative answer ${currentAlternatives + 1} (optional)`;
        newField.className = 'form-control mb-2';

        container.appendChild(newField);
    }

    getAnswerData() {
        const questionText = this.form.querySelector('#question_text_blank');
        const correctAnswer = this.form.querySelector('#correct_answer');
        const caseSensitive = this.form.querySelector('#case_sensitive');
        const explanation = this.form.querySelector('#explanation');
        
        if (!questionText || !questionText.value.trim()) {
            return { valid: false, message: 'Please enter the question text' };
        }

        if (!questionText.value.includes('___')) {
            return { valid: false, message: 'Question must include ___ to indicate the blank position' };
        }

        if (!correctAnswer || !correctAnswer.value.trim()) {
            return { valid: false, message: 'Please enter the correct answer' };
        }

        // Get alternative answers
        const alternatives = [];
        const alternativeInputs = this.answerFields.querySelectorAll('input[name^="alternative_"]');
        alternativeInputs.forEach(input => {
            if (input.value.trim()) {
                alternatives.push(input.value.trim());
            }
        });

        return {
            valid: true,
            data: {
                question_text: questionText.value.trim(),
                correct_answer: correctAnswer.value.trim(),
                alternative_answers: alternatives,
                case_sensitive: caseSensitive ? caseSensitive.checked : false,
                explanation: explanation ? explanation.value : ''
            }
        };
    }

    loadData(data) {
        if (!data) return;
        
        // Load question text
        if (data.question_text) {
            const questionField = this.form.querySelector('#question_text_blank');
            if (questionField) questionField.value = data.question_text;
        }

        // Load correct answer
        if (data.correct_answer) {
            const correctField = this.form.querySelector('#correct_answer');
            if (correctField) correctField.value = data.correct_answer;
        }

        // Load alternative answers
        if (data.alternative_answers && Array.isArray(data.alternative_answers)) {
            const container = this.answerFields.querySelector('#alternatives-container');
            if (container) {
                // Clear existing alternatives
                container.innerHTML = '<input type="text" name="alternative_1" placeholder="Alternative answer 1 (optional)" class="form-control mb-2">';
                
                // Add alternatives
                data.alternative_answers.forEach((alt, index) => {
                    if (index === 0) {
                        // Update first field
                        const firstField = container.querySelector('input[name="alternative_1"]');
                        if (firstField) firstField.value = alt;
                    } else {
                        // Add additional fields
                        this.addAlternativeField();
                        const newField = container.querySelector(`input[name="alternative_${index + 1}"]`);
                        if (newField) newField.value = alt;
                    }
                });
            }
        }

        // Load case sensitivity
        if (typeof data.case_sensitive === 'boolean') {
            const caseSensitiveField = this.form.querySelector('#case_sensitive');
            if (caseSensitiveField) caseSensitiveField.checked = data.case_sensitive;
        }

        // Load explanation
        if (data.explanation) {
            const explanationField = this.form.querySelector('#explanation');
            if (explanationField) explanationField.value = data.explanation;
        }
    }

    validate() {
        return this.getAnswerData();
    }

    destroy() {
        if (this.answerFields) {
            this.answerFields.innerHTML = '';
        }
    }
}

// Make globally available for compatibility
window.FillBlankQuestion = FillBlankQuestion;
