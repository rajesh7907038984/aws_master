document.addEventListener('DOMContentLoaded', function() {
    console.log('Course details JS loaded');
    
    // Get all tab elements
    const tabs = document.querySelectorAll('.tab');
    
    // Add click event to each tab
    tabs.forEach(tab => {
        tab.addEventListener('click', function() {
            console.log('Tab clicked:', this.textContent.trim());
            
            // Remove active class from all tabs
            tabs.forEach(t => t.classList.remove('active'));
            
            // Add active class to clicked tab
            this.classList.add('active');
            
            // Get content type from tab text
            const contentType = this.textContent.trim().toLowerCase();
            
            // Hide all content divs
            const contentDivs = document.querySelectorAll('.tab-content > div');
            contentDivs.forEach(div => div.style.display = 'none');
            
            // Show the selected content div
            const selectedContent = document.querySelector(`.${contentType}-content`);
            if (selectedContent) {
                console.log('Found content div for', contentType);
                selectedContent.style.display = 'block';
            } else {
                console.log('Could not find content div for', contentType);
            }
        });
    });
    
    // Explicitly show overview content by default
    document.querySelector('.overview-content').style.display = 'block';
}); 