// SCORM API wrapper
const SCORM = {
    version: '1.2',
    API: null,
    data: {
        cmi: {
            core: {
                lesson_status: 'not attempted',
                lesson_location: '',
                score: {
                    raw: '0',
                    min: '0',
                    max: '100'
                },
                total_time: '0000:00:00',
                session_time: '0000:00:00',
                suspend_data: ''
            }
        }
    },
    
    initialize: function() {
        this.API = window.API || window.API_1484_11;
        if (this.API) {
            return this.API.LMSInitialize('');
        }
        return false;
    },
    
    finish: function() {
        if (this.API) {
            return this.API.LMSFinish('');
        }
        return false;
    },
    
    getValue: function(element) {
        if (this.API) {
            return this.API.LMSGetValue(element);
        }
        return '';
    },
    
    setValue: function(element, value) {
        if (this.API) {
            return this.API.LMSSetValue(element, value);
        }
        return false;
    },
    
    save: function() {
        if (this.API) {
            return this.API.LMSSave('');
        }
        return false;
    }
};

// SCORM Player functionality
document.addEventListener('DOMContentLoaded', function() {
    const scormFrame = document.getElementById('scormFrame');
    if (scormFrame) {
        // Initialize SCORM when frame loads
        scormFrame.addEventListener('load', function() {
            if (SCORM.initialize()) {
                console.log('SCORM initialized successfully');
            } else {
                console.error('Failed to initialize SCORM');
            }
        });
        
        // Handle window unload
        window.addEventListener('beforeunload', function() {
            SCORM.finish();
        });
    }
}); 