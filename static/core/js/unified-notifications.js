/**
 * Unified Notifications System for LMS
 * Centralized notification handling
 */

(function() {
    'use strict';

    const UnifiedNotifications = {
        notifications: [],
        maxNotifications: 100,
        
        init: function() {
            this.setupNotificationContainer();
            this.setupNotificationHandlers();
        },
        
        setupNotificationContainer: function() {
            // Create notification container if it doesn't exist
            if (!document.getElementById('notification-container')) {
                const container = document.createElement('div');
                container.id = 'notification-container';
                container.style.cssText = `
                    position: fixed;
                    top: 20px;
                    right: 20px;
                    z-index: 100200;
                    max-width: 400px;
                `;
                document.body.appendChild(container);
            }
        },
        
        setupNotificationHandlers: function() {
            // Handle custom notification events
            window.addEventListener('showNotification', (event) => {
                this.show(event.detail.message, event.detail.type, event.detail.options);
            });
        },
        
        show: function(message, type = 'info', options = {}) {
            const notification = {
                id: Date.now() + Math.random(),
                message: message,
                type: type,
                timestamp: new Date(),
                options: options
            };
            
            this.notifications.push(notification);
            
            // Keep only recent notifications
            if (this.notifications.length > this.maxNotifications) {
                this.notifications.shift();
            }
            
            this.renderNotification(notification);
            
            // Auto-remove after delay
            if (options.autoRemove !== false) {
                setTimeout(() => {
                    this.remove(notification.id);
                }, options.duration || 5000);
            }
        },
        
        renderNotification: function(notification) {
            const container = document.getElementById('notification-container');
            if (!container) return;
            
            const notificationElement = document.createElement('div');
            notificationElement.className = `notification notification-${notification.type}`;
            notificationElement.dataset.id = notification.id;
            notificationElement.style.cssText = `
                margin-bottom: 10px;
                padding: 15px;
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
                animation: slideIn 0.3s ease-out;
                position: relative;
            `;
            
            // Set colors based on type
            const colors = {
                success: { bg: '#d1fae5', border: '#a7f3d0', text: '#065f46' },
                error: { bg: '#fee2e2', border: '#fecaca', text: '#991b1b' },
                warning: { bg: '#fef3c7', border: '#fde68a', text: '#92400e' },
                info: { bg: '#dbeafe', border: '#bfdbfe', text: '#1e40af' }
            };
            
            const color = colors[notification.type] || colors.info;
            notificationElement.style.backgroundColor = color.bg;
            notificationElement.style.border = `1px solid ${color.border}`;
            notificationElement.style.color = color.text;
            
            // Add close button
            const closeButton = document.createElement('button');
            closeButton.innerHTML = '×';
            closeButton.style.cssText = `
                position: absolute;
                top: 5px;
                right: 10px;
                background: none;
                border: none;
                font-size: 18px;
                cursor: pointer;
                color: inherit;
            `;
            closeButton.addEventListener('click', () => {
                this.remove(notification.id);
            });
            
            // Add icon
            const icon = this.getIcon(notification.type);
            notificationElement.innerHTML = `
                <div style="display: flex; align-items: center;">
                    <span style="margin-right: 10px; font-size: 18px;">${icon}</span>
                    <span style="flex: 1;">${notification.message}</span>
                </div>
            `;
            
            notificationElement.appendChild(closeButton);
            container.appendChild(notificationElement);
        },
        
        getIcon: function(type) {
            const icons = {
                success: '✓',
                error: '✕',
                warning: '⚠',
                info: 'ℹ'
            };
            return icons[type] || icons.info;
        },
        
        remove: function(id) {
            const element = document.querySelector(`[data-id="${id}"]`);
            if (element) {
                element.style.animation = 'slideOut 0.3s ease-in';
                setTimeout(() => {
                    element.remove();
                }, 300);
            }
            
            // Remove from notifications array
            this.notifications = this.notifications.filter(n => n.id !== id);
        },
        
        clear: function() {
            const container = document.getElementById('notification-container');
            if (container) {
                container.innerHTML = '';
            }
            this.notifications = [];
        },
        
        getNotifications: function() {
            return this.notifications;
        }
    };

    // Add CSS animations
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideIn {
            from {
                transform: translateX(100%);
                opacity: 0;
            }
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }
        
        @keyframes slideOut {
            from {
                transform: translateX(0);
                opacity: 1;
            }
            to {
                transform: translateX(100%);
                opacity: 0;
            }
        }
    `;
    document.head.appendChild(style);

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            UnifiedNotifications.init();
        });
    } else {
        UnifiedNotifications.init();
    }

    // Export to global scope
    window.UnifiedNotifications = UnifiedNotifications;
    window.showNotification = (message, type, options) => {
        UnifiedNotifications.show(message, type, options);
    };
})();