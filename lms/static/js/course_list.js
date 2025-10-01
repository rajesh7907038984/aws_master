document.addEventListener('DOMContentLoaded', function() {
    const courseContainer = document.getElementById('course-container');
    const gridViewBtn = document.getElementById('grid-view');
    const listViewBtn = document.getElementById('list-view');

    // Check if all required elements exist
    if (!courseContainer || !gridViewBtn || !listViewBtn) {
        console.warn('Course list view toggle: Required elements not found');
        return;
    }

    // Check for saved preference
    const savedView = localStorage.getItem('courseViewPreference');
    if (savedView) {
        applyView(savedView);
    }

    gridViewBtn.addEventListener('click', function() {
        applyView('grid');
        localStorage.setItem('courseViewPreference', 'grid');
    });

    listViewBtn.addEventListener('click', function() {
        applyView('list');
        localStorage.setItem('courseViewPreference', 'list');
    });

    function applyView(view) {
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
    }
}); 