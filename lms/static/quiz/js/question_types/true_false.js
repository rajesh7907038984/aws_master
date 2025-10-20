const TrueFalseQuestion = {
    init(formElement, initialData = {}) {
        this.form = formElement;
        this.correctAnswer = initialData.correctAnswer || '';
        this.setupEventListeners();
        if (this.correctAnswer) {
            this.setInitialValue();
        }
    },

    setupEventListeners() {
        const radioInputs = this.form.querySelectorAll('input[name="correct_answer"]');
        radioInputs.forEach(input => {
            input.addEventListener('change', () => this.validateAnswer());
        });
    },

    setInitialValue() {
        const radio = this.form.querySelector(`input[value="${this.correctAnswer}"]`);
        if (radio) {
            radio.checked = true;
        }
    },

    validateAnswer() {
        const selectedAnswer = this.form.querySelector('input[name="correct_answer"]:checked');
        return !!selectedAnswer;
    },

    getAnswerFields() {
        return `
            <div class="form-group">
                <label class="form-label">Correct Answer *</label>
                <div class="true-false-options">
                    <div class="option">
                        <input type="radio" id="true_option" name="correct_answer" value="True" class="form-radio" required>
                        <label for="true_option">True</label>
                    </div>
                    <div class="option">
                        <input type="radio" id="false_option" name="correct_answer" value="False" class="form-radio" required>
                        <label for="false_option">False</label>
                    </div>
                </div>
                <div class="form-text">Select the correct answer for this True/False question.</div>
            </div>
        `;
    }
};

// Make TrueFalseQuestion available globally
window.TrueFalseQuestion = TrueFalseQuestion; 