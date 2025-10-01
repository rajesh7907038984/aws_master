// Category Field JavaScript

// Function to initialize category field
function initializeCategoryField() {
    const categorySelect = document.getElementById('category');
    if (categorySelect) {
        // Add custom styling
        categorySelect.classList.add('category-select');
        
        // Add change event listener
        categorySelect.addEventListener('change', function(e) {
            const selectedValue = e.target.value;
            handleCategoryChange(selectedValue);
        });
    }
}

// Function to handle category change
function handleCategoryChange(categoryId) {
    // You can add additional logic here when category changes
    console.log('Category changed to:', categoryId);
}

// Function to update category field
function updateCategoryField(categories) {
    const categorySelect = document.getElementById('category');
    if (categorySelect) {
        // Store current value
        const currentValue = categorySelect.value;
        
        // Clear existing options except the first one
        while (categorySelect.options.length > 1) {
            categorySelect.remove(1);
        }
        
        // Add new options
        categories.forEach(category => {
            const option = new Option(category.name, category.id);
            categorySelect.add(option);
        });
        
        // Restore previous value if it exists in new options
        if (currentValue) {
            const optionExists = Array.from(categorySelect.options).some(option => option.value === currentValue);
            if (optionExists) {
                categorySelect.value = currentValue;
            }
        }
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initializeCategoryField();
}); 