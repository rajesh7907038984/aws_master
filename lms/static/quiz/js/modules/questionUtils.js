// Question Utils Module
const QuestionUtils = {
    getCSRFToken() {
        const csrfInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
        if (!csrfInput) {
            console.error('CSRF token not found');
            return null;
        }
        return csrfInput.value;
    },

    collectOptions() {
        const optionsContainer = document.getElementById('optionsContainer');
        if (!optionsContainer) return [];

        const options = [];
        const optionInputs = optionsContainer.querySelectorAll('input[type="text"]');
        const correctOption = optionsContainer.querySelector('input[type="radio"]:checked');

        optionInputs.forEach((input, index) => {
            options.push({
                text: input.value.trim(),
                is_correct: correctOption ? correctOption.value === (index + 1).toString() : false
            });
        });

        return options;
    }
};

// Make it globally available
window.QuestionUtils = QuestionUtils; 