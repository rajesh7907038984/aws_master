/**
 * DragDropMatchingLearner - Handler for Drag & Drop Matching questions in quiz attempts
 */
class DragDropMatchingLearner {
    constructor(container) {
        this.container = container;
        this.questionId = container.dataset.questionId;
        this.dragItems = container.querySelectorAll('.drag-item');
        this.dropZones = container.querySelectorAll('.drop-zone');
        this.matches = {};
        this.hiddenInput = null;
        
        this.init();
    }
    
    init() {
        this.setupDragItems();
        this.setupDropZones();
        this.setupControls();
        this.createHiddenInput();
        this.updateProgress();
    }
    
    setupDragItems() {
        this.dragItems.forEach((item, index) => {
            item.draggable = true;
            item.classList.add('drag-item');
            
            // Remove existing listeners to prevent duplicates
            item.removeEventListener('dragstart', this.handleDragStart.bind(this));
            item.removeEventListener('dragend', this.handleDragEnd.bind(this));
            
            item.addEventListener('dragstart', this.handleDragStart.bind(this));
            item.addEventListener('dragend', this.handleDragEnd.bind(this));
        });
    }
    
    setupDropZones() {
        this.dropZones.forEach((zone, index) => {
            // Remove existing listeners to prevent duplicates
            zone.removeEventListener('dragover', this.handleDragOver.bind(this));
            zone.removeEventListener('drop', this.handleDrop.bind(this));
            zone.removeEventListener('dragenter', this.handleDragEnter.bind(this));
            zone.removeEventListener('dragleave', this.handleDragLeave.bind(this));
            
            zone.addEventListener('dragover', this.handleDragOver.bind(this));
            zone.addEventListener('drop', this.handleDrop.bind(this));
            zone.addEventListener('dragenter', this.handleDragEnter.bind(this));
            zone.addEventListener('dragleave', this.handleDragLeave.bind(this));
        });
    }
    
    setupControls() {
        const clearBtn = this.container.querySelector('.clear-matches-btn');
        if (clearBtn) {
            clearBtn.addEventListener('click', this.clearAllMatches.bind(this));
        }
    }
    
    createHiddenInput() {
        // Create or find the hidden input for storing matches
        this.hiddenInput = this.container.querySelector(`input[name="question_${this.questionId}_drag_drop"]`);
        if (!this.hiddenInput) {
            this.hiddenInput = document.createElement('input');
            this.hiddenInput.type = 'hidden';
            this.hiddenInput.name = `question_${this.questionId}_drag_drop`;
            this.container.appendChild(this.hiddenInput);
        }
        
        // Initialize with empty object
        this.hiddenInput.value = '{}';
    }
    
    handleDragStart(e) {
        const leftItem = e.target.dataset.leftItem;
        e.dataTransfer.setData('text/plain', leftItem);
        e.dataTransfer.effectAllowed = 'move';
        e.target.classList.add('dragging');
        
        // Add visual feedback
        this.dragItems.forEach(item => {
            if (item !== e.target) {
                item.classList.add('drag-disabled');
            }
        });
    }
    
    handleDragEnd(e) {
        e.target.classList.remove('dragging');
        
        // Remove visual feedback
        this.dragItems.forEach(item => {
            item.classList.remove('drag-disabled');
        });
    }
    
    handleDragOver(e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
    }
    
    handleDragEnter(e) {
        e.preventDefault();
        e.target.classList.add('drag-over');
    }
    
    handleDragLeave(e) {
        e.target.classList.remove('drag-over');
    }
    
    handleDrop(e) {
        e.preventDefault();
        e.target.classList.remove('drag-over');
        
        const leftItem = e.dataTransfer.getData('text/plain');
        const rightItem = e.target.dataset.rightItem;
        
        if (!leftItem || !rightItem) {
            return;
        }
        
        // Check if this drop zone is already occupied
        if (e.target.classList.contains('matched')) {
            // Remove the existing match
            this.removeMatch(e.target);
        }
        
        // Create the match
        this.createMatch(leftItem, rightItem, e.target);
    }
    
    createMatch(leftItem, rightItem, dropZone) {
        // Update the matches object
        this.matches[leftItem] = rightItem;
        
        // Update the drop zone display
        dropZone.innerHTML = `
            <span class="matched-item">${leftItem}</span>
            <button type="button" class="remove-match-btn" onclick="this.parentElement.dispatchEvent(new CustomEvent('removeMatch', {detail: {leftItem: '${leftItem}'}}))">×</button>
        `;
        dropZone.classList.add('matched');
        
        // Hide the corresponding drag item
        const dragItem = Array.from(this.dragItems).find(item => 
            item.dataset.leftItem === leftItem
        );
        if (dragItem) {
            dragItem.style.display = 'none';
        }
        
        // Update hidden input
        this.updateHiddenInput();
        
        // Update progress
        this.updateProgress();
        
        // Dispatch custom event for external listeners
        this.container.dispatchEvent(new CustomEvent('matchCreated', {
            detail: { leftItem, rightItem }
        }));
    }
    
    removeMatch(dropZone) {
        const matchedItem = dropZone.querySelector('.matched-item');
        if (matchedItem) {
            const leftItem = matchedItem.textContent;
            
            // Remove from matches
            delete this.matches[leftItem];
            
            // Show the drag item again
            const dragItem = Array.from(this.dragItems).find(item => 
                item.dataset.leftItem === leftItem
            );
            if (dragItem) {
                dragItem.style.display = '';
            }
            
            // Reset drop zone
            dropZone.innerHTML = '<span class="drop-placeholder">Drop here</span>';
            dropZone.classList.remove('matched');
            
            // Update hidden input
            this.updateHiddenInput();
            
            // Update progress
            this.updateProgress();
            
            // Dispatch custom event
            this.container.dispatchEvent(new CustomEvent('matchRemoved', {
                detail: { leftItem }
            }));
        }
    }
    
    clearAllMatches() {
        // Clear all matches
        this.matches = {};
        
        // Reset all drop zones
        this.dropZones.forEach(zone => {
            zone.innerHTML = '<span class="drop-placeholder">Drop here</span>';
            zone.classList.remove('matched');
        });
        
        // Show all drag items
        this.dragItems.forEach(item => {
            item.style.display = '';
        });
        
        // Update hidden input
        this.updateHiddenInput();
        
        // Update progress
        this.updateProgress();
        
        // Dispatch custom event
        this.container.dispatchEvent(new CustomEvent('allMatchesCleared'));
    }
    
    updateHiddenInput() {
        if (this.hiddenInput) {
            this.hiddenInput.value = JSON.stringify(this.matches);
        }
    }
    
    updateProgress() {
        const matchedCount = Object.keys(this.matches).length;
        const totalCount = this.dragItems.length;
        
        // Update progress bar
        const progressBar = this.container.querySelector('.matching-progress');
        if (progressBar) {
            const percentage = (matchedCount / totalCount) * 100;
            progressBar.style.width = `${percentage}%`;
        }
        
        // Update progress text
        const progressText = this.container.querySelector('.progress-text');
        if (progressText) {
            progressText.textContent = `${matchedCount}/${totalCount} matched`;
        }
        
        // Update visual feedback
        if (matchedCount === totalCount) {
            this.container.classList.add('all-matched');
        } else {
            this.container.classList.remove('all-matched');
        }
    }
    
    // Public method to get current matches
    getMatches() {
        return { ...this.matches };
    }
    
    // Public method to set matches (for loading saved data)
    setMatches(matches) {
        this.matches = { ...matches };
        this.updateDisplay();
        this.updateHiddenInput();
        this.updateProgress();
    }
    
    updateDisplay() {
        // Clear all drop zones first
        this.dropZones.forEach(zone => {
            zone.innerHTML = '<span class="drop-placeholder">Drop here</span>';
            zone.classList.remove('matched');
        });
        
        // Show all drag items
        this.dragItems.forEach(item => {
            item.style.display = '';
        });
        
        // Apply current matches
        Object.entries(this.matches).forEach(([leftItem, rightItem]) => {
            const dropZone = Array.from(this.dropZones).find(zone => 
                zone.dataset.rightItem === rightItem
            );
            
            if (dropZone) {
                dropZone.innerHTML = `
                    <span class="matched-item">${leftItem}</span>
                    <button type="button" class="remove-match-btn" onclick="this.parentElement.dispatchEvent(new CustomEvent('removeMatch', {detail: {leftItem: '${leftItem}'}}))">×</button>
                `;
                dropZone.classList.add('matched');
                
                // Hide the corresponding drag item
                const dragItem = Array.from(this.dragItems).find(item => 
                    item.dataset.leftItem === leftItem
                );
                if (dragItem) {
                    dragItem.style.display = 'none';
                }
            }
        });
    }
}

// Static method for initialization
DragDropMatchingLearner.init = function(container) {
    return new DragDropMatchingLearner(container);
};

// Make globally available
window.DragDropMatchingLearner = DragDropMatchingLearner;
