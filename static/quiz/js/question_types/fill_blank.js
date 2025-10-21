const FillBlankQuestion = {
    init(formElement, initialData = {}) {
        this.form = formElement;
        this.answer = initialData.answer || '';
        if (this.answer) {
            this.setInitialValue();
        }
    },

    setInitialValue() {
        const input = this.form.querySelector('input[name="blank_answer"]');
        if (input) {
            input.value = this.answer;
        }
    },

    validateAnswer() {
        const answer = this.form.querySelector('input[name="blank_answer"]').value.trim();
        return answer.length > 0;
    },

    getAnswerFields() {
        return `
            <div class="form-group">
                <label class="form-label">Correct Answer *</label>
                <input type="text" name="blank_answer" class="form-control" required>
                <div class="form-text">Enter the correct answer that students must type exactly.</div>
            </div>
        `;
    }
};

// Make FillBlankQuestion available globally
window.FillBlankQuestion = FillBlankQuestion; 