// Direct fix for assignment selection visibility issue
(function() {
    // Run immediately when the script loads
    function fixAssignmentField() {
        console.log('FIX: Running assignment field visibility fix');
        
        // Check if we're on a topic edit page
        if (window.location.pathname.includes('/topic/') && window.location.pathname.includes('/edit')) {
            console.log('FIX: On topic edit page');
            
            // Check if this is an assignment topic
            const assignmentRadio = document.querySelector('input[name="content_type"][value="Assignment"]:checked');
            const contentTypeHidden = document.querySelector('input[type="hidden"][name="content_type"][value="Assignment"]');
            
            if (assignmentRadio || contentTypeHidden) {
                console.log('FIX: Assignment content type detected');
                
                // Force assignment field to be visible
                const assignmentField = document.getElementById('assignment-content');
                if (assignmentField) {
                    // Use !important to override any other styles
                    assignmentField.setAttribute('style', 'display: block !important; visibility: visible !important; opacity: 1 !important;');
                    assignmentField.classList.add('active');
                    console.log('FIX: Made assignment field visible');
                    
                    // Also make select visible
                    const assignmentSelect = assignmentField.querySelector('select[name="assignment"]');
                    if (assignmentSelect) {
                        assignmentSelect.setAttribute('style', 'display: block !important; visibility: visible !important; opacity: 1 !important;');
                        console.log('FIX: Made assignment select visible');
                        
                        // If there are no options or only the default option, try to fetch assignments
                        if (assignmentSelect.options.length <= 1) {
                            fetchAssignments(assignmentSelect);
                        } else {
                            // Try to select correct option from hidden field
                            const assignmentIdField = document.querySelector('input[name="assignment_id"]');
                            if (assignmentIdField && assignmentIdField.value) {
                                console.log('FIX: Found assignment_id in hidden field:', assignmentIdField.value);
                                
                                // Try to find and select the option
                                const option = assignmentSelect.querySelector(`option[value="${assignmentIdField.value}"]`);
                                if (option) {
                                    option.selected = true;
                                    console.log('FIX: Selected assignment option:', option.textContent);
                                }
                            }
                        }
                    } else {
                        // SELECT ELEMENT NOT FOUND - CREATE IT
                        console.log('FIX: Assignment select NOT FOUND - creating it');
                        
                        // Try to find the form group first
                        let formGroup = assignmentField.querySelector('.form-group');
                        
                        // If no form group, create one
                        if (!formGroup) {
                            formGroup = document.createElement('div');
                            formGroup.className = 'form-group';
                            assignmentField.appendChild(formGroup);
                        }
                        
                        // Check if form group has label
                        let label = formGroup.querySelector('label');
                        if (!label) {
                            label = document.createElement('label');
                            label.textContent = 'Select Assignment';
                            formGroup.appendChild(label);
                        }
                        
                        // Create new select element
                        const newSelect = document.createElement('select');
                        newSelect.name = 'assignment';
                        newSelect.id = 'assignment-select';
                        newSelect.setAttribute('style', 'display: block !important; visibility: visible !important; opacity: 1 !important;');
                        
                        // Add default option
                        const defaultOption = document.createElement('option');
                        defaultOption.value = '';
                        defaultOption.textContent = 'Select an assignment';
                        newSelect.appendChild(defaultOption);
                        
                        // Add to the form group
                        formGroup.appendChild(newSelect);
                        
                        // Try to get assignment ID from hidden field
                        const assignmentIdField = document.querySelector('input[name="assignment_id"]');
                        if (assignmentIdField && assignmentIdField.value) {
                            console.log('FIX: Creating option for assignment ID:', assignmentIdField.value);
                            
                            // Create an option for this assignment
                            const option = document.createElement('option');
                            option.value = assignmentIdField.value;
                            option.textContent = 'Assignment #' + assignmentIdField.value;
                            option.selected = true;
                            newSelect.appendChild(option);
                        }
                        
                        console.log('FIX: Created new assignment select dropdown');
                        
                        // Fetch assignments to populate the dropdown
                        fetchAssignments(newSelect);
                    }
                    
                    // Make sure all children of the assignment field are visible
                    const allElements = assignmentField.querySelectorAll('*');
                    allElements.forEach(element => {
                        element.style.visibility = 'visible';
                        element.style.display = element.tagName === 'SELECT' ? 'block' : '';
                        element.style.opacity = '1';
                    });
                } else {
                    // ASSIGNMENT FIELD NOT FOUND - CREATE IT
                    console.log('FIX: Assignment field NOT FOUND - creating it');
                    
                    // Create the assignment field container
                    const newAssignmentField = document.createElement('div');
                    newAssignmentField.id = 'assignment-content';
                    newAssignmentField.className = 'content-type-field active';
                    newAssignmentField.setAttribute('style', 'display: block !important; visibility: visible !important; opacity: 1 !important;');
                    
                    // Create the form group
                    const formGroup = document.createElement('div');
                    formGroup.className = 'form-group';
                    
                    // Create label
                    const label = document.createElement('label');
                    label.textContent = 'Select Assignment';
                    formGroup.appendChild(label);
                    
                    // Create select element
                    const newSelect = document.createElement('select');
                    newSelect.name = 'assignment';
                    newSelect.id = 'assignment-select';
                    newSelect.setAttribute('style', 'display: block !important; visibility: visible !important; opacity: 1 !important;');
                    
                    // Add default option
                    const defaultOption = document.createElement('option');
                    defaultOption.value = '';
                    defaultOption.textContent = 'Select an assignment';
                    newSelect.appendChild(defaultOption);
                    
                    // Try to get assignment ID from hidden field
                    const assignmentIdField = document.querySelector('input[name="assignment_id"]');
                    if (assignmentIdField && assignmentIdField.value) {
                        console.log('FIX: Creating option for assignment ID:', assignmentIdField.value);
                        
                        // Create an option for this assignment
                        const option = document.createElement('option');
                        option.value = assignmentIdField.value;
                        option.textContent = 'Assignment #' + assignmentIdField.value;
                        option.selected = true;
                        newSelect.appendChild(option);
                    }
                    
                    // Add select to form group
                    formGroup.appendChild(newSelect);
                    
                    // Add form group to field
                    newAssignmentField.appendChild(formGroup);
                    
                    // Find place to insert the field
                    const contentSection = document.querySelector('.space-y-6');
                    if (contentSection) {
                        contentSection.appendChild(newAssignmentField);
                    } else {
                        // Fallback to form
                        const form = document.getElementById('topicForm');
                        if (form) {
                            form.appendChild(newAssignmentField);
                        }
                    }
                    
                    console.log('FIX: Created new assignment field with select dropdown');
                    
                    // Fetch assignments to populate the dropdown
                    fetchAssignments(newSelect);
                }
            }
        }
    }
    
    // Function to fetch assignments from the server
    function fetchAssignments(selectElement) {
        if (!selectElement) return;
        
        console.log('FIX: Fetching assignments from server');
        
        // Get CSRF token
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
        
        // Make request to get assignments
        fetch('/assignments/api/list/', {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': csrfToken
            }
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Failed to fetch assignments');
            }
            return response.json();
        })
        .then(data => {
            if (data.assignments && data.assignments.length > 0) {
                console.log('FIX: Received assignments from server:', data.assignments.length);
                
                // Clear existing options except the default one
                const defaultOption = selectElement.querySelector('option[value=""]');
                selectElement.innerHTML = '';
                if (defaultOption) {
                    selectElement.appendChild(defaultOption);
                } else {
                    // Create default option if it doesn't exist
                    const newDefaultOption = document.createElement('option');
                    newDefaultOption.value = '';
                    newDefaultOption.textContent = 'Select an assignment';
                    selectElement.appendChild(newDefaultOption);
                }
                
                // Add options from server data
                data.assignments.forEach(assignment => {
                    const option = document.createElement('option');
                    option.value = assignment.id;
                    option.textContent = assignment.title || `Assignment #${assignment.id}`;
                    selectElement.appendChild(option);
                });
                
                // Try to select correct option from hidden field
                const assignmentIdField = document.querySelector('input[name="assignment_id"]');
                if (assignmentIdField && assignmentIdField.value) {
                    const option = selectElement.querySelector(`option[value="${assignmentIdField.value}"]`);
                    if (option) {
                        option.selected = true;
                    }
                }
            }
        })
        .catch(error => {
            console.error('FIX: Error fetching assignments:', error);
            // Fallback to creating a single option for the current assignment
            const assignmentIdField = document.querySelector('input[name="assignment_id"]');
            if (assignmentIdField && assignmentIdField.value) {
                // Create an option for this assignment
                const option = document.createElement('option');
                option.value = assignmentIdField.value;
                option.textContent = `Assignment #${assignmentIdField.value}`;
                option.selected = true;
                selectElement.appendChild(option);
            }
        });
    }
    
    // Run the fix when the page loads
    document.addEventListener('DOMContentLoaded', fixAssignmentField);
    
    // Also run it now in case the DOM is already loaded
    if (document.readyState === 'interactive' || document.readyState === 'complete') {
        fixAssignmentField();
    }
})(); 