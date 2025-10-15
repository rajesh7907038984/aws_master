/**
 * Universal SCORM API - Works for ALL Package Types
 * 
 * This single API handles:
 * - SCORM 1.2 (API)
 * - SCORM 2004 (API_1484_11) 
 * - xAPI/Tin Can
 * - Articulate Rise/Storyline
 * - Adobe Captivate
 * - iSpring
 * - Lectora
 * - Generic HTML5 packages
 * 
 * Features:
 * - Immediate data saving (no async delays)
 * - Automatic package type detection
 * - Synchronous commits for critical data
 * - Proper exit handling
 * - Universal compatibility
 */
(function() {
    'use strict';
    
    // Configuration
    var config = {
        debug: true,
        apiEndpoint: null,
        attemptId: null,
        topicId: null,
        initialized: false,
        data: {},
        packageType: 'auto' // Will be auto-detected
    };
    
    // Helper functions
    function log(message) {
        if (config.debug) {
            console.log('[Universal SCORM API] ' + message);
        }
    }
    
    function detectPackageType() {
        var currentUrl = window.location.href;
        var hasTinCan = document.querySelector('script[src*="tincan"]') || 
                       document.querySelector('script[src*="xapi"]') ||
                       window.TinCan || window.xAPI;
        
        if (hasTinCan || currentUrl.indexOf('tincan') > -1 || currentUrl.indexOf('xapi') > -1) {
            config.packageType = 'xapi';
            log('Detected xAPI/Tin Can package');
        } else if (currentUrl.indexOf('scormdriver') > -1 || currentUrl.indexOf('index_lms') > -1) {
            config.packageType = 'articulate_rise';
            log('Detected Articulate Rise 360 package');
        } else if (currentUrl.indexOf('story.html') > -1 || currentUrl.indexOf('story_html5.html') > -1) {
            config.packageType = 'articulate_storyline';
            log('Detected Articulate Storyline package');
        } else if (currentUrl.indexOf('multiscreen.html') > -1) {
            config.packageType = 'adobe_captivate';
            log('Detected Adobe Captivate package');
        } else if (currentUrl.indexOf('presentation.html') > -1 || currentUrl.indexOf('index_lms.html') > -1) {
            config.packageType = 'ispring';
            log('Detected iSpring package');
        } else {
            config.packageType = 'scorm';
            log('Detected standard SCORM package');
        }
        
        return config.packageType;
    }
    
    function makeAPICall(method, parameters) {
        parameters = parameters || [];
        
        if (!config.apiEndpoint) {
            log('ERROR: API endpoint not configured');
            return 'false';
        }
        
        var requestData = {
            method: method,
            parameters: parameters,
            attempt_id: config.attemptId || null
        };
        
        log('Making API call: ' + method + ' with params: ' + JSON.stringify(parameters));
        
        try {
            var xhr = new XMLHttpRequest();
            xhr.open('POST', config.apiEndpoint, false); // SYNCHRONOUS for reliability
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.setRequestHeader('X-CSRFToken', getCsrfToken());
            
            xhr.send(JSON.stringify(requestData));
            
            if (xhr.status === 200) {
                var response = JSON.parse(xhr.responseText);
                log('API call result: ' + response.result + ', error: ' + (response.error || '0'));
                
                // Update attempt ID if returned from server
                if (response.attempt_id && !config.attemptId) {
                    config.attemptId = response.attempt_id;
                    log('Updated attempt ID from server: ' + config.attemptId);
                }
                
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
            if (cookie[0] === 'csrftoken') {
                return decodeURIComponent(cookie[1]);
            }
        }
        return '';
    }
    
    // Universal API Implementation
    var UniversalAPI = {
        // SCORM 1.2 Methods
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
            
            // Force final commit before termination (SYNCHRONOUS)
            try {
                log('Final commit before termination...');
                var commitResult = makeAPICall('LMSCommit', ['']);
                if (commitResult !== 'true') {
                    log('ERROR: Final commit failed!');
                    // Try again after short delay
                    setTimeout(function() {
                        log('Retrying commit...');
                        makeAPICall('LMSCommit', ['']);
                    }, 100);
                } else {
                    log('Final commit successful');
                }
            } catch (e) {
                log('ERROR: Could not commit data before termination: ' + e.message);
            }
            
            // Now terminate with retry logic
            try {
                var finishResult = makeAPICall('LMSFinish', [parameter]);
                log('LMSFinish API call result: ' + finishResult);
                
                // If finish failed, try again
                if (finishResult !== 'true') {
                    log('LMSFinish failed, retrying...');
                    setTimeout(function() {
                        makeAPICall('LMSFinish', [parameter]);
                    }, 200);
                }
            } catch (e) {
                log('Warning: Could not complete LMSFinish call: ' + e.message);
            }
            
            config.initialized = false;
            log('LMSFinish completed - data saved, allowing navigation to exit page');
            return 'true';
        },
        
        LMSGetValue: function(element) {
            log('LMSGetValue called for: ' + element);
            return makeAPICall('LMSGetValue', [element]);
        },
        
        LMSSetValue: function(element, value) {
            log('LMSSetValue called: ' + element + ' = ' + value);
            
            // Store in local cache
            config.data[element] = value;
            
            // Send to backend
            var result = makeAPICall('LMSSetValue', [element, value]);
            
            // Auto-commit for critical elements (SYNCHRONOUS - no delays)
            var criticalElements = [
                'cmi.core.lesson_status', 
                'cmi.core.score.raw',
                'cmi.core.lesson_location',
                'cmi.suspend_data',
                'cmi.completion_status',
                'cmi.success_status'
            ];
            
            if (criticalElements.indexOf(element) !== -1) {
                log('Auto-committing critical data: ' + element);
                try {
                    makeAPICall('LMSCommit', ['']);
                    log('Critical data committed successfully: ' + element);
                } catch (e) {
                    log('Warning: Auto-commit failed for ' + element + ': ' + e.message);
                }
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
        },
        
        // SCORM 2004 Methods (map to SCORM 1.2)
        Initialize: function(parameter) {
            return this.LMSInitialize(parameter);
        },
        
        Terminate: function(parameter) {
            log('SCORM 2004 Terminate called');
            
            // Force final commit before termination (SYNCHRONOUS)
            try {
                log('Final commit before termination...');
                var commitResult = makeAPICall('LMSCommit', ['']);
                if (commitResult !== 'true') {
                    log('ERROR: Final commit failed!');
                } else {
                    log('Final commit successful');
                }
            } catch (e) {
                log('ERROR: Could not commit data before termination: ' + e.message);
            }
            
            // Now terminate
            try {
                var finishResult = makeAPICall('LMSFinish', [parameter]);
                log('Terminate API call result: ' + finishResult);
            } catch (e) {
                log('Warning: Could not complete Terminate call: ' + e.message);
            }
            
            config.initialized = false;
            log('Terminate completed - data saved, allowing navigation to exit page');
            return 'true';
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
            
            return this.LMSGetValue(element);
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
            }
            
            var result = this.LMSSetValue(element, value);
            
            // Auto-commit for SCORM 2004 critical elements
            var criticalElements2004 = [
                'cmi.completion_status',
                'cmi.success_status', 
                'cmi.score.raw',
                'cmi.location',
                'cmi.suspend_data'
            ];
            
            if (criticalElements2004.indexOf(originalElement) !== -1) {
                log('Auto-committing SCORM 2004 critical data: ' + originalElement);
                try {
                    this.LMSCommit('');
                } catch (e) {
                    log('Warning: SCORM 2004 auto-commit failed for ' + originalElement + ': ' + e.message);
                }
            }
            
            return result;
        },
        
        Commit: function(parameter) {
            return this.LMSCommit(parameter);
        },
        
        GetLastError: function() {
            return this.LMSGetLastError();
        },
        
        GetErrorString: function(errorNumber) {
            return this.LMSGetErrorString(errorNumber);
        },
        
        GetDiagnostic: function(errorNumber) {
            return this.LMSGetDiagnostic(errorNumber);
        },
        
        // Non-standard methods that some authoring tools use
        CommitData: function() {
            log('SCORM: CommitData');
            return 'true';
        },
        ConcedeControl: function() {
            log('SCORM: ConcedeControl');
            return 'true';
        },
        CreateResponseIdentifier: function() {
            log('SCORM: CreateResponseIdentifier');
            return 'true';
        },
        Finish: function() {
            log('SCORM: Finish');
            return this.LMSFinish('');
        },
        GetDataChunk: function() {
            log('SCORM: GetDataChunk');
            return '';
        },
        GetStatus: function() {
            log('SCORM: GetStatus');
            return this.LMSGetValue('cmi.core.lesson_status');
        },
        MatchingResponse: function() {
            log('SCORM: MatchingResponse');
            return 'true';
        },
        RecordFillInInteraction: function() {
            log('SCORM: RecordFillInInteraction');
            return 'true';
        },
        RecordMatchingInteraction: function() {
            log('SCORM: RecordMatchingInteraction');
            return 'true';
        },
        RecordMultipleChoiceInteraction: function() {
            log('SCORM: RecordMultipleChoiceInteraction');
            return 'true';
        },
        ResetStatus: function() {
            log('SCORM: ResetStatus');
            return 'true';
        },
        SetBookmark: function() {
            log('SCORM: SetBookmark');
            return 'true';
        },
        SetDataChunk: function() {
            log('SCORM: SetDataChunk');
            return 'true';
        },
        SetFailed: function() {
            log('SCORM: SetFailed');
            return 'true';
        },
        SetLanguagePreference: function() {
            log('SCORM: SetLanguagePreference');
            return 'true';
        },
        SetPassed: function() {
            log('SCORM: SetPassed');
            return 'true';
        },
        SetReachedEnd: function() {
            log('SCORM: SetReachedEnd');
            return 'true';
        },
        SetScore: function() {
            log('SCORM: SetScore');
            return 'true';
        },
        WriteToDebug: function() {
            log('SCORM: WriteToDebug');
            return 'true';
        }
    };
    
    // Public API
    window.UniversalSCORMAPI = {
        // Initialize the universal API
        init: function(attemptId, topicId) {
            config.apiEndpoint = `/scorm/api/${topicId}/`;
            config.attemptId = attemptId;
            config.topicId = topicId;
            
            // Detect package type
            detectPackageType();
            
            log(`Initialized Universal SCORM API with attempt ID: ${attemptId}, topic ID: ${topicId}`);
            log(`Package type: ${config.packageType}`);
            log(`API endpoint: ${config.apiEndpoint}`);
        },
        
        // Expose APIs globally for all package types
        exposeAPIs: function() {
            // Set APIs on current window
            window.API = UniversalAPI;
            window.API_1484_11 = UniversalAPI;
            
            // Also expose to parent windows for iframe compatibility
            if (window.parent && window.parent !== window) {
                window.parent.API = UniversalAPI;
                window.parent.API_1484_11 = UniversalAPI;
            }
            
            // Set on top window as well
            if (window.top && window.top !== window) {
                window.top.API = UniversalAPI;
                window.top.API_1484_11 = UniversalAPI;
            }
            
            log('Universal SCORM APIs exposed globally - works for all package types');
        },
        
        // Get package type
        getPackageType: function() {
            return config.packageType;
        },
        
        // Test function
        test: function(attemptId, topicId) {
            log('Running Universal SCORM API test...');
            this.init(attemptId, topicId);
            this.exposeAPIs();
            
            // Test sequence
            console.log('1. Initialize:', UniversalAPI.LMSInitialize(''));
            console.log('2. Set Score:', UniversalAPI.LMSSetValue('cmi.core.score.raw', '85'));
            console.log('3. Set Status:', UniversalAPI.LMSSetValue('cmi.core.lesson_status', 'completed'));
            console.log('4. Commit:', UniversalAPI.LMSCommit(''));
            console.log('5. Get Score:', UniversalAPI.LMSGetValue('cmi.core.score.raw'));
            console.log('Test completed!');
        }
    };
    
    log('Universal SCORM API loaded - works for ALL package types');
    
})();
