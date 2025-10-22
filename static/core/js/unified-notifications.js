/**
 * Unified Notification System for LMS
 * 
 * This file provides a centralized notification system to replace
 * all the conflicting showNotification functions across the project.
 * 
 * Usage:
 * - showNotification(message, type, duration)
 * - showSuccess(message, duration)
 * - showError(message, duration)
 * - showWarning(message, duration)
 * - showInfo(message, duration)
 */

class UnifiedNotificationSystem {
    constructor() {
        this.notifications = [];
        this.maxNotifications = 5;
        this.defaultDuration = 5000;
        this.container = null;
        this.init();
    }

    init() {
        // Wait for DOM to be ready before creating container
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.createContainer());
        } else {
            this.createContainer();
        }
    }

    createContainer() {
        // Create notification container if it doesn't exist
        if (!this.container && document.body) {
            this.container = document.createElement('div');
            this.container.id = 'unified-notification-container';
            this.container.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 10000;
                max-width: 400px;
                pointer-events: none;
            `;
            document.body.appendChild(this.container);
        }
    }

    show(message, type = 'info', duration = null) {
        if (!message) return;

        // Ensure container exists before showing notification
        if (!this.container) {
            this.createContainer();
        }
        
        if (!this.container) {
            console.error('Cannot show notification: container not available');
            return;
        }

        const notificationId = 'notification-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
        const notificationDuration = duration || this.defaultDuration;

        // Create notification element
        const notification = document.createElement('div');
        notification.id = notificationId;
        notification.className = `unified-notification unified-notification-${type}`;
        
        // Set styles based on type
        const styles = this.getTypeStyles(type);
        notification.style.cssText = `
            background: ${styles.background};
            color: ${styles.color};
            border: 1px solid ${styles.border};
            border-radius: 8px;
            padding: 12px 16px;
            margin-bottom: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            font-size: 14px;
            font-weight: 500;
            line-height: 1.4;
            opacity: 0;
            transform: translateX(100%);
            transition: all 0.3s ease;
            pointer-events: auto;
            display: flex;
            align-items: flex-start;
            gap: 8px;
            max-width: 100%;
            word-wrap: break-word;
        `;

        // Create icon
        const icon = this.createIcon(type);
        
        // Create content
        const content = document.createElement('div');
        content.style.flex = '1';
        content.textContent = message;

        // Create close button
        const closeBtn = document.createElement('button');
        closeBtn.innerHTML = '×';
        closeBtn.style.cssText = `
            background: none;
            border: none;
            color: inherit;
            font-size: 18px;
            font-weight: bold;
            cursor: pointer;
            padding: 0;
            margin-left: 8px;
            opacity: 0.7;
            transition: opacity 0.2s ease;
        `;
        closeBtn.onmouseover = () => closeBtn.style.opacity = '1';
        closeBtn.onmouseout = () => closeBtn.style.opacity = '0.7';
        closeBtn.onclick = () => this.remove(notificationId);

        // Assemble notification
        notification.appendChild(icon);
        notification.appendChild(content);
        notification.appendChild(closeBtn);

        // Add to container
        this.container.appendChild(notification);
        this.notifications.push(notificationId);

        // Animate in
        requestAnimationFrame(() => {
            notification.style.opacity = '1';
            notification.style.transform = 'translateX(0)';
        });

        // Auto remove
        if (notificationDuration > 0) {
            setTimeout(() => this.remove(notificationId), notificationDuration);
        }

        // Limit number of notifications
        if (this.notifications.length > this.maxNotifications) {
            const oldestId = this.notifications.shift();
            this.remove(oldestId);
        }

        return notificationId;
    }

    remove(notificationId) {
        const notification = document.getElementById(notificationId);
        if (notification) {
            notification.style.opacity = '0';
            notification.style.transform = 'translateX(100%)';
            
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
                const index = this.notifications.indexOf(notificationId);
                if (index > -1) {
                    this.notifications.splice(index, 1);
                }
            }, 300);
        }
    }

    createIcon(type) {
        const icon = document.createElement('div');
        icon.style.cssText = `
            flex-shrink: 0;
            width: 20px;
            height: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 16px;
        `;

        switch (type) {
            case 'success':
                icon.innerHTML = '✓';
                break;
            case 'error':
                icon.innerHTML = '✕';
                break;
            case 'warning':
                icon.innerHTML = '⚠';
                break;
            case 'info':
            default:
                icon.innerHTML = 'ℹ';
                break;
        }

        return icon;
    }

    getTypeStyles(type) {
        const styles = {
            success: {
                background: '#d1fae5',
                color: '#065f46',
                border: '#10b981'
            },
            error: {
                background: '#fee2e2',
                color: '#991b1b',
                border: '#ef4444'
            },
            warning: {
                background: '#fef3c7',
                color: '#92400e',
                border: '#f59e0b'
            },
            info: {
                background: '#dbeafe',
                color: '#1e40af',
                border: '#3b82f6'
            }
        };

        return styles[type] || styles.info;
    }

    clear() {
        this.notifications.forEach(id => this.remove(id));
    }
}

// Create global instance
const notificationSystem = new UnifiedNotificationSystem();

// Global functions for backward compatibility
function showNotification(message, type = 'info', duration = null) {
    return notificationSystem.show(message, type, duration);
}

function showSuccess(message, duration = null) {
    return notificationSystem.show(message, 'success', duration);
}

function showError(message, duration = null) {
    return notificationSystem.show(message, 'error', duration);
}

function showWarning(message, duration = null) {
    return notificationSystem.show(message, 'warning', duration);
}

function showInfo(message, duration = null) {
    return notificationSystem.show(message, 'info', duration);
}

// Expose to global scope
window.showNotification = showNotification;
window.showSuccess = showSuccess;
window.showError = showError;
window.showWarning = showWarning;
window.showInfo = showInfo;
window.notificationSystem = notificationSystem;

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        UnifiedNotificationSystem,
        showNotification,
        showSuccess,
        showError,
        showWarning,
        showInfo
    };
}
