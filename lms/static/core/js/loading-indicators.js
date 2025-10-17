/**
 * Loading Indicators for LMS
 * ==========================
 * 
 * This module provides loading indicators for all async operations
 * including search, pagination, filtering, and form submissions.
 */

class LoadingIndicatorManager {
    constructor() {
        this.activeLoaders = new Set();
        this.loadingOverlay = null;
        this.init();
    }

    init() {
        this.createLoadingOverlay();
        this.setupGlobalEventListeners();
        this.setupFormLoading();
        this.setupSearchLoading();
        this.setupPaginationLoading();
    }

    createLoadingOverlay() {
        // Create global loading overlay
        this.loadingOverlay = document.createElement('div');
        this.loadingOverlay.id = 'global-loading-overlay';
        this.loadingOverlay.innerHTML = `
            <div class="loading-content">
                <div class="loading-spinner"></div>
                <div class="loading-text">Loading...</div>
            </div>
        `;
        
        // Add styles
        const styles = `
            #global-loading-overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.5);
                display: none;
                justify-content: center;
                align-items: center;
                z-index: 10000;
                backdrop-filter: blur(2px);
            }
            
            .loading-content {
                background: white;
                padding: 2rem;
                border-radius: 12px;
                text-align: center;
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
            }
            
            .loading-spinner {
                width: 40px;
                height: 40px;
                border: 4px solid #f3f4f6;
                border-top: 4px solid #3b82f6;
                border-radius: 50%;
                animation: spin 1s linear infinite;
                margin: 0 auto 1rem;
            }
            
            .loading-text {
                color: #374151;
                font-weight: 500;
            }
            
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            .loading-inline {
                display: inline-block;
                width: 16px;
                height: 16px;
                border: 2px solid #f3f4f6;
                border-top: 2px solid #3b82f6;
                border-radius: 50%;
                animation: spin 1s linear infinite;
                margin-right: 0.5rem;
            }
            
            .loading-button {
                position: relative;
                pointer-events: none;
                opacity: 0.7;
            }
            
            .loading-button .loading-inline {
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                margin: 0;
            }
        `;
        
        if (!document.querySelector('#loading-indicator-styles')) {
            const styleSheet = document.createElement('style');
            styleSheet.id = 'loading-indicator-styles';
            styleSheet.textContent = styles;
            document.head.appendChild(styleSheet);
        }
        
        document.body.appendChild(this.loadingOverlay);
    }

    setupGlobalEventListeners() {
        // Show loading for all fetch requests
        const originalFetch = window.fetch;
        window.fetch = async (...args) => {
            const url = args[0];
            
            // Don't show loading for certain requests
            if (this.shouldSkipLoading(url)) {
                return originalFetch(...args);
            }
            
            this.showLoading(`Loading...`);
            
            try {
                const response = await originalFetch(...args);
                return response;
            } finally {
                this.hideLoading();
            }
        };

        // Show loading for form submissions
        document.addEventListener('submit', (e) => {
            const form = e.target;
            if (form.classList.contains('no-loading')) return;
            
            this.showFormLoading(form);
        });

        // Show loading for AJAX requests
        if (typeof $ !== 'undefined') {
            $(document).ajaxStart(() => {
                this.showLoading('Processing...');
            }).ajaxStop(() => {
                this.hideLoading();
            });
        }
    }

    setupFormLoading() {
        // Add loading indicators to all forms
        document.querySelectorAll('form').forEach(form => {
            if (form.classList.contains('no-loading')) return;
            
            const submitButton = form.querySelector('button[type="submit"], input[type="submit"]');
            if (submitButton) {
                submitButton.addEventListener('click', () => {
                    this.showButtonLoading(submitButton);
                });
            }
        });
    }

    setupSearchLoading() {
        // Add loading to search inputs
        document.querySelectorAll('input[type="search"], input[name="q"]').forEach(input => {
            let searchTimeout;
            
            input.addEventListener('input', () => {
                clearTimeout(searchTimeout);
                
                // Show inline loading
                this.showInlineLoading(input);
                
                searchTimeout = setTimeout(() => {
                    this.hideInlineLoading(input);
                }, 500);
            });
        });
    }

    setupPaginationLoading() {
        // Add loading to pagination links
        document.querySelectorAll('a[href*="page="]').forEach(link => {
            link.addEventListener('click', (e) => {
                this.showLoading('Loading page...');
            });
        });
    }

    showLoading(message = 'Loading...') {
        if (this.loadingOverlay) {
            this.loadingOverlay.querySelector('.loading-text').textContent = message;
            this.loadingOverlay.style.display = 'flex';
        }
    }

    hideLoading() {
        if (this.loadingOverlay) {
            this.loadingOverlay.style.display = 'none';
        }
    }

    showFormLoading(form) {
        const submitButton = form.querySelector('button[type="submit"], input[type="submit"]');
        if (submitButton) {
            this.showButtonLoading(submitButton);
        }
    }

    showButtonLoading(button) {
        if (button.classList.contains('loading-button')) return;
        
        button.classList.add('loading-button');
        button.disabled = true;
        
        const originalText = button.textContent;
        button.setAttribute('data-original-text', originalText);
        button.innerHTML = '<div class="loading-inline"></div>' + originalText;
    }

    hideButtonLoading(button) {
        if (!button.classList.contains('loading-button')) return;
        
        button.classList.remove('loading-button');
        button.disabled = false;
        
        const originalText = button.getAttribute('data-original-text');
        if (originalText) {
            button.textContent = originalText;
            button.removeAttribute('data-original-text');
        }
    }

    showInlineLoading(element) {
        if (element.classList.contains('loading-inline-active')) return;
        
        element.classList.add('loading-inline-active');
        
        const loadingIcon = document.createElement('div');
        loadingIcon.className = 'loading-inline';
        loadingIcon.style.position = 'absolute';
        loadingIcon.style.right = '10px';
        loadingIcon.style.top = '50%';
        loadingIcon.style.transform = 'translateY(-50%)';
        
        element.style.position = 'relative';
        element.parentNode.appendChild(loadingIcon);
    }

    hideInlineLoading(element) {
        if (!element.classList.contains('loading-inline-active')) return;
        
        element.classList.remove('loading-inline-active');
        
        const loadingIcon = element.parentNode.querySelector('.loading-inline');
        if (loadingIcon) {
            loadingIcon.remove();
        }
    }

    shouldSkipLoading(url) {
        // Skip loading for certain URLs
        const skipPatterns = [
            '/api/health/',
            '/api/ping/',
            '/api/keep-alive/',
            '/static/',
            '/media/'
        ];
        
        return skipPatterns.some(pattern => url.includes(pattern));
    }

    // Public methods for manual control
    showPageLoading() {
        this.showLoading('Loading page...');
    }

    showSearchLoading() {
        this.showLoading('Searching...');
    }

    showFilterLoading() {
        this.showLoading('Applying filters...');
    }

    showSaveLoading() {
        this.showLoading('Saving...');
    }

    showDeleteLoading() {
        this.showLoading('Deleting...');
    }
}

// Initialize loading indicator manager
document.addEventListener('DOMContentLoaded', () => {
    window.loadingManager = new LoadingIndicatorManager();
});

// Export for use in other modules
window.LoadingIndicatorManager = LoadingIndicatorManager;
