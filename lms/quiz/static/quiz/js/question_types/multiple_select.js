/**
 * MultipleSelectQuestion - Handler for Multiple Select question type
 */
class MultipleSelectQuestion {
    constructor(formElement) {
        this.form = formElement;
        this.answerFields = this.form.querySelector('#answerFields');
        this.optionCount = 2;
        this.maxOptions = 8;
    }

    setupFields() {
        if (!this.answerFields) return;
        
        this.answerFields.innerHTML = `
            <div class="form-group">
                <label class="form-label">Answer Options (Select all correct answers):</label>
                <div id="options-container">
                    <!-- Options will be generated here -->
                </div>
                <div class="button-group" style="margin-top: 15px;">
                    <button type="button" id="addOption" class="btn btn-secondary btn-sm">Add Option</button>
                    <button type="button" id="removeOption" class="btn btn-danger btn-sm">Remove Option</button>
                </div>
            </div>
            <div class="form-group">
                <label for="explanation">Explanation (Optional):</label>
                <textarea id="explanation" name="explanation" rows="3" 
                         placeholder="Provide an explanation for the correct answers..."></textarea>
            </div>
        `;

        this.generateOptions();
        this.setupEventListeners();
    }

    generateOptions() {
        const container = this.answerFields.querySelector('#options-container');
        if (!container) return;

        container.innerHTML = '';

        for (let i = 0; i < this.optionCount; i++) {
            const optionDiv = document.createElement('div');
            optionDiv.className = 'option-row';
            optionDiv.innerHTML = `
                <div class="option-input-group">
                    <div class="checkbox-wrapper">
                        <input type="checkbox" id="correct_${i}" name="correct_options" value="${i}">
                        <label for="correct_${i}" class="checkbox-label">Correct</label>
                    </div>
                    <div class="text-wrapper">
                        <input type="text" id="option_${i}" name="option_${i}" 
                               placeholder="Enter option ${i + 1}" required class="form-control">
                    </div>
                </div>
            `;
            container.appendChild(optionDiv);
        }
    }

    setupEventListeners() {
        const addBtn = this.answerFields.querySelector('#addOption');
        const removeBtn = this.answerFields.querySelector('#removeOption');

        if (addBtn) {
            addBtn.addEventListener('click', () => {
                if (this.optionCount < this.maxOptions) {
                    this.optionCount++;
                    this.generateOptions();
                }
            });
        }

        if (removeBtn) {
            removeBtn.addEventListener('click', () => {
                if (this.optionCount > 2) {
                    this.optionCount--;
                    this.generateOptions();
                }
            });
        }
    }

    getAnswerData() {
        const correctOptions = Array.from(this.form.querySelectorAll('input[name="correct_options"]:checked'))
                                   .map(input => parseInt(input.value));
        const explanation = this.form.querySelector('#explanation');
        
        if (correctOptions.length === 0) {
            return { valid: false, message: 'Please select at least one correct option' };
        }

        const options = [];
        let hasEmptyOption = false;

        for (let i = 0; i < this.optionCount; i++) {
            const optionInput = this.form.querySelector(`#option_${i}`);
            if (optionInput) {
                const optionText = optionInput.value.trim();
                if (!optionText) {
                    hasEmptyOption = true;
                    break;
                }
                options.push(optionText);
            }
        }

        if (hasEmptyOption) {
            return { valid: false, message: 'Please fill in all option fields' };
        }

        if (options.length < 2) {
            return { valid: false, message: 'Please provide at least 2 options' };
        }

        return {
            valid: true,
            data: {
                options: options,
                correct_options: correctOptions,
                explanation: explanation ? explanation.value : ''
            }
        };
    }

    loadData(data) {
        if (!data) return;
        
        // Set option count and generate options
        if (data.options && data.options.length > 0) {
            this.optionCount = Math.max(2, Math.min(data.options.length, this.maxOptions));
            this.generateOptions();

            // Load option values
            data.options.forEach((option, index) => {
                const optionInput = this.form.querySelector(`#option_${index}`);
                if (optionInput) {
                    optionInput.value = option;
                }
            });

            // Set correct options
            if (data.correct_options && Array.isArray(data.correct_options)) {
                data.correct_options.forEach(optionIndex => {
                    const checkbox = this.form.querySelector(`input[name="correct_options"][value="${optionIndex}"]`);
                    if (checkbox) checkbox.checked = true;
                });
            }
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
window.MultipleSelectQuestion = MultipleSelectQuestion;
