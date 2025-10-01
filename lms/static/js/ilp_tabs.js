/**
 * ILP Tabs JavaScript
 * Handles nested tab functionality within the Individual Learning Plan tab
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('ILP tabs script loaded');
    
    // Initialize ILP nested tabs
    initializeILPTabs();
    
    // Initialize Learning Profile nested tabs
    initializeLearningProfileTabs();
});

function openILPTab(evt, tabName) {
    var i, tabcontent, tablinks;
    
    // Hide all ILP tab contents
    tabcontent = document.getElementsByClassName("ilp-tab-content");
    for (i = 0; i < tabcontent.length; i++) {
        tabcontent[i].style.display = "none";
    }
    
    // Remove active class from all ILP tab buttons
    tablinks = document.getElementsByClassName("ilp-tab-button");
    for (i = 0; i < tablinks.length; i++) {
        tablinks[i].classList.remove("active");
    }
    
    // Show the selected ILP tab content
    const targetTab = document.getElementById(tabName);
    if (targetTab) {
        targetTab.style.display = "block";
        
        // If this is the learning profile tab, initialize its nested tabs
        if (tabName === 'learning-profile-tab') {
            setTimeout(() => {
                openLearningProfileTab(null, 'learning-preferences-tab');
            }, 100);
        }
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
    
    console.log('Switched to ILP tab:', tabName);
}

function openLearningProfileTab(evt, tabName) {
    var i, tabcontent, tablinks;
    
    // Hide all learning profile tab contents
    tabcontent = document.getElementsByClassName("learning-profile-tab-content");
    for (i = 0; i < tabcontent.length; i++) {
        tabcontent[i].style.display = "none";
    }
    
    // Remove active class from all learning profile tab buttons
    tablinks = document.getElementsByClassName("learning-profile-tab-button");
    for (i = 0; i < tablinks.length; i++) {
        tablinks[i].classList.remove("active");
    }
    
    // Show the selected learning profile tab content
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
    
    console.log('Switched to learning profile tab:', tabName);
}

function initializeILPTabs() {
    // Check if ILP tabs exist
    const ilpTabButtons = document.querySelectorAll('.ilp-tab-button');
    
    if (ilpTabButtons.length > 0) {
        // Show first ILP tab by default
        openILPTab(null, 'overview-tab');
        
        // Add click event listeners
        ilpTabButtons.forEach(button => {
            button.addEventListener('click', function(e) {
                e.preventDefault();
                const onclick = this.getAttribute('onclick');
                if (onclick) {
                    const match = onclick.match(/openILPTab\([^,]+,\s*['"]([^'"]+)['"]/);
                    if (match) {
                        openILPTab(e, match[1]);
                    }
                }
            });
        });
    }
}

function initializeLearningProfileTabs() {
    // Check if Learning Profile tabs exist
    const learningProfileTabButtons = document.querySelectorAll('.learning-profile-tab-button');
    
    if (learningProfileTabButtons.length > 0) {
        // Add click event listeners
        learningProfileTabButtons.forEach(button => {
            button.addEventListener('click', function(e) {
                e.preventDefault();
                const onclick = this.getAttribute('onclick');
                if (onclick) {
                    const match = onclick.match(/openLearningProfileTab\([^,]+,\s*['"]([^'"]+)['"]/);
                    if (match) {
                        openLearningProfileTab(e, match[1]);
                    }
                }
            });
        });
    }
} 