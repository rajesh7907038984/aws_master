/**
 * Topic View Accordion Handler
 * 
 * This script handles the accordion functionality for the topic view page
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('Topic Accordion Handler: Initialized');
    
    // Initialize the accordion state
    document.querySelectorAll('.section-content').forEach(content => {
        if (!content.classList.contains('hidden')) {
            const icon = content.closest('.section-container').querySelector('.section-toggle-icon i');
            if (icon) {
                icon.classList.add('rotate-180');
            }
            console.log('Initialized open section:', content.closest('.section-container').querySelector('h3')?.textContent);
        }
    });
    
    // Accordion functionality for course sections
    const sectionHeaders = document.querySelectorAll('.section-header');
    sectionHeaders.forEach(header => {
        header.addEventListener('click', function(e) {
            try {
                const container = this.closest('.section-container');
                const content = container.querySelector('.section-content');
                const icon = this.querySelector('.section-toggle-icon i');
                
                // Toggle current section
                if (content.classList.contains('hidden')) {
                    // Opening this section
                    content.classList.remove('hidden');
                    icon.classList.add('rotate-180');
                } else {
                    // Closing this section
                    content.classList.add('hidden');
                    icon.classList.remove('rotate-180');
                }
                
                console.log('Section toggled:', this.querySelector('h3').textContent);
                console.log('Section is now:', content.classList.contains('hidden') ? 'closed' : 'open');
                
                // Store state in localStorage for persistence
                try {
                    const sectionId = this.getAttribute('data-section-id');
                    if (sectionId) {
                        let openSections = TypeSafety.safeJsonParse(localStorage.getItem('topicViewOpenSections'), []);
                        
                        if (!content.classList.contains('hidden')) {
                            // Section is open, add to openSections if not already there
                            if (!openSections.includes(sectionId)) {
                                openSections.push(sectionId);
                            }
                        } else {
                            // Section is closed, remove from openSections
                            openSections = openSections.filter(id => id !== sectionId);
                        }
                        
                        localStorage.setItem('topicViewOpenSections', JSON.stringify(openSections));
                    }
                } catch (storageError) {
                    console.error('Error storing section state:', storageError);
                }
            } catch (error) {
                console.error('Error in section click handler:', error);
            }
        });
    });
    
    // Restore accordion state from localStorage
    try {
        const openSections = TypeSafety.safeJsonParse(localStorage.getItem('topicViewOpenSections'), []);
        
        openSections.forEach(sectionId => {
            const header = document.querySelector(`.section-header[data-section-id="${sectionId}"]`);
            if (header) {
                const container = header.closest('.section-container');
                const content = container.querySelector('.section-content');
                const icon = header.querySelector('.section-toggle-icon i');
                
                if (content && icon) {
                    content.classList.remove('hidden');
                    icon.classList.add('rotate-180');
                }
            }
        });
    } catch (error) {
        console.error('Error restoring section states:', error);
    }
}); 