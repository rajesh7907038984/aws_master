document.addEventListener('DOMContentLoaded', function() {
    console.log('=== Question Form Script Loading ===');
    
    const questionType = document.getElementById('id_question_type');
    const answerFields = document.getElementById('answerFields');
    const form = document.getElementById('questionForm');
    const isEdit = document.querySelector('input[name="is_edit"]')?.value === 'true';

    console.log('Elements found:');
    console.log('- Question type dropdown:', questionType ? 'Found' : 'NOT FOUND');
    console.log('- Answer fields container:', answerFields ? 'Found' : 'NOT FOUND');
    console.log('- Form element:', form ? 'Found' : 'NOT FOUND');
    console.log('- Is edit mode:', isEdit);
    
    if (isEdit) {
        console.log('Initial question type:', questionType?.value);
        console.log('Options JSON:', window.options_json);
        console.log('Correct answers JSON:', window.correct_answers_json);
    } else {
        console.log('New question mode - initializing empty data');
    }

    // Add form submission handling for TinyMCE
    if (form) {
        form.addEventListener('submit', function(e) {
            // Save TinyMCE content to the form before submitting
            if (typeof tinymce !== 'undefined') {
                const editor = tinymce.get('question_text_editor');
                if (editor) {
                    console.log('Saving TinyMCE content before submission');
                    editor.save(); // This will update the textarea with the editor content
                }
            }
        });
    }

    function handleEditMode() {
        if (isEdit && questionType) {
            const originalValue = questionType.value;
            
            questionType.addEventListener('mousedown', function(e) {
                if (isEdit) {
                    e.preventDefault();
                    this.blur();
                    return false;
                }
            });
            
            questionType.addEventListener('change', function(e) {
                if (isEdit) {
                    this.value = originalValue;
                }
            });
        }
    }

    function setupOptionHandlers() {
        const addOptionBtn = document.getElementById('addOptionBtn');
        if (addOptionBtn) {
            addOptionBtn.addEventListener('click', function() {
                const container = document.getElementById('optionsContainer');
                const optionCount = container.children.length;
                const isVakTest = window.is_vak_test || false;
                const isInitialAssessment = window.is_initial_assessment || false;
                const isAssessmentType = isVakTest || isInitialAssessment;
                
                const newOption = document.createElement('div');
                newOption.className = 'input-group';
                
                const correctAnswerInput = !isVakTest ? `
                    <div class="form-check">
                        <input type="${questionType.value === 'multiple_select' ? 'checkbox' : 'radio'}" 
                               name="correct_answers[]" 
                               value="${optionCount}"
                               class="form-check-input"
                               id="correct_${optionCount}"
                               title="Mark as correct answer">
                        <label class="form-check-label" for="correct_${optionCount}">
                            ${questionType.value === 'multiple_select' ? 'Correct' : 'Correct'}
                        </label>
                    </div>
                ` : '';
                
                const learningStyleDropdown = isVakTest ? `
                    <select name="learning_styles[]" 
                            class="learning-style-select" 
                            title="Learning style for this option" 
                            required>
                        <option value="">Select Learning Style</option>
                        <option value="visual">Visual</option>
                        <option value="auditory">Auditory</option>
                        <option value="kinesthetic">Kinesthetic</option>
                    </select>
                ` : '';
                
                newOption.innerHTML = `
                    <input type="text" 
                           name="options[]" 
                           class="form-control" 
                           placeholder="Enter option ${optionCount + 1}" 
                           required>
                    <div class="input-group-actions">
                        ${correctAnswerInput}
                        ${learningStyleDropdown}
                        <button type="button" 
                                class="btn-remove remove-option" 
                                title="Remove this option"
                                data-index="${optionCount}">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                `;
                container.appendChild(newOption);
                
                // Add event listener for the new remove button
                newOption.querySelector('.remove-option').addEventListener('click', function() {
                    this.closest('.input-group').remove();
                });
            });
        }

        // Setup remove option handlers
        document.querySelectorAll('.remove-option').forEach(button => {
            button.addEventListener('click', function() {
                this.closest('.input-group').remove();
            });
        });
    }

    function setupMultiBlankHandlers() {
        const addBlankBtn = document.getElementById('addBlankBtn');
        if (addBlankBtn) {
            addBlankBtn.addEventListener('click', function() {
                const container = document.getElementById('multiBlankContainer');
                const blankCount = container.children.length;
                
                const newBlank = document.createElement('div');
                newBlank.className = 'input-group';
                newBlank.style.cssText = 'display: flex; align-items: center; gap: 8px; margin-bottom: 8px;';
                newBlank.innerHTML = `
                    <input type="text" 
                           name="multi_blank_answers[]" 
                           class="form-control" 
                           placeholder="Answer ${blankCount + 1}"
                           required>
                    <button type="button" class="btn btn-danger btn-sm remove-blank" title="Remove this answer">
                        <i class="fas fa-times"></i>
                    </button>
                `;
                container.appendChild(newBlank);
                
                // Add event listener for the new remove button
                newBlank.querySelector('.remove-blank').addEventListener('click', function() {
                    this.closest('.input-group').remove();
                });
            });
        }

        // Setup remove blank handlers for existing buttons
        document.querySelectorAll('.remove-blank').forEach(button => {
            button.addEventListener('click', function() {
                this.closest('.input-group').remove();
            });
        });
    }

    function setupMatchingHandlers() {
        const addPairBtn = document.getElementById('addPairBtn');
        if (addPairBtn) {
            addPairBtn.addEventListener('click', function() {
                const container = document.getElementById('matchingContainer');
                const pairCount = container.children.length;
                
                const newPair = document.createElement('div');
                newPair.className = 'grid grid-cols-2 gap-4';
                newPair.innerHTML = `
                    <input type="text" 
                           name="matching_left[]" 
                           class="form-control" 
                           placeholder="Left item ${pairCount + 1}"
                           required>
                    <div class="flex">
                        <input type="text" 
                               name="matching_right[]" 
                               class="form-control" 
                               placeholder="Right item ${pairCount + 1}"
                               required>
                        <button type="button" class="btn btn-danger btn-sm remove-pair ml-2">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                `;
                container.appendChild(newPair);
            });
        }

        // Setup remove pair handlers
        document.querySelectorAll('.remove-pair').forEach(button => {
            button.addEventListener('click', function() {
                this.closest('.grid').remove();
            });
        });
    }

    function setupDragDropMatchingHandlers() {
        const addDragDropPairBtn = document.getElementById('addDragDropPairBtn');
        if (addDragDropPairBtn) {
            addDragDropPairBtn.addEventListener('click', function() {
                const container = document.getElementById('dragDropMatchingContainer');
                const pairCount = container.children.length;
                
                const newPair = document.createElement('div');
                newPair.className = 'input-group';
                newPair.innerHTML = `
                    <input type="text" 
                           name="matching_left[]" 
                           class="form-control" 
                           placeholder="Left item ${pairCount + 1} (drag source)"
                           required>
                    <input type="text" 
                           name="matching_right[]" 
                           class="form-control" 
                           placeholder="Right item ${pairCount + 1} (drop target)"
                           required>
                    <button type="button" class="btn btn-danger btn-sm remove-pair">
                        <i class="fas fa-times"></i>
                    </button>
                `;
                container.appendChild(newPair);
            });
        }

        // Setup remove pair handlers using event delegation
        const container = document.getElementById('dragDropMatchingContainer');
        if (container) {
            container.addEventListener('click', function(e) {
                if (e.target.closest('.remove-pair')) {
                    e.target.closest('.input-group').remove();
                }
            });
        }
    }

    function generateTrueFalseHtml(correctAnswer) {
        return `
            <div class="form-group">
                <label class="form-label">Correct Answer *</label>
                <div class="space-y-2">
                    <div class="flex items-center">
                        <input type="radio" id="true_option" name="correct_answer" value="True" class="form-radio" required ${correctAnswer === 'True' ? 'checked' : ''}>
                        <label for="true_option" class="ml-2">True</label>
                    </div>
                    <div class="flex items-center">
                        <input type="radio" id="false_option" name="correct_answer" value="False" class="form-radio" required ${correctAnswer === 'False' ? 'checked' : ''}>
                        <label for="false_option" class="ml-2">False</label>
                    </div>
                </div>
                <div class="form-text mt-2">Select the correct answer for this True/False question.</div>
            </div>
        `;
    }

    function generateMultipleChoiceHtml(type, options, correctAnswers, learningStyles = []) {
        const isVakTest = window.is_vak_test || false;
        const learningStyleOptions = [
            { value: '', label: 'Select Learning Style' },
            { value: 'visual', label: 'Visual' },
            { value: 'auditory', label: 'Auditory' },
            { value: 'kinesthetic', label: 'Kinesthetic' }
        ];
        
        // Ensure correctAnswers is an array - handle both array and object formats
        let correctAnswersArray = [];
        if (Array.isArray(correctAnswers)) {
            correctAnswersArray = correctAnswers;
        } else if (typeof correctAnswers === 'object' && correctAnswers !== null) {
            // Convert object format {0: true, 1: false, 2: true} to array of indices
            correctAnswersArray = Object.keys(correctAnswers).filter(key => correctAnswers[key] === true);
        }
        
        // Debug logging for correct answers (only in development)
        if (false || false) {
            console.log('generateMultipleChoiceHtml - correctAnswers:', correctAnswers);
            console.log('generateMultipleChoiceHtml - correctAnswersArray:', correctAnswersArray);
            console.log('generateMultipleChoiceHtml - options:', options);
        }
        
        return `
            <div class="answer-options-container">
                <label class="form-label">Answer Options *</label>
                <div id="optionsContainer" class="options-container">
                    ${options.map((option, index) => `
                        <div class="input-group">
                            <input type="text" 
                                   name="options[]" 
                                   class="form-control" 
                                   value="${option}" 
                                   placeholder="Enter option ${index + 1}" 
                                   required>
                            <div class="input-group-actions">
                                ${!isVakTest ? `
                                    <div class="form-check">
                                        <input type="${type === 'multiple_select' ? 'checkbox' : 'radio'}" 
                                               name="correct_answers[]" 
                                               value="${index}"
                                               ${correctAnswersArray.includes(String(index)) ? 'checked' : ''}
                                               class="form-check-input"
                                               id="correct_${index}"
                                               title="Mark as correct answer">
                                        <label class="form-check-label" for="correct_${index}">
                                            ${type === 'multiple_select' ? 'Correct' : 'Correct'}
                                        </label>
                                    </div>
                                ` : ''}
                                ${isVakTest ? `
                                    <select name="learning_styles[]" 
                                            class="learning-style-select" 
                                            title="Learning style for this option" 
                                            required>
                                        ${learningStyleOptions.map(ls => `
                                            <option value="${ls.value}" ${(learningStyles[index] || '') === ls.value ? 'selected' : ''}>${ls.label}</option>
                                        `).join('')}
                                    </select>
                                ` : ''}
                                <button type="button" 
                                        class="btn-remove remove-option" 
                                        title="Remove this option"
                                        data-index="${index}">
                                    <i class="fas fa-trash"></i>
                                </button>
                            </div>
                        </div>
                    `).join('')}
                </div>
                <button type="button" id="addOptionBtn" class="btn-add">
                    <i class="fas fa-plus"></i> Add Option
                </button>
                <div class="form-text">${isVakTest ? 'Add answer options and select the learning style for each option. All options are valid choices for VAK tests.' : 'Add answer options and select the correct one(s).'}</div>
            </div>
        `;
    }

    function generateFillBlankHtml(existingAnswer) {
        return `
            <div class="form-group">
                <label class="form-label">Correct Answer *</label>
                <input type="text" name="blank_answer" class="form-control" value="${existingAnswer}" required>
                <div class="form-text mt-2">Enter the correct answer that students must type exactly.</div>
            </div>
        `;
    }

    function generateMultiBlankHtml(answers) {
        return `
            <div class="form-group">
                <label class="form-label">Multiple Blank Answers *</label>
                <div id="multiBlankContainer" class="space-y-2">
                    ${answers.map((answer, index) => `
                        <div class="input-group">
                            <input type="text" name="multi_blank_answers[]" class="form-control" value="${answer}" placeholder="Answer ${index + 1}" required>
                            <button type="button" class="btn btn-danger btn-sm remove-blank ml-2">
                                <i class="fas fa-times"></i>
                            </button>
                        </div>
                    `).join('')}
                </div>
                <button type="button" id="addBlankBtn" class="btn btn-secondary btn-sm mt-2">
                    <i class="fas fa-plus"></i> Add Blank
                </button>
                <div class="form-text mt-2">Add multiple correct answers for fill-in-the-blank question.</div>
            </div>
        `;
    }

    function generateMatchingHtml(pairs) {
        return `
            <div class="form-group">
                <label class="form-label">Matching Pairs *</label>
                <div id="matchingContainer" class="space-y-2">
                    ${pairs.left.map((left, index) => `
                        <div class="grid grid-cols-2 gap-4">
                            <input type="text" 
                                   name="matching_left[]" 
                                   class="form-control" 
                                   value="${left}"
                                   placeholder="Left item ${index + 1}"
                                   required>
                            <div class="flex">
                                <input type="text" 
                                       name="matching_right[]" 
                                       class="form-control" 
                                       value="${pairs.right[index]}"
                                       placeholder="Right item ${index + 1}"
                                       required>
                                <button type="button" class="btn btn-danger btn-sm remove-pair ml-2">
                                    <i class="fas fa-times"></i>
                                </button>
                            </div>
                        </div>
                    `).join('')}
                </div>
                <button type="button" id="addPairBtn" class="btn btn-secondary btn-sm mt-2">
                    <i class="fas fa-plus"></i> Add Pair
                </button>
                <div class="form-text mt-2">Add matching pairs for students to connect.</div>
            </div>
        `;
    }

    function updateAnswerFields() {
        if (!answerFields) {
            console.log('Answer fields container not found');
            return;
        }
        
        const type = questionType.value;
        console.log('Updating answer fields for type:', type);
        console.log('Question type element:', questionType);
        console.log('Question type options:', questionType.options);
        
        // Initialize empty data for new questions if not already set
        if (!window.options_json) window.options_json = [];
        if (!window.correct_answers_json) window.correct_answers_json = [];
        if (!window.learning_styles_json) window.learning_styles_json = [];
        if (!window.multiple_blank_answers_json) window.multiple_blank_answers_json = [];
        if (!window.matching_pairs_json) window.matching_pairs_json = {left: [], right: []};
        if (!window.blank_answer) window.blank_answer = '';
        
        // Use requestAnimationFrame to prevent flickering during DOM updates
        requestAnimationFrame(() => {
            answerFields.innerHTML = '';
            
            switch(type) {
            case 'multiple_choice':
            case 'multiple_select':
                const options = window.options_json || [];
                const correctAnswers = window.correct_answers_json || [];
                const learningStyles = window.learning_styles_json || [];
                
                // Debug logging (only in development)
                if (false || false) {
                    console.log('updateAnswerFields - type:', type);
                    console.log('updateAnswerFields - options:', options);
                    console.log('updateAnswerFields - correctAnswers:', correctAnswers);
                    console.log('updateAnswerFields - learningStyles:', learningStyles);
                }
                
                // Ensure at least 2 empty options for new questions
                const optionsToShow = options.length > 0 ? options : ['', '', ''];
                
                answerFields.innerHTML = generateMultipleChoiceHtml(type, optionsToShow, correctAnswers, learningStyles);
                setupOptionHandlers();
                break;
                
            case 'true_false':
                const isVakTestTrueFalse = window.is_vak_test || false;
                // Handle correct answer for true/false - could be array or object format
                let correctAnswer = '';
                if (Array.isArray(window.correct_answers_json) && window.correct_answers_json.length > 0) {
                    correctAnswer = window.correct_answers_json[0];
                } else if (typeof window.correct_answers_json === 'object' && window.correct_answers_json !== null) {
                    // Find the first correct answer from object format
                    for (const [key, value] of Object.entries(window.correct_answers_json)) {
                        if (value === true) {
                            const answerIndex = parseInt(key);
                            if (window.options_json && window.options_json[answerIndex]) {
                                correctAnswer = window.options_json[answerIndex];
                                break;
                            }
                        }
                    }
                }
                
                if (isVakTestTrueFalse) {
                    // For VAK Test only, don't show correct answer selection
                    answerFields.innerHTML = `
                        <div class="form-group">
                            <div class="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                                <p class="text-blue-800 text-sm">
                                    <i class="fas fa-info-circle mr-2"></i>
                                    VAK Test questions do not require correct answer selection. Both True and False options will be available to students.
                                </p>
                            </div>
                        </div>
                    `;
                } else {
                    answerFields.innerHTML = `
                        <div class="form-group">
                            <label class="form-label">Correct Answer</label>
                            <div class="space-y-2">
                                <label class="inline-flex items-center">
                                    <input type="radio" name="correct_answer" value="True" class="form-radio" ${correctAnswer === 'True' ? 'checked' : ''}>
                                    <span class="ml-2">True</span>
                                </label>
                                <label class="inline-flex items-center ml-6">
                                    <input type="radio" name="correct_answer" value="False" class="form-radio" ${correctAnswer === 'False' ? 'checked' : ''}>
                                    <span class="ml-2">False</span>
                                </label>
                            </div>
                        </div>
                    `;
                }
                break;
                
            case 'fill_blank':
                const isVakTestFillBlank = window.is_vak_test || false;
                const blankAnswer = window.blank_answer || '';
                console.log('Setting blank answer:', blankAnswer);
                
                if (isVakTestFillBlank) {
                    // For VAK Test only, don't require correct answer
                    answerFields.innerHTML = `
                        <div class="form-group">
                            <div class="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                                <p class="text-blue-800 text-sm">
                                    <i class="fas fa-info-circle mr-2"></i>
                                    VAK Test questions do not require correct answer specification. Students' responses will be recorded without correctness validation.
                                </p>
                            </div>
                        </div>
                    `;
                } else {
                    answerFields.innerHTML = `
                        <div class="form-group">
                            <label for="blank_answer" class="form-label">Correct Answer</label>
                            <input type="text" 
                                   name="blank_answer" 
                                   id="blank_answer"
                                   class="form-control" 
                                   value="${blankAnswer}"
                                   placeholder="Enter the correct answer"
                                   required>
                            <div class="form-text">Enter the exact answer that students must type</div>
                        </div>
                    `;
                }
                break;
                
            case 'multi_blank':
                const multiBlankAnswers = window.multiple_blank_answers_json || [];
                // Ensure at least one empty field for new questions
                const answersToShow = multiBlankAnswers.length > 0 ? multiBlankAnswers : ['', ''];
                answerFields.innerHTML = `
                    <div class="form-group">
                        <label class="form-label">Correct Answers *</label>
                        <div id="multiBlankContainer" class="space-y-2">
                            ${answersToShow.map((answer, index) => `
                                <div class="input-group" style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                                    <input type="text" 
                                           name="multi_blank_answers[]" 
                                           class="form-control" 
                                           value="${answer}"
                                           placeholder="Answer ${index + 1}"
                                           required>
                                    <button type="button" class="btn btn-danger btn-sm remove-blank" title="Remove this answer">
                                        <i class="fas fa-times"></i>
                                    </button>
                                </div>
                            `).join('')}
                        </div>
                        <button type="button" id="addBlankBtn" class="btn btn-secondary btn-sm mt-2">
                            <i class="fas fa-plus"></i> Add Answer
                        </button>
                        <div class="form-text mt-2">Add multiple correct answers for this fill-in-the-blank question.</div>
                    </div>
                `;
                setupMultiBlankHandlers();
                break;
                
            case 'matching':
                const matchingPairs = window.matching_pairs_json || {left: [], right: []};
                // Ensure matchingPairs has the correct structure and at least 2 empty pairs for new questions
                const safeMatchingPairs = {
                    left: Array.isArray(matchingPairs.left) ? matchingPairs.left : [],
                    right: Array.isArray(matchingPairs.right) ? matchingPairs.right : []
                };
                const pairsToShow = safeMatchingPairs.left.length > 0 ? safeMatchingPairs : {left: ['', ''], right: ['', '']};
                answerFields.innerHTML = `
                    <div class="form-group">
                        <label class="form-label">Matching Pairs *</label>
                        <div id="matchingContainer" class="space-y-2">
                            ${pairsToShow.left.map((leftItem, index) => `
                                <div class="grid grid-cols-2 gap-4">
                                    <input type="text" 
                                           name="matching_left[]" 
                                           class="form-control" 
                                           value="${leftItem}"
                                           placeholder="Left item ${index + 1}"
                                           required>
                                    <div class="flex">
                                        <input type="text" 
                                               name="matching_right[]" 
                                               class="form-control" 
                                               value="${pairsToShow.right[index] || ''}"
                                               placeholder="Right item ${index + 1}"
                                               required>
                                        <button type="button" class="btn btn-danger btn-sm remove-pair ml-2" title="Remove this pair">
                                            <i class="fas fa-times"></i>
                                        </button>
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                        <button type="button" id="addPairBtn" class="btn btn-secondary btn-sm mt-2">
                            <i class="fas fa-plus"></i> Add Pair
                        </button>
                        <div class="form-text mt-2">Add matching pairs for students to connect.</div>
                    </div>
                `;
                setupMatchingHandlers();
                break;
                
            case 'drag_drop_matching':
                const dragDropMatchingPairs = window.matching_pairs_json || {left: [], right: []};
                
                // Ensure dragDropMatchingPairs has the correct structure and at least 2 empty pairs for new questions
                const safeDragDropMatchingPairs = {
                    left: Array.isArray(dragDropMatchingPairs.left) ? dragDropMatchingPairs.left : [],
                    right: Array.isArray(dragDropMatchingPairs.right) ? dragDropMatchingPairs.right : []
                };
                const dragDropPairsToShow = safeDragDropMatchingPairs.left.length > 0 ? safeDragDropMatchingPairs : {left: ['', ''], right: ['', '']};
                answerFields.innerHTML = `
                    <div class="form-group">
                        <label class="form-label">Drag & Drop Matching Pairs *</label>
                        <div id="dragDropMatchingContainer" class="space-y-2 drag-drop-matching-container">
                            ${dragDropPairsToShow.left.map((leftItem, index) => `
                                <div class="input-group" style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                                    <input type="text" 
                                           name="matching_left[]" 
                                           class="form-control" 
                                           value="${leftItem}"
                                           placeholder="Left item ${index + 1} (drag source)"
                                           required>
                                    <input type="text" 
                                           name="matching_right[]" 
                                           class="form-control" 
                                           value="${dragDropPairsToShow.right[index] || ''}"
                                           placeholder="Right item ${index + 1} (drop target)"
                                           required>
                                    <button type="button" class="btn btn-danger btn-sm remove-pair" title="Remove this pair">
                                        <i class="fas fa-times"></i>
                                    </button>
                                </div>
                            `).join('')}
                        </div>
                        <button type="button" id="addDragDropPairBtn" class="btn btn-secondary btn-sm mt-2">
                            <i class="fas fa-plus"></i> Add Pair
                        </button>
                        <div class="form-text mt-2">Add matching pairs for drag and drop. Left items will be draggable, right items will be drop targets.</div>
                    </div>
                `;
                setupDragDropMatchingHandlers();
                break;
                
            default:
                // For new questions or unrecognized types, show placeholder
                answerFields.innerHTML = `
                    <div class="form-group">
                        <div class="p-4 bg-gray-50 border border-gray-200 rounded-lg text-center">
                            <p class="text-gray-600">Please select a question type above to configure answer options.</p>
                        </div>
                    </div>
                `;
                break;
            }
        });
    }

    function validateForm(e) {
        let isValid = true;
        let errorMessage = '';
        const questionTypeValue = questionType?.value;
        
        // Check if question text is filled
        let questionText = '';
        
        // Try to get content from TinyMCE if available
        if (typeof tinymce !== 'undefined') {
            const editor = tinymce.get('question_text_editor');
            if (editor) {
                questionText = editor.getContent();
            }
        }
        
        // Fallback to regular textarea
        if (!questionText) {
            const questionTextarea = document.getElementById('question_text_editor');
            questionText = questionTextarea?.value || '';
        }
        
        if (!questionText.trim()) {
            e.preventDefault();
            isValid = false;
            const textarea = document.getElementById('question_text_editor');
            
            // Add error UI indication
            if (textarea) {
                textarea.classList.add('border-red-500');
                
                // Add error message
                let errorMsg = textarea.parentNode.querySelector('.error-message');
                if (!errorMsg) {
                    errorMsg = document.createElement('div');
                    errorMsg.className = 'error-message text-red-500 text-sm mt-1';
                    errorMsg.textContent = 'Please enter a question.';
                    textarea.parentNode.appendChild(errorMsg);
                }
            }
        }
        
        // Continue with other validations
        if (questionTypeValue === 'true_false') {
            const selectedAnswer = form.querySelector('input[name="correct_answer"]:checked');
            if (!selectedAnswer) {
                isValid = false;
                errorMessage = 'Please select either True or False as the correct answer.';
            }
        } else if (questionTypeValue === 'multiple_choice' || questionTypeValue === 'multiple_select') {
            const options = Array.from(form.querySelectorAll('input[name="options[]"]'))
                .map(input => input.value.trim())
                .filter(Boolean);
                
            const correctAnswers = form.querySelectorAll('input[name="correct_answers[]"]:checked');
            const isVakTest = window.is_vak_test || false;
            
            if (options.length < 2) {
                isValid = false;
                errorMessage = 'Please add at least two options.';
            } else if (!isVakTest && correctAnswers.length === 0) {
                isValid = false;
                errorMessage = 'Please select at least one correct answer.';
            } else if (!isVakTest && questionTypeValue === 'multiple_choice' && correctAnswers.length > 1) {
                isValid = false;
                errorMessage = 'Multiple choice questions can only have one correct answer.';
            }
            
            // For VAK tests, validate learning styles instead
            if (isVakTest) {
                const learningStyleSelects = form.querySelectorAll('select[name="learning_styles[]"]');
                let hasEmptyLearningStyle = false;
                
                learningStyleSelects.forEach(select => {
                    if (!select.value) {
                        hasEmptyLearningStyle = true;
                    }
                });
                
                if (hasEmptyLearningStyle) {
                    isValid = false;
                    errorMessage = 'Please select a learning style for all answer options.';
                }
            }
        } else if (questionTypeValue === 'fill_blank') {
            const answer = form.querySelector('input[name="blank_answer"]').value.trim();
            if (!answer) {
                isValid = false;
                errorMessage = 'Please enter the correct answer.';
            }
        } else if (questionTypeValue === 'multi_blank') {
            const answers = Array.from(form.querySelectorAll('input[name="multi_blank_answers[]"]'))
                .map(input => input.value.trim())
                .filter(Boolean);
            
            if (answers.length === 0) {
                isValid = false;
                errorMessage = 'Please add at least one answer.';
            }
        } else if (questionTypeValue === 'matching') {
            const leftItems = Array.from(form.querySelectorAll('input[name="matching_left[]"]'))
                .map(input => input.value.trim())
                .filter(Boolean);
            const rightItems = Array.from(form.querySelectorAll('input[name="matching_right[]"]'))
                .map(input => input.value.trim())
                .filter(Boolean);
            
            if (leftItems.length < 2 || rightItems.length < 2) {
                isValid = false;
                errorMessage = 'Please add at least two matching pairs.';
            }
        }
        
        if (!isValid) {
            alert(errorMessage);
            return;
        }
        
        form.submit();
    }

    // Initialize
    console.log('=== Initializing Form ===');
    handleEditMode();
    
    if (questionType && answerFields) {
        console.log('Setting up event listeners...');
        questionType.addEventListener('change', function() {
            console.log('Question type changed to:', questionType.value);
            updateAnswerFields();
        });
        
        console.log('Calling initial updateAnswerFields...');
        updateAnswerFields(); // Call initially to set up fields
    } else {
        console.error('Missing required elements - cannot initialize form');
        if (!questionType) console.error('Question type dropdown not found');
        if (!answerFields) console.error('Answer fields container not found');
    }
    
    // Form validation
    if (form) {
        form.addEventListener('submit', validateForm);
    }

    console.log('=== Form Initialization Complete ===');
}); 