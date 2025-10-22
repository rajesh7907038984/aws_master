/**
 * MatchingQuestion - Handler for Matching question type
 */
class MatchingQuestion {
    constructor(formElement) {
        this.form = formElement;
        this.answerFields = this.form.querySelector('#answerFields');
        this.pairCount = 3; // Start with 3 pairs minimum
        this.maxPairs = 8; // Maximum 8 pairs
    }

    setupFields() {
        if (!this.answerFields) return;
        
        this.answerFields.innerHTML = `
            <div class="form-group">
                <label class="form-label">Instructions:</label>
                <p class="text-muted">Create pairs of items that students need to match. The left column items will be presented to students, and they need to match them with the correct right column items.</p>
            </div>
            <div class="form-group">
                <label class="form-label">Number of Matching Pairs:</label>
                <div class="input-group" style="max-width: 200px;">
                    <button type="button" id="decreasePairs" class="btn btn-outline-secondary">−</button>
                    <input type="number" id="pairCount" min="3" max="8" value="3" class="form-control text-center" readonly>
                    <button type="button" id="increasePairs" class="btn btn-outline-secondary">+</button>
                </div>
            </div>
            <div id="pairs-container">
                <!-- Matching pairs will be generated here -->
            </div>
            <div class="form-group">
                <div class="form-check">
                    <input type="checkbox" id="shuffle_right" name="shuffle_right" class="form-check-input" checked>
                    <label for="shuffle_right" class="form-check-label">Shuffle right column items (recommended)</label>
                </div>
            </div>
            <div class="form-group">
                <label for="explanation">Explanation (Optional):</label>
                <textarea id="explanation" name="explanation" rows="3" 
                         placeholder="Provide an explanation for the correct matches..."></textarea>
            </div>
        `;

        this.generatePairFields();
        this.setupEventListeners();
    }

    generatePairFields() {
        const container = this.answerFields.querySelector('#pairs-container');
        if (!container) return;

        container.innerHTML = `
            <div class="matching-header">
                <div class="row">
                    <div class="col-md-5">
                        <h6>Left Column (Items to Match)</h6>
                    </div>
                    <div class="col-md-2 text-center">
                        <h6>Match</h6>
                    </div>
                    <div class="col-md-5">
                        <h6>Right Column (Match Options)</h6>
                    </div>
                </div>
            </div>
        `;

        for (let i = 1; i <= this.pairCount; i++) {
            const pairDiv = document.createElement('div');
            pairDiv.className = 'matching-pair row mb-3';
            pairDiv.innerHTML = `
                <div class="col-md-5">
                    <div class="form-group">
                        <label for="left_${i}" class="sr-only">Left item ${i}</label>
                        <input type="text" id="left_${i}" name="left_${i}" required
                               placeholder="Item ${i} (left side)" class="form-control">
                    </div>
                </div>
                <div class="col-md-2 text-center">
                    <div class="match-indicator">
                        <i class="fas fa-arrows-alt-h" style="margin-top: 10px; color: #666;"></i>
                        <div class="small text-muted">Pair ${i}</div>
                    </div>
                </div>
                <div class="col-md-5">
                    <div class="form-group">
                        <label for="right_${i}" class="sr-only">Right item ${i}</label>
                        <input type="text" id="right_${i}" name="right_${i}" required
                               placeholder="Match for item ${i} (right side)" class="form-control">
                    </div>
                </div>
            `;
            container.appendChild(pairDiv);
        }

        // Update pair count display
        const pairCountInput = this.answerFields.querySelector('#pairCount');
        if (pairCountInput) pairCountInput.value = this.pairCount;
    }

    setupEventListeners() {
        const increaseBtn = this.answerFields.querySelector('#increasePairs');
        const decreaseBtn = this.answerFields.querySelector('#decreasePairs');

        if (increaseBtn) {
            increaseBtn.addEventListener('click', () => {
                if (this.pairCount < this.maxPairs) {
                    this.pairCount++;
                    this.generatePairFields();
                }
            });
        }

        if (decreaseBtn) {
            decreaseBtn.addEventListener('click', () => {
                if (this.pairCount > 3) {
                    this.pairCount--;
                    this.generatePairFields();
                }
            });
        }
    }

    getAnswerData() {
        const shuffleRight = this.form.querySelector('#shuffle_right');
        const explanation = this.form.querySelector('#explanation');
        
        const pairs = [];
        let hasEmptyField = false;

        for (let i = 1; i <= this.pairCount; i++) {
            const leftInput = this.form.querySelector(`#left_${i}`);
            const rightInput = this.form.querySelector(`#right_${i}`);
            
            if (!leftInput || !rightInput) continue;
            
            const leftText = leftInput.value.trim();
            const rightText = rightInput.value.trim();
            
            if (!leftText || !rightText) {
                hasEmptyField = true;
                break;
            }

            pairs.push({
                left: leftText,
                right: rightText,
                pair_id: i
            });
        }

        if (hasEmptyField) {
            return { valid: false, message: 'Please fill in all matching pair fields' };
        }

        if (pairs.length < 3) {
            return { valid: false, message: 'Please provide at least 3 matching pairs' };
        }

        // Check for duplicate items in left column
        const leftItems = pairs.map(p => p.left.toLowerCase());
        const uniqueLeftItems = [...new Set(leftItems)];
        if (leftItems.length !== uniqueLeftItems.length) {
            return { valid: false, message: 'Left column items must be unique' };
        }

        // Check for duplicate items in right column
        const rightItems = pairs.map(p => p.right.toLowerCase());
        const uniqueRightItems = [...new Set(rightItems)];
        if (rightItems.length !== uniqueRightItems.length) {
            return { valid: false, message: 'Right column items must be unique' };
        }

        return {
            valid: true,
            data: {
                pairs: pairs,
                pair_count: this.pairCount,
                shuffle_right_column: shuffleRight ? shuffleRight.checked : true,
                explanation: explanation ? explanation.value : ''
            }
        };
    }

    loadData(data) {
        if (!data) return;
        
        // Set pair count first
        if (data.pair_count) {
            this.pairCount = Math.max(3, Math.min(data.pair_count, this.maxPairs));
        } else if (data.pairs && Array.isArray(data.pairs)) {
            this.pairCount = Math.max(3, Math.min(data.pairs.length, this.maxPairs));
        }

        this.generatePairFields();

        // Load pairs
        if (data.pairs && Array.isArray(data.pairs)) {
            data.pairs.forEach((pair, index) => {
                const pairIndex = index + 1;
                
                const leftField = this.form.querySelector(`#left_${pairIndex}`);
                const rightField = this.form.querySelector(`#right_${pairIndex}`);
                
                if (leftField && pair.left) {
                    leftField.value = pair.left;
                }
                
                if (rightField && pair.right) {
                    rightField.value = pair.right;
                }
            });
        }

        // Load shuffle option
        if (typeof data.shuffle_right_column === 'boolean') {
            const shuffleField = this.form.querySelector('#shuffle_right');
            if (shuffleField) shuffleField.checked = data.shuffle_right_column;
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
window.MatchingQuestion = MatchingQuestion;
