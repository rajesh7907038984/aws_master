from django.contrib import admin
from .models import CalendarEvent

@admin.register(CalendarEvent)
class CalendarEventAdmin(admin.ModelAdmin):
    list_display = ('title', 'start_date', 'end_date', 'created_by', 'is_all_day')
    list_filter = ('is_all_day', 'created_by')
    search_fields = ('title', 'description') 