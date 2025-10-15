/**
 * Simple SCORM API Wrapper (pipwerks-style)
 * Intercepts SCORM calls and forwards them to backend via REST API
 */

(function() {
    'use strict';
    
    // Configuration
    var config = {
        version: "1.2",
        debug: true,
        apiEndpoint: null, // Will be set dynamically
        initialized: false,
        data: {}
    };
    
    // Helper functions
    function log(message) {
        if (config.debug) {
            console.log('[SCORM API Wrapper] ' + message);
        }
    }
    
    function makeAPICall(method, parameters) {
        parameters = parameters || [];
        
        if (!config.apiEndpoint) {
            log('ERROR: API endpoint not configured');
            return 'false';
        }
        
        var requestData = {
            method: method,
            parameters: parameters
        };
        
        log('Making API call: ' + method + ' with params: ' + JSON.stringify(parameters));
        
        // Use XMLHttpRequest for SCORM compatibility
        try {
            var xhr = new XMLHttpRequest();
            xhr.open('POST', config.apiEndpoint, false); // Keep synchronous for SCORM standard compliance
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.setRequestHeader('X-CSRFToken', getCsrfToken());
            
            xhr.send(JSON.stringify(requestData));
            
            if (xhr.status === 200) {
                var response = JSON.parse(xhr.responseText);
                log('API call result: ' + response.result + ', error: ' + (response.error_code || '0'));
                return response.result || 'false';
            } else {
                log('API call failed: HTTP ' + xhr.status);
                return 'false';
            }
        } catch (error) {
            log('API call error: ' + error.message);
            return 'false';
        }
    }
    
    function getCsrfToken() {
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var cookie = cookies[i].trim().split('=');
            var name = cookie[0];
            var value = cookie[1];
            if (name === 'csrftoken') {
                return decodeURIComponent(value);
            }
        }
        return '';
    }
    
    // SCORM 1.2 API Implementation
    var API = {
        LMSInitialize: function(parameter) {
            log('LMSInitialize called');
            var result = makeAPICall('LMSInitialize', [parameter]);
            if (result === 'true') {
                config.initialized = true;
            }
            return result;
        },
        
        LMSFinish: function(parameter) {
            log('LMSFinish called');
            
            // CRITICAL FIX: Force commit before termination to ensure data is saved
            try {
                log('Auto-committing data before termination...');
                makeAPICall('LMSCommit', ['']);
                log('Data committed successfully before termination');
            } catch (e) {
                log('Warning: Could not commit data before termination: ' + e.message);
            }
            
            var result = makeAPICall('LMSFinish', [parameter]);
            config.initialized = false;
            
            // SCORM EXIT FIX: Check if content initiated exit
            if (result === 'true') {
                setTimeout(function() {
                    checkForContentExit();
                }, 500);
            }
            
            return result;
        },
        
        LMSGetValue: function(element) {
            log('LMSGetValue called for: ' + element);
            return makeAPICall('LMSGetValue', [element]);
        },
        
        LMSSetValue: function(element, value) {
            log('LMSSetValue called: ' + element + ' = ' + value);
            
            // Store in local cache for immediate access
            config.data[element] = value;
            
            // Send to backend
            var result = makeAPICall('LMSSetValue', [element, value]);
            
            // CRITICAL FIX: Enhanced auto-commit for critical data elements
            var criticalElements = [
                'cmi.core.lesson_status', 
                'cmi.core.score.raw',
                'cmi.core.lesson_location',
                'cmi.suspend_data',
                'cmi.core.exit',
                'cmi.completion_status',
                'cmi.success_status',
                'cmi.location'
            ];
            
            if (criticalElements.indexOf(element) !== -1) {
                log('Auto-committing critical data: ' + element);
                setTimeout(function() {
                    try {
                        var commitResult = makeAPICall('LMSCommit', ['']);
                        log('Critical data auto-commit result: ' + commitResult + ' for ' + element);
                    } catch (e) {
                        log('Warning: Auto-commit failed for ' + element + ': ' + e.message);
                    }
                }, 50); // Reduced delay for faster persistence
            }
            
            return result;
        },
        
        LMSCommit: function(parameter) {
            log('LMSCommit called - saving data to backend');
            return makeAPICall('LMSCommit', [parameter]);
        },
        
        LMSGetLastError: function() {
            return makeAPICall('LMSGetLastError', []);
        },
        
        LMSGetErrorString: function(errorNumber) {
            return makeAPICall('LMSGetErrorString', [errorNumber]);
        },
        
        LMSGetDiagnostic: function(errorNumber) {
            return makeAPICall('LMSGetDiagnostic', [errorNumber]);
        }
    };
    
    // SCORM 2004 API (API_1484_11) - maps to SCORM 1.2 calls
    var API_1484_11 = {
        Initialize: function(parameter) {
            return API.LMSInitialize(parameter);
        },
        
        Terminate: function(parameter) {
            log('Terminate (SCORM 2004) called');
            
            // CRITICAL FIX: Force commit before termination (SCORM 2004)
            try {
                log('Auto-committing data before SCORM 2004 termination...');
                API.LMSCommit('');
                log('Data committed successfully before SCORM 2004 termination');
            } catch (e) {
                log('Warning: Could not commit data before SCORM 2004 termination: ' + e.message);
            }
            
            var result = API.LMSFinish(parameter);
            
            // SCORM EXIT FIX: Check if content initiated exit
            if (result === 'true') {
                setTimeout(function() {
                    checkForContentExit();
                }, 500);
            }
            
            return result;
        },
        
        GetValue: function(element) {
            // Map SCORM 2004 elements to SCORM 1.2
            if (element.startsWith('cmi.learner_')) {
                element = element.replace('cmi.learner_', 'cmi.core.student_');
            } else if (element === 'cmi.location') {
                element = 'cmi.core.lesson_location';
            } else if (element === 'cmi.completion_status') {
                element = 'cmi.core.lesson_status';
            }
            
            return API.LMSGetValue(element);
        },
        
        SetValue: function(element, value) {
            log('SCORM 2004 SetValue called: ' + element + ' = ' + value);
            
            // Map SCORM 2004 elements to SCORM 1.2
            var originalElement = element;
            if (element.startsWith('cmi.learner_')) {
                element = element.replace('cmi.learner_', 'cmi.core.student_');
            } else if (element === 'cmi.location') {
                element = 'cmi.core.lesson_location';
            } else if (element === 'cmi.completion_status') {
                element = 'cmi.core.lesson_status';
                // Map SCORM 2004 completion_status to SCORM 1.2 lesson_status
                if (value === 'completed') {
                    value = 'completed';
                } else if (value === 'incomplete') {
                    value = 'incomplete';
                }
            }
            
            var result = API.LMSSetValue(element, value);
            
            // CRITICAL FIX: Auto-commit for SCORM 2004 critical elements
            var criticalElements2004 = [
                'cmi.completion_status',
                'cmi.success_status', 
                'cmi.score.raw',
                'cmi.location',
                'cmi.suspend_data',
                'cmi.exit'
            ];
            
            if (criticalElements2004.indexOf(originalElement) !== -1) {
                log('Auto-committing SCORM 2004 critical data: ' + originalElement);
                setTimeout(function() {
                    try {
                        var commitResult = API.LMSCommit('');
                        log('SCORM 2004 critical data auto-commit result: ' + commitResult + ' for ' + originalElement);
                    } catch (e) {
                        log('Warning: SCORM 2004 auto-commit failed for ' + originalElement + ': ' + e.message);
                    }
                }, 50);
            }
            
            return result;
        },
        
        Commit: function(parameter) {
            return API.LMSCommit(parameter);
        },
        
        GetLastError: function() {
            return API.LMSGetLastError();
        },
        
        GetErrorString: function(errorNumber) {
            return API.LMSGetErrorString(errorNumber);
        },
        
        GetDiagnostic: function(errorNumber) {
            return API.LMSGetDiagnostic(errorNumber);
        }
    };
    
    // Public API
    window.ScormAPIWrapper = {
        // Initialize the wrapper with attempt ID
        init: function(attemptId) {
            config.apiEndpoint = `/scorm/api/${attemptId}/`;
            log(`Initialized with attempt ID: ${attemptId}, endpoint: ${config.apiEndpoint}`);
        },
        
        // Get API objects
        getAPI: function() {
            return API;
        },
        
        getAPI_1484_11: function() {
            return API_1484_11;
        },
        
        // Expose APIs globally for SCORM content with enhanced Storyline support
        exposeAPIs: function() {
            // Primary API exposure
            window.API = API;
            window.API_1484_11 = API_1484_11;
            
            // Enhanced Storyline support - expose to multiple contexts
            this.exposeStorylineAPIs();
            
            log('APIs exposed globally - API available:', typeof window.API, 'API_1484_11 available:', typeof window.API_1484_11);
        },
        
        // Enhanced API exposure specifically for Articulate Storyline
        exposeStorylineAPIs: function() {
            var self = this;
            
            // Function to safely expose APIs to a window object
            function safeExposeAPIs(targetWindow, context) {
                try {
                    if (targetWindow && targetWindow !== window) {
                        targetWindow.API = API;
                        targetWindow.API_1484_11 = API_1484_11;
                        
                        // Storyline sometimes looks for these specific properties
                        targetWindow.scormAPI = API;
                        targetWindow.SCORM_API = API;
                        
                        log('APIs exposed to ' + context + ' window');
                        return true;
                    }
                    return false;
                } catch (e) {
                    log('Failed to expose APIs to ' + context + ': ' + e.message);
                    return false;
                }
            }
            
            // Expose to parent windows (critical for iframes)
            safeExposeAPIs(window.parent, 'parent');
            safeExposeAPIs(window.top, 'top');
            safeExposeAPIs(window.opener, 'opener');
            
            // Document-level exposure for some Storyline versions
            try {
                if (document) {
                    document.API = API;
                    document.API_1484_11 = API_1484_11;
                    log('APIs exposed to document object');
                }
            } catch (e) {
                log('Could not expose APIs to document: ' + e.message);
            }
            
            // Set up periodic re-exposure for dynamic Storyline content
            var exposureCount = 0;
            var maxExposures = 10;
            var exposureInterval = setInterval(function() {
                exposureCount++;
                
                // Re-expose APIs to ensure they're available
                safeExposeAPIs(window.parent, 'parent-refresh');
                safeExposeAPIs(window.top, 'top-refresh');
                
                // Ensure current window still has APIs
                if (!window.API) {
                    window.API = API;
                    window.API_1484_11 = API_1484_11;
                }
                
                // Stop after max attempts or when we're confident APIs are stable
                if (exposureCount >= maxExposures || 
                    (window.API && window.parent && window.parent.API && window.top && window.top.API)) {
                    clearInterval(exposureInterval);
                    log('Storyline API exposure complete after ' + exposureCount + ' attempts');
                }
            }, 250); // Check every 250ms
            
            // Create a global API finder function that Storyline can use
            window.getAPI = function() {
                return API;
            };
            
            window.getAPIHandle = function() {
                return API;
            };
            
            // Some Storyline versions look for these
            window.findAPI = function() {
                return API;
            };
            
            window.scanForAPI = function() {
                return API;
            };
            
            log('Enhanced Storyline API support initialized');
        },
        
        // Test function
        test: function(attemptId) {
            log('Running SCORM API test...');
            this.init(attemptId);
            this.exposeAPIs();
            
            // Test sequence
            console.log('1. Initialize:', API.LMSInitialize(''));
            console.log('2. Set Score:', API.LMSSetValue('cmi.core.score.raw', '85'));
            console.log('3. Set Status:', API.LMSSetValue('cmi.core.lesson_status', 'completed'));
            console.log('4. Commit:', API.LMSCommit(''));
            console.log('5. Get Score:', API.LMSGetValue('cmi.core.score.raw'));
            console.log('Test completed!');
        }
    };
    
    // SCORM EXIT FIX: Function to check if content wants to exit
    function checkForContentExit() {
        if (!config.apiEndpoint) return;
        
        try {
            // ENHANCED: Check multiple exit indicators for different authoring tools
            var exitCheck = makeAPICall('LMSGetValue', ['_content_initiated_exit']);
            log('🔍 Checking content exit flag: "' + exitCheck + '"');
            
            // Also check standard SCORM exit elements
            var scormExit = makeAPICall('LMSGetValue', ['cmi.core.exit']);
            var lessonStatus = makeAPICall('LMSGetValue', ['cmi.core.lesson_status']);
            var completionStatus = makeAPICall('LMSGetValue', ['cmi.completion_status']);
            var successStatus = makeAPICall('LMSGetValue', ['cmi.success_status']);
            
            log('🔍 SCORM exit indicators - exit: "' + scormExit + '", lesson_status: "' + lessonStatus + '", completion: "' + completionStatus + '", success: "' + successStatus + '"');
            
            // ENHANCED: Package-type specific exit detection
            var shouldExit = false;
            var exitReason = '';
            
            // Method 1: Explicit content-initiated exit flag (most reliable)
            if (exitCheck === 'true') {
                shouldExit = true;
                exitReason = 'content_initiated_exit_flag';
                log('✅ Exit detected: Content explicitly requested exit via _content_initiated_exit flag');
            }
            
            // CRITICAL FIX: Method 1a - Detect when SCORM content has completed and is ready to exit
            // This handles cases where content completes internally but doesn't set the exit flag
            else if (completionStatus === 'completed' || successStatus === 'passed' || lessonStatus === 'completed' || lessonStatus === 'passed') {
                // Check if this is a recent completion (not stale data from previous session)
                var currentTime = new Date().getTime();
                var lastExitCheck = window.scormLastExitCheck || 0;
                var timeSinceLastCheck = currentTime - lastExitCheck;
                
                // If we haven't checked recently, this might be a fresh completion
                if (timeSinceLastCheck > 2000) { // 2 seconds
                    shouldExit = true;
                    exitReason = 'fresh_completion_detected';
                    log('✅ Exit detected: Fresh completion status detected (' + (completionStatus || successStatus || lessonStatus) + ')');
                    window.scormLastExitCheck = currentTime;
                }
            }
            
            // Method 1b: Check if content is signaling exit through suspend data or location
            else {
                var suspendData = makeAPICall('LMSGetValue', ['cmi.suspend_data']);
                var lessonLocation = makeAPICall('LMSGetValue', ['cmi.core.lesson_location']) || makeAPICall('LMSGetValue', ['cmi.location']);
                
                // Look for exit indicators in suspend data or location
                if (suspendData && (suspendData.toLowerCase().includes('exit') || suspendData.toLowerCase().includes('complete') || suspendData.toLowerCase().includes('finished'))) {
                    shouldExit = true;
                    exitReason = 'suspend_data_exit_signal';
                    log('✅ Exit detected: Exit signal in suspend data');
                }
                else if (lessonLocation && (lessonLocation.toLowerCase().includes('exit') || lessonLocation.toLowerCase().includes('end') || lessonLocation.toLowerCase().includes('complete'))) {
                    shouldExit = true;
                    exitReason = 'location_exit_signal';
                    log('✅ Exit detected: Exit signal in lesson location');
                }
            }
            
            // Method 2: SCORM exit element indicates user wants to leave
            if (!shouldExit && scormExit && scormExit !== '' && scormExit !== 'suspend') {
                // 'logout', 'normal', or 'time-out' all indicate user wants to exit
                shouldExit = true;
                exitReason = 'scorm_exit_element_' + scormExit;
                log('✅ Exit detected: SCORM exit element set to "' + scormExit + '"');
            }
            
            // Method 3: Completion-based exit (for packages that auto-exit on completion)
            if (!shouldExit && (completionStatus === 'completed' || lessonStatus === 'passed' || lessonStatus === 'completed')) {
                // Check if this is genuinely a fresh completion by looking at other indicators
                var hasExitIntent = (exitCheck === 'true' || scormExit === 'normal' || scormExit === 'logout');
                
                if (hasExitIntent) {
                    shouldExit = true;
                    exitReason = 'completion_with_exit_intent';
                    log('✅ Exit detected: Completion with exit intent (' + (completionStatus || lessonStatus) + ')');
                }
            }
            
            // Method 4: scormcontent/ specific patterns (Articulate Rise, etc.)
            if (!shouldExit && completionStatus === 'completed') {
                // For scormcontent/ packages, completion alone is often sufficient for exit
                // These packages typically set completion_status when user finishes
                shouldExit = true;
                exitReason = 'scormcontent_completion';
                log('✅ Exit detected: scormcontent/ package completion');
            }
            
            if (shouldExit) {
                log('🚪 Content initiated exit detected - starting navigation process');
                
                // CRITICAL FIX: Force final commit before exit to ensure all data is saved
                try {
                    log('💾 Final commit before exit...');
                    var finalCommitResult = makeAPICall('LMSCommit', ['']);
                    log('✅ Final commit result: ' + finalCommitResult);
                    
                    // Also try to properly terminate the session
                    var terminateResult = makeAPICall('LMSFinish', ['']);
                    log('✅ Final terminate result: ' + terminateResult);
                    
                } catch (e) {
                    log('❌ Error during final data save: ' + e.message);
                }
                
                // Clear the exit flag after saving data
                var clearResult = makeAPICall('LMSSetValue', ['_content_initiated_exit', 'false']);
                log('🧹 Exit flag cleared, result: ' + clearResult);
                
                // Enhanced navigation with multiple methods
                var navigationSuccess = false;
                
                // Method 1: Try parent window exitCourse
                try {
                    if (window.parent && window.parent.exitCourse && typeof window.parent.exitCourse === 'function') {
                        log('🎯 Attempting parent.exitCourse()...');
                        window.parent.exitCourse();
                        navigationSuccess = true;
                        return;
                    }
                } catch (e) {
                    log('❌ Parent exitCourse failed: ' + e.message);
                }
                
                // Method 2: Try top window exitCourse
                try {
                    if (window.top && window.top.exitCourse && typeof window.top.exitCourse === 'function') {
                        log('🔝 Attempting top.exitCourse()...');
                        window.top.exitCourse();
                        navigationSuccess = true;
                        return;
                    }
                } catch (e) {
                    log('❌ Top exitCourse failed: ' + e.message);
                }
                
                // Method 3: Direct URL navigation
                if (!navigationSuccess) {
                    try {
                        var urlParts = window.location.pathname.split('/');
                        var topicId = null;
                        for (var i = 0; i < urlParts.length; i++) {
                            if (urlParts[i] === 'scorm' && urlParts[i+1] === 'view' && urlParts[i+2]) {
                                topicId = urlParts[i+2];
                                break;
                            }
                        }
                        
                        if (topicId) {
                            var topicUrl = '/courses/topic/' + topicId + '/';
                            log('🌐 Direct navigation to: ' + topicUrl);
                            window.top.location.href = topicUrl;
                            navigationSuccess = true;
                        } else {
                            log('🌐 Fallback navigation to courses list');
                            window.top.location.href = '/courses/';
                            navigationSuccess = true;
                        }
                    } catch (e) {
                        log('❌ Direct navigation failed: ' + e.message);
                    }
                }
                
                // Method 4: Final fallback alert
                if (!navigationSuccess) {
                    log('🚨 All navigation methods failed - showing user alert');
                    alert('Course exit requested by content. Please manually close this window to return to the course.');
                }
            }
        } catch (e) {
            log('Error checking for content exit: ' + e.message);
        }
    }
    
    // Expose the exit check function globally so the player can use it
    window.checkForContentExit = checkForContentExit;
    
    log('SCORM API Wrapper loaded successfully');
    
})();
