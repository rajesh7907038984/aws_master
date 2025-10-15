/**
 * SCORM + xAPI Wrapper
 * Provides unified API for both SCORM and xAPI/Tin Can packages
 * Automatically detects package type and uses appropriate API
 */
(function() {
    'use strict';
    
    // Configuration
    var config = {
        version: "1.2",
        debug: true,
        apiEndpoint: null,
        xapiEndpoint: null,
        initialized: false,
        data: {},
        packageType: 'scorm' // 'scorm' or 'xapi'
    };
    
    // Helper functions
    function log(message) {
        if (config.debug) {
            console.log('[SCORM/xAPI Wrapper] ' + message);
        }
    }
    
    function detectPackageType() {
        // Detect if this is an xAPI/Tin Can package
        var currentUrl = window.location.href;
        var hasTinCan = document.querySelector('script[src*="tincan"]') || 
                       document.querySelector('script[src*="xapi"]') ||
                       window.TinCan || window.xAPI;
        
        if (hasTinCan || currentUrl.indexOf('tincan') > -1 || currentUrl.indexOf('xapi') > -1) {
            config.packageType = 'xapi';
            log('Detected xAPI/Tin Can package');
        } else {
            config.packageType = 'scorm';
            log('Detected SCORM package');
        }
        
        return config.packageType;
    }
    
    function makeAPICall(method, parameters) {
        parameters = parameters || [];
        
        if (config.packageType === 'xapi') {
            return makeXAPICall(method, parameters);
        } else {
            return makeSCORMCall(method, parameters);
        }
    }
    
    function makeSCORMCall(method, parameters) {
        if (!config.apiEndpoint) {
            log('ERROR: API endpoint not configured');
            return 'false';
        }
        
        var requestData = {
            method: method,
            parameters: parameters,
            attempt_id: config.attemptId || null
        };
        
        log('Making SCORM API call: ' + method + ' with params: ' + JSON.stringify(parameters) + ', attempt_id: ' + (config.attemptId || 'null'));
        
        try {
            var xhr = new XMLHttpRequest();
            xhr.open('POST', config.apiEndpoint, false);
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.setRequestHeader('X-CSRFToken', getCsrfToken());
            
            xhr.send(JSON.stringify(requestData));
            
            if (xhr.status === 200) {
                var response = JSON.parse(xhr.responseText);
                log('SCORM API call result: ' + response.result + ', error: ' + (response.error_code || '0') + ', attempt_id: ' + (response.attempt_id || 'null'));
                
                // Update attempt ID if returned from server
                if (response.attempt_id && !config.attemptId) {
                    config.attemptId = response.attempt_id;
                    log('Updated attempt ID from server: ' + config.attemptId);
                }
                
                return response.result || 'false';
            } else {
                log('SCORM API call failed: HTTP ' + xhr.status);
                return 'false';
            }
        } catch (error) {
            log('SCORM API call error: ' + error.message);
            return 'false';
        }
    }
    
    function makeXAPICall(method, parameters) {
        if (!config.xapiEndpoint) {
            log('ERROR: xAPI endpoint not configured');
            return 'false';
        }
        
        // Convert SCORM calls to xAPI statements
        var statement = convertSCORMToXAPI(method, parameters);
        
        log('Making xAPI call: ' + method + ' with statement: ' + JSON.stringify(statement));
        
        try {
            var xhr = new XMLHttpRequest();
            xhr.open('POST', config.xapiEndpoint, false);
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.setRequestHeader('X-CSRFToken', getCsrfToken());
            
            xhr.send(JSON.stringify(statement));
            
            if (xhr.status === 200) {
                var response = JSON.parse(xhr.responseText);
                log('xAPI call result: ' + response.success);
                return response.success ? 'true' : 'false';
            } else {
                log('xAPI call failed: HTTP ' + xhr.status);
                return 'false';
            }
        } catch (error) {
            log('xAPI call error: ' + error.message);
            return 'false';
        }
    }
    
    function convertSCORMToXAPI(method, parameters) {
        var statement = {
            "id": generateUUID(),
            "actor": {
                "objectType": "Agent",
                "name": "Learner",
                "mbox": "mailto:learner@example.com"
            },
            "verb": {
                "id": "http://adlnet.gov/expapi/verbs/experienced",
                "display": {"en-US": "experienced"}
            },
            "object": {
                "id": window.location.href,
                "objectType": "Activity",
                "definition": {
                    "name": {"en-US": "SCORM Activity"}
                }
            },
            "timestamp": new Date().toISOString()
        };
        
        // Map SCORM methods to xAPI verbs
        if (method === 'LMSInitialize' || method === 'Initialize') {
            statement.verb.id = "http://adlnet.gov/expapi/verbs/attempted";
            statement.verb.display = {"en-US": "attempted"};
        } else if (method === 'LMSFinish' || method === 'Terminate') {
            statement.verb.id = "http://adlnet.gov/expapi/verbs/completed";
            statement.verb.display = {"en-US": "completed"};
        } else if (method === 'LMSSetValue' || method === 'SetValue') {
            var element = parameters[0];
            var value = parameters[1];
            
            if (element === 'cmi.core.lesson_status' || element === 'cmi.completion_status') {
                if (value === 'completed' || value === 'passed') {
                    statement.verb.id = "http://adlnet.gov/expapi/verbs/completed";
                    statement.verb.display = {"en-US": "completed"};
                } else if (value === 'failed') {
                    statement.verb.id = "http://adlnet.gov/expapi/verbs/failed";
                    statement.verb.display = {"en-US": "failed"};
                }
            }
            
            // Add result data
            statement.result = {
                "completion": value === 'completed' || value === 'passed',
                "success": value === 'passed',
                "score": {}
            };
            
            // Handle score data
            if (element === 'cmi.core.score.raw' || element === 'cmi.score.raw') {
                statement.result.score.raw = parseFloat(value) || 0;
            }
        }
        
        return statement;
    }
    
    function generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            var r = Math.random() * 16 | 0;
            var v = c == 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
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
            
            // Auto-commit before termination
            try {
                log('Auto-committing data before termination...');
                makeAPICall('LMSCommit', ['']);
            } catch (e) {
                log('Warning: Could not commit data before termination: ' + e.message);
            }
            
            var result = makeAPICall('LMSFinish', [parameter]);
            config.initialized = false;
            
            return result;
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
            
            // Auto-commit for critical elements
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
                setTimeout(function() {
                    try {
                        makeAPICall('LMSCommit', ['']);
                    } catch (e) {
                        log('Warning: Auto-commit failed for ' + element + ': ' + e.message);
                    }
                }, 50);
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
            return API.LMSFinish(parameter);
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
            }
            
            var result = API.LMSSetValue(element, value);
            
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
                setTimeout(function() {
                    try {
                        API.LMSCommit('');
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
    window.ScormXAPIWrapper = {
        // Initialize the wrapper
        init: function(attemptId, topicId) {
            config.apiEndpoint = `/scorm/api/${topicId}/`;
            config.xapiEndpoint = `/scorm/xapi/${attemptId}/`;
            config.attemptId = attemptId;
            config.topicId = topicId;
            
            // Detect package type
            detectPackageType();
            
            log(`Initialized with attempt ID: ${attemptId}, topic ID: ${topicId}`);
            log(`Package type: ${config.packageType}`);
            log(`API endpoint: ${config.apiEndpoint}`);
            log(`xAPI endpoint: ${config.xapiEndpoint}`);
        },
        
        // Get API objects
        getAPI: function() {
            return API;
        },
        
        getAPI_1484_11: function() {
            return API_1484_11;
        },
        
        // Expose APIs globally
        exposeAPIs: function() {
            window.API = API;
            window.API_1484_11 = API_1484_11;
            
            // Also expose to parent windows for iframe compatibility
            if (window.parent && window.parent !== window) {
                window.parent.API = API;
                window.parent.API_1484_11 = API_1484_11;
            }
            
            log('APIs exposed globally - API available:', typeof window.API, 'API_1484_11 available:', typeof window.API_1484_11);
        },
        
        // Test function
        test: function(attemptId, topicId) {
            log('Running SCORM/xAPI API test...');
            this.init(attemptId, topicId);
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
    
    log('SCORM/xAPI Wrapper loaded successfully');
    
})();
