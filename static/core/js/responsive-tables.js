/**
 * Responsive Tables - Handles table responsiveness on mobile devices
 */
(function() {
    'use strict';
    
    const ResponsiveTables = {
        init: function() {
            this.setupResponsiveTables();
            this.setupTableFilters();
            this.setupTableSorting();
            this.handleWindowResize();
        },
        
        setupResponsiveTables: function() {
            const tables = document.querySelectorAll('table[data-responsive]');
            
            tables.forEach(table => {
                this.makeTableResponsive(table);
            });
        },
        
        makeTableResponsive: function(table) {
            // Add responsive wrapper
            if (!table.parentNode.classList.contains('table-responsive')) {
                const wrapper = document.createElement('div');
                wrapper.className = 'table-responsive overflow-x-auto';
                table.parentNode.insertBefore(wrapper, table);
                wrapper.appendChild(table);
            }
            
            // Add mobile labels
            this.addMobileLabels(table);
        },
        
        addMobileLabels: function(table) {
            const headers = Array.from(table.querySelectorAll('th'));
            const rows = table.querySelectorAll('tbody tr');
            
            rows.forEach(row => {
                const cells = row.querySelectorAll('td');
                cells.forEach((cell, index) => {
                    if (headers[index]) {
                        cell.setAttribute('data-label', headers[index].textContent.trim());
                    }
                });
            });
        },
        
        setupTableFilters: function() {
            const filterInputs = document.querySelectorAll('[data-table-filter]');
            
            filterInputs.forEach(input => {
                input.addEventListener('input', this.handleTableFilter.bind(this));
            });
        },
        
        handleTableFilter: function(event) {
            const input = event.target;
            const targetTable = document.querySelector(input.getAttribute('data-table-filter'));
            const filterValue = input.value.toLowerCase();
            
            if (!targetTable) return;
            
            const rows = targetTable.querySelectorAll('tbody tr');
            
            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                if (text.includes(filterValue)) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        },
        
        setupTableSorting: function() {
            const sortableHeaders = document.querySelectorAll('[data-sortable]');
            
            sortableHeaders.forEach(header => {
                header.style.cursor = 'pointer';
                header.addEventListener('click', this.handleSort.bind(this));
                
                // Add sort indicator
                if (!header.querySelector('.sort-indicator')) {
                    const indicator = document.createElement('span');
                    indicator.className = 'sort-indicator ml-2';
                    indicator.innerHTML = '↕️';
                    header.appendChild(indicator);
                }
            });
        },
        
        handleSort: function(event) {
            const header = event.currentTarget;
            const table = header.closest('table');
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            const columnIndex = Array.from(header.parentNode.children).indexOf(header);
            
            // Determine sort direction
            const currentSort = header.getAttribute('data-sort') || 'none';
            const newSort = currentSort === 'asc' ? 'desc' : 'asc';
            
            // Clear other headers
            header.parentNode.querySelectorAll('[data-sortable]').forEach(h => {
                h.setAttribute('data-sort', 'none');
                const indicator = h.querySelector('.sort-indicator');
                if (indicator) indicator.innerHTML = '↕️';
            });
            
            // Set current header
            header.setAttribute('data-sort', newSort);
            const indicator = header.querySelector('.sort-indicator');
            if (indicator) {
                indicator.innerHTML = newSort === 'asc' ? '↑' : '↓';
            }
            
            // Sort rows
            rows.sort((a, b) => {
                const aText = a.children[columnIndex].textContent.trim();
                const bText = b.children[columnIndex].textContent.trim();
                
                const aNum = parseFloat(aText);
                const bNum = parseFloat(bText);
                
                let comparison;
                if (!isNaN(aNum) && !isNaN(bNum)) {
                    comparison = aNum - bNum;
                } else {
                    comparison = aText.localeCompare(bText);
                }
                
                return newSort === 'asc' ? comparison : -comparison;
            });
            
            // Re-append sorted rows
            rows.forEach(row => tbody.appendChild(row));
        },
        
        handleWindowResize: function() {
            let resizeTimeout;
            window.addEventListener('resize', () => {
                clearTimeout(resizeTimeout);
                resizeTimeout = setTimeout(() => {
                    this.checkTableOverflow();
                }, 150);
            });
        },
        
        checkTableOverflow: function() {
            const responsiveTables = document.querySelectorAll('.table-responsive table');
            
            responsiveTables.forEach(table => {
                const wrapper = table.parentNode;
                if (table.offsetWidth > wrapper.offsetWidth) {
                    wrapper.classList.add('overflow-visible');
                } else {
                    wrapper.classList.remove('overflow-visible');
                }
            });
        }
    };
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            ResponsiveTables.init();
        });
    } else {
        ResponsiveTables.init();
    }
    
    // Export to global scope
    window.ResponsiveTables = ResponsiveTables;
})();
