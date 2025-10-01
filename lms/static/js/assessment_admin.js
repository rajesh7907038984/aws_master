// Handle dynamic form fields based on question type
document.addEventListener('DOMContentLoaded', function() {
    const questionTypeSelect = document.getElementById('id_question_type');
    if (!questionTypeSelect) return;

    function updateQuestionFields(questionType) {
        // Hide all dynamic form sections first
        const inlineGroups = document.querySelectorAll('.inline-group');
        inlineGroups.forEach(group => group.style.display = 'none');

        const answerFieldsets = document.querySelectorAll('.answer-fieldset');
        answerFieldsets.forEach(fieldset => {
            const parentFieldset = fieldset.closest('fieldset');
            if (parentFieldset) {
                parentFieldset.style.display = 'none';
            }
        });

        // Show the appropriate fields based on question type
        switch(questionType) {
            case 'multiple_choice':
            case 'multiple_select':
                // Show the options inline formset
                const optionsInline = document.querySelector('.inline-group');
                if (optionsInline) {
                    optionsInline.style.display = 'block';
                }
                break;

            case 'matching':
                // Show both the matching pairs fieldset and inline formset
                const matchingFieldset = document.querySelector('.field-matching_pairs');
                if (matchingFieldset) {
                    const parentFieldset = matchingFieldset.closest('fieldset');
                    if (parentFieldset) {
                        parentFieldset.style.display = 'block';
                    }
                }
                const matchingInline = document.querySelector('.inline-group');
                if (matchingInline) {
                    matchingInline.style.display = 'block';
                }
                break;

            case 'fill_blank':
                // Show the blank answer fieldset
                const blankFieldset = document.querySelector('.field-blank_answer');
                if (blankFieldset) {
                    const parentFieldset = blankFieldset.closest('fieldset');
                    if (parentFieldset) {
                        parentFieldset.style.display = 'block';
                    }
                }
                break;

            case 'multi_blank':
                // Show the multiple blank answers fieldset
                const multiBlankFieldset = document.querySelector('.field-multiple_blank_answers');
                if (multiBlankFieldset) {
                    const parentFieldset = multiBlankFieldset.closest('fieldset');
                    if (parentFieldset) {
                        parentFieldset.style.display = 'block';
                    }
                }
                break;
        }
    }

    // Update fields when question type changes
    questionTypeSelect.addEventListener('change', function() {
        updateQuestionFields(this.value);
        // Add a small delay to ensure DOM is updated
        setTimeout(() => {
            updateQuestionFields(this.value);
        }, 100);
    });

    // Initial update when page loads
    updateQuestionFields(questionTypeSelect.value);

    // Add CSS to ensure proper form field visibility
    const style = document.createElement('style');
    style.textContent = `
        .inline-group { margin-top: 20px; }
        .answer-fieldset {
            padding: 10px;
            margin-bottom: 10px;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        .answer-fieldset .form-row {
            padding: 8px;
            margin: 0;
        }
        .inline-related h3 { margin-top: 0; }
        .field-blank_answer input,
        .field-multiple_blank_answers textarea,
        .field-matching_pairs textarea {
            width: 100%;
            max-width: 600px;
        }
    `;
    document.head.appendChild(style);
}); 