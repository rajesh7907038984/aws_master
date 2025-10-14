/**
 * Simple SCORM API Wrapper (pipwerks-style)
 * Intercepts SCORM calls and forwards them to backend via REST API
 */

(function() {
    'use strict';
    
    // Configuration
    const config = {
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
    
    function makeAPICall(method, parameters = []) {
        if (!config.apiEndpoint) {
            log('ERROR: API endpoint not configured');
            return 'false';
        }
        
        const requestData = {
            method: method,
            parameters: parameters
        };
        
        log(`Making API call: ${method} with params: ${JSON.stringify(parameters)}`);
        
        // Use fetch API for better performance
        try {
            const xhr = new XMLHttpRequest();
            xhr.open('POST', config.apiEndpoint, false); // Keep synchronous for SCORM standard compliance
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.setRequestHeader('X-CSRFToken', getCsrfToken());
            
            xhr.send(JSON.stringify(requestData));
            
            if (xhr.status === 200) {
                const response = JSON.parse(xhr.responseText);
                log(`API call result: ${response.result}, error: ${response.error_code || '0'}`);
                return response.result || 'false';
            } else {
                log(`API call failed: HTTP ${xhr.status}`);
                return 'false';
            }
        } catch (error) {
            log(`API call error: ${error.message}`);
            return 'false';
        }
    }
    
    function getCsrfToken() {
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [name, value] = cookie.trim().split('=');
            if (name === 'csrftoken') {
                return decodeURIComponent(value);
            }
        }
        return '';
    }
    
    // SCORM 1.2 API Implementation
    const API = {
        LMSInitialize: function(parameter) {
            log('LMSInitialize called');
            const result = makeAPICall('LMSInitialize', [parameter]);
            if (result === 'true') {
                config.initialized = true;
                // On init, try to pull resume data so content can resume immediately
                try {
                    const entry = API.LMSGetValue('cmi.core.entry');
                    const loc = API.LMSGetValue('cmi.core.lesson_location');
                    const sus = API.LMSGetValue('cmi.suspend_data');
                    log(`Resume check: entry=${entry}, location=${loc?.slice?.(0,120) || ''}, suspend_data_len=${(sus||'').length}`);
                } catch (e) {}
            }
            return result;
        },
        
        LMSFinish: function(parameter) {
            log('LMSFinish called');
            const result = makeAPICall('LMSFinish', [parameter]);
            config.initialized = false;
            return result;
        },
        
        LMSGetValue: function(element) {
            log(`LMSGetValue called for: ${element}`);
            return makeAPICall('LMSGetValue', [element]);
        },
        
        LMSSetValue: function(element, value) {
            log(`LMSSetValue called: ${element} = ${value}`);
            
            // Store in local cache for immediate access
            config.data[element] = value;
            
            // Send to backend
            const result = makeAPICall('LMSSetValue', [element, value]);
            
            // Auto-commit for critical values including bookmarking
            const isBookmark = (element === 'cmi.core.lesson_location' || element === 'cmi.suspend_data');
            const isCritical = (element === 'cmi.core.lesson_status' || element === 'cmi.core.score.raw');
            if (isBookmark || isCritical) {
                log('Auto-committing critical data');
                setTimeout(() => {
                    makeAPICall('LMSCommit', ['']);
                }, 100);
            }
            
            return result;
        },
        
        LMSCommit: function(parameter) {
            // Ensure exit is set to suspend before commit to enable resume
            try { API.LMSSetValue('cmi.core.exit', 'suspend'); } catch (e) {}
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
    const API_1484_11 = {
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
            // Map SCORM 2004 elements to SCORM 1.2
            if (element.startsWith('cmi.learner_')) {
                element = element.replace('cmi.learner_', 'cmi.core.student_');
            } else if (element === 'cmi.location') {
                element = 'cmi.core.lesson_location';
            } else if (element === 'cmi.exit') {
                // Map exit to 1.2 and prefer suspend
                element = 'cmi.core.exit';
                if (value !== 'suspend' && value !== "") {
                    // Force suspend for resume unless course explicitly clears it
                    value = 'suspend';
                }
            } else if (element === 'cmi.completion_status') {
                element = 'cmi.core.lesson_status';
                // Map SCORM 2004 completion_status to SCORM 1.2 lesson_status
                if (value === 'completed') {
                    value = 'completed';
                } else if (value === 'incomplete') {
                    value = 'incomplete';
                }
            }
            
            return API.LMSSetValue(element, value);
        },
        
        Commit: function(parameter) {
            try { API.LMSSetValue('cmi.core.exit', 'suspend'); } catch (e) {}
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
        
        // Expose APIs globally for SCORM content
        exposeAPIs: function() {
            // Try multiple locations for maximum compatibility
            window.API = API;
            window.API_1484_11 = API_1484_11;
            
            if (window.parent && window.parent !== window) {
                window.parent.API = API;
                window.parent.API_1484_11 = API_1484_11;
            }
            
            if (window.top && window.top !== window) {
                window.top.API = API;
                window.top.API_1484_11 = API_1484_11;
            }
            
            log('APIs exposed globally');
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
    
    log('SCORM API Wrapper loaded successfully');
    
})();
