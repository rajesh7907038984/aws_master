/**
 * Template Fixes JavaScript
 * Handles inline event handlers that were converted to data attributes
 */

document.addEventListener('DOMContentLoaded', function() {
    // Handle toast close buttons
    document.addEventListener('click', function(e) {
        if (e.target.closest('[data-toast-close="true"]')) {
            const toast = e.target.closest('.toast-enter');
            if (toast) {
                toast.classList.add('toast-leave');
                setTimeout(() => {
                    toast.remove();
                }, 300);
            }
        }
    });

    // Handle history back buttons
    document.addEventListener('click', function(e) {
        if (e.target.closest('[data-action="history-back"]')) {
            history.back();
        }
    });

    // Handle reload page buttons
    document.addEventListener('click', function(e) {
        if (e.target.closest('[data-action="reload"]')) {
            location.reload();
        }
    });

    // Handle search toast triggers
    document.addEventListener('click', function(e) {
        if (e.target.closest('.search-toast-trigger')) {
            e.preventDefault();
            const message = e.target.getAttribute('data-message');
            const type = e.target.getAttribute('data-type') || 'info';
            
            // Create a modern toast notification
            const toast = document.createElement('div');
            toast.className = 'toast-notification';
            toast.innerHTML = `
                <div class="flex items-center">
                    <i class="fas fa-info-circle mr-2 text-blue-500"></i>
                    <span>${message}</span>
                </div>
            `;
            document.body.appendChild(toast);
            
            // Auto-remove after 3 seconds
            setTimeout(() => {
                toast.remove();
            }, 3000);
        }
    });

    // Handle branch switching
    document.addEventListener('click', function(e) {
        if (e.target.closest('.branch-switch-btn')) {
            const branchId = e.target.getAttribute('data-branch-id');
            const branchName = e.target.getAttribute('data-branch-name');
            if (branchId && branchName && typeof switchToBranch === 'function') {
                switchToBranch(branchId, branchName);
            }
        }
    });

    // Handle question editing and deletion (if functions exist)
    if (typeof editQuestion === 'function') {
        window.editQuestion = editQuestion;
    }
    
    if (typeof deleteQuestion === 'function') {
        window.deleteQuestion = deleteQuestion;
    }

    // Handle induction item deletion
    if (typeof deleteExistingInductionItem === 'function') {
        window.deleteExistingInductionItem = deleteExistingInductionItem;
    }

    // Handle question type fields
    if (typeof QuestionTypeFields !== 'undefined' && QuestionTypeFields.addAnswer) {
        window.QuestionTypeFields = QuestionTypeFields;
    }
});
