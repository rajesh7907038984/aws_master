const MatchingQuestion = {
    init(formElement, initialData = {}) {
        this.form = formElement;
        this.pairs = initialData.pairs || { left: [], right: [] };
        this.setupEventListeners();
        if (this.pairs.left.length > 0) {
            this.setInitialValues();
        }
    },

    setupEventListeners() {
        const addButton = this.form.querySelector('#addPairBtn');
        if (addButton) {
            addButton.addEventListener('click', () => this.addPair());
        }

        this.form.addEventListener('click', (e) => {
            if (e.target.closest('.remove-pair')) {
                this.removePair(e.target.closest('.input-group'));
            }
        });
    },

    setInitialValues() {
        const container = this.form.querySelector('#matchingContainer');
        if (!container) return;

        container.innerHTML = this.pairs.left.map((leftItem, index) => `
            <div class="input-group">
                <input type="text" name="matching_left[]" class="form-control" 
                       value="${leftItem}" placeholder="Left item" required>
                <input type="text" name="matching_right[]" class="form-control" 
                       value="${this.pairs.right[index]}" placeholder="Right item" required>
                <button type="button" class="btn btn-danger btn-sm remove-pair">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `).join('');
    },

    addPair() {
        const container = this.form.querySelector('#matchingContainer');
        const div = document.createElement('div');
        div.className = 'input-group';
        div.innerHTML = `
            <input type="text" name="matching_left[]" class="form-control" placeholder="Left item" required>
            <input type="text" name="matching_right[]" class="form-control" placeholder="Right item" required>
            <button type="button" class="btn btn-danger btn-sm remove-pair">
                <i class="fas fa-times"></i>
            </button>
        `;
        container.appendChild(div);
    },

    removePair(pairElement) {
        pairElement.remove();
    },

    validateAnswer() {
        const leftItems = Array.from(this.form.querySelectorAll('input[name="matching_left[]"]'))
            .map(input => input.value.trim())
            .filter(Boolean);
        
        const rightItems = Array.from(this.form.querySelectorAll('input[name="matching_right[]"]'))
            .map(input => input.value.trim())
            .filter(Boolean);
        
        return leftItems.length > 0 && leftItems.length === rightItems.length;
    },

    getAnswerFields() {
        return `
            <div class="form-group">
                <label class="form-label">Matching Pairs *</label>
                <div id="matchingContainer" class="space-y-2"></div>
                <button type="button" id="addPairBtn" class="btn btn-secondary btn-sm mt-2">
                    <i class="fas fa-plus"></i> Add Pair
                </button>
                <div class="form-text">Add matching pairs for students to connect.</div>
            </div>
        `;
    }
};

// Make MatchingQuestion available globally
window.MatchingQuestion = MatchingQuestion; 