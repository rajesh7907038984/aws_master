// Question UI Module
const QuestionUI = {
    init() {
        this.createNotificationContainer();
    },

    createNotificationContainer() {
        let container = document.getElementById('notificationContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'notificationContainer';
            container.className = 'fixed top-4 right-4 z-50 space-y-2';
            document.body.appendChild(container);
        }
    },

    showNotification(message, type) {
        const container = document.getElementById('notificationContainer');
        if (!container) return;

        const notification = document.createElement('div');
        notification.className = `p-4 rounded-lg shadow-lg transform transition-all duration-300 ease-in-out ${
            type === 'error' ? 'bg-red-500' : 'bg-green-500'
        } text-white`;
        
        notification.innerHTML = `
            <div class="flex items-center space-x-2">
                <span>${message}</span>
                <button class="ml-auto">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                    </svg>
                </button>
            </div>
        `;

        container.appendChild(notification);

        // Add click handler for close button
        const closeBtn = notification.querySelector('button');
        closeBtn.addEventListener('click', () => {
            notification.remove();
        });

        // Auto remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 5000);
    },

    showSuccess(message) {
        this.showNotification(message, 'success');
    },

    showError(message) {
        this.showNotification(message, 'error');
    },

    clearForm() {
        const form = document.getElementById('inlineQuestionForm');
        if (form) {
            form.reset();
            const dynamicFields = document.getElementById('dynamicFields');
            if (dynamicFields) {
                dynamicFields.innerHTML = '';
            }
        }
    }
};

// Make it globally available
window.QuestionUI = QuestionUI; 