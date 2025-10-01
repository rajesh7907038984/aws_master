// JavaScript for TopicProgress admin interface
(function($) {
    $(document).ready(function() {
        // Add collapsible functionality to viewing session history
        if ($('.viewing-sessions').length) {
            // Add click handler to session history header
            $('h4:contains("Viewing Session History")').css('cursor', 'pointer').click(function() {
                $(this).next('.viewing-sessions').slideToggle();
            });
        }
        
        // Format dates to local timezone
        $('.progress-data td, .completion-data td').each(function() {
            const text = $(this).text();
            if (text.match(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/)) {
                try {
                    const date = new Date(text);
                    if (!isNaN(date)) {
                        $(this).text(date.toLocaleString());
                    }
                } catch (e) {
                    // Keep original text if date parsing fails
                }
            }
        });
    });
})(django.jQuery); 