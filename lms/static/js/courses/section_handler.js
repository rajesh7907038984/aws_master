// Section deletion handler
async function deleteSection(sectionId) {
    if (!confirm('Are you sure you want to delete this section?')) {
        return;
    }
    
    try {
        // Add loading state
        const sectionElement = document.querySelector(`.section-item[data-section-id="${sectionId}"]`);
        if (sectionElement) {
            sectionElement.style.opacity = '0.5';
        }

        const response = await fetch(`/courses/api/sections/${sectionId}/delete/`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            }
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Remove the section element from the DOM with animation
            if (sectionElement) {
                sectionElement.style.transition = 'all 0.3s ease';
                sectionElement.style.opacity = '0';
                sectionElement.style.height = '0';
                sectionElement.style.margin = '0';
                sectionElement.style.padding = '0';
                
                // Remove the element after animation
                setTimeout(async () => {
                    sectionElement.remove();
                    
                    // Update empty state if no sections left
                    const remainingSections = document.querySelectorAll('.section-item');
                    if (remainingSections.length === 0) {
                        const emptySectionsMessage = document.querySelector('.empty-sections-message');
                        if (emptySectionsMessage) {
                            emptySectionsMessage.style.display = 'block';
                        }
                    } else {
                        // Reorder remaining sections
                        const newOrder = Array.from(remainingSections).map((section, index) => ({
                            section_id: section.dataset.sectionId,
                            order: index + 1
                        }));
                        
                        try {
                            const reorderResponse = await fetch('/courses/api/sections/reorder/', {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                    'X-Requested-With': 'XMLHttpRequest',
                                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                                },
                                body: JSON.stringify({ 
                                    course_id: document.querySelector('[name=course_id]').value,
                                    section_orders: newOrder 
                                })
                            });
                            
                            if (!reorderResponse.ok) {
                                throw new Error('Failed to reorder sections');
                            }
                        } catch (error) {
                            console.error('Error reordering sections:', error);
                        }
                    }

                    // Reload the page to refresh sections after deletion
                    window.location.reload();
                }, 300);
            }
        } else {
            // Restore opacity if error
            if (sectionElement) {
                sectionElement.style.opacity = '1';
            }
            throw new Error(data.error || 'Failed to delete section');
        }
    } catch (error) {
        console.error('Error:', error);
        alert(error.message || 'An error occurred while deleting the section. Please try again.');
        
        // Restore opacity if error
        const sectionElement = document.querySelector(`.section-item[data-section-id="${sectionId}"]`);
        if (sectionElement) {
            sectionElement.style.opacity = '1';
        }
    }
}

// Function to initialize drag and drop functionality
function initializeDragAndDrop() {
    const sections = document.querySelectorAll('.section-item');
    sections.forEach(section => {
        section.draggable = true;
    });
}

// Initialize drag and drop when the page loads
document.addEventListener('DOMContentLoaded', initializeDragAndDrop);

// Expose deleteSection to global scope
window.deleteSection = deleteSection;

// Section edit handler
document.addEventListener('click', function(e) {
    if (e.target.closest('.edit-section-btn')) {
        const sectionId = e.target.closest('.edit-section-btn').dataset.sectionId;
        const sectionElement = document.querySelector(`[data-section-id="${sectionId}"]`);
        
        if (sectionElement) {
            const title = sectionElement.querySelector('h3').textContent;
            const description = sectionElement.querySelector('.description')?.textContent || '';
            
            // Populate the edit form
            const editForm = document.getElementById('sectionEditForm');
            if (editForm) {
                editForm.querySelector('[name="title"]').value = title;
                editForm.querySelector('[name="description"]').value = description;
                editForm.querySelector('[name="section_id"]').value = sectionId;
                
                // Show the edit popup
                sectionPopup.show();
            }
        }
    }
});

// Section reordering handler
let draggedSection = null;

document.addEventListener('dragstart', function(e) {
    if (e.target.closest('.section-item')) {
        draggedSection = e.target.closest('.section-item');
        e.target.closest('.section-item').classList.add('opacity-50');
    }
});

document.addEventListener('dragend', function(e) {
    if (e.target.closest('.section-item')) {
        e.target.closest('.section-item').classList.remove('opacity-50');
        draggedSection = null;
    }
});

document.addEventListener('dragover', function(e) {
    e.preventDefault();
    if (e.target.closest('.section-item') && e.target.closest('.section-item') !== draggedSection) {
        const section = e.target.closest('.section-item');
        const rect = section.getBoundingClientRect();
        const midY = rect.top + rect.height / 2;
        
        if (e.clientY < midY) {
            section.parentNode.insertBefore(draggedSection, section);
        } else {
            section.parentNode.insertBefore(draggedSection, section.nextSibling);
        }
    }
});

document.addEventListener('drop', async function(e) {
    e.preventDefault();
    if (draggedSection) {
        const sections = Array.from(document.querySelectorAll('.section-item'));
        const newOrder = sections.map((section, index) => ({
            section_id: section.dataset.sectionId,
            order: index + 1
        }));
        
        try {
            const response = await fetch('/courses/api/sections/reorder/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                },
                body: JSON.stringify({ 
                    course_id: document.querySelector('[name=course_id]').value,
                    section_orders: newOrder 
                })
            });
            
            const data = await response.json();
            
            if (!data.success) {
                throw new Error(data.error || 'Failed to update section order');
            }
        } catch (error) {
            console.error('Error:', error);
            alert(error.message || 'An error occurred while updating section order. Please try again.');
        }
    }
}); 