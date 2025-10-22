const MultipleSelectQuestion = {
    init(formElement, initialData = {}) {
        this.form = formElement;
        this.options = initialData.options || [];
        this.correctAnswers = initialData.correctAnswers || [];
        this.setupEventListeners();
        if (this.options.length > 0) {
            this.setInitialValues();
        }
    },

    setupEventListeners() {
        const addButton = this.form.querySelector('#addOptionBtn');
        if (addButton) {
            addButton.addEventListener('click', () => this.addOption());
        }

        this.form.addEventListener('click', (e) => {
            if (e.target.closest('.remove-option')) {
                this.removeOption(e.target.closest('.input-group'));
            }
        });
    },

    setInitialValues() {
        const container = this.form.querySelector('#optionsContainer');
        if (!container) return;

        container.innerHTML = this.options.map((option, index) => `
            <div class="input-group">
                <input type="text" name="options[]" class="form-control" value="${option}" placeholder="Option ${index + 1}" required>
                <div class="input-group-append">
                    <input type="checkbox" name="correct_answers[]" value="${index}" class="form-check-input"
                           ${this.correctAnswers.includes(index) ? 'checked' : ''}>
                    <button type="button" class="btn btn-danger btn-sm remove-option">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </div>
        `).join('');
    },

    addOption() {
        const container = this.form.querySelector('#optionsContainer');
        const optionCount = container.children.length;
        const div = document.createElement('div');
        div.className = 'input-group';
        div.innerHTML = `
            <input type="text" name="options[]" class="form-control" placeholder="Option ${optionCount + 1}" required>
            <div class="input-group-append">
                <input type="checkbox" name="correct_answers[]" value="${optionCount}" class="form-check-input">
                <button type="button" class="btn btn-danger btn-sm remove-option">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;
        container.appendChild(div);
    },

    removeOption(optionElement) {
        optionElement.remove();
        this.updateOptionIndices();
    },

    updateOptionIndices() {
        const container = this.form.querySelector('#optionsContainer');
        Array.from(container.children).forEach((div, index) => {
            const input = div.querySelector('input[type="checkbox"]');
            if (input) {
                input.value = index;
            }
            const textInput = div.querySelector('input[name="options[]"]');
            if (textInput) {
                textInput.placeholder = `Option ${index + 1}`;
            }
        });
    },

    validateAnswer() {
        const options = Array.from(this.form.querySelectorAll('input[name="options[]"]'))
            .map(input => input.value.trim())
            .filter(Boolean);
        
        const correctAnswers = this.form.querySelectorAll('input[name="correct_answers[]"]:checked');
        
        return options.length >= 2 && correctAnswers.length > 0;
    },

    getAnswerFields() {
        return `
            <div class="form-group">
                <label class="form-label">Answer Options *</label>
                <div id="optionsContainer" class="space-y-2"></div>
                <button type="button" id="addOptionBtn" class="btn btn-secondary btn-sm mt-2">
                    <i class="fas fa-plus"></i> Add Option
                </button>
                <div class="form-text">Add at least two options and select one or more correct answers.</div>
            </div>
        `;
    }
};

// Make MultipleSelectQuestion available globally
window.MultipleSelectQuestion = MultipleSelectQuestion; 