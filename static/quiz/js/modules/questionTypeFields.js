// Question Type Fields Module
const QuestionTypeFields = {
    init() {
        this.dynamicFields = document.getElementById('dynamicFields');
    },

    toggle(questionType) {
        console.log('Toggling fields for question type:', questionType);
        if (!this.dynamicFields) {
            console.error('Dynamic fields container not found');
            return;
        }

        this.dynamicFields.innerHTML = '';
        
        switch(questionType) {
            case 'multiple_choice':
                this.createMultipleChoiceFields();
                break;
            case 'multiple_select':
                this.createMultipleSelectFields();
                break;
            case 'true_false':
                this.createTrueFalseFields();
                break;
            case 'fill_blank':
                this.createFillBlankFields();
                break;
            case 'multi_blank':
                this.createMultiBlankFields();
                break;
            case 'matching':
                this.createMatchingFields();
                break;
            default:
                console.log('No specific fields needed for this question type');
        }
    },

    createMultipleChoiceFields() {
        const template = `
            <div class="space-y-4 mt-4">
                <div class="flex items-center space-x-2">
                    <button type="button" id="addOptionBtn" class="px-3 py-1 bg-blue-500 text-white rounded hover:bg-blue-600">
                        Add Option
                    </button>
                </div>
                <div id="optionsContainer" class="space-y-2"></div>
            </div>
        `;

        this.dynamicFields.innerHTML = template;
        this.initializeOptionHandlers();
        this.addOption(); // Add first option by default
    },

    createMultipleSelectFields() {
        const template = `
            <div class="space-y-4 mt-4">
                <div class="flex items-center space-x-2">
                    <button type="button" id="addOptionBtn" class="px-3 py-1 bg-blue-500 text-white rounded hover:bg-blue-600">
                        Add Option
                    </button>
                </div>
                <div id="optionsContainer" class="space-y-2"></div>
            </div>
        `;

        this.dynamicFields.innerHTML = template;
        this.initializeOptionHandlers('checkbox');
        this.addOption('checkbox'); // Add first option by default
    },

    createTrueFalseFields() {
        const template = `
            <div class="space-y-4 mt-4">
                <div class="flex items-center space-x-4">
                    <label class="inline-flex items-center">
                        <input type="radio" name="correct_answer" value="true" class="form-radio" required>
                        <span class="ml-2">True</span>
                    </label>
                    <label class="inline-flex items-center">
                        <input type="radio" name="correct_answer" value="false" class="form-radio" required>
                        <span class="ml-2">False</span>
                    </label>
                </div>
            </div>
        `;

        this.dynamicFields.innerHTML = template;
    },

    createFillBlankFields() {
        const template = `
            <div class="space-y-4 mt-4">
                <div class="flex flex-col">
                    <label class="text-sm font-medium text-gray-700 mb-2">Correct Answer(s)</label>
                    <div class="space-y-2" id="answersContainer">
                        <div class="flex items-center space-x-2">
                            <input type="text" name="answers[]" required
                                   class="flex-1 rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                                   placeholder="Enter an acceptable answer">
                            <button type="button" class="px-3 py-1 bg-blue-500 text-white rounded hover:bg-blue-600" onclick="QuestionTypeFields.addAnswer()">
                                Add Another Answer
                            </button>
                        </div>
                    </div>
                    <p class="mt-1 text-sm text-gray-500">Add multiple answers if there are different acceptable responses.</p>
                </div>
            </div>
        `;

        this.dynamicFields.innerHTML = template;
    },

    createMultiBlankFields() {
        const template = `
            <div class="space-y-4 mt-4">
                <div class="flex flex-col">
                    <label class="text-sm font-medium text-gray-700 mb-2">Blanks and Their Answers</label>
                    <div class="space-y-4" id="blanksContainer">
                        <div class="flex flex-col space-y-2 p-4 border border-gray-200 rounded-md">
                            <input type="text" name="blank_labels[]" required
                                   class="rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                                   placeholder="Blank label (e.g., 'First blank', 'Capital city')">
                            <div class="space-y-2" id="answers_1">
                                <div class="flex items-center space-x-2">
                                    <input type="text" name="answers_1[]" required
                                           class="flex-1 rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                                           placeholder="Enter an acceptable answer">
                                    <button type="button" class="px-3 py-1 bg-blue-500 text-white rounded hover:bg-blue-600"
                                            onclick="QuestionTypeFields.addAnswerToBlank(1)">
                                        Add Answer
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                    <button type="button" class="mt-2 px-3 py-1 bg-green-500 text-white rounded hover:bg-green-600"
                            onclick="QuestionTypeFields.addBlank()">
                        Add Another Blank
                    </button>
                </div>
            </div>
        `;

        this.dynamicFields.innerHTML = template;
    },

    createMatchingFields() {
        const template = `
            <div class="space-y-4 mt-4">
                <div class="flex flex-col">
                    <label class="text-sm font-medium text-gray-700 mb-2">Matching Pairs</label>
                    <div class="space-y-4" id="pairsContainer">
                        <div class="flex items-center space-x-2">
                            <div class="flex-1">
                                <input type="text" name="prompts[]" required
                                       class="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                                       placeholder="Prompt">
                            </div>
                            <div class="flex-1">
                                <input type="text" name="matches[]" required
                                       class="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                                       placeholder="Match">
                            </div>
                            <button type="button" class="text-red-500 hover:text-red-700">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                                </svg>
                            </button>
                        </div>
                    </div>
                    <button type="button" class="mt-2 px-3 py-1 bg-blue-500 text-white rounded hover:bg-blue-600"
                            onclick="QuestionTypeFields.addMatchingPair()">
                        Add Matching Pair
                    </button>
                </div>
            </div>
        `;

        this.dynamicFields.innerHTML = template;
        this.initializeMatchingHandlers();
    },

    initializeOptionHandlers(inputType = 'radio') {
        const addOptionBtn = document.getElementById('addOptionBtn');
        if (addOptionBtn) {
            addOptionBtn.addEventListener('click', () => this.addOption(inputType));
        }
    },

    addOption(inputType = 'radio') {
        const optionsContainer = document.getElementById('optionsContainer');
        if (!optionsContainer) return;

        const optionCount = optionsContainer.children.length;
        const optionDiv = document.createElement('div');
        optionDiv.className = 'flex items-center space-x-2';
        
        optionDiv.innerHTML = `
            <input type="text" name="option_${optionCount + 1}" required
                   class="flex-1 rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                   placeholder="Option ${optionCount + 1}">
            <input type="${inputType}" name="correct_option" value="${optionCount + 1}" required
                   class="form-${inputType}">
            <button type="button" class="text-red-500 hover:text-red-700">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
            </button>
        `;

        const deleteBtn = optionDiv.querySelector('button');
        deleteBtn.addEventListener('click', () => {
            optionDiv.remove();
            this.updateOptionNumbers();
        });

        optionsContainer.appendChild(optionDiv);
    },

    updateOptionNumbers() {
        const optionsContainer = document.getElementById('optionsContainer');
        if (!optionsContainer) return;

        Array.from(optionsContainer.children).forEach((optionDiv, index) => {
            const input = optionDiv.querySelector('input[type="text"]');
            const radio = optionDiv.querySelector('input[type="radio"], input[type="checkbox"]');
            
            input.name = `option_${index + 1}`;
            input.placeholder = `Option ${index + 1}`;
            radio.value = index + 1;
        });
    },

    addAnswer() {
        const container = document.getElementById('answersContainer');
        if (!container) return;

        const answerDiv = document.createElement('div');
        answerDiv.className = 'flex items-center space-x-2';
        answerDiv.innerHTML = `
            <input type="text" name="answers[]" required
                   class="flex-1 rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                   placeholder="Enter an acceptable answer">
            <button type="button" class="text-red-500 hover:text-red-700">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
            </button>
        `;

        const deleteBtn = answerDiv.querySelector('button');
        deleteBtn.addEventListener('click', () => answerDiv.remove());

        container.appendChild(answerDiv);
    },

    addBlank() {
        const container = document.getElementById('blanksContainer');
        if (!container) return;

        const blankCount = container.children.length + 1;
        const blankDiv = document.createElement('div');
        blankDiv.className = 'flex flex-col space-y-2 p-4 border border-gray-200 rounded-md';
        blankDiv.innerHTML = `
            <div class="flex items-center space-x-2">
                <input type="text" name="blank_labels[]" required
                       class="flex-1 rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                       placeholder="Blank label">
                <button type="button" class="text-red-500 hover:text-red-700">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                    </svg>
                </button>
            </div>
            <div class="space-y-2" id="answers_${blankCount}">
                <div class="flex items-center space-x-2">
                    <input type="text" name="answers_${blankCount}[]" required
                           class="flex-1 rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                           placeholder="Enter an acceptable answer">
                    <button type="button" class="px-3 py-1 bg-blue-500 text-white rounded hover:bg-blue-600"
                            onclick="QuestionTypeFields.addAnswerToBlank(${blankCount})">
                        Add Answer
                    </button>
                </div>
            </div>
        `;

        const deleteBtn = blankDiv.querySelector('button');
        deleteBtn.addEventListener('click', () => blankDiv.remove());

        container.appendChild(blankDiv);
    },

    addAnswerToBlank(blankNumber) {
        const container = document.getElementById(`answers_${blankNumber}`);
        if (!container) return;

        const answerDiv = document.createElement('div');
        answerDiv.className = 'flex items-center space-x-2';
        answerDiv.innerHTML = `
            <input type="text" name="answers_${blankNumber}[]" required
                   class="flex-1 rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                   placeholder="Enter an acceptable answer">
            <button type="button" class="text-red-500 hover:text-red-700">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
            </button>
        `;

        const deleteBtn = answerDiv.querySelector('button');
        deleteBtn.addEventListener('click', () => answerDiv.remove());

        container.appendChild(answerDiv);
    },

    addMatchingPair() {
        const container = document.getElementById('pairsContainer');
        if (!container) return;

        const pairDiv = document.createElement('div');
        pairDiv.className = 'flex items-center space-x-2';
        pairDiv.innerHTML = `
            <div class="flex-1">
                <input type="text" name="prompts[]" required
                       class="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                       placeholder="Prompt">
            </div>
            <div class="flex-1">
                <input type="text" name="matches[]" required
                       class="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                       placeholder="Match">
            </div>
            <button type="button" class="text-red-500 hover:text-red-700">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
            </button>
        `;

        const deleteBtn = pairDiv.querySelector('button');
        deleteBtn.addEventListener('click', () => pairDiv.remove());

        container.appendChild(pairDiv);
    },

    initializeMatchingHandlers() {
        // Add initial pair
        this.addMatchingPair();
    }
};

// Make it globally available
window.QuestionTypeFields = QuestionTypeFields; 