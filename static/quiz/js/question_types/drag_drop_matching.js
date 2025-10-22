const DragDropMatchingQuestion = {
    init(formElement, initialData = {}) {
        this.form = formElement;
        this.pairs = initialData.pairs || { left: [], right: [] };
        this.setupEventListeners();
        if (this.pairs.left.length > 0) {
            this.setInitialValues();
        }
    },

    setupEventListeners() {
        const addButton = this.form.querySelector('#addDragDropPairBtn');
        if (addButton) {
            addButton.addEventListener('click', () => this.addPair());
        }

        this.form.addEventListener('click', (e) => {
            if (e.target.closest('.remove-pair')) {
                this.removePair(e.target.closest('.input-group'));
            }
        });
    },

    setInitialValues() {
        const container = this.form.querySelector('#dragDropMatchingContainer');
        if (!container) return;

        container.innerHTML = this.pairs.left.map((leftItem, index) => `
            <div class="input-group">
                <input type="text" name="matching_left[]" class="form-control" 
                       value="${leftItem}" placeholder="Left item (drag source)" required>
                <input type="text" name="matching_right[]" class="form-control" 
                       value="${this.pairs.right[index]}" placeholder="Right item (drop target)" required>
                <button type="button" class="btn btn-danger btn-sm remove-pair">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `).join('');
    },

    addPair() {
        const container = this.form.querySelector('#dragDropMatchingContainer');
        const div = document.createElement('div');
        div.className = 'input-group';
        div.innerHTML = `
            <input type="text" name="matching_left[]" class="form-control" 
                   placeholder="Left item (drag source)" required>
            <input type="text" name="matching_right[]" class="form-control" 
                   placeholder="Right item (drop target)" required>
            <button type="button" class="btn btn-danger btn-sm remove-pair">
                <i class="fas fa-times"></i>
            </button>
        `;
        container.appendChild(div);
    },

    removePair(pairElement) {
        pairElement.remove();
    },

    validateAnswer() {
        const leftItems = Array.from(this.form.querySelectorAll('input[name="matching_left[]"]'))
            .map(input => input.value.trim())
            .filter(Boolean);
        
        const rightItems = Array.from(this.form.querySelectorAll('input[name="matching_right[]"]'))
            .map(input => input.value.trim())
            .filter(Boolean);
        
        return leftItems.length > 0 && leftItems.length === rightItems.length;
    },

    getAnswerFields() {
        return `
            <div class="form-group">
                <label class="form-label">Drag & Drop Matching Pairs *</label>
                <div id="dragDropMatchingContainer" class="space-y-2"></div>
                <button type="button" id="addDragDropPairBtn" class="btn btn-secondary btn-sm mt-2">
                    <i class="fas fa-plus"></i> Add Pair
                </button>
                <div class="form-text">
                    Add matching pairs for students to drag and drop. Left items will be draggable, 
                    right items will be drop targets.
                </div>
            </div>
        `;
    }
};

// Drag and Drop functionality for learner view
const DragDropMatchingLearner = {
    init(questionContainer) {
        this.container = questionContainer;
        this.questionId = questionContainer.dataset.questionId;
        this.draggedItem = null;
        this.touchDraggedItem = null;
        this.touchStartX = 0;
        this.touchStartY = 0;
        this.setupDragAndDrop();
        this.setupClearButton();
        this.updateProgress();
    },

    setupDragAndDrop() {
        const leftItems = this.container.querySelectorAll('.drag-item');
        const dropZones = this.container.querySelectorAll('.drop-zone');
        
        console.log('Setting up drag and drop:', {
            leftItems: leftItems.length,
            dropZones: dropZones.length,
            questionId: this.questionId
        });
        
        // Make left items draggable
        leftItems.forEach((item, index) => {
            item.draggable = true;
            // Safari requires these attributes for proper drag behavior
            item.setAttribute('draggable', 'true');
            item.setAttribute('data-index', index);
            
            // Remove any existing event listeners to prevent duplicates
            item.removeEventListener('dragstart', this.handleDragStart);
            item.removeEventListener('dragend', this.handleDragEnd);
            item.removeEventListener('touchstart', this.handleTouchStart);
            item.removeEventListener('touchmove', this.handleTouchMove);
            item.removeEventListener('touchend', this.handleTouchEnd);
            
            // Add event listeners
            item.addEventListener('dragstart', this.handleDragStart.bind(this));
            item.addEventListener('dragend', this.handleDragEnd.bind(this));
            
            // Add touch events for mobile devices
            item.addEventListener('touchstart', this.handleTouchStart.bind(this), { passive: false });
            item.addEventListener('touchmove', this.handleTouchMove.bind(this), { passive: false });
            item.addEventListener('touchend', this.handleTouchEnd.bind(this), { passive: false });
            
            console.log('Set up drag item:', item.textContent, item.dataset.leftItem);
        });

        // Setup drop zones
        dropZones.forEach((zone, index) => {
            zone.setAttribute('data-index', index);
            
            // Remove any existing event listeners to prevent duplicates
            zone.removeEventListener('dragover', this.handleDragOver);
            zone.removeEventListener('drop', this.handleDrop);
            zone.removeEventListener('dragenter', this.handleDragEnter);
            zone.removeEventListener('dragleave', this.handleDragLeave);
            zone.removeEventListener('touchstart', this.handleTouchStart);
            zone.removeEventListener('touchmove', this.handleTouchMove);
            zone.removeEventListener('touchend', this.handleTouchEnd);
            
            // Add event listeners
            zone.addEventListener('dragover', this.handleDragOver.bind(this));
            zone.addEventListener('drop', this.handleDrop.bind(this));
            zone.addEventListener('dragenter', this.handleDragEnter.bind(this));
            zone.addEventListener('dragleave', this.handleDragLeave.bind(this));
            
            // Add touch events for mobile devices
            zone.addEventListener('touchstart', this.handleTouchStart.bind(this), { passive: false });
            zone.addEventListener('touchmove', this.handleTouchMove.bind(this), { passive: false });
            zone.addEventListener('touchend', this.handleTouchEnd.bind(this), { passive: false });
            
            console.log('Set up drop zone:', zone.dataset.rightItem);
        });
    },

    setupClearButton() {
        const clearBtn = this.container.querySelector('.clear-matches-btn');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => this.clearAllMatches());
        }
    },

    handleDragStart(e) {
        console.log('Drag start:', e.target);
        // Safari compatibility: ensure dataTransfer is available
        if (e.dataTransfer) {
            e.dataTransfer.setData('text/plain', e.target.dataset.leftItem);
            e.dataTransfer.effectAllowed = 'move';
            // Also set data in a way that works across browsers
            e.dataTransfer.setData('application/json', JSON.stringify({
                leftItem: e.target.dataset.leftItem,
                index: e.target.dataset.index
            }));
        }
        e.target.classList.add('dragging');
        this.draggedItem = e.target;
        
        // Add visual feedback
        e.target.style.opacity = '0.5';
        e.target.style.transform = 'rotate(5deg) scale(0.95)';
    },

    handleDragEnd(e) {
        console.log('Drag end:', e.target);
        e.target.classList.remove('dragging');
        e.target.style.opacity = '';
        e.target.style.transform = '';
        this.draggedItem = null;
    },

    handleDragOver(e) {
        e.preventDefault();
        // Safari requires this for drop to work
        if (e.dataTransfer) {
            e.dataTransfer.dropEffect = 'move';
        }
    },

    handleDragEnter(e) {
        e.preventDefault();
        const dropZone = e.target.closest('.drop-zone');
        if (dropZone) {
            dropZone.classList.add('drag-over');
        }
    },

    handleDragLeave(e) {
        const dropZone = e.target.closest('.drop-zone');
        if (dropZone) {
            dropZone.classList.remove('drag-over');
        }
    },

    handleDrop(e) {
        e.preventDefault();
        const dropZone = e.target.closest('.drop-zone');
        if (!dropZone) return;
        
        dropZone.classList.remove('drag-over');
        
        let leftItem;
        try {
            // Try to get data from JSON first
            const jsonData = e.dataTransfer.getData('application/json');
            if (jsonData) {
                const data = JSON.parse(jsonData);
                leftItem = data.leftItem;
            } else {
                leftItem = e.dataTransfer.getData('text/plain');
            }
        } catch (err) {
            leftItem = e.dataTransfer.getData('text/plain');
        }
        
        const rightItem = dropZone.dataset.rightItem;
        
        console.log('Drop event:', { leftItem, rightItem, dropZone });
        
        if (!leftItem) {
            console.error('No left item data found in drop event');
            return;
        }
        
        // Check if this drop zone already has a match
        if (dropZone.classList.contains('matched')) {
            console.log('Drop zone already matched, removing previous match');
            this.removeMatch(dropZone);
        }
        
        // Update the drop zone to show the matched item
        dropZone.innerHTML = `
            <span class="matched-item">${leftItem}</span>
            <button type="button" class="remove-match-btn" title="Remove match">×</button>
        `;
        dropZone.classList.add('matched');
        
        // Update hidden input
        this.updateHiddenInput(leftItem, rightItem);
        
        // Add remove functionality
        const removeBtn = dropZone.querySelector('.remove-match-btn');
        removeBtn.addEventListener('click', (event) => {
            event.stopPropagation();
            this.removeMatch(dropZone);
        });
        
        // Update progress
        this.updateProgress();
        
        console.log('Match created successfully');
    },

    removeMatch(dropZone) {
        const leftItem = dropZone.querySelector('.matched-item').textContent;
        
        dropZone.innerHTML = `
            <span class="drop-placeholder">Drop here</span>
        `;
        dropZone.classList.remove('matched');
        
        // Remove from hidden input
        this.removeFromHiddenInput(leftItem);
        
        // Update progress
        this.updateProgress();
    },

    updateHiddenInput(leftItem, rightItem) {
        let hiddenInput = this.container.querySelector(`input[name="question_${this.questionId}_drag_drop"]`);
        if (!hiddenInput) {
            hiddenInput = document.createElement('input');
            hiddenInput.type = 'hidden';
            hiddenInput.name = `question_${this.questionId}_drag_drop`;
            this.container.appendChild(hiddenInput);
        }
        
        let matches = {};
        try {
            matches = JSON.parse(hiddenInput.value || '{}');
        } catch (e) {
            matches = {};
        }
        
        matches[leftItem] = rightItem;
        hiddenInput.value = JSON.stringify(matches);
    },

    removeFromHiddenInput(leftItem) {
        const hiddenInput = this.container.querySelector(`input[name="question_${this.questionId}_drag_drop"]`);
        if (!hiddenInput) return;
        
        let matches = {};
        try {
            matches = JSON.parse(hiddenInput.value || '{}');
        } catch (e) {
            matches = {};
        }
        
        delete matches[leftItem];
        hiddenInput.value = JSON.stringify(matches);
    },

    clearAllMatches() {
        const dropZones = this.container.querySelectorAll('.drop-zone.matched');
        dropZones.forEach(zone => {
            zone.innerHTML = `<span class="drop-placeholder">Drop here</span>`;
            zone.classList.remove('matched');
        });
        
        // Clear hidden input
        const hiddenInput = this.container.querySelector(`input[name="question_${this.questionId}_drag_drop"]`);
        if (hiddenInput) {
            hiddenInput.value = '{}';
        }
        
        this.updateProgress();
    },

    updateProgress() {
        const totalPairs = this.container.querySelectorAll('.drop-zone').length;
        const matchedPairs = this.container.querySelectorAll('.drop-zone.matched').length;
        
        const progressBar = this.container.querySelector('.matching-progress');
        if (progressBar) {
            const percentage = (matchedPairs / totalPairs) * 100;
            progressBar.style.width = `${percentage}%`;
            
            const progressText = this.container.querySelector('.progress-text');
            if (progressText) {
                progressText.textContent = `${matchedPairs}/${totalPairs} matched`;
            }
        }
    },

    // Touch event handlers for mobile devices
    handleTouchStart(e) {
        if (e.target.classList.contains('drag-item')) {
            console.log('Touch start on drag item:', e.target);
            e.preventDefault();
            this.touchStartX = e.touches[0].clientX;
            this.touchStartY = e.touches[0].clientY;
            this.touchDraggedItem = e.target;
            e.target.classList.add('dragging');
            e.target.style.opacity = '0.5';
            e.target.style.transform = 'rotate(5deg) scale(0.95)';
        }
    },

    handleTouchMove(e) {
        if (this.touchDraggedItem) {
            e.preventDefault();
            const touch = e.touches[0];
            const deltaX = touch.clientX - this.touchStartX;
            const deltaY = touch.clientY - this.touchStartY;
            
            // Only start moving if we've moved a minimum distance
            if (Math.abs(deltaX) > 5 || Math.abs(deltaY) > 5) {
                // Move the dragged item
                this.touchDraggedItem.style.transform = `translate(${deltaX}px, ${deltaY}px) rotate(5deg) scale(0.95)`;
                
                // Check if we're over a drop zone
                const elementBelow = document.elementFromPoint(touch.clientX, touch.clientY);
                const dropZone = elementBelow ? elementBelow.closest('.drop-zone') : null;
                
                // Remove previous drag-over class
                this.container.querySelectorAll('.drop-zone.drag-over').forEach(zone => {
                    zone.classList.remove('drag-over');
                });
                
                if (dropZone) {
                    dropZone.classList.add('drag-over');
                }
            }
        }
    },

    handleTouchEnd(e) {
        if (this.touchDraggedItem) {
            console.log('Touch end on drag item:', this.touchDraggedItem);
            e.preventDefault();
            const touch = e.changedTouches[0];
            const elementBelow = document.elementFromPoint(touch.clientX, touch.clientY);
            const dropZone = elementBelow ? elementBelow.closest('.drop-zone') : null;
            
            // Reset transform and styles
            this.touchDraggedItem.style.transform = '';
            this.touchDraggedItem.style.opacity = '';
            this.touchDraggedItem.classList.remove('dragging');
            
            // Remove drag-over class
            this.container.querySelectorAll('.drop-zone.drag-over').forEach(zone => {
                zone.classList.remove('drag-over');
            });
            
            if (dropZone && this.touchDraggedItem.classList.contains('drag-item')) {
                console.log('Touch drop on zone:', dropZone);
                // Simulate a drop event
                const leftItem = this.touchDraggedItem.dataset.leftItem;
                const rightItem = dropZone.dataset.rightItem;
                
                console.log('Touch drop data:', { leftItem, rightItem });
                
                // Check if this drop zone already has a match
                if (dropZone.classList.contains('matched')) {
                    console.log('Drop zone already matched, removing previous match');
                    this.removeMatch(dropZone);
                }
                
                // Update the drop zone
                dropZone.innerHTML = `
                    <span class="matched-item">${leftItem}</span>
                    <button type="button" class="remove-match-btn" title="Remove match">×</button>
                `;
                dropZone.classList.add('matched');
                
                // Update hidden input
                this.updateHiddenInput(leftItem, rightItem);
                
                // Add remove functionality
                const removeBtn = dropZone.querySelector('.remove-match-btn');
                removeBtn.addEventListener('click', (event) => {
                    event.stopPropagation();
                    this.removeMatch(dropZone);
                });
                
                // Update progress
                this.updateProgress();
                
                console.log('Touch match created successfully');
            }
            
            this.touchDraggedItem = null;
        }
    }
};

// Make available globally for non-module usage
if (typeof window !== 'undefined') {
    window.DragDropMatchingQuestion = DragDropMatchingQuestion;
    window.DragDropMatchingLearner = DragDropMatchingLearner;
} 