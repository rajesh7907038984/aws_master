function handleContentTypeChange(select) {
    if (!select) return;

    const contentTypes = {
        'file': '.field-content_file',
        'text': '.field-text_content',
        'url': '.field-web_url',
        'embed': '.field-embed_code'
    };

    // Hide all content type fields
    Object.values(contentTypes).forEach(selector => {
        const element = document.querySelector(selector);
        if (element) {
            element.classList.remove('show');
        }
    });

    // Show the selected content type field
    const selectedType = select.value;
    const selectedSelector = contentTypes[selectedType];
    if (selectedSelector) {
        const element = document.querySelector(selectedSelector);
        if (element) {
            element.classList.add('show');
        }
    }
} 