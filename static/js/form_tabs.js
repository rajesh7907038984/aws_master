/**
 * Form Tabs JavaScript
 * Handles tab switching and form state management for tabbed forms
 */

document.addEventListener('DOMContentLoaded', function() {
    try {
        // Handle tab state from URL parameters
        const urlParams = new URLSearchParams(window.location.search);
        const activeTabFromUrl = urlParams.get('tab');
        
        if (activeTabFromUrl) {
            setTimeout(() => {
                try {
                    openTab(null, activeTabFromUrl);
                } catch (error) {
                    console.error('Error opening tab from URL:', error);
                }
            }, 100);
        }
    } catch (error) {
        console.error('Error initializing form tabs:', error);
    }
});

function openTab(evt, tabName) {
    try {
        var i, tabcontent, tablinks;
        
        // Hide all tab contents
        tabcontent = document.getElementsByClassName("tab-content");
        for (i = 0; i < tabcontent.length; i++) {
            try {
                tabcontent[i].style.display = "none";
            } catch (error) {
                console.error('Error hiding tab content:', error);
            }
        }
        
        // Remove active class from all tab buttons
        tablinks = document.getElementsByClassName("tab-button");
        for (i = 0; i < tablinks.length; i++) {
            try {
                tablinks[i].classList.remove("active");
            } catch (error) {
                console.error('Error removing active class from tab button:', error);
            }
        }
        
        // Show the selected tab content
        const targetTab = document.getElementById(tabName);
        if (targetTab) {
            targetTab.style.display = "block";
        }
        
        // Add active class to the clicked button
        if (evt && evt.currentTarget) {
            evt.currentTarget.classList.add("active");
        } else {
            // Find and activate the corresponding button
            const targetButton = document.querySelector(`[onclick*="${tabName}"]`);
            if (targetButton) {
                targetButton.classList.add("active");
            }
        }
    } catch (error) {
        console.error('Error in openTab function:', error);
    }
} 