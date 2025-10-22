const MultiBlankQuestion = {
    init(formElement, initialData = {}) {
        this.form = formElement;
        this.answers = initialData.answers || [];
        this.setupEventListeners();
        if (this.answers.length > 0) {
            this.setInitialValues();
        }
    },

    setupEventListeners() {
        const addButton = this.form.querySelector('#addBlankBtn');
        if (addButton) {
            addButton.addEventListener('click', () => this.addBlank());
        }

        this.form.addEventListener('click', (e) => {
            if (e.target.closest('.remove-blank')) {
                this.removeBlank(e.target.closest('.input-group'));
            }
        });
    },

    setInitialValues() {
        const container = this.form.querySelector('#multiBlankContainer');
        if (!container) return;

        container.innerHTML = this.answers.map((answer, index) => `
            <div class="input-group">
                <input type="text" name="multi_blank_answers[]" class="form-control" 
                       value="${answer}" placeholder="Answer for blank #${index + 1}" required>
                <button type="button" class="btn btn-danger btn-sm remove-blank">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `).join('');
    },

    addBlank() {
        const container = this.form.querySelector('#multiBlankContainer');
        const blankCount = container.children.length;
        const div = document.createElement('div');
        div.className = 'input-group';
        div.innerHTML = `
            <input type="text" name="multi_blank_answers[]" class="form-control" 
                   placeholder="Answer for blank #${blankCount + 1}" required>
            <button type="button" class="btn btn-danger btn-sm remove-blank">
                <i class="fas fa-times"></i>
            </button>
        `;
        container.appendChild(div);
    },

    removeBlank(blankElement) {
        blankElement.remove();
        this.updateBlankIndices();
    },

    updateBlankIndices() {
        const container = this.form.querySelector('#multiBlankContainer');
        Array.from(container.children).forEach((div, index) => {
            const input = div.querySelector('input[name="multi_blank_answers[]"]');
            if (input) {
                input.placeholder = `Answer for blank #${index + 1}`;
            }
        });
    },

    validateAnswer() {
        const answers = Array.from(this.form.querySelectorAll('input[name="multi_blank_answers[]"]'))
            .map(input => input.value.trim())
            .filter(Boolean);
        
        return answers.length > 0;
    },

    getAnswerFields() {
        return `
            <div class="form-group">
                <label class="form-label">Multiple Blank Answers *</label>
                <div id="multiBlankContainer" class="space-y-2"></div>
                <button type="button" id="addBlankBtn" class="btn btn-secondary btn-sm mt-2">
                    <i class="fas fa-plus"></i> Add Blank
                </button>
                <div class="form-text">Add answers for each blank in the question.</div>
            </div>
        `;
    }
};

// Make MultiBlankQuestion available globally
window.MultiBlankQuestion = MultiBlankQuestion; 