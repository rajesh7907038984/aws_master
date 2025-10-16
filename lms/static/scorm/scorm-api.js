/**
 * SCORM API Implementation for iframe content
 * This script provides a complete SCORM 1.2 API that works within iframe context
 */

(function() {
    'use strict';
    
    // SCORM API Configuration
    var SCORM_API = {
        initialized: false,
        commit_url: window.location.origin + '/scorm/api/' + getTopicIdFromUrl(),
        user_id: null,
        topic_id: null,
        
        // SCORM data storage
        data: {
            'cmi.core.lesson_status': 'incomplete',
            'cmi.core.score.raw': '',
            'cmi.core.score.min': '',
            'cmi.core.score.max': '',
            'cmi.core.total_time': 'PT0S',
            'cmi.core.session_time': 'PT0S',
            'cmi.core.lesson_location': '',
            'cmi.core.exit': '',
            'cmi.core.entry': 'ab-initio',
            'cmi.core.student_id': '',
            'cmi.core.student_name': '',
            'cmi.core.credit': 'credit',
            'cmi.core.lesson_mode': 'normal',
            'cmi.core.max_time_allowed': '',
            'cmi.core.mastery_score': '',
            'cmi.core.suspend_data': '',
            'cmi.core.launch_data': ''
        },
        
        // SCORM API Methods
        LMSInitialize: function(param) {
            console.log('SCORM API: LMSInitialize called with:', param);
            this.initialized = true;
            return "true";
        },
        
        LMSGetValue: function(element) {
            console.log('SCORM API: LMSGetValue called for:', element);
            return this.data[element] || "";
        },
        
        LMSSetValue: function(element, value) {
            console.log('SCORM API: LMSSetValue called:', element, '=', value);
            this.data[element] = value;
            return "true";
        },
        
        LMSCommit: function(param) {
            console.log('SCORM API: LMSCommit called');
            this.sendDataToServer();
            return "true";
        },
        
        LMSFinish: function(param) {
            console.log('SCORM API: LMSFinish called');
            this.sendDataToServer();
            return "true";
        },
        
        LMSGetLastError: function() {
            return "0";
        },
        
        LMSGetErrorString: function(errorCode) {
            return "No Error";
        },
        
        LMSGetDiagnostic: function(errorCode) {
            return "No Error";
        },
        
        // Additional SCORM API functions that Articulate content expects
        CommitData: function() {
            console.log('SCORM API: CommitData called');
            this.sendDataToServer();
            return "true";
        },
        
        ConcedeControl: function() {
            console.log('SCORM API: ConcedeControl called');
            return "true";
        },
        
        CreateResponseIdentifier: function() {
            console.log('SCORM API: CreateResponseIdentifier called');
            return "true";
        },
        
        Finish: function() {
            console.log('SCORM API: Finish called');
            this.sendDataToServer();
            return "true";
        },
        
        GetDataChunk: function() {
            console.log('SCORM API: GetDataChunk called');
            return "";
        },
        
        GetStatus: function() {
            console.log('SCORM API: GetStatus called');
            return this.data['cmi.core.lesson_status'] || "incomplete";
        },
        
        MatchingResponse: function() {
            console.log('SCORM API: MatchingResponse called');
            return "true";
        },
        
        RecordFillInInteraction: function() {
            console.log('SCORM API: RecordFillInInteraction called');
            return "true";
        },
        
        RecordMatchingInteraction: function() {
            console.log('SCORM API: RecordMatchingInteraction called');
            return "true";
        },
        
        RecordMultipleChoiceInteraction: function() {
            console.log('SCORM API: RecordMultipleChoiceInteraction called');
            return "true";
        },
        
        ResetStatus: function() {
            console.log('SCORM API: ResetStatus called');
            this.data['cmi.core.lesson_status'] = 'incomplete';
            return "true";
        },
        
        SetBookmark: function(bookmark) {
            console.log('SCORM API: SetBookmark called with:', bookmark);
            this.data['cmi.core.lesson_location'] = bookmark;
            
            // FIXED: Send bookmark data to server immediately
            this.sendDataToServer();
            
            return "true";
        },
        
        SetDataChunk: function(data) {
            console.log('SCORM API: SetDataChunk called with:', data);
            this.data['cmi.core.suspend_data'] = data;
            
            // FIXED: Send suspend data to server immediately
            this.sendDataToServer();
            
            return "true";
        },
        
        SetFailed: function() {
            console.log('SCORM API: SetFailed called');
            this.data['cmi.core.lesson_status'] = 'failed';
            return "true";
        },
        
        SetLanguagePreference: function(lang) {
            console.log('SCORM API: SetLanguagePreference called with:', lang);
            return "true";
        },
        
        SetPassed: function() {
            console.log('SCORM API: SetPassed called');
            this.data['cmi.core.lesson_status'] = 'passed';
            
            // FIXED: Send status to server immediately
            this.sendDataToServer();
            
            return "true";
        },
        
        SetReachedEnd: function() {
            console.log('SCORM API: SetReachedEnd called');
            this.data['cmi.core.lesson_status'] = 'completed';
            
            // FIXED: Send completion status to server immediately
            this.sendDataToServer();
            
            return "true";
        },
        
        SetScore: function(score) {
            console.log('SCORM API: SetScore called with:', score);
            this.data['cmi.core.score.raw'] = score;
            
            // FIXED: Send score to server immediately
            this.sendDataToServer();
            
            return "true";
        },
        
        WriteToDebug: function(message) {
            console.log('SCORM API: WriteToDebug called with:', message);
            return "true";
        },
        
        // Send data to server
        sendDataToServer: function() {
            if (!this.commit_url) {
                console.error('SCORM API: No commit URL available');
                return;
            }
            
            const formData = new FormData();
            formData.append('action', 'SetValue');
            
            // Send all data
            for (const [key, value] of Object.entries(this.data)) {
                formData.append('element', key);
                formData.append('value', value);
            }
            
            fetch(this.commit_url, {
                method: 'POST',
                body: formData,
                credentials: 'same-origin'
            }).then(response => response.json())
            .then(data => {
                console.log('SCORM API: Data sent to server:', data);
            }).catch(error => {
                console.error('SCORM API: Error sending data:', error);
            });
        }
    };
    
    // Extract topic ID from URL
    function getTopicIdFromUrl() {
        const url = window.location.href;
        const match = url.match(/\/scorm\/content\/(\d+)\//);
        return match ? match[1] : null;
    }
    
    // Make API available globally
    window.API = SCORM_API;
    window.parent.API = SCORM_API;
    window.top.API = SCORM_API;
    
    // Also try to set API in parent frames
    try {
        if (window.parent && window.parent !== window) {
            window.parent.API = SCORM_API;
        }
        if (window.top && window.top !== window) {
            window.top.API = SCORM_API;
        }
    } catch (e) {
        console.log('SCORM API: Could not set API in parent frames (cross-origin)');
    }
    
    console.log('SCORM API: Initialized and available globally');
    
})();
