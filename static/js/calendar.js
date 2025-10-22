// Calendar JavaScript
class Calendar {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.currentDate = new Date();
        this.events = [];
        this.selectedDate = null;
        this.init();
    }

    init() {
        this.render();
        this.bindEvents();
        this.loadEvents();
    }

    bindEvents() {
        // Navigation buttons
        const prevBtn = this.container.querySelector('.calendar-prev');
        const nextBtn = this.container.querySelector('.calendar-next');
        const todayBtn = this.container.querySelector('.calendar-today');

        if (prevBtn) {
            prevBtn.addEventListener('click', () => this.previousMonth());
        }
        if (nextBtn) {
            nextBtn.addEventListener('click', () => this.nextMonth());
        }
        if (todayBtn) {
            todayBtn.addEventListener('click', () => this.goToToday());
        }

        // Day clicks
        this.container.addEventListener('click', (e) => {
            const dayElement = e.target.closest('.calendar-day');
            if (dayElement && !dayElement.classList.contains('other-month')) {
                this.selectDate(dayElement);
            }
        });
    }

    render() {
        const year = this.currentDate.getFullYear();
        const month = this.currentDate.getMonth();
        
        // Update month/year display
        const monthYearElement = this.container.querySelector('.calendar-month-year');
        if (monthYearElement) {
            monthYearElement.textContent = this.currentDate.toLocaleDateString('en-US', {
                month: 'long',
                year: 'numeric'
            });
        }

        // Clear calendar
        const calendarGrid = this.container.querySelector('.calendar-grid');
        if (!calendarGrid) return;

        // Remove existing day elements (keep headers)
        const existingDays = calendarGrid.querySelectorAll('.calendar-day');
        existingDays.forEach(day => day.remove());

        // Get first day of month and number of days
        const firstDay = new Date(year, month, 1);
        const lastDay = new Date(year, month + 1, 0);
        const today = new Date();

        // Add empty cells for days before month starts
        for (let i = 0; i < firstDay.getDay(); i++) {
            const emptyDay = document.createElement('div');
            emptyDay.className = 'calendar-day other-month';
            const prevMonthDate = new Date(firstDay);
            prevMonthDate.setDate(prevMonthDate.getDate() - (firstDay.getDay() - i));
            emptyDay.innerHTML = `<div class="calendar-day-number">${prevMonthDate.getDate()}</div>`;
            calendarGrid.appendChild(emptyDay);
        }

        // Add days of current month
        for (let day = 1; day <= lastDay.getDate(); day++) {
            const dayElement = document.createElement('div');
            const dayDate = new Date(year, month, day);
            
            dayElement.className = 'calendar-day';
            if (this.isSameDay(dayDate, today)) {
                dayElement.classList.add('today');
            }
            
            dayElement.innerHTML = `
                <div class="calendar-day-number">${day}</div>
                <div class="calendar-events" data-date="${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}"></div>
            `;
            
            calendarGrid.appendChild(dayElement);
        }

        // Add empty cells for days after month ends
        const totalCells = calendarGrid.children.length - 7; // Subtract header row
        const remainingCells = 42 - totalCells; // 6 rows * 7 days
        for (let i = 1; i <= remainingCells; i++) {
            const emptyDay = document.createElement('div');
            emptyDay.className = 'calendar-day other-month';
            emptyDay.innerHTML = `<div class="calendar-day-number">${i}</div>`;
            calendarGrid.appendChild(emptyDay);
        }

        this.renderEvents();
    }

    renderEvents() {
        // Clear existing events
        const eventContainers = this.container.querySelectorAll('.calendar-events');
        eventContainers.forEach(container => {
            container.innerHTML = '';
        });

        // Add events to calendar
        this.events.forEach(event => {
            const eventDate = new Date(event.start);
            const dateString = eventDate.toISOString().split('T')[0];
            const eventContainer = this.container.querySelector(`[data-date="${dateString}"]`);
            
            if (eventContainer) {
                const eventElement = document.createElement('div');
                eventElement.className = `calendar-event ${event.priority || 'medium'}-priority`;
                eventElement.textContent = event.title;
                eventElement.title = event.description || event.title;
                eventContainer.appendChild(eventElement);
            }
        });
    }

    loadEvents() {
        const startDate = new Date(this.currentDate.getFullYear(), this.currentDate.getMonth(), 1);
        const endDate = new Date(this.currentDate.getFullYear(), this.currentDate.getMonth() + 1, 0);
        
        const params = new URLSearchParams({
            start_date: startDate.toISOString().split('T')[0],
            end_date: endDate.toISOString().split('T')[0]
        });

        fetch(`/calendar/api/activities/?${params}`, {
            credentials: 'same-origin',
            headers: {
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || ''
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                this.events = data.activities || [];
                this.renderEvents();
            } else {
                console.error('Error loading events:', data.error);
            }
        })
        .catch(error => {
            console.error('Error loading events:', error);
        });
    }

    previousMonth() {
        this.currentDate.setMonth(this.currentDate.getMonth() - 1);
        this.render();
        this.loadEvents();
    }

    nextMonth() {
        this.currentDate.setMonth(this.currentDate.getMonth() + 1);
        this.render();
        this.loadEvents();
    }

    goToToday() {
        this.currentDate = new Date();
        this.render();
        this.loadEvents();
    }

    selectDate(dayElement) {
        // Remove previous selection
        const previousSelected = this.container.querySelector('.calendar-day.selected');
        if (previousSelected) {
            previousSelected.classList.remove('selected');
        }

        // Add selection to clicked day
        dayElement.classList.add('selected');
        this.selectedDate = dayElement;

        // Trigger custom event
        const event = new CustomEvent('dateSelected', {
            detail: {
                date: dayElement.querySelector('[data-date]')?.getAttribute('data-date'),
                element: dayElement
            }
        });
        this.container.dispatchEvent(event);
    }

    isSameDay(date1, date2) {
        return date1.getDate() === date2.getDate() &&
               date1.getMonth() === date2.getMonth() &&
               date1.getFullYear() === date2.getFullYear();
    }

    addEvent(event) {
        this.events.push(event);
        this.renderEvents();
    }

    removeEvent(eventId) {
        this.events = this.events.filter(event => event.id !== eventId);
        this.renderEvents();
    }

    updateEvent(eventId, updatedEvent) {
        const index = this.events.findIndex(event => event.id === eventId);
        if (index !== -1) {
            this.events[index] = { ...this.events[index], ...updatedEvent };
            this.renderEvents();
        }
    }
}

// Event Modal
class EventModal {
    constructor() {
        this.modal = null;
        this.isOpen = false;
        this.currentEvent = null;
    }

    open(event = null) {
        this.currentEvent = event;
        this.createModal();
        this.showModal();
    }

    createModal() {
        if (this.modal) {
            this.modal.remove();
        }

        this.modal = document.createElement('div');
        this.modal.className = 'event-modal';
        this.modal.innerHTML = `
            <div class="event-modal-content">
                <div class="event-modal-header">
                    <h3 class="event-modal-title">${this.currentEvent ? 'Edit Event' : 'Add Event'}</h3>
                    <button class="event-modal-close">&times;</button>
                </div>
                <form class="event-form" id="eventForm">
                    <div class="form-group">
                        <label class="form-label" for="eventTitle">Title</label>
                        <input type="text" id="eventTitle" name="title" class="form-input" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label" for="eventDescription">Description</label>
                        <textarea id="eventDescription" name="description" class="form-input form-textarea"></textarea>
                    </div>
                    <div class="form-group">
                        <label class="form-label" for="eventStart">Start Date</label>
                        <input type="datetime-local" id="eventStart" name="start" class="form-input" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label" for="eventEnd">End Date</label>
                        <input type="datetime-local" id="eventEnd" name="end" class="form-input" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label" for="eventColor">Color</label>
                        <select id="eventColor" name="color" class="form-select">
                            <option value="#3b82f6">Blue</option>
                            <option value="#dc2626">Red</option>
                            <option value="#f59e0b">Orange</option>
                            <option value="#10b981">Green</option>
                            <option value="#8b5cf6">Purple</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="form-label" for="eventPriority">Priority</label>
                        <select id="eventPriority" name="priority" class="form-select">
                            <option value="low">Low</option>
                            <option value="medium">Medium</option>
                            <option value="high">High</option>
                        </select>
                    </div>
                    <div class="form-buttons">
                        ${this.currentEvent ? '<button type="button" class="btn btn-danger" id="deleteEvent">Delete</button>' : ''}
                        <button type="button" class="btn btn-secondary" id="cancelEvent">Cancel</button>
                        <button type="submit" class="btn btn-primary">${this.currentEvent ? 'Update' : 'Create'}</button>
                    </div>
                </form>
            </div>
        `;

        document.body.appendChild(this.modal);
        this.bindModalEvents();
        this.populateForm();
    }

    bindModalEvents() {
        const closeBtn = this.modal.querySelector('.event-modal-close');
        const cancelBtn = this.modal.querySelector('#cancelEvent');
        const form = this.modal.querySelector('#eventForm');
        const deleteBtn = this.modal.querySelector('#deleteEvent');

        closeBtn.addEventListener('click', () => this.close());
        cancelBtn.addEventListener('click', () => this.close());
        
        if (deleteBtn) {
            deleteBtn.addEventListener('click', () => this.deleteEvent());
        }

        form.addEventListener('submit', (e) => {
            e.preventDefault();
            this.saveEvent();
        });

        // Close on backdrop click
        this.modal.addEventListener('click', (e) => {
            if (e.target === this.modal) {
                this.close();
            }
        });
    }

    populateForm() {
        if (this.currentEvent) {
            document.getElementById('eventTitle').value = this.currentEvent.title || '';
            document.getElementById('eventDescription').value = this.currentEvent.description || '';
            document.getElementById('eventStart').value = this.currentEvent.start || '';
            document.getElementById('eventEnd').value = this.currentEvent.end || '';
            document.getElementById('eventColor').value = this.currentEvent.color || '#3b82f6';
            document.getElementById('eventPriority').value = this.currentEvent.priority || 'medium';
        }
    }

    showModal() {
        this.modal.style.display = 'flex';
        this.isOpen = true;
        document.body.style.overflow = 'hidden';
    }

    close() {
        if (this.modal) {
            this.modal.remove();
            this.modal = null;
        }
        this.isOpen = false;
        this.currentEvent = null;
        document.body.style.overflow = '';
    }

    saveEvent() {
        const formData = new FormData(this.modal.querySelector('#eventForm'));
        const eventData = {
            title: formData.get('title'),
            description: formData.get('description'),
            start: formData.get('start'),
            end: formData.get('end'),
            color: formData.get('color'),
            priority: formData.get('priority')
        };

        const url = this.currentEvent ? 
            `/calendar/events/${this.currentEvent.id}/` : 
            '/calendar/events/create/';
        const method = this.currentEvent ? 'PUT' : 'POST';

        fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || ''
            },
            body: JSON.stringify(eventData)
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                alert('Error: ' + data.error);
            } else {
                this.close();
                // Trigger calendar refresh
                const calendar = window.calendarInstance;
                if (calendar) {
                    calendar.loadEvents();
                }
            }
        })
        .catch(error => {
            console.error('Error saving event:', error);
            alert('Error saving event');
        });
    }

    deleteEvent() {
        if (!this.currentEvent) return;

        if (confirm('Are you sure you want to delete this event?')) {
            fetch(`/calendar/events/${this.currentEvent.id}/`, {
                method: 'DELETE',
                headers: {
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || ''
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    this.close();
                    // Trigger calendar refresh
                    const calendar = window.calendarInstance;
                    if (calendar) {
                        calendar.loadEvents();
                    }
                } else {
                    alert('Error deleting event');
                }
            })
            .catch(error => {
                console.error('Error deleting event:', error);
                alert('Error deleting event');
            });
        }
    }
}

// Initialize calendar when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    const calendarContainer = document.getElementById('calendar');
    if (calendarContainer) {
        window.calendarInstance = new Calendar('calendar');
        window.eventModal = new EventModal();

        // Add event button
        const addEventBtn = document.getElementById('addEventBtn');
        if (addEventBtn) {
            addEventBtn.addEventListener('click', () => {
                window.eventModal.open();
            });
        }

        // Date selection handler
        calendarContainer.addEventListener('dateSelected', (e) => {
            console.log('Date selected:', e.detail.date);
            // You can add custom logic here for date selection
        });
    }
});
