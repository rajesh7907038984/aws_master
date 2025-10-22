/**
 * Form Tabs JavaScript
 * Handles tab switching and form state management for tabbed forms
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('Form tabs script loaded');
    
    // Handle tab state from URL parameters
    const urlParams = new URLSearchParams(window.location.search);
    const activeTabFromUrl = urlParams.get('tab');
    
    if (activeTabFromUrl) {
        setTimeout(() => {
            openTab(null, activeTabFromUrl);
        }, 100);
    }
});

function openTab(evt, tabName) {
    var i, tabcontent, tablinks;
    
    // Hide all tab contents
    tabcontent = document.getElementsByClassName("tab-content");
    for (i = 0; i < tabcontent.length; i++) {
        tabcontent[i].style.display = "none";
    }
    
    // Remove active class from all tab buttons
    tablinks = document.getElementsByClassName("tab-button");
    for (i = 0; i < tablinks.length; i++) {
        tablinks[i].classList.remove("active");
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
    
    console.log('Switched to tab:', tabName);
} 