/**
 * TrueFalseQuestion - Handler for True/False question type
 */
class TrueFalseQuestion {
    constructor(formElement) {
        this.form = formElement;
        this.answerFields = this.form.querySelector('#answerFields');
    }

    setupFields() {
        if (!this.answerFields) return;
        
        this.answerFields.innerHTML = `
            <div class="form-group">
                <label class="form-label">Correct Answer:</label>
                <div class="radio-group">
                    <div class="radio-item">
                        <input type="radio" id="correct_true" name="correct_answer" value="true" required>
                        <label for="correct_true">True</label>
                    </div>
                    <div class="radio-item">
                        <input type="radio" id="correct_false" name="correct_answer" value="false" required>
                        <label for="correct_false">False</label>
                    </div>
                </div>
            </div>
            <div class="form-group">
                <label for="explanation">Explanation (Optional):</label>
                <textarea id="explanation" name="explanation" rows="3" 
                         placeholder="Provide an explanation for the correct answer..."></textarea>
            </div>
        `;
    }

    getAnswerData() {
        const correctAnswer = this.form.querySelector('input[name="correct_answer"]:checked');
        const explanation = this.form.querySelector('#explanation');
        
        if (!correctAnswer) {
            return { valid: false, message: 'Please select the correct answer' };
        }

        return {
            valid: true,
            data: {
                correct_answer: correctAnswer.value,
                explanation: explanation ? explanation.value : ''
            }
        };
    }

    loadData(data) {
        if (!data) return;
        
        // Load correct answer
        if (data.correct_answer) {
            const radio = this.form.querySelector(`input[name="correct_answer"][value="${data.correct_answer}"]`);
            if (radio) radio.checked = true;
        }

        // Load explanation
        if (data.explanation) {
            const explanationField = this.form.querySelector('#explanation');
            if (explanationField) explanationField.value = data.explanation;
        }
    }

    validate() {
        const result = this.getAnswerData();
        return result;
    }

    destroy() {
        // Cleanup if needed
        if (this.answerFields) {
            this.answerFields.innerHTML = '';
        }
    }
}

// Make globally available for compatibility
window.TrueFalseQuestion = TrueFalseQuestion;
