/**
 * Unified Auth Handler - Manages authentication state
 */
(function() {
    'use strict';
    
    const UnifiedAuthHandler = {
        isAuthenticated: false,
        user: null,
        
        init: function() {
            this.checkAuthStatus();
            this.setupAuthEvents();
        },
        
        checkAuthStatus: function() {
            // Check if user data exists in DOM
            const userDataElement = document.querySelector('[data-user-authenticated]');
            if (userDataElement) {
                this.isAuthenticated = userDataElement.dataset.userAuthenticated === 'true';
                this.user = {
                    id: userDataElement.dataset.userId || null,
                    username: userDataElement.dataset.username || null,
                    role: userDataElement.dataset.userRole || null
                };
            }
        },
        
        setupAuthEvents: function() {
            // Handle login form submissions
            const loginForms = document.querySelectorAll('form[action*="login"]');
            loginForms.forEach(form => {
                form.addEventListener('submit', this.handleLoginSubmit.bind(this));
            });
            
            // Handle logout forms and links
            const logoutForms = document.querySelectorAll('form[action*="logout"]');
            logoutForms.forEach(form => {
                form.addEventListener('submit', this.handleLogoutSubmit.bind(this));
            });
            
            const logoutLinks = document.querySelectorAll('a[href*="logout"]');
            logoutLinks.forEach(link => {
                link.addEventListener('click', this.handleLogoutClick.bind(this));
            });
        },
        
        handleLoginSubmit: function(event) {
            const form = event.target;
            const submitButton = form.querySelector('button[type="submit"]');
            
            if (submitButton) {
                submitButton.disabled = true;
                submitButton.textContent = 'Logging in...';
            }
        },
        
        handleLogoutSubmit: function(event) {
            // Clear any cached user data
            this.isAuthenticated = false;
            this.user = null;
            
            // Show logout message
            const submitButton = event.target.querySelector('button[type="submit"]');
            if (submitButton) {
                submitButton.disabled = true;
                submitButton.textContent = 'Logging out...';
            }
            
            // Let the form submit normally
        },
        
        handleLogoutClick: function(event) {
            // Clear any cached user data
            this.isAuthenticated = false;
            this.user = null;
            
            // Don't prevent default behavior - let the form submit normally
            // The logout form should handle the actual logout process
        },
        
        getUser: function() {
            return this.user;
        },
        
        isUserAuthenticated: function() {
            return this.isAuthenticated;
        }
    };
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            UnifiedAuthHandler.init();
        });
    } else {
        UnifiedAuthHandler.init();
    }
    
    // Export to global scope
    window.UnifiedAuthHandler = UnifiedAuthHandler;
})();
