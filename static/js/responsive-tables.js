/**
 * Responsive Tables JavaScript Utility
 * Automatically enhances tables with responsive behavior
 */

class ResponsiveTableManager {
    constructor() {
        this.tables = [];
        this.breakpoint = 768; // Mobile breakpoint
        this.init();
    }

    init() {
        // Wait for DOM to be ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.setup());
        } else {
            this.setup();
        }
    }

    setup() {
        // Find all tables that aren't already responsive
        const tables = document.querySelectorAll('table:not(.responsive-table):not(.gradebook-table)');
        
        tables.forEach(table => {
            // Skip tables that are already wrapped or have specific classes to ignore
            if (table.closest('.responsive-table-wrapper') || 
                table.classList.contains('ignore-responsive') ||
                table.querySelector('.mobile-card')) {
                return;
            }
            
            this.makeTableResponsive(table);
        });

        // Handle window resize
        window.addEventListener('resize', this.debounce(() => {
            this.handleResize();
        }, 250));

        // Handle dynamic content
        this.observeForNewTables();
    }

    makeTableResponsive(table) {
        // Get table headers
        const headers = Array.from(table.querySelectorAll('thead th, thead td'))
            .map(th => th.textContent.trim());

        if (headers.length === 0) return;

        // Create wrapper
        const wrapper = document.createElement('div');
        wrapper.className = 'auto-responsive-table-wrapper';
        table.parentNode.insertBefore(wrapper, table);

        // Create desktop container
        const desktopContainer = document.createElement('div');
        desktopContainer.className = 'auto-desktop-table table-scroll-wrapper';
        
        // Create mobile container
        const mobileContainer = document.createElement('div');
        mobileContainer.className = 'auto-mobile-cards mobile-table-cards';

        // Move table to desktop container
        desktopContainer.appendChild(table);
        table.classList.add('responsive-table');

        // Generate mobile cards
        this.generateMobileCards(table, mobileContainer, headers);

        // Add to wrapper
        wrapper.appendChild(desktopContainer);
        wrapper.appendChild(mobileContainer);

        // Store reference
        this.tables.push({
            wrapper,
            table,
            desktopContainer,
            mobileContainer,
            headers
        });
    }

    generateMobileCards(table, container, headers) {
        const rows = table.querySelectorAll('tbody tr');
        
        rows.forEach(row => {
            const cells = row.querySelectorAll('td');
            if (cells.length === 0) return;

            const card = document.createElement('div');
            card.className = 'mobile-card auto-generated';

            // Card header (first cell becomes title)
            const firstCell = cells[0];
            if (firstCell) {
                const header = document.createElement('div');
                header.className = 'mobile-card-header';
                
                const title = document.createElement('div');
                title.className = 'mobile-card-title';
                title.innerHTML = firstCell.innerHTML;
                header.appendChild(title);
                
                card.appendChild(header);
            }

            // Card body (remaining cells)
            const body = document.createElement('div');
            body.className = 'mobile-card-body';

            cells.forEach((cell, index) => {
                if (index === 0) return; // Skip first cell (already used as title)

                const cardRow = document.createElement('div');
                cardRow.className = 'mobile-card-row';

                const label = document.createElement('span');
                label.className = 'mobile-card-label';
                label.textContent = headers[index] + ':';

                const value = document.createElement('span');
                value.className = 'mobile-card-value';
                value.innerHTML = cell.innerHTML;

                cardRow.appendChild(label);
                cardRow.appendChild(value);
                body.appendChild(cardRow);
            });

            card.appendChild(body);
            container.appendChild(card);
        });

        // Handle empty state
        if (rows.length === 0 || (rows.length === 1 && rows[0].cells.length === 1)) {
            const emptyState = document.createElement('div');
            emptyState.className = 'table-empty';
            emptyState.innerHTML = `
                <div class="table-empty-icon">
                    <i class="fas fa-table"></i>
                </div>
                <div class="table-empty-title">No data available</div>
                <div class="table-empty-description">No information to display at this time.</div>
            `;
            container.appendChild(emptyState);
        }
    }

    handleResize() {
        // Update visibility based on screen size
        const isMobile = window.innerWidth < this.breakpoint;
        
        this.tables.forEach(tableData => {
            if (isMobile) {
                tableData.desktopContainer.style.display = 'none';
                tableData.mobileContainer.style.display = 'block';
            } else {
                tableData.desktopContainer.style.display = 'block';
                tableData.mobileContainer.style.display = 'none';
            }
        });
    }

    observeForNewTables() {
        // Observe for dynamically added tables
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                mutation.addedNodes.forEach((node) => {
                    if (node.nodeType === 1) { // Element node
                        const newTables = node.querySelectorAll ? 
                            node.querySelectorAll('table:not(.responsive-table):not(.gradebook-table)') : 
                            [];
                        
                        newTables.forEach(table => {
                            if (!table.closest('.responsive-table-wrapper') &&
                                !table.classList.contains('ignore-responsive')) {
                                this.makeTableResponsive(table);
                            }
                        });
                    }
                });
            });
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    }

    // Utility function for debouncing
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    // Method to refresh specific table
    refreshTable(tableElement) {
        const tableData = this.tables.find(t => t.table === tableElement);
        if (tableData) {
            // Clear mobile container
            tableData.mobileContainer.innerHTML = '';
            
            // Regenerate mobile cards
            this.generateMobileCards(
                tableData.table, 
                tableData.mobileContainer, 
                tableData.headers
            );
        }
    }

    // Method to add a table manually
    addTable(tableElement) {
        if (!tableElement.classList.contains('responsive-table') &&
            !tableElement.closest('.responsive-table-wrapper')) {
            this.makeTableResponsive(tableElement);
        }
    }
}

// Auto-responsive table CSS (inline for immediate application)
const autoResponsiveCSS = `
.auto-responsive-table-wrapper {
    background: white;
    border-radius: 0.5rem;
    box-shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1);
    overflow: hidden;
    margin-bottom: 1rem;
}

.auto-desktop-table {
    display: block;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
}

.auto-mobile-cards {
    display: none;
    padding: 1rem;
}

.mobile-card.auto-generated {
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 0.5rem;
    padding: 1rem;
    margin-bottom: 1rem;
}

.mobile-card.auto-generated:last-child {
    margin-bottom: 0;
}

@media (max-width: 768px) {
    .auto-desktop-table {
        display: none !important;
    }
    
    .auto-mobile-cards {
        display: block !important;
    }
}

/* Ensure auto-generated tables have proper styling */
.auto-responsive-table-wrapper table.responsive-table th {
    background-color: #f9fafb;
    font-weight: 600;
    color: #374151;
    font-size: 0.875rem;
    padding: 0.75rem 1rem;
}

.auto-responsive-table-wrapper table.responsive-table td {
    padding: 0.75rem 1rem;
    color: #6b7280;
    font-size: 0.875rem;
    border-bottom: 1px solid #e5e7eb;
}

.auto-responsive-table-wrapper table.responsive-table tr:hover td {
    background-color: #f9fafb;
}
`;

// Add CSS to document
function addAutoResponsiveCSS() {
    if (!document.getElementById('auto-responsive-table-css')) {
        const style = document.createElement('style');
        style.id = 'auto-responsive-table-css';
        style.textContent = autoResponsiveCSS;
        document.head.appendChild(style);
    }
}

// Initialize everything
addAutoResponsiveCSS();
const responsiveTableManager = new ResponsiveTableManager();

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ResponsiveTableManager;
} else if (typeof window !== 'undefined') {
    window.ResponsiveTableManager = ResponsiveTableManager;
    window.responsiveTableManager = responsiveTableManager;
}
