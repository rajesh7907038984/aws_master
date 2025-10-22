/**
 * MultiBlankQuestion - Handler for Multiple Fill in the Blank question type
 */
class MultiBlankQuestion {
    constructor(formElement) {
        this.form = formElement;
        this.answerFields = this.form.querySelector('#answerFields');
        this.blankCount = 1;
        this.maxBlanks = 6;
    }

    setupFields() {
        if (!this.answerFields) return;
        
        this.answerFields.innerHTML = `
            <div class="form-group">
                <label for="question_text_multi">Question with Multiple Blanks:</label>
                <textarea id="question_text_multi" name="question_text_multi" rows="4" required
                         placeholder="Enter your question with {1}, {2}, {3}, etc. for blanks. Example: The capital of {1} is {2} and it has a population of {3}."></textarea>
                <small class="form-text text-muted">Use {1}, {2}, {3}, etc. to indicate blank positions.</small>
            </div>
            <div class="form-group">
                <label class="form-label">Number of Blanks:</label>
                <div class="input-group" style="max-width: 200px;">
                    <button type="button" id="decreaseBlanks" class="btn btn-outline-secondary">−</button>
                    <input type="number" id="blankCount" min="1" max="6" value="1" class="form-control text-center" readonly>
                    <button type="button" id="increaseBlanks" class="btn btn-outline-secondary">+</button>
                </div>
            </div>
            <div id="blanks-container">
                <!-- Blank fields will be generated here -->
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
                         placeholder="Provide an explanation for the correct answers..."></textarea>
            </div>
        `;

        this.generateBlankFields();
        this.setupEventListeners();
    }

    generateBlankFields() {
        const container = this.answerFields.querySelector('#blanks-container');
        if (!container) return;

        container.innerHTML = '';

        for (let i = 1; i <= this.blankCount; i++) {
            const blankDiv = document.createElement('div');
            blankDiv.className = 'form-group blank-group';
            blankDiv.innerHTML = `
                <label for="blank_${i}">Answer for Blank ${i} ({${i}}):</label>
                <input type="text" id="blank_${i}" name="blank_${i}" required
                       placeholder="Correct answer for blank ${i}" class="form-control">
                <div class="alternatives-section" style="margin-top: 10px;">
                    <label class="small">Alternative answers (optional):</label>
                    <div id="alternatives_${i}">
                        <input type="text" name="alternative_${i}_1" placeholder="Alternative for blank ${i}" class="form-control form-control-sm mb-1">
                    </div>
                    <button type="button" class="btn btn-sm btn-secondary" onclick="this.parentElement.parentElement.querySelector('.alternatives-section').appendChild(this.cloneAlternativeField(${i}))">Add Alternative</button>
                </div>
            `;
            container.appendChild(blankDiv);
        }

        // Update blank count display
        const blankCountInput = this.answerFields.querySelector('#blankCount');
        if (blankCountInput) blankCountInput.value = this.blankCount;
    }

    cloneAlternativeField(blankNumber) {
        const container = this.answerFields.querySelector(`#alternatives_${blankNumber}`);
        if (!container) return null;

        const currentAlternatives = container.querySelectorAll('input').length;
        if (currentAlternatives >= 3) return null; // Limit alternatives per blank

        const newField = document.createElement('input');
        newField.type = 'text';
        newField.name = `alternative_${blankNumber}_${currentAlternatives + 1}`;
        newField.placeholder = `Alternative for blank ${blankNumber}`;
        newField.className = 'form-control form-control-sm mb-1';

        return newField;
    }

    setupEventListeners() {
        const increaseBtn = this.answerFields.querySelector('#increaseBlanks');
        const decreaseBtn = this.answerFields.querySelector('#decreaseBlanks');

        if (increaseBtn) {
            increaseBtn.addEventListener('click', () => {
                if (this.blankCount < this.maxBlanks) {
                    this.blankCount++;
                    this.generateBlankFields();
                }
            });
        }

        if (decreaseBtn) {
            decreaseBtn.addEventListener('click', () => {
                if (this.blankCount > 1) {
                    this.blankCount--;
                    this.generateBlankFields();
                }
            });
        }

        // Add event listener for alternative buttons
        this.answerFields.addEventListener('click', (e) => {
            if (e.target.textContent === 'Add Alternative') {
                e.preventDefault();
                const match = e.target.onclick?.toString().match(/(\d+)/);
                if (match) {
                    const blankNumber = parseInt(match[1]);
                    const newField = this.cloneAlternativeField(blankNumber);
                    if (newField) {
                        const container = this.answerFields.querySelector(`#alternatives_${blankNumber}`);
                        container?.appendChild(newField);
                    }
                }
            }
        });
    }

    getAnswerData() {
        const questionText = this.form.querySelector('#question_text_multi');
        const caseSensitive = this.form.querySelector('#case_sensitive');
        const explanation = this.form.querySelector('#explanation');
        
        if (!questionText || !questionText.value.trim()) {
            return { valid: false, message: 'Please enter the question text' };
        }

        // Check if question has the required blank markers
        const expectedBlanks = [];
        for (let i = 1; i <= this.blankCount; i++) {
            expectedBlanks.push(`{${i}}`);
        }

        let missingBlanks = expectedBlanks.filter(blank => !questionText.value.includes(blank));
        if (missingBlanks.length > 0) {
            return { 
                valid: false, 
                message: `Question must include all blank markers: ${expectedBlanks.join(', ')}. Missing: ${missingBlanks.join(', ')}` 
            };
        }

        // Collect answers for all blanks
        const blanks = {};
        for (let i = 1; i <= this.blankCount; i++) {
            const blankInput = this.form.querySelector(`#blank_${i}`);
            if (!blankInput || !blankInput.value.trim()) {
                return { valid: false, message: `Please provide an answer for blank ${i}` };
            }

            // Collect alternatives for this blank
            const alternatives = [];
            const alternativeInputs = this.answerFields.querySelectorAll(`input[name^="alternative_${i}_"]`);
            alternativeInputs.forEach(input => {
                if (input.value.trim()) {
                    alternatives.push(input.value.trim());
                }
            });

            blanks[i] = {
                correct_answer: blankInput.value.trim(),
                alternatives: alternatives
            };
        }

        return {
            valid: true,
            data: {
                question_text: questionText.value.trim(),
                blank_count: this.blankCount,
                blanks: blanks,
                case_sensitive: caseSensitive ? caseSensitive.checked : false,
                explanation: explanation ? explanation.value : ''
            }
        };
    }

    loadData(data) {
        if (!data) return;
        
        // Set blank count first
        if (data.blank_count) {
            this.blankCount = Math.max(1, Math.min(data.blank_count, this.maxBlanks));
        }

        this.generateBlankFields();

        // Load question text
        if (data.question_text) {
            const questionField = this.form.querySelector('#question_text_multi');
            if (questionField) questionField.value = data.question_text;
        }

        // Load blank answers
        if (data.blanks) {
            Object.keys(data.blanks).forEach(blankNumber => {
                const blankData = data.blanks[blankNumber];
                
                // Load correct answer
                const blankField = this.form.querySelector(`#blank_${blankNumber}`);
                if (blankField && blankData.correct_answer) {
                    blankField.value = blankData.correct_answer;
                }

                // Load alternatives
                if (blankData.alternatives && Array.isArray(blankData.alternatives)) {
                    const container = this.answerFields.querySelector(`#alternatives_${blankNumber}`);
                    if (container) {
                        blankData.alternatives.forEach((alt, index) => {
                            if (index === 0) {
                                // Update first alternative field
                                const firstAlt = container.querySelector('input');
                                if (firstAlt) firstAlt.value = alt;
                            } else {
                                // Add and populate additional fields
                                const newField = this.cloneAlternativeField(parseInt(blankNumber));
                                if (newField) {
                                    newField.value = alt;
                                    container.appendChild(newField);
                                }
                            }
                        });
                    }
                }
            });
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
window.MultiBlankQuestion = MultiBlankQuestion;
