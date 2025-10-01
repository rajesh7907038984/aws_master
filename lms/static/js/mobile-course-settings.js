/**
 * Mobile Course Settings Enhancement
 * Improves the course settings page experience on mobile devices
 */

class MobileCourseSettings {
    constructor() {
        this.init();
    }

    init() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.setup());
        } else {
            this.setup();
        }
    }

    setup() {
        this.enhanceFormLayout();
        this.addMobileNavigation();
        this.optimizeInputFields();
        this.handleAccordionBehavior();
    }

    enhanceFormLayout() {
        // Make form sections more mobile-friendly
        const formSections = document.querySelectorAll('.form-section, .course-settings-section');
        
        formSections.forEach(section => {
            section.classList.add('mobile-optimized-section');
        });

        // Stack form fields vertically on mobile
        const formRows = document.querySelectorAll('.form-row, .grid-cols-2');
        formRows.forEach(row => {
            row.classList.add('mobile-stacked');
        });
    }

    addMobileNavigation() {
        // Add mobile-friendly section navigation if it doesn't exist
        const sections = document.querySelectorAll('h2, h3, .section-title');
        if (sections.length > 3) {
            this.createMobileNav(sections);
        }
    }

    createMobileNav(sections) {
        const nav = document.createElement('div');
        nav.className = 'mobile-course-settings-nav';
        nav.innerHTML = `
            <button type="button" class="mobile-nav-toggle">
                <i class="fas fa-bars"></i>
                <span>Quick Navigation</span>
                <i class="fas fa-chevron-down"></i>
            </button>
            <div class="mobile-nav-menu hidden">
                ${Array.from(sections).map((section, index) => 
                    `<a href="#section-${index}" class="mobile-nav-item">
                        ${section.textContent.trim()}
                    </a>`
                ).join('')}
            </div>
        `;

        // Add IDs to sections
        sections.forEach((section, index) => {
            section.id = `section-${index}`;
        });

        // Insert navigation
        const form = document.querySelector('form, .course-settings-form');
        if (form) {
            form.insertBefore(nav, form.firstChild);
        }

        // Handle navigation toggle
        const toggle = nav.querySelector('.mobile-nav-toggle');
        const menu = nav.querySelector('.mobile-nav-menu');
        
        toggle.addEventListener('click', () => {
            menu.classList.toggle('hidden');
            toggle.querySelector('.fa-chevron-down').classList.toggle('rotate-180');
        });

        // Handle navigation clicks
        nav.querySelectorAll('.mobile-nav-item').forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                const targetId = item.getAttribute('href');
                const target = document.querySelector(targetId);
                if (target) {
                    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    menu.classList.add('hidden');
                }
            });
        });
    }

    optimizeInputFields() {
        // Enhance form inputs for mobile
        const inputs = document.querySelectorAll('input, select, textarea');
        
        inputs.forEach(input => {
            // Add mobile-friendly attributes
            if (input.type === 'email') {
                input.setAttribute('inputmode', 'email');
            }
            if (input.type === 'tel') {
                input.setAttribute('inputmode', 'tel');
            }
            if (input.type === 'number') {
                input.setAttribute('inputmode', 'numeric');
            }
            
            // Increase touch target size
            input.classList.add('mobile-touch-input');
        });

        // Handle file inputs specially
        const fileInputs = document.querySelectorAll('input[type="file"]');
        fileInputs.forEach(input => {
            this.enhanceFileInput(input);
        });
    }

    enhanceFileInput(input) {
        const wrapper = document.createElement('div');
        wrapper.className = 'mobile-file-input-wrapper';
        
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'mobile-file-input-button';
        button.innerHTML = '<i class="fas fa-upload"></i> Choose File';
        
        const info = document.createElement('div');
        info.className = 'mobile-file-input-info';
        info.textContent = 'No file selected';
        
        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(button);
        wrapper.appendChild(info);
        wrapper.appendChild(input);
        
        button.addEventListener('click', () => input.click());
        
        input.addEventListener('change', () => {
            if (input.files && input.files.length > 0) {
                info.textContent = input.files[0].name;
                info.classList.add('file-selected');
            } else {
                info.textContent = 'No file selected';
                info.classList.remove('file-selected');
            }
        });
    }

    handleAccordionBehavior() {
        // Convert complex form sections to accordions on mobile
        const accordionTriggers = document.querySelectorAll('[data-accordion-target]');
        
        accordionTriggers.forEach(trigger => {
            trigger.addEventListener('click', () => {
                const targetId = trigger.getAttribute('data-accordion-target');
                const target = document.querySelector(targetId);
                
                if (target) {
                    target.classList.toggle('hidden');
                    
                    const icon = trigger.querySelector('.fa-chevron-down, .fa-chevron-up');
                    if (icon) {
                        icon.classList.toggle('fa-chevron-down');
                        icon.classList.toggle('fa-chevron-up');
                    }
                }
            });
        });
    }
}

// CSS for mobile course settings
const mobileCourseSettingsCSS = `
.mobile-course-settings-nav {
    margin-bottom: 1rem;
    display: none;
}

.mobile-nav-toggle {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem;
    background: #f3f4f6;
    border: 1px solid #d1d5db;
    border-radius: 0.5rem;
    font-size: 0.875rem;
    font-weight: 500;
    color: #374151;
    cursor: pointer;
    transition: all 0.15s ease;
}

.mobile-nav-toggle:hover {
    background: #e5e7eb;
}

.mobile-nav-menu {
    margin-top: 0.5rem;
    background: white;
    border: 1px solid #d1d5db;
    border-radius: 0.5rem;
    box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
    overflow: hidden;
}

.mobile-nav-item {
    display: block;
    padding: 0.75rem 1rem;
    color: #374151;
    text-decoration: none;
    border-bottom: 1px solid #f3f4f6;
    transition: background-color 0.15s ease;
}

.mobile-nav-item:hover {
    background: #f9fafb;
}

.mobile-nav-item:last-child {
    border-bottom: none;
}

.mobile-optimized-section {
    margin-bottom: 2rem;
    padding: 1rem;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 0.5rem;
}

.mobile-touch-input {
    min-height: 44px; /* Apple's minimum touch target size */
    font-size: 16px; /* Prevents zoom on iOS */
}

.mobile-file-input-wrapper {
    position: relative;
    display: inline-block;
    width: 100%;
}

.mobile-file-input-wrapper input[type="file"] {
    position: absolute;
    opacity: 0;
    width: 0.1px;
    height: 0.1px;
    overflow: hidden;
}

.mobile-file-input-button {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    padding: 0.75rem 1rem;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 0.5rem;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: background-color 0.15s ease;
    min-height: 44px;
}

.mobile-file-input-button:hover {
    background: #2563eb;
}

.mobile-file-input-button i {
    margin-right: 0.5rem;
}

.mobile-file-input-info {
    margin-top: 0.5rem;
    padding: 0.5rem;
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 0.375rem;
    font-size: 0.875rem;
    color: #6b7280;
    text-align: center;
}

.mobile-file-input-info.file-selected {
    color: #059669;
    background: #ecfdf5;
    border-color: #10b981;
}

@media (max-width: 768px) {
    .mobile-course-settings-nav {
        display: block;
    }
    
    .mobile-stacked {
        display: flex !important;
        flex-direction: column !important;
        gap: 1rem;
    }
    
    .mobile-stacked > * {
        width: 100% !important;
        max-width: none !important;
    }
    
    /* Form field improvements */
    .form-group,
    .field-group {
        margin-bottom: 1.5rem;
    }
    
    .form-group label,
    .field-group label {
        display: block;
        margin-bottom: 0.5rem;
        font-weight: 600;
        color: #374151;
    }
    
    /* Button improvements */
    .btn,
    button {
        min-height: 44px;
        padding: 0.75rem 1.5rem;
        font-size: 0.875rem;
        border-radius: 0.5rem;
    }
    
    /* Checkbox and radio improvements */
    input[type="checkbox"],
    input[type="radio"] {
        width: 20px;
        height: 20px;
        margin-right: 0.5rem;
    }
    
    /* Select improvements */
    select {
        appearance: none;
        background-image: url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%236b7280' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='m6 8 4 4 4-4'/%3e%3c/svg%3e");
        background-position: right 0.5rem center;
        background-repeat: no-repeat;
        background-size: 1.5em 1.5em;
        padding-right: 2.5rem;
    }
    
    /* Textarea improvements */
    textarea {
        min-height: 120px;
        resize: vertical;
    }
}

@media (max-width: 480px) {
    .mobile-optimized-section {
        margin-left: -1rem;
        margin-right: -1rem;
        border-radius: 0;
        border-left: none;
        border-right: none;
    }
    
    .mobile-nav-toggle,
    .mobile-touch-input,
    .mobile-file-input-button {
        min-height: 48px; /* Larger touch targets for small screens */
    }
}
`;

// Add CSS
function addMobileCourseSettingsCSS() {
    if (!document.getElementById('mobile-course-settings-css')) {
        const style = document.createElement('style');
        style.id = 'mobile-course-settings-css';
        style.textContent = mobileCourseSettingsCSS;
        document.head.appendChild(style);
    }
}

// Initialize
addMobileCourseSettingsCSS();

// Only initialize on course settings pages
if (window.location.pathname.includes('course') && 
    (window.location.pathname.includes('settings') || 
     window.location.pathname.includes('edit'))) {
    new MobileCourseSettings();
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MobileCourseSettings;
} else if (typeof window !== 'undefined') {
    window.MobileCourseSettings = MobileCourseSettings;
}