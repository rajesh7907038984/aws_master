document.addEventListener('DOMContentLoaded', function() {
    // Tab functionality
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabButtons.forEach(button => {
        button.addEventListener('click', function() {
            // Remove active class from all buttons and contents
            tabButtons.forEach(btn => {
                btn.classList.remove('active');
                btn.classList.remove('active-tab');
                btn.classList.remove('border-blue-600');
                btn.classList.add('text-gray-400');
            });
            
            tabContents.forEach(content => {
                content.classList.remove('active');
                content.classList.add('hidden');
            });
            
            // Add active class to clicked button
            this.classList.add('active');
            this.classList.add('active-tab');
            this.classList.add('border-blue-600');
            this.classList.remove('text-gray-400');
            
            // Show corresponding content
            const target = this.getAttribute('data-tab-target');
            const targetContent = document.querySelector(target);
            if (targetContent) {
                targetContent.classList.add('active');
                targetContent.classList.remove('hidden');
            }
        });
    });
    
    // Grid/List view toggle
    const gridViewBtn = document.getElementById('grid-view');
    const listViewBtn = document.getElementById('list-view');
    const topicsContainer = document.getElementById('topics-container');
    
    if (gridViewBtn && listViewBtn && topicsContainer) {
        gridViewBtn.addEventListener('click', function() {
            topicsContainer.classList.remove('flex', 'flex-col');
            topicsContainer.classList.add('grid', 'grid-cols-1', 'md:grid-cols-2', 'lg:grid-cols-3');
            
            gridViewBtn.classList.add('active');
            listViewBtn.classList.remove('active');
        });
        
        listViewBtn.addEventListener('click', function() {
            topicsContainer.classList.remove('grid', 'grid-cols-1', 'md:grid-cols-2', 'lg:grid-cols-3');
            topicsContainer.classList.add('flex', 'flex-col');
            
            listViewBtn.classList.add('active');
            gridViewBtn.classList.remove('active');
        });
    }

    // Initialize and enhance progress bars
    const progressBars = document.querySelectorAll('.topic-item .bg-blue-600');
    progressBars.forEach(bar => {
        // If width not set, ensure it's 0%
        if (!bar.style.width) {
            bar.style.width = '0%';
        }
        
        // Add animation effect when hovering on the topic
        const topicItem = bar.closest('.topic-item');
        if (topicItem) {
            topicItem.addEventListener('mouseenter', function() {
                bar.style.transition = 'width 0.3s ease-in-out, background-color 0.3s ease';
                if (parseFloat(bar.style.width) > 0) {
                    bar.style.filter = 'brightness(1.2)';
                }
            });
            
            topicItem.addEventListener('mouseleave', function() {
                bar.style.filter = 'brightness(1)';
            });
        }
    });

    // Update percentage display to match the progress bar
    const progressTexts = document.querySelectorAll('.topic-item .text-xs.text-gray-400');
    progressTexts.forEach(text => {
        const bar = text.previousElementSibling.querySelector('.bg-blue-600');
        if (bar && bar.style.width) {
            const percentage = bar.style.width;
            if (text.textContent.trim() === '0%' && parseInt(percentage) > 0) {
                text.textContent = percentage;
            }
        }
    });
}); 