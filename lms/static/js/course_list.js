document.addEventListener('DOMContentLoaded', function() {
    try {
        const courseContainer = document.getElementById('course-container');
        const gridViewBtn = document.getElementById('grid-view');
        const listViewBtn = document.getElementById('list-view');

        // Check if all required elements exist
        if (!courseContainer || !gridViewBtn || !listViewBtn) {
            return;
        }

        // Check for saved preference
        const savedView = localStorage.getItem('courseViewPreference');
        if (savedView) {
            applyView(savedView);
        }

        gridViewBtn.addEventListener('click', function() {
            try {
                applyView('grid');
                localStorage.setItem('courseViewPreference', 'grid');
            } catch (error) {
                console.error('Error handling grid view click:', error);
            }
        });

        listViewBtn.addEventListener('click', function() {
            try {
                applyView('list');
                localStorage.setItem('courseViewPreference', 'list');
            } catch (error) {
                console.error('Error handling list view click:', error);
            }
        });

        function applyView(view) {
            try {
                if (view === 'grid') {
                    courseContainer.classList.remove('course-list');
                    courseContainer.classList.add('course-grid');
                    gridViewBtn.classList.add('bg-gray-100');
                    listViewBtn.classList.remove('bg-gray-100');
                } else {
                    courseContainer.classList.remove('course-grid');
                    courseContainer.classList.add('course-list');
                    listViewBtn.classList.add('bg-gray-100');
                    gridViewBtn.classList.remove('bg-gray-100');
                }
            } catch (error) {
                console.error('Error applying view:', error);
            }
        }
    } catch (error) {
        console.error('Error initializing course list:', error);
    }
}); 