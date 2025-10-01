(function($) {
    $(document).ready(function() {
        var $branchSelect = $('#id_branch');
        var $createdBySelect = $('#id_created_by');
        
        function updateCreatedByOptions() {
            var branchId = $branchSelect.val();
            if (branchId) {
                // Get the current URL
                var url = window.location.pathname;
                // Add or update the branch parameter
                url += '?branch=' + branchId;
                
                // Fetch the updated form with filtered created_by options
                $.get(url, function(data) {
                    var $newCreatedBy = $(data).find('#id_created_by');
                    $createdBySelect.html($newCreatedBy.html());
                });
            }
        }

        // Update created_by options when branch changes
        $branchSelect.on('change', updateCreatedByOptions);
    });
})(django.jQuery); 