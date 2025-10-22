document.addEventListener('DOMContentLoaded', function() {
    // Function to update field visibility for a single inline form
    function updateInlineFormFields(inlineForm) {
        const contentTypeSelect = inlineForm.querySelector('select[name*="content_type"]');
        const contentFieldset = inlineForm.querySelector('.content-fields');
        const textContentField = contentFieldset.querySelector('.field-text_content');
        const contentFileField = contentFieldset.querySelector('.field-content_file');
        const webUrlField = contentFieldset.querySelector('.field-web_url');
        const quizzesField = contentFieldset.querySelector('.field-quizzes');
        const assignmentsField = contentFieldset.querySelector('.field-assignments');

        if (!contentTypeSelect || !contentFieldset || !textContentField || !contentFileField || !webUrlField) {
            return;
        }

        function updateFieldVisibility(contentType) {
            // Always ensure content fieldset is visible when there's a content type
            contentFieldset.style.display = contentType ? 'block' : 'none';

            // Hide all content-specific fields first with proper visibility
            const fields = {
                textContentField,
                contentFileField,
                webUrlField,
                quizzesField,
                assignmentsField
            };

            // Hide all fields first
            Object.values(fields).forEach(field => {
                if (field) {
                    field.style.visibility = 'hidden';
                    field.style.display = 'none';
                    field.setAttribute('aria-hidden', 'true');
                }
            });

            // Show relevant field based on content type
            let fieldToShow = null;
            switch(contentType) {
                case 'Text':
                    fieldToShow = textContentField;
                    break;
                case 'Video':
                case 'Audio':
                case 'Document':
                case 'SCORM':
                    fieldToShow = contentFileField;
                    break;
                case 'Web':
                    fieldToShow = webUrlField;
                    break;
                case 'Quiz':
                    fieldToShow = quizzesField;
                    break;
                case 'Assignment':
                    fieldToShow = assignmentsField;
                    break;
            }

            // Show the relevant field with proper visibility
            if (fieldToShow) {
                fieldToShow.style.visibility = 'visible';
                fieldToShow.style.display = 'block';
                fieldToShow.setAttribute('aria-hidden', 'false');
            }
        }

        // Initial visibility update
        updateFieldVisibility(contentTypeSelect.value);

        // Update visibility when content type changes
        contentTypeSelect.addEventListener('change', function() {
            updateFieldVisibility(this.value);
        });
    }

    // Initialize all existing inline forms
    document.querySelectorAll('.dynamic-inline .inline-related').forEach(updateInlineFormFields);

    // Handle dynamically added inline forms
    django.jQuery(document).on('formset:added', function(event, row) {
        updateInlineFormFields(row[0]);
    });
}); 