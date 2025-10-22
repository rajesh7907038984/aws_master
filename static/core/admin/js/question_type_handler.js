(function($) {
    'use strict';
    $(document).ready(function() {
        var questionType = $('#id_question_type');
        var formRows = {
            multipleChoice: $('.inline-group').has('.dynamic-questionoption_set'),
            matching: $('.field-matching_pairs').closest('.form-row'),
            fillBlank: $('.field-blank_answer').closest('.form-row'),
            multiBlank: $('.field-multiple_blank_answers').closest('.form-row')
        };

        function hideAllFormRows() {
            // Hide all special fields
            Object.values(formRows).forEach(function(row) {
                if (row.length) {
                    row.hide();
                }
            });
            // Hide all inline groups
            $('.inline-group').hide();
        }

        function showRelevantFields(selectedType) {
            console.log('Showing fields for type:', selectedType);
            
            switch(selectedType) {
                case 'multiple_choice':
                case 'multiple_select':
                    console.log('Multiple choice/select selected');
                    var optionsGroup = $('.inline-group').has('.dynamic-questionoption_set');
                    console.log('Options group found:', optionsGroup.length);
                    optionsGroup.show();
                    break;
                case 'matching':
                    console.log('Matching selected');
                    var matchingGroup = $('.inline-group').has('.dynamic-matchingpair_set');
                    console.log('Matching group found:', matchingGroup.length);
                    matchingGroup.show();
                    formRows.matching.show();
                    break;
                case 'fill_blank':
                    console.log('Fill blank selected');
                    formRows.fillBlank.show();
                    break;
                case 'multi_blank':
                    console.log('Multi blank selected');
                    formRows.multiBlank.show();
                    break;
            }
        }

        function updateFormFields() {
            var selectedType = questionType.val();
            console.log('Updating fields for type:', selectedType);
            
            hideAllFormRows();
            if (selectedType) {
                showRelevantFields(selectedType);
            }
        }

        // Update fields when question type changes
        questionType.on('change', updateFormFields);

        // Initial update on page load - try multiple times to ensure it works
        $(window).on('load', function() {
            console.log('Window loaded');
            updateFormFields();
        });

        // Immediate update
        updateFormFields();
        
        // Backup timeout update
        setTimeout(updateFormFields, 100);
        setTimeout(updateFormFields, 500);

        // Add validation for matching pairs format
        $('form').on('submit', function(e) {
            var selectedType = questionType.val();
            if (selectedType === 'matching') {
                var matchingPairs = $('.field-matching_pairs textarea').val();
                if (matchingPairs) {  // Only validate if there's content
                    var lines = matchingPairs.split('\n').filter(function(line) {
                        return line.trim() !== '';
                    });
                    
                    var isValid = lines.every(function(line) {
                        return line.includes('->');
                    });

                    if (!isValid) {
                        e.preventDefault();
                        alert('Please ensure all matching pairs are in the format "left -> right"');
                    }
                }
            }
        });

        // Debug logging
        console.log('Question type handler initialized');
        console.log('Form rows found:', {
            multipleChoice: formRows.multipleChoice.length,
            matching: formRows.matching.length,
            fillBlank: formRows.fillBlank.length,
            multiBlank: formRows.multiBlank.length
        });
        console.log('Current question type:', questionType.val());
    });
})(django.jQuery); 