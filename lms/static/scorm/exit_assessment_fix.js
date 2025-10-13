/**
 * SCORM Exit Assessment Button Fix
 * Handles exit button clicks within SCORM content
 * 
 * This script is injected into SCORM content frames to handle exit button clicks
 * and ensure proper data saving before exiting.
 */

(function() {
    'use strict';
    
    console.log('[Exit Assessment Fix] Script loaded');
    
    // Get the attempt ID and topic URL from parent window
    const ATTEMPT_ID = window.SCORM_ATTEMPT_ID || '';
    const TOPIC_URL = window.SCORM_TOPIC_URL || '';
    
    console.log('[Exit Assessment Fix] Attempt ID:', ATTEMPT_ID);
    console.log('[Exit Assessment Fix] Topic URL:', TOPIC_URL);
    
    /**
     * Send exit message to parent frame
     */
    function sendExitMessage() {
        console.log('[Exit Assessment Fix] Sending exit message to parent');
        try {
            // Try multiple methods to ensure the message is received
            if (window.parent && window.parent !== window) {
                // Send specific exit message types
                window.parent.postMessage({ type: 'exit' }, '*');
                window.parent.postMessage({ type: 'rise360Exit' }, '*');
                window.parent.postMessage({ type: 'scorm:exit' }, '*');
                window.parent.postMessage('exit', '*');
                window.parent.postMessage('close', '*');
            }
        } catch (e) {
            console.error('[Exit Assessment Fix] Error sending message to parent:', e);
        }
    }
    
    /**
     * Override exit functions that might be called by SCORM content
     */
    function overrideExitFunctions() {
        // Common exit function names used by various SCORM authoring tools
        const exitFunctionNames = [
            'exitCourse',
            'closeCourse',
            'quitCourse',
            'exitSCO',
            'closeSCO',
            'Exit',
            'Close',
            'Quit',
            'doExit',
            'doClose',
            'doQuit',
            'exitAssessment',
            'closeAssessment',
            'finishAssessment',
            'endAssessment'
        ];
        
        exitFunctionNames.forEach(function(funcName) {
            if (typeof window[funcName] === 'function') {
                console.log('[Exit Assessment Fix] Overriding function:', funcName);
                const originalFunc = window[funcName];
                window[funcName] = function() {
                    console.log('[Exit Assessment Fix] Intercepted call to:', funcName);
                    sendExitMessage();
                    // Call original function after sending message
                    return originalFunc.apply(this, arguments);
                };
            }
        });
    }
    
    /**
     * Monitor for exit button clicks
     */
    function monitorExitButtons() {
        // Common exit button selectors
        const exitButtonSelectors = [
            // Generic exit buttons
            '[id*="exit"]',
            '[class*="exit"]',
            '[onclick*="exit"]',
            '[onclick*="close"]',
            '[onclick*="quit"]',
            
            // Specific to various authoring tools
            '.exit-button',
            '.exitButton',
            '.exit-btn',
            '.exitBtn',
            '.close-button',
            '.closeButton',
            '.close-btn',
            '.closeBtn',
            '#exitButton',
            '#exitBtn',
            '#closeButton',
            '#closeBtn',
            
            // Articulate Storyline
            '.player-exit',
            '[data-acc-text*="Exit"]',
            '[aria-label*="Exit"]',
            '[title*="Exit"]',
            
            // Adobe Captivate
            '.playbarExit',
            '#playbarExit',
            
            // iSpring
            '.ispring-exit',
            
            // Rise 360
            '.rise-exit',
            '[data-exit-course]',
            
            // Generic text-based selectors
            'button:contains("Exit")',
            'button:contains("Close")',
            'button:contains("Quit")',
            'a:contains("Exit")',
            'a:contains("Close")',
            'a:contains("Quit")'
        ];
        
        // Click handler for exit buttons
        function handleExitClick(event) {
            console.log('[Exit Assessment Fix] Exit button clicked:', event.target);
            event.preventDefault();
            event.stopPropagation();
            sendExitMessage();
            return false;
        }
        
        // Attach listeners to existing exit buttons
        function attachExitListeners() {
            exitButtonSelectors.forEach(function(selector) {
                try {
                    const elements = document.querySelectorAll(selector);
                    elements.forEach(function(element) {
                        if (!element.hasAttribute('data-exit-listener-attached')) {
                            element.addEventListener('click', handleExitClick, true);
                            element.setAttribute('data-exit-listener-attached', 'true');
                            console.log('[Exit Assessment Fix] Attached listener to:', element);
                        }
                    });
                } catch (e) {
                    // Ignore selector errors (e.g., :contains is not standard)
                }
            });
            
            // Also check for elements with exit-related text
            const allButtons = document.querySelectorAll('button, a, div[role="button"], span[role="button"]');
            allButtons.forEach(function(element) {
                const text = element.textContent || element.innerText || '';
                const ariaLabel = element.getAttribute('aria-label') || '';
                const title = element.getAttribute('title') || '';
                
                if (/exit|close|quit|finish/i.test(text + ariaLabel + title)) {
                    if (!element.hasAttribute('data-exit-listener-attached')) {
                        element.addEventListener('click', handleExitClick, true);
                        element.setAttribute('data-exit-listener-attached', 'true');
                        console.log('[Exit Assessment Fix] Attached listener to text-based element:', element);
                    }
                }
            });
        }
        
        // Initial attachment
        attachExitListeners();
        
        // Monitor for dynamic content changes
        const observer = new MutationObserver(function(mutations) {
            // Debounce to avoid excessive processing
            clearTimeout(window.exitButtonDebounce);
            window.exitButtonDebounce = setTimeout(attachExitListeners, 100);
        });
        
        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
        
        console.log('[Exit Assessment Fix] Exit button monitoring active');
    }
    
    /**
     * Initialize when DOM is ready
     */
    function initialize() {
        console.log('[Exit Assessment Fix] Initializing...');
        
        // Override exit functions
        overrideExitFunctions();
        
        // Start monitoring for exit buttons
        monitorExitButtons();
        
        // Also intercept window.close calls
        const originalClose = window.close;
        window.close = function() {
            console.log('[Exit Assessment Fix] Intercepted window.close()');
            sendExitMessage();
            // Don't actually close the window - let parent handle it
            return false;
        };
        
        // Intercept unload events
        window.addEventListener('beforeunload', function(event) {
            console.log('[Exit Assessment Fix] beforeunload event triggered');
            sendExitMessage();
        });
        
        console.log('[Exit Assessment Fix] Initialization complete');
    }
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialize);
    } else {
        // DOM already loaded
        initialize();
    }
    
    // Also initialize after a delay to catch late-loading content
    setTimeout(initialize, 1000);
    setTimeout(initialize, 3000);
    
})();
