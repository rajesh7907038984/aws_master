// Question form handling
document.addEventListener('DOMContentLoaded', function() {
    console.log("DOM fully loaded");
    
    // Add event delegation for question actions
    const questionsList = document.getElementById('questionsList');
    if (questionsList) {
        questionsList.addEventListener('click', function(e) {
            const target = e.target;
            
            // Find the closest button if clicked on SVG or path
            const actionButton = target.closest('button');
            if (!actionButton) return;
            
            // Get the question ID from the data attribute
            const questionId = actionButton.dataset.questionId;
            if (!questionId) return;
            
            // Handle edit action
            if (actionButton.classList.contains('edit-question')) {
                e.preventDefault();
                editQuestion(questionId);
            }
            
            // Handle delete action
            if (actionButton.classList.contains('delete-question')) {
                e.preventDefault();
                deleteQuestion(questionId);
            }
        });
    }
    
    // Get CSRF token once and store it
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
    if (!csrfToken) {
        console.error('CSRF token not found!');
    }

    // Get form elements
    const questionFormContainer = document.getElementById('questionFormContainer');
    const questionForm = document.getElementById('inlineQuestionForm');
    const questionTypeSelect = document.getElementById('question_type');
    const optionsContainer = document.getElementById('optionsContainer');

    // Initialize form submission handler
    if (questionForm) {
        questionForm.addEventListener('submit', submitQuestionForm);
    }

    // Toggle question form visibility
    window.toggleQuestionForm = function() {
        console.log('Toggle question form called');
        const formContainer = document.getElementById('questionFormContainer');
        if (!formContainer) {
            console.error('Question form container not found');
            return;
        }
        
        const isHidden = formContainer.classList.contains('hidden');
        console.log('Form is currently hidden:', isHidden);
        
        if (isHidden) {
            // Show the form
            formContainer.classList.remove('hidden');
            // Reset form
            const form = document.getElementById('inlineQuestionForm');
            if (form) {
                form.reset();
                const questionType = document.getElementById('question_type');
                if (questionType) {
                    questionType.value = '';
                    const typeHint = document.getElementById('question_type_hint');
                    if (typeHint) {
                        typeHint.textContent = 'Select the type of question you want to create';
                    }
                }
            }
            // Hide all dynamic fields
            const dynamicFields = document.querySelectorAll('.dynamic-field');
            dynamicFields.forEach(field => field.classList.add('hidden'));
            
            // Clear options container
            if (optionsContainer) {
                optionsContainer.innerHTML = '';
            }
            
            // Scroll to form
            formContainer.scrollIntoView({ behavior: 'smooth' });
        } else {
            // Hide the form
            formContainer.classList.add('hidden');
        }
    };

    // Handle question type changes
    window.toggleQuestionTypeFields = function() {
        const questionType = questionTypeSelect?.value;
        console.log('Question type changed to:', questionType);
        
        // Hide all dynamic fields first
        const dynamicFields = document.querySelectorAll('.dynamic-field');
        dynamicFields.forEach(field => field.classList.add('hidden'));
        
        // Show appropriate container based on question type
        if (questionType) {
            switch(questionType) {
                case 'multiple_choice':
                case 'multiple_select':
                    document.getElementById('answerOptionsContainer').classList.remove('hidden');
                    setupMultipleChoiceOptions(questionType === 'multiple_select');
                    break;
                case 'true_false':
                    document.getElementById('answerOptionsContainer').classList.remove('hidden');
                    setupTrueFalseOptions();
                    break;
                case 'fill_blank':
                    document.getElementById('fillBlankContainer').classList.remove('hidden');
                    setupFillBlankField();
                    break;
                case 'multi_blank':
                    document.getElementById('multiBlankContainer').classList.remove('hidden');
                    setupMultiBlankFields();
                    break;
                case 'matching':
                    document.getElementById('matchingContainer').classList.remove('hidden');
                    setupMatchingFields();
                    break;
            }
        }
    };

    // Setup multiple choice/select options
    window.setupMultipleChoiceOptions = function(isMultiSelect = false) {
        if (!optionsContainer) return;
        
        console.log('Setting up multiple choice options, isMultiSelect:', isMultiSelect);
        optionsContainer.innerHTML = '';
        
        // Add initial options
        addOption('', false, isMultiSelect);
        addOption('', false, isMultiSelect);
        
        // Add option button
        const addButton = document.createElement('button');
        addButton.type = 'button';
        addButton.className = 'mt-4 px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600 transition-colors';
        addButton.textContent = 'Add Option';
        addButton.onclick = () => addOption('', false, isMultiSelect);
        
        const buttonContainer = document.getElementById('optionButtons');
        if (buttonContainer) {
            buttonContainer.innerHTML = '';
            buttonContainer.appendChild(addButton);
        }
        
        // Update the hint text based on question type
        const typeHint = document.getElementById('question_type_hint');
        if (typeHint) {
            typeHint.textContent = isMultiSelect ? 
                'Students can select multiple correct answers' : 
                'Students must select exactly one correct answer';
        }
    };

    // Add option function
    window.addOption = function(text = '', isCorrect = false, isMultiSelect = false) {
        const optionDiv = document.createElement('div');
        optionDiv.className = 'flex items-center space-x-4 mb-4';
        
        const optionCount = optionsContainer.children.length;
        
        const input = document.createElement('input');
        input.type = 'text';
        input.name = 'option_text[]';
        input.className = 'flex-1 rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm';
        input.value = text;
        input.placeholder = 'Enter option text';
        input.required = true;
        
        const correctInput = document.createElement('input');
        correctInput.type = isMultiSelect ? 'checkbox' : 'radio';
        correctInput.name = isMultiSelect ? 'correct_options[]' : 'correct_option';
        correctInput.value = optionCount.toString();
        correctInput.className = `h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 ${isMultiSelect ? 'rounded' : 'rounded-full'}`;
        correctInput.checked = isCorrect;
        
        const label = document.createElement('label');
        label.className = 'text-sm text-gray-700 flex items-center space-x-2';
        label.appendChild(correctInput);
        const span = document.createElement('span');
        span.textContent = 'Correct';
        label.appendChild(span);
        
        const deleteBtn = document.createElement('button');
        deleteBtn.type = 'button';
        deleteBtn.className = 'text-red-600 hover:text-red-700';
        deleteBtn.innerHTML = '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>';
        deleteBtn.onclick = function() {
            optionDiv.remove();
            // Update the values of remaining inputs
            const inputs = optionsContainer.querySelectorAll('input[type="radio"], input[type="checkbox"]');
            inputs.forEach((input, index) => {
                input.value = index.toString();
            });
        };
        
        optionDiv.appendChild(input);
        optionDiv.appendChild(label);
        optionDiv.appendChild(deleteBtn);
        
        optionsContainer.appendChild(optionDiv);
        
        // For multiple choice, ensure only one option is selected as correct
        if (!isMultiSelect) {
            correctInput.addEventListener('change', function() {
                if (this.checked) {
                    // Uncheck all other radio buttons
                    optionsContainer.querySelectorAll('input[type="radio"]').forEach(radio => {
                        if (radio !== this) {
                            radio.checked = false;
                        }
                    });
                }
            });
        }
    };

    // Setup true/false options
    window.setupTrueFalseOptions = function() {
        if (!optionsContainer) return;
        
        optionsContainer.innerHTML = '';
        
        // Create True option
        const trueDiv = document.createElement('div');
        trueDiv.className = 'flex items-center space-x-4 mb-4';
        
        const trueLabel = document.createElement('label');
        trueLabel.className = 'flex items-center space-x-3 flex-1';
        
        const trueInput = document.createElement('input');
        trueInput.type = 'text';
        trueInput.name = 'option_text[]';
        trueInput.value = 'True';
        trueInput.className = 'hidden';
        
        const trueRadio = document.createElement('input');
        trueRadio.type = 'radio';
        trueRadio.name = 'correct_option';
        trueRadio.value = '0';
        trueRadio.className = 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded-full';
        
        const trueText = document.createElement('span');
        trueText.textContent = 'True';
        trueText.className = 'text-gray-700';
        
        trueLabel.appendChild(trueRadio);
        trueLabel.appendChild(trueText);
        trueLabel.appendChild(trueInput);
        trueDiv.appendChild(trueLabel);
        
        // Create False option
        const falseDiv = document.createElement('div');
        falseDiv.className = 'flex items-center space-x-4 mb-4';
        
        const falseLabel = document.createElement('label');
        falseLabel.className = 'flex items-center space-x-3 flex-1';
        
        const falseInput = document.createElement('input');
        falseInput.type = 'text';
        falseInput.name = 'option_text[]';
        falseInput.value = 'False';
        falseInput.className = 'hidden';
        
        const falseRadio = document.createElement('input');
        falseRadio.type = 'radio';
        falseRadio.name = 'correct_option';
        falseRadio.value = '1';
        falseRadio.className = 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded-full';
        
        const falseText = document.createElement('span');
        falseText.textContent = 'False';
        falseText.className = 'text-gray-700';
        
        falseLabel.appendChild(falseRadio);
        falseLabel.appendChild(falseText);
        falseLabel.appendChild(falseInput);
        falseDiv.appendChild(falseLabel);
        
        optionsContainer.appendChild(trueDiv);
        optionsContainer.appendChild(falseDiv);
        
        // Update the hint text
        const typeHint = document.getElementById('question_type_hint');
        if (typeHint) {
            typeHint.textContent = 'Select whether True or False is the correct answer';
        }
    };

    // Setup fill in blank field
    window.setupFillBlankField = function() {
        const container = document.getElementById('fillBlankAnswerContainer');
        if (!container) return;
        
        container.innerHTML = `
            <div class="space-y-4">
                <input type="text" 
                       name="blank_answer"
                       class="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
                       placeholder="Enter the correct answer"
                       required>
                <p class="text-sm text-gray-500">Students must enter this exact answer to be marked correct</p>
            </div>
        `;
    };

    // Setup multiple blanks fields
    window.setupMultiBlankFields = function() {
        const container = document.getElementById('blanksContainer');
        if (!container) return;
        
        container.innerHTML = '';
        addBlank(); // Add first blank
        addBlank(); // Add second blank
    };

    // Add blank function
    window.addBlank = function() {
        const container = document.getElementById('blanksContainer');
        if (!container) return;
        
        const blankDiv = document.createElement('div');
        blankDiv.className = 'flex items-center space-x-4 mb-4';
        
        const input = document.createElement('input');
        input.type = 'text';
        input.name = 'blank_answers[]';
        input.className = 'flex-1 rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm';
        input.placeholder = 'Enter correct answer for blank';
        input.required = true;
        
        const deleteBtn = document.createElement('button');
        deleteBtn.type = 'button';
        deleteBtn.className = 'text-red-600 hover:text-red-700';
        deleteBtn.innerHTML = '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>';
        deleteBtn.onclick = () => blankDiv.remove();
        
        blankDiv.appendChild(input);
        blankDiv.appendChild(deleteBtn);
        
        container.appendChild(blankDiv);
    };

    // Setup matching fields
    window.setupMatchingFields = function() {
        const container = document.getElementById('matchingPairsContainer');
        if (!container) return;
        
        container.innerHTML = '';
        addMatchingPair(); // Add first pair
        addMatchingPair(); // Add second pair
    };

    // Add matching pair function
    window.addMatchingPair = function() {
        const container = document.getElementById('matchingPairsContainer');
        if (!container) return;
        
        const pairDiv = document.createElement('div');
        pairDiv.className = 'flex items-center space-x-4 mb-4';
        
        const leftInput = document.createElement('input');
        leftInput.type = 'text';
        leftInput.name = 'pair_lefts[]';
        leftInput.className = 'flex-1 rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm';
        leftInput.placeholder = 'Left item';
        leftInput.required = true;
        
        const rightInput = document.createElement('input');
        rightInput.type = 'text';
        rightInput.name = 'pair_rights[]';
        rightInput.className = 'flex-1 rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm';
        rightInput.placeholder = 'Right item';
        rightInput.required = true;
        
        const deleteBtn = document.createElement('button');
        deleteBtn.type = 'button';
        deleteBtn.className = 'text-red-600 hover:text-red-700';
        deleteBtn.innerHTML = '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>';
        deleteBtn.onclick = () => pairDiv.remove();
        
        pairDiv.appendChild(leftInput);
        pairDiv.appendChild(rightInput);
        pairDiv.appendChild(deleteBtn);
        
        container.appendChild(pairDiv);
    };

    // Initialize question type fields if form is visible
    if (questionTypeSelect && !questionFormContainer?.classList.contains('hidden')) {
        toggleQuestionTypeFields();
    }

    // Set up question type change handler
    if (questionTypeSelect) {
        questionTypeSelect.addEventListener('change', toggleQuestionTypeFields);
    }

    function validateQuestionForm() {
        let isValid = true;
        const questionType = document.getElementById('question_type').value;
        const questionText = document.getElementById('question_text').value.trim();
        const points = document.getElementById('question_points').value;

        // Reset error messages
        document.querySelectorAll('[id$="_error"]').forEach(el => {
            el.classList.add('hidden');
        });

        // Validate question type
        if (!questionType) {
            document.getElementById('question_type_error').textContent = 'Please select a question type';
            document.getElementById('question_type_error').classList.remove('hidden');
            isValid = false;
        }

        // Validate question text
        if (!questionText) {
            document.getElementById('question_text_error').textContent = 'Please enter a question text';
            document.getElementById('question_text_error').classList.remove('hidden');
            isValid = false;
        }

        // Validate points
        if (!points || points < 1) {
            document.getElementById('question_points_error').textContent = 'Points must be at least 1';
            document.getElementById('question_points_error').classList.remove('hidden');
            isValid = false;
        }

        // Validate options based on question type
        if (['multiple_choice', 'multiple_select', 'true_false'].includes(questionType)) {
            const options = document.querySelectorAll('input[name="options[]"]');
            if (options.length < 2) {
                showError('Questions must have at least two options');
                isValid = false;
            }

            // Check if at least one option is marked as correct
            const hasCorrectOption = Array.from(options).some(option => 
                option.closest('.option-container').querySelector('input[type="checkbox"]').checked
            );
            if (!hasCorrectOption) {
                showError('At least one option must be marked as correct');
                isValid = false;
            }
        }

        return isValid;
    }

    function showError(message) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'p-4 mb-4 bg-red-800 text-red-100 rounded-lg';
        messageDiv.textContent = message;
        
        const form = document.getElementById('inlineQuestionForm');
        form.insertAdjacentElement('beforebegin', messageDiv);
        
        // Remove message after 5 seconds
        setTimeout(() => messageDiv.remove(), 5000);
    }

    function showSuccess(message) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'p-4 mb-4 bg-green-800 text-green-100 rounded-lg';
        messageDiv.textContent = message;
        
        const form = document.getElementById('inlineQuestionForm');
        form.insertAdjacentElement('beforebegin', messageDiv);
        
        // Remove message after 5 seconds
        setTimeout(() => messageDiv.remove(), 5000);
    }

    async function submitQuestionForm(event) {
        event.preventDefault();
        
        if (!validateQuestionForm()) {
            return;
        }

        const form = event.target;
        
        try {
            // Use the enhanced LMS form submission
            const result = await window.submitLMSForm(form, {
                expectJson: true,
                successMessage: 'Question added successfully!'
            });

            if (result.success) {
                form.reset();
                toggleQuestionForm();
                updateQuestionsList();
                
                // Show success message
                if (window.LMS && window.LMS.ErrorHandler) {
                    window.LMS.ErrorHandler.showSuccess('Question added successfully!');
                } else {
                    showSuccess('Question added successfully!');
                }
            }
        } catch (error) {
            // Error already handled by LMS error handler
            console.error('Question submission error:', error);
        }
    }

    // Helper function to create question HTML
    function createQuestionHTML(question) {
        return `
            <div class="bg-white rounded-lg p-4 shadow-sm border border-gray-200" id="question_${question.id}">
                <div class="flex justify-between items-start">
                    <div class="flex-1">
                        <p class="text-gray-900">${question.question_text}</p>
                        <div class="mt-2 text-sm text-gray-500">
                            Type: ${question.question_type_display} | Points: ${question.points}
                        </div>
                    </div>
                    <div class="ml-4 flex space-x-2">
                        <button onclick="editQuestion(${question.id})" class="text-blue-600 hover:text-blue-700">
                            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>
                            </svg>
                        </button>
                        <button onclick="deleteQuestion(${question.id})" class="text-red-600 hover:text-red-700">
                            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
                            </svg>
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    function populateEditForm(question) {
        // Set form values
        document.getElementById('edit_question_id').value = question.id;
        document.getElementById('edit_question_text').value = question.question_text;
        document.getElementById('edit_question_type').value = question.question_type_display || question.question_type;
        document.getElementById('edit_question_points').value = question.points;
        
        // Handle options for multiple choice, multiple select, and true/false questions
        const editOptionsContainer = document.getElementById('editOptionsContainer');
        const editOptionsList = document.getElementById('editOptionsList');
        
        if (question.question_type === 'multiple_choice' || 
            question.question_type === 'true_false' || 
            question.question_type === 'multiple_select') {
            
            editOptionsContainer.classList.remove('hidden');
            editOptionsList.innerHTML = '';
            
            const isMultiSelect = question.question_type === 'multiple_select';
            
            // Add options
            if (question.answers) {
                question.answers.forEach((answer, index) => {
                    addOptionToEditForm(answer.answer_text, answer.is_correct, answer.id, isMultiSelect);
                });
            } else if (question.options) {
                question.options.forEach((option, index) => {
                    addOptionToEditForm(option.text, option.is_correct, option.id, isMultiSelect);
                });
            }
            
            // Add "Add Option" button for multiple choice and multiple select
            if (question.question_type !== 'true_false') {
                const addButton = document.createElement('button');
                addButton.type = 'button';
                addButton.className = 'mt-4 px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600 transition-colors';
                addButton.textContent = 'Add Option';
                addButton.onclick = () => addOptionToEditForm('', false, null, isMultiSelect);
                editOptionsContainer.appendChild(addButton);
            }
        } else if (question.question_type === 'fill_blank') {
            // Handle fill in the blank questions
            editOptionsContainer.classList.remove('hidden');
            editOptionsList.innerHTML = '';
            
            // Create input container
            const inputContainer = document.createElement('div');
            inputContainer.className = 'space-y-4';
            
            // Create answer input
            const answerInput = document.createElement('input');
            answerInput.type = 'text';
            answerInput.name = 'edit_blank_answer';
            answerInput.className = 'w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm';
            answerInput.placeholder = 'Enter the correct answer';
            answerInput.required = true;
            
            // Set the answer value from the question data
            if (question.answers && question.answers.length > 0) {
                answerInput.value = question.answers[0].answer_text;
            } else if (question.blank_answer) {
                answerInput.value = question.blank_answer;
            }
            
            // Add help text
            const helpText = document.createElement('p');
            helpText.className = 'text-sm text-gray-500';
            helpText.textContent = 'Students must enter this exact answer to be marked correct';
            
            // Add elements to container
            inputContainer.appendChild(answerInput);
            inputContainer.appendChild(helpText);
            editOptionsList.appendChild(inputContainer);
        } else if (question.question_type === 'multi_blank') {
            // Handle multiple blanks questions
            editOptionsContainer.classList.remove('hidden');
            editOptionsList.innerHTML = '';
            
            // Create container for blanks
            const blanksContainer = document.createElement('div');
            blanksContainer.className = 'space-y-4';
            blanksContainer.id = 'editBlanksContainer';
            
            // Add existing answers
            if (question.answers) {
                question.answers.forEach(answer => {
                    addBlankToEditForm(answer.answer_text);
                });
            }
            
            // Add "Add Blank" button
            const addButton = document.createElement('button');
            addButton.type = 'button';
            addButton.className = 'mt-4 px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600 transition-colors';
            addButton.textContent = 'Add Blank';
            addButton.onclick = () => addBlankToEditForm('');
            
            editOptionsList.appendChild(blanksContainer);
            editOptionsContainer.appendChild(addButton);
        } else if (question.question_type === 'matching') {
            // Handle matching questions
            editOptionsContainer.classList.remove('hidden');
            editOptionsList.innerHTML = '';
            
            // Create container for matching pairs
            const pairsContainer = document.createElement('div');
            pairsContainer.className = 'space-y-4';
            pairsContainer.id = 'editMatchingPairsContainer';
            
            // Add existing pairs
            if (question.pairs) {
                question.pairs.forEach(pair => {
                    addMatchingPairToEditForm(pair.left_text, pair.right_text);
                });
            }
            
            // Add "Add Pair" button
            const addButton = document.createElement('button');
            addButton.type = 'button';
            addButton.className = 'mt-4 px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600 transition-colors';
            addButton.textContent = 'Add Matching Pair';
            addButton.onclick = () => addMatchingPairToEditForm('', '');
            
            editOptionsList.appendChild(pairsContainer);
            editOptionsContainer.appendChild(addButton);
        } else {
            editOptionsContainer.classList.add('hidden');
        }
    }

    function addOptionToEditForm(text, isCorrect, optionId, isMultiSelect = false) {
        const editOptionsList = document.getElementById('editOptionsList');
        const optionCount = editOptionsList.children.length;
        
        const optionDiv = document.createElement('div');
        optionDiv.className = 'flex items-center space-x-2';
        
        // For true/false questions, make the inputs readonly
        const isReadOnly = text === 'True' || text === 'False';
        
        // Create the correct answer input (checkbox or radio)
        const correctInput = document.createElement('input');
        correctInput.type = isMultiSelect ? 'checkbox' : 'radio';
        correctInput.name = isMultiSelect ? 'edit_correct_options[]' : 'edit_correct_option';
        correctInput.value = optionCount;
        correctInput.className = `h-4 w-4 text-blue-600 border-gray-300 focus:ring-blue-500 ${isMultiSelect ? 'rounded' : 'rounded-full'}`;
        correctInput.checked = isCorrect;
        
        // Create the text input
        const textInput = document.createElement('input');
        textInput.type = 'text';
        textInput.name = 'edit_options[]';
        textInput.value = text;
        textInput.readOnly = isReadOnly;
        textInput.className = `flex-grow px-3 py-2 ${isReadOnly ? 'bg-gray-100' : 'bg-white'} border border-gray-300 rounded-md text-gray-700 shadow-sm focus:border-blue-500 focus:ring-blue-500`;
        
        // Create the hidden input for option ID
        const hiddenInput = document.createElement('input');
        hiddenInput.type = 'hidden';
        hiddenInput.name = 'edit_option_ids[]';
        hiddenInput.value = optionId || '';
        
        // Create the label for correct/incorrect
        const label = document.createElement('label');
        label.className = 'flex items-center space-x-2 min-w-[80px]';
        label.appendChild(correctInput);
        const span = document.createElement('span');
        span.textContent = 'Correct';
        span.className = 'text-sm text-gray-700';
        label.appendChild(span);
        
        // Add all elements to the option div
        optionDiv.appendChild(textInput);
        optionDiv.appendChild(label);
        optionDiv.appendChild(hiddenInput);
        
        // Add remove button if not a true/false option and not the first two options
        if (!isReadOnly && optionCount > 1) {
            const removeButton = document.createElement('button');
            removeButton.type = 'button';
            removeButton.className = 'px-2 py-1 bg-red-500 text-white rounded text-sm hover:bg-red-600';
            removeButton.textContent = 'Remove';
            removeButton.onclick = function() {
                optionDiv.remove();
                // Update the values of remaining inputs
                editOptionsList.querySelectorAll('input[type="radio"], input[type="checkbox"]').forEach((input, index) => {
                    input.value = index.toString();
                });
            };
            optionDiv.appendChild(removeButton);
        }
        
        editOptionsList.appendChild(optionDiv);
        
        // For multiple choice (not multiple select), ensure only one option is selected as correct
        if (!isMultiSelect) {
            correctInput.addEventListener('change', function() {
                if (this.checked) {
                    // Uncheck all other radio buttons
                    editOptionsList.querySelectorAll('input[type="radio"]').forEach(radio => {
                        if (radio !== this) {
                            radio.checked = false;
                        }
                    });
                }
            });
        }
    }

    function addBlankToEditForm(answer = '') {
        const container = document.getElementById('editBlanksContainer');
        if (!container) return;
        
        const blankDiv = document.createElement('div');
        blankDiv.className = 'flex items-center space-x-4 mb-4';
        
        const input = document.createElement('input');
        input.type = 'text';
        input.name = 'edit_blank_answers[]';
        input.className = 'flex-1 rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm';
        input.placeholder = 'Enter correct answer for blank';
        input.value = answer;
        input.required = true;
        
        const deleteBtn = document.createElement('button');
        deleteBtn.type = 'button';
        deleteBtn.className = 'text-red-600 hover:text-red-700';
        deleteBtn.innerHTML = '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>';
        deleteBtn.onclick = () => blankDiv.remove();
        
        blankDiv.appendChild(input);
        blankDiv.appendChild(deleteBtn);
        
        container.appendChild(blankDiv);
    }

    function addMatchingPairToEditForm(leftText = '', rightText = '') {
        const container = document.getElementById('editMatchingPairsContainer');
        if (!container) return;
        
        const pairDiv = document.createElement('div');
        pairDiv.className = 'flex items-center space-x-4 mb-4';
        
        const leftInput = document.createElement('input');
        leftInput.type = 'text';
        leftInput.name = 'edit_pair_lefts[]';
        leftInput.className = 'flex-1 rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm';
        leftInput.placeholder = 'Left item';
        leftInput.value = leftText;
        leftInput.required = true;
        
        const rightInput = document.createElement('input');
        rightInput.type = 'text';
        rightInput.name = 'edit_pair_rights[]';
        rightInput.className = 'flex-1 rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm';
        rightInput.placeholder = 'Right item';
        rightInput.value = rightText;
        rightInput.required = true;
        
        const deleteBtn = document.createElement('button');
        deleteBtn.type = 'button';
        deleteBtn.className = 'text-red-600 hover:text-red-700';
        deleteBtn.innerHTML = '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>';
        deleteBtn.onclick = () => pairDiv.remove();
        
        pairDiv.appendChild(leftInput);
        pairDiv.appendChild(rightInput);
        pairDiv.appendChild(deleteBtn);
        
        container.appendChild(pairDiv);
    }

    function updateQuestion() {
        const form = document.getElementById('editQuestionForm');
        const formData = new FormData(form);
        const questionId = document.getElementById('edit_question_id').value;
        const questionType = document.getElementById('edit_question_type').value;
        
        // Show loading
        const submitBtn = form.querySelector('button[type="button"]:last-child');
        const originalBtnText = submitBtn.innerHTML;
        submitBtn.innerHTML = 'Updating...';
        submitBtn.disabled = true;
        
        // Handle different question types
        try {
            if (questionType === 'fill_blank') {
                const blankAnswer = form.querySelector('input[name="edit_blank_answer"]')?.value.trim();
                if (!blankAnswer) {
                    throw new Error('Please provide an answer for the blank');
                }
                formData.append('blank_answer', blankAnswer);
            } else if (questionType === 'multi_blank') {
                const blankAnswers = [];
                const blankInputs = form.querySelectorAll('input[name="edit_blank_answers[]"]');
                
                blankInputs.forEach((input, index) => {
                    const answer = input.value.trim();
                    if (answer) {
                        blankAnswers.push(answer);
                        formData.append('blank_answers[]', answer);
                    }
                });
                
                if (blankAnswers.length < 1) {
                    throw new Error('Please add at least one blank answer');
                }
            } else if (questionType === 'matching') {
                const pairs = [];
                const leftInputs = form.querySelectorAll('input[name="edit_pair_lefts[]"]');
                const rightInputs = form.querySelectorAll('input[name="edit_pair_rights[]"]');
                
                leftInputs.forEach((input, index) => {
                    const leftText = input.value.trim();
                    const rightText = rightInputs[index]?.value.trim();
                    
                    if (leftText && rightText) {
                        pairs.push({ left: leftText, right: rightText });
                        formData.append('pair_lefts[]', leftText);
                        formData.append('pair_rights[]', rightText);
                    }
                });
                
                if (pairs.length < 2) {
                    throw new Error('Please add at least two matching pairs');
                }
            } else if (questionType.toLowerCase().includes('multiple select') || 
                      questionType === 'multiple_choice' || 
                      questionType === 'true_false') {
                // Get all options and their correct status
                const options = [];
                const isMultiSelect = questionType.toLowerCase().includes('multiple select');
                
                form.querySelectorAll('input[name="edit_options[]"]').forEach((input, index) => {
                    if (input.value.trim()) {
                        options.push(input.value.trim());
                        formData.append('options[]', input.value.trim());
                        
                        if (isMultiSelect) {
                            // For multiple select, check if this option is selected
                            const isChecked = form.querySelector(`input[name="edit_correct_options[]"][value="${index}"]`)?.checked;
                            formData.append('correct_options[]', isChecked ? '1' : '0');
                        }
                    }
                });
                
                // For single select questions, get the correct option
                if (!isMultiSelect) {
                    const correctOption = form.querySelector('input[name="edit_correct_option"]:checked');
                    if (correctOption) {
                        formData.append('correct_option', correctOption.value);
                    }
                }
            }
        } catch (error) {
            const errorMsg = document.createElement('div');
            errorMsg.className = 'p-4 mb-4 bg-red-800 text-red-100 rounded-lg';
            errorMsg.textContent = error.message;
            form.insertAdjacentElement('beforebegin', errorMsg);
            
            // Remove error message after 5 seconds
            setTimeout(() => {
                errorMsg.remove();
            }, 5000);
            
            // Restore button state
            submitBtn.innerHTML = originalBtnText;
            submitBtn.disabled = false;
            return;
        }
        
        fetch(`/quiz/question/${questionId}/edit/`, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            }
        })
        .then(response => {
            if (!response.ok) {
                return response.text().then(text => {
                    try {
                        const data = JSON.parse(text);
                        throw new Error(data.error || 'Error updating question');
                    } catch (e) {
                        throw new Error(`Server error: ${text}`);
                    }
                });
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                // Update the question in the UI
                const questionElement = document.getElementById(`question_${questionId}`);
                if (questionElement) {
                    const newQuestionHTML = createQuestionHTML(data.question);
                    questionElement.outerHTML = newQuestionHTML;
                }
                
                // Close modal and show success message
                closeEditModal();
                
                const successMsg = document.createElement('div');
                successMsg.className = 'p-4 mb-4 bg-green-800 text-green-100 rounded-lg';
                successMsg.textContent = 'Question updated successfully!';
                document.querySelector('.space-y-4').insertAdjacentElement('beforebegin', successMsg);
                
                // Remove success message after 3 seconds
                setTimeout(() => {
                    successMsg.remove();
                }, 3000);
            } else {
                throw new Error(data.error || 'Error updating question');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            const errorMsg = document.createElement('div');
            errorMsg.className = 'p-4 mb-4 bg-red-800 text-red-100 rounded-lg';
            errorMsg.textContent = error.message;
            form.insertAdjacentElement('beforebegin', errorMsg);
            
            // Remove error message after 5 seconds
            setTimeout(() => {
                errorMsg.remove();
            }, 5000);
        })
        .finally(() => {
            // Restore button state
            submitBtn.innerHTML = originalBtnText;
            submitBtn.disabled = false;
        });
    }

    function editQuestion(questionId) {
        console.log("Editing question:", questionId);
        
        // Show loading state
        const modal = document.getElementById('editQuestionModal');
        if (!modal) {
            console.error('Edit question modal not found!');
            return;
        }
        
        modal.classList.remove('hidden');
        
        // Get the submit button
        const submitButton = modal.querySelector('button[onclick="updateQuestion()"]');
        if (!submitButton) {
            console.error('Submit button not found in modal!');
            return;
        }
        
        submitButton.disabled = true;
        submitButton.innerHTML = '<svg class="animate-spin h-5 w-5 mr-2" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> Loading...';
        
        // Clear any existing options
        const editOptionsList = document.getElementById('editOptionsList');
        if (editOptionsList) {
            editOptionsList.innerHTML = '';
        }
        
        // Get CSRF token
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        if (!csrfToken) {
            console.error('CSRF token not found!');
            alert('Error: CSRF token not found. Please refresh the page and try again.');
            return;
        }
        
        // Fetch question data
        fetch(`/quiz/question/${questionId}/`, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': csrfToken,
                'Accept': 'application/json'
            }
        })
        .then(response => {
            if (!response.ok) {
                return response.text().then(text => {
                    try {
                        const data = JSON.parse(text);
                        throw new Error(data.error || 'Error fetching question data');
                    } catch (e) {
                        throw new Error(`Server error: ${text}`);
                    }
                });
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                populateEditForm(data.question);
                // Enable submit button after data is loaded
                submitButton.disabled = false;
                submitButton.innerHTML = 'Update Question';
            } else {
                throw new Error(data.error || 'Error fetching question data');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Error fetching question data. Please try again.');
            closeEditModal();
        });
    }

    function deleteQuestion(questionId) {
        if (confirm('Are you sure you want to delete this question? This action cannot be undone.')) {
            // Get CSRF token
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
            if (!csrfToken) {
                console.error('CSRF token not found!');
                alert('Error: CSRF token not found. Please refresh the page and try again.');
                return;
            }
            
            // Show loading state
            const questionElement = document.getElementById(`question_${questionId}`);
            if (!questionElement) {
                console.error('Question element not found!');
                return;
            }
            
            const originalContent = questionElement.innerHTML;
            questionElement.innerHTML = '<div class="flex justify-center items-center p-4"><svg class="animate-spin h-5 w-5 text-white" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg></div>';
            
            // Send delete request
            fetch(`/quiz/question/${questionId}/delete/`, {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': csrfToken
                }
            })
            .then(response => {
                if (!response.ok) {
                    return response.text().then(text => {
                        try {
                            const data = JSON.parse(text);
                            throw new Error(data.error || 'Error deleting question');
                        } catch (e) {
                            throw new Error(`Server error: ${text}`);
                        }
                    });
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    // Remove the question element
                    questionElement.remove();
                    
                    // Show success message
                    const successMsg = document.createElement('div');
                    successMsg.className = 'p-4 mb-4 bg-green-800 text-green-100 rounded-lg';
                    successMsg.textContent = 'Question deleted successfully!';
                    document.getElementById('questionsList').insertAdjacentElement('beforebegin', successMsg);
                    
                    // Remove success message after 3 seconds
                    setTimeout(() => {
                        successMsg.remove();
                    }, 3000);
                    
                    // Check if there are any questions left
                    const questionsList = document.getElementById('questionsList');
                    if (questionsList.children.length === 0) {
                        questionsList.innerHTML = `
                            <div class="text-center py-8">
                                <div class="text-gray-500">No questions have been added to this quiz yet.</div>
                                <a href="{% url 'quiz:edit_quiz' quiz.id %}" 
                                   class="mt-4 inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700">
                                    Add Questions
                                </a>
                            </div>
                        `;
                    }
                } else {
                    throw new Error(data.error || 'Error deleting question');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                // Restore original content
                questionElement.innerHTML = originalContent;
                
                // Show error message
                const errorMsg = document.createElement('div');
                errorMsg.className = 'p-4 mb-4 bg-red-800 text-red-100 rounded-lg';
                errorMsg.textContent = error.message || 'Error deleting question. Please try again.';
                document.getElementById('questionsList').insertAdjacentElement('beforebegin', errorMsg);
                
                // Remove error message after 5 seconds
                setTimeout(() => {
                    errorMsg.remove();
                }, 5000);
            });
        }
    }
});