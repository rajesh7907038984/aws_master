// Global popup objects
const categoryPopup = {
    container: document.getElementById('popup-container'),
    show: function() {
        if (this.container) {
            this.container.style.display = 'flex';
            this.container.classList.add('active');
            document.body.style.overflow = 'hidden';
        }
    },
    hide: function() {
        if (this.container) {
            this.container.style.display = 'none';
            this.container.classList.remove('active');
            document.body.style.overflow = '';
            // Reset form
            const form = document.getElementById('categoryForm');
            if (form) {
                form.reset();
            }
        }
    }
};

const userPopup = {
    container: document.getElementById('user-popup-container'),
    show: function() {
        if (this.container) {
            this.container.style.display = 'flex';
            this.container.classList.add('active');
            document.body.style.overflow = 'hidden';
        }
    },
    hide: function() {
        if (this.container) {
            this.container.style.display = 'none';
            this.container.classList.remove('active');
            document.body.style.overflow = '';
            // Reset form
            const form = document.getElementById('userForm');
            if (form) {
                form.reset();
            }
        }
    }
};

const outcomePopup = {
    container: document.getElementById('outcome-popup-container'),
    show: function() {
        if (this.container) {
            this.container.style.display = 'flex';
            this.container.classList.add('active');
            document.body.style.overflow = 'hidden';
        }
    },
    hide: function() {
        if (this.container) {
            this.container.style.display = 'none';
            this.container.classList.remove('active');
            document.body.style.overflow = '';
            // Reset form
            const form = document.getElementById('outcomeForm');
            if (form) {
                form.reset();
            }
        }
    }
};

const rubricPopup = {
    container: document.getElementById('rubric-popup-container'),
    show: function() {
        if (this.container) {
            this.container.style.display = 'flex';
            this.container.classList.add('active');
            document.body.style.overflow = 'hidden';
        }
    },
    hide: function() {
        if (this.container) {
            this.container.style.display = 'none';
            this.container.classList.remove('active');
            document.body.style.overflow = '';
            // Reset form
            const form = document.getElementById('rubricForm');
            if (form) {
                form.reset();
            }
        }
    }
};

const groupPopup = {
    container: document.getElementById('group-popup-container'),
    show: function() {
        if (this.container) {
            this.container.style.display = 'flex';
            this.container.classList.add('active');
            document.body.style.overflow = 'hidden';
        }
    },
    hide: function() {
        if (this.container) {
            this.container.style.display = 'none';
            this.container.classList.remove('active');
            document.body.style.overflow = '';
            // Reset form
            const form = document.getElementById('groupForm');
            if (form) {
                form.reset();
            }
        }
    }
};

const settingsPopup = {
    container: document.getElementById('settings-popup-container'),
    show: function() {
        if (this.container) {
            this.container.style.display = 'flex';
            this.container.classList.add('active');
            document.body.style.overflow = 'hidden';
        }
    },
    hide: function() {
        if (this.container) {
            this.container.style.display = 'none';
            this.container.classList.remove('active');
            document.body.style.overflow = '';
            // Reset form
            const form = document.getElementById('settingsForm');
            if (form) {
                form.reset();
            }
        }
    }
};

const sectionPopup = {
    container: document.getElementById('section-popup-container'),
    show: function() {
        if (this.container) {
            this.container.style.display = 'flex';
            this.container.classList.add('active');
            document.body.style.overflow = 'hidden';
        }
    },
    hide: function() {
        if (this.container) {
            this.container.style.display = 'none';
            this.container.classList.remove('active');
            document.body.style.overflow = '';
            // Reset form
            const form = document.getElementById('sectionForm');
            if (form) {
                form.reset();
            }
        }
    }
};

// Initialize popups when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded in popup_handler.js');

    // Add Category Button Click Handler
    const addCategoryBtn = document.getElementById('add-category-btn');
    if (addCategoryBtn) {
        addCategoryBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            categoryPopup.show();
        });
    }

    // Add User Button Click Handler
    const addUserBtn = document.getElementById('add-user-btn');
    if (addUserBtn) {
        addUserBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            userPopup.show();
        });
    }

    // Add Outcome Button Click Handler
    const addOutcomeBtn = document.getElementById('add-outcome-btn');
    if (addOutcomeBtn) {
        addOutcomeBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            outcomePopup.show();
        });
    }

    // Add Rubric Button Click Handler
    const addRubricBtn = document.getElementById('add-rubric-btn');
    if (addRubricBtn) {
        addRubricBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            rubricPopup.show();
        });
    }

    // Add Group Button Click Handler
    const addGroupBtn = document.getElementById('add-group-btn');
    if (addGroupBtn) {
        addGroupBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            groupPopup.show();
        });
    }

    // Settings Button Click Handler
    const settingsBtn = document.querySelector('[data-action="settings"]');
    if (settingsBtn) {
        settingsBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            settingsPopup.show();
        });
    }

    // Add Section Button Click Handler
    const addSectionBtn = document.getElementById('add-section-btn');
    if (addSectionBtn) {
        addSectionBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            sectionPopup.show();
        });
    }

    // Close popups when clicking outside
    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('popup-container') || 
            e.target.id === 'user-popup-container' || 
            e.target.id === 'outcome-popup-container' || 
            e.target.id === 'rubric-popup-container' || 
            e.target.id === 'group-popup-container' || 
            e.target.id === 'settings-popup-container' || 
            e.target.id === 'section-popup-container') {
            
            if (e.target === categoryPopup.container) {
                categoryPopup.hide();
            } else if (e.target === userPopup.container) {
                userPopup.hide();
            } else if (e.target === outcomePopup.container) {
                outcomePopup.hide();
            } else if (e.target === rubricPopup.container) {
                rubricPopup.hide();
            } else if (e.target === groupPopup.container) {
                groupPopup.hide();
            } else if (e.target === settingsPopup.container) {
                settingsPopup.hide();
            } else if (e.target === sectionPopup.container) {
                sectionPopup.hide();
            }
        }
    });

    // Close Category popup when clicking cancel button
    document.querySelectorAll('.btn-cancel').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            categoryPopup.hide();
        });
    });

    // Close User popup when clicking cancel button
    document.querySelectorAll('.user-btn-cancel').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            userPopup.hide();
        });
    });

    // Close Outcome popup when clicking cancel button
    document.querySelectorAll('.outcome-btn-cancel').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            outcomePopup.hide();
        });
    });

    // Close Rubric popup when clicking cancel button
    document.querySelectorAll('.rubric-btn-cancel').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            rubricPopup.hide();
        });
    });

    // Close Group popup when clicking cancel button
    document.querySelectorAll('.group-btn-cancel').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            groupPopup.hide();
        });
    });

    // Close Settings popup when clicking cancel button
    document.querySelectorAll('.settings-btn-cancel').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            settingsPopup.hide();
        });
    });

    // Handle form submissions
    // Add Users form submission
    const addSelectedUsersBtn = document.getElementById('add-selected-users');
    if (addSelectedUsersBtn) {
        addSelectedUsersBtn.addEventListener('click', function(e) {
            e.preventDefault();
            
            // Get selected users
            const selectedUsers = [];
            const checkboxes = document.querySelectorAll('input[name="selected_users"]:checked');
            checkboxes.forEach(checkbox => selectedUsers.push(checkbox.value));
            
            if (selectedUsers.length === 0) {
                if (typeof showToast === 'function') {
                    showToast('Please select at least one user', 'warning');
                }
                return;
            }
            
            // Submit the form data
            if (typeof showToast === 'function') {
                showToast(`Selected ${selectedUsers.length} user(s) for course enrollment`, 'success');
            }
            
            // You could submit this data to the server here
            userPopup.hide();
        });
    }

    // Add Outcome form submission
    const addOutcomeSubmitBtn = document.getElementById('add-outcome');
    if (addOutcomeSubmitBtn) {
        addOutcomeSubmitBtn.addEventListener('click', function(e) {
            e.preventDefault();
            
            // Get selected outcomes
            const selectedOutcomes = [];
            const checkboxes = document.querySelectorAll('input[name="selected_outcomes"]:checked');
            checkboxes.forEach(checkbox => selectedOutcomes.push(checkbox.value));
            
            if (selectedOutcomes.length === 0) {
                if (typeof showToast === 'function') {
                    showToast('Please select at least one learning outcome', 'warning');
                }
                return;
            }
            
            // Add outcomes to the course
            if (typeof showToast === 'function') {
                showToast(`Added ${selectedOutcomes.length} learning outcome(s) to course`, 'success');
            }
            
            // You could update the UI here to show selected outcomes
            outcomePopup.hide();
        });
    }

    // Add Rubric form submission
    const addRubricSubmitBtn = document.getElementById('add-rubric');
    if (addRubricSubmitBtn) {
        addRubricSubmitBtn.addEventListener('click', function(e) {
            e.preventDefault();
            
            // Get selected rubrics
            const selectedRubrics = [];
            const checkboxes = document.querySelectorAll('input[name="selected_rubrics"]:checked');
            checkboxes.forEach(checkbox => selectedRubrics.push(checkbox.value));
            
            if (selectedRubrics.length === 0) {
                if (typeof showToast === 'function') {
                    showToast('Please select at least one rubric', 'warning');
                }
                return;
            }
            
            // Add rubrics to the course
            if (typeof showToast === 'function') {
                showToast(`Added ${selectedRubrics.length} rubric(s) to course`, 'success');
            }
            
            // You could update the UI here to show selected rubrics
            rubricPopup.hide();
        });
    }

    // Add Groups form submission
    const addSelectedGroupsBtn = document.getElementById('add-selected-groups');
    if (addSelectedGroupsBtn) {
        addSelectedGroupsBtn.addEventListener('click', function(e) {
            e.preventDefault();
            
            // Get selected groups
            const selectedGroups = [];
            const checkboxes = document.querySelectorAll('input[name="selected_groups"]:checked');
            checkboxes.forEach(checkbox => selectedGroups.push(checkbox.value));
            
            if (selectedGroups.length === 0) {
                if (typeof showToast === 'function') {
                    showToast('Please select at least one group', 'warning');
                }
                return;
            }
            
            // Add groups to the course
            if (typeof showToast === 'function') {
                showToast(`Added ${selectedGroups.length} group(s) to course`, 'success');
            }
            
            // You could update the UI here to show selected groups
            groupPopup.hide();
        });
    }

    // Save Settings form submission
    const saveSettingsBtn = document.getElementById('save-settings');
    if (saveSettingsBtn) {
        saveSettingsBtn.addEventListener('click', function(e) {
            e.preventDefault();
            
            // Collect form data from the settings form
            const formData = new FormData(document.getElementById('settingsForm'));
            
            // Basic validation
            const requiredFields = ['course_name', 'course_description'];
            let isValid = true;
            
            for (const field of requiredFields) {
                const value = formData.get(field);
                if (!value || value.trim() === '') {
                    if (typeof showToast === 'function') {
                        showToast(`Please fill in the ${field.replace('_', ' ')}`, 'error');
                    }
                    isValid = false;
                    break;
                }
            }
            
            if (isValid) {
                if (typeof showToast === 'function') {
                    showToast('Course settings saved successfully', 'success');
                }
                settingsPopup.hide();
                
                // You could submit this data to the server here
                // fetch('/courses/save-settings/', { method: 'POST', body: formData })
            }
        });
    }
}); 