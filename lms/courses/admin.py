from django.contrib import admin, messages
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.utils.html import format_html, mark_safe
from django.db import models, transaction
from django import forms
from django.shortcuts import render
from django.apps import apps
from django.urls import reverse
from django.conf import settings
import logging
import json
from django.utils import timezone

from branches.models import Branch
from users.models import CustomUser
from .models import (
    Course, Topic, CourseEnrollment
)

# Try to import optional models
try:
    from .models import CourseCategory
except ImportError:
    CourseCategory = None

try:
    from .models import CourseTopic
except ImportError:
    CourseTopic = None

try:
    from .models import LearningObjective
except ImportError:
    LearningObjective = None

try:
    from .models import CourseFeature
except ImportError:
    CourseFeature = None
from .forms import TopicAdminForm
logger = logging.getLogger(__name__)

class CourseEnrollmentInline(admin.TabularInline):
    model = CourseEnrollment
    extra = 0
    fields = ('user', 'enrolled_at', 'completed', 'completion_date')
    readonly_fields = ('enrolled_at', 'completion_date')

    def get_queryset(self, request):
        """Override to apply permissions"""
        qs = super().get_queryset(request)
        
        # Apply permissions
        if not request.user.is_superuser:
            # Filter based on user permissions
            pass
        
        return qs

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if request.user.role == 'admin':
            if obj is None:
                return True
            course = get_topic_course(obj.topic)
            return course and course.branch == request.user.branch
        if request.user.role == 'instructor':
            if obj is None:
                return True
            course = get_topic_course(obj.topic)
            return course and (course.instructor == request.user or
                              course.accessible_groups.filter(
                                  memberships__user=request.user,
                                  memberships__is_active=True
                              ).exists())
        return False

    def has_change_permission(self, request, obj=None):
        return self.has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        # Allow superusers and admins to delete topic progress records
        return request.user.is_superuser or request.user.role == 'admin'

    def has_add_permission(self, request):
        return False

    def get_readonly_fields(self, request, obj=None):
        if request.user.is_superuser:
            # Superusers can edit all fields except the auto-updated timestamp fields and display fields
            return ('last_accessed', 'first_accessed', 'completion_data_display', 'progress_data_display')
        else:
            # Non-superusers have restricted edit access
            return self.readonly_fields + ('user', 'topic', 'progress_data', 'bookmark', 'completion_data')

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser:
            if db_field.name == "user":
                kwargs["queryset"] = CustomUser.objects.filter(
                    branch=request.user.branch
                )
            elif db_field.name == "topic":
                kwargs["queryset"] = Topic.objects.filter(
                    coursetopic__course__branch=request.user.branch
                ).distinct()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_progress_display(self, obj):
        """Enhanced progress display with removed support"""
        if obj.topic.content_type == 'removed':
            removed_content = obj.topic.get_removed_content()
            if removed_content:
                registration = removed_content.package.get_registration(obj.user)
                if registration:
                    status = registration.completion_status
                    score = registration.score
                    status_display = status.replace('_', ' ').title()
                    if score is not None:
                        return "{{status_display}} (Score: {{score}}%%)"
                    return status_display
            return "Not Started"
        return "{{obj.get_progress_percentage()}}%%"

    get_progress_display.short_description = 'Progress'

    def get_status_display(self, obj):
        if obj.completed:
            return "Completed ({{obj.completion_method}})"
        if obj.attempts > 0:
            return 'In Progress'
        return 'Not Started'
        
    get_status_display.short_description = 'Status'

    def save_model(self, request, obj, form, change):
        """Ensure consistency between completion_method and manually_completed fields"""
        if 'completion_method' in form.changed_data:
            # Update manually_completed based on completion_method
            obj.manually_completed = (obj.completion_method == 'manual')
            
            # Make sure completion_data is also updated
            if not obj.completion_data:
                obj.completion_data = {}
            
            obj.completion_data.update({
                'completion_method': obj.completion_method,
                'manually_completed': obj.manually_completed
            })
        
        if 'completed' in form.changed_data and obj.completed and not obj.completed_at:
            # Set completed_at date if missing
            obj.completed_at = timezone.now()
            
            # Update completion data
            if not obj.completion_data:
                obj.completion_data = {}
                
            obj.completion_data.update({
                'completed_at': obj.completed_at.isoformat()
            })
            
            # If we're marking as completed, ensure progress_data shows 100% for video content
            if obj.topic.content_type == 'Video' or obj.topic.content_type == 'EmbedVideo':
                if not obj.progress_data:
                    obj.progress_data = {}
                
                # Set progress to 100% if marking as complete
                if obj.completed:
                    obj.progress_data['progress'] = 100.0
                
                # Add logging for debugging
                logger.info("Admin completion update for topic {{obj.topic.id}}, user {{obj.user.id}}")
                logger.info("Setting progress_data to: {{obj.progress_data}}")
        
        # Handle direct edits to progress_data field (for superusers)
        if 'progress_data' in form.changed_data and request.user.is_superuser:
            # Add logging for tracking changes
            logger.info("Direct progress_data update by admin for topic {{obj.topic.id}}, user {{obj.user.id}}")
            logger.info("New progress_data: {{obj.progress_data}}")
            
            # If progress in progress_data is 100% but completed is False, update completed
            if obj.progress_data and obj.progress_data.get('progress', 0) >= 95 and not obj.completed:
                obj.completed = True
                obj.completion_method = 'auto'
                obj.completed_at = timezone.now()
                
                # Update completion_data to match
                if not obj.completion_data:
                    obj.completion_data = {}
                
                obj.completion_data.update({
                    'completed_at': obj.completed_at.isoformat(),
                    'completion_method': 'auto',
                    'manually_completed': False
                })
                
                logger.info("Auto-setting completed=True based on progress_data value")
            
        super().save_model(request, obj, form, change)
        
    class Media:
        css = {
            'all': ('admin/css/topic_progress_admin.css',)
        }
        js = ('admin/js/topic_progress_admin.js',)

    def completion_data_display(self, obj):
        """Format completion data as readable HTML"""
        if not obj.completion_data:
            return "No completion data available"
            
        html = "<table class='completion-data'>"
        html += "<tr><th>Property</th><th>Value</th></tr>"
        
        # Extract and format main properties
        if 'completed_at' in obj.completion_data:
            html += "<tr><td>Completed At</td><td>{{obj.completion_data['completed_at']}}</td></tr>"
        
        if 'completion_method' in obj.completion_data:
            method = obj.completion_data['completion_method']
            html += "<tr><td>Method</td><td>{{method.title()}}</td></tr>"
            
        if 'final_score' in obj.completion_data:
            html += "<tr><td>Final Score</td><td>{{obj.completion_data['final_score']}}%%</td></tr>"
            
        if 'best_score' in obj.completion_data and obj.completion_data['best_score'] is not None:
            html += "<tr><td>Best Score</td><td>{{obj.completion_data['best_score']}}%%</td></tr>"
            
        if 'total_attempts' in obj.completion_data:
            html += "<tr><td>Attempts</td><td>{{obj.completion_data['total_attempts']}}</td></tr>"
            
        if 'total_time' in obj.completion_data:
            seconds = obj.completion_data['total_time']
            minutes = seconds // 60
            remaining_seconds = seconds % 60
            html += "<tr><td>Total Time</td><td>{{minutes}}m {{remaining_seconds}}s</td></tr>"
        
        # Add last attempt details if available
        if 'last_attempt' in obj.completion_data:
            last = obj.completion_data['last_attempt']
            html += "<tr><td colspan='2'><b>Last Attempt:</b></td></tr>"
            html += "<tr><td>Date</td><td>{{last.get('date', 'N/A')}}</td></tr>"
            
            if 'score' in last and last['score'] is not None:
                html += "<tr><td>Score</td><td>{{last['score']}}%%</td></tr>"
                
            if 'status' in last:
                html += "<tr><td>Status</td><td>{{last['status'].title()}}</td></tr>"
                
            if 'time_spent' in last:
                seconds = last['time_spent']
                minutes = seconds // 60
                remaining_seconds = seconds % 60
                html += "<tr><td>Time</td><td>{{minutes}}m {{remaining_seconds}}s</td></tr>"
        
        html += "</table>"
        return mark_safe(html)
    
    completion_data_display.short_description = "Completion Data"

    def progress_data_display(self, obj):
        """Format progress data as readable HTML"""
        if not obj.progress_data:
            return "No progress data available"
            
        html = "<table class='progress-data'>"
        html += "<tr><th>Property</th><th>Value</th></tr>"
        
        # Display completion status
        completion_status = obj.progress_data.get('completion_status', 'not_attempted')
        html += "<tr><td>Completion Status</td><td>{{completion_status.replace('_', ' ').title()}}</td></tr>"
        
        # Display completion percentage
        completion_percent = obj.progress_data.get('completion_percent', 0)
        html += "<tr><td>Completion Percent</td><td>{{completion_percent}}</td></tr>"
        
        html += "</table>"
        return mark_safe(html)
        
        # Handle Discussion progress special case
        if obj.topic.content_type == 'Discussion':
            # Display completion status
            html += "<tr><td>Discussion Completed</td><td>{{'Yes' if obj.completed else 'No'}}</td></tr>"
            
            # Display view count if available
            view_count = obj.progress_data.get('view_count', 0)
            html += "<tr><td>Views</td><td>{{view_count}}</td></tr>"
            
            # Display interaction count if available
            comment_count = obj.progress_data.get('comment_count', 0)
            html += "<tr><td>Comments</td><td>{{comment_count}}</td></tr>"
            
            # Display timestamps
            if 'first_viewed_at' in obj.progress_data:
                html += "<tr><td>First Viewed</td><td>{{obj.progress_data['first_viewed_at']}}</td></tr>"
                
            if 'last_updated_at' in obj.progress_data:
                html += "<tr><td>Last Updated</td><td>{{obj.progress_data['last_updated_at']}}</td></tr>"
                
            if 'completed_at' in obj.progress_data:
                html += "<tr><td>Completed At</td><td>{{obj.progress_data['completed_at']}}</td></tr>"
            
            html += "</table>"
            return mark_safe(html)
        
        # Handle Video progress special case
        if obj.topic.content_type in ['Video', 'EmbedVideo']:
            # Display percentage progress
            progress_value = obj.progress_data.get('progress', 0)
            html += "<tr><td>Progress</td><td>{{progress_value:.1f}}%</td></tr>"
            
            # Display duration if available
            if 'duration' in obj.progress_data:
                duration = obj.progress_data['duration']
                minutes = int(duration // 60)
                seconds = int(duration % 60)
                html += "<tr><td>Duration</td><td>{{minutes}}m {{seconds}}s</td></tr>"
            
            # Display last position if available
            if 'last_position' in obj.progress_data:
                position = obj.progress_data['last_position']
                minutes = int(position // 60)
                seconds = int(position % 60)
                html += "<tr><td>Last Position</td><td>{{minutes}}m {{seconds}}s</td></tr>"
                
            # Display view count
            view_count = obj.progress_data.get('view_count', 0)
            html += "<tr><td>Views</td><td>{{view_count}}</td></tr>"
            
            # Display total viewing time if available
            if 'total_viewing_time' in obj.progress_data:
                seconds = obj.progress_data['total_viewing_time']
                minutes = int(seconds // 60)
                remaining_seconds = int(seconds % 60)
                html += "<tr><td>Total Time</td><td>{{minutes}}m {{remaining_seconds}}s</td></tr>"
                
            # Display timestamps
            if 'first_viewed_at' in obj.progress_data:
                html += "<tr><td>First Viewed</td><td>{{obj.progress_data['first_viewed_at']}}</td></tr>"
                
            if 'last_updated_at' in obj.progress_data:
                html += "<tr><td>Last Updated</td><td>{{obj.progress_data['last_updated_at']}}</td></tr>"
                
            if 'completed_at' in obj.progress_data:
                html += "<tr><td>Completed At</td><td>{{obj.progress_data['completed_at']}}</td></tr>"
                
            # If we have viewing sessions, show the latest
            if 'viewing_sessions' in obj.progress_data and obj.progress_data['viewing_sessions']:
                sessions = obj.progress_data['viewing_sessions']
                if len(sessions) > 0:
                    latest = sessions[-1]
                    html += "<tr><td colspan='2'><b>Latest Session:</b></td></tr>"
                    
                    if 'progress' in latest:
                        html += "<tr><td>Progress</td><td>{{latest['progress']:.1f}}%</td></tr>"
                        
                    if 'position' in latest:
                        pos = latest['position']
                        min_pos = int(pos // 60)
                        sec_pos = int(pos % 60)
                        html += "<tr><td>Position</td><td>{{min_pos}}m {{sec_pos}}s</td></tr>"
                        
                    if 'started_at' in latest:
                        html += "<tr><td>Started</td><td>{{latest['started_at']}}</td></tr>"
                        
                    if 'updated_at' in latest:
                        html += "<tr><td>Updated</td><td>{{latest['updated_at']}}</td></tr>"
            
            html += "</table>"
            return mark_safe(html)
        
        # Default rendering for other content types
        for key, value in obj.progress_data.items():
            # Skip complex nested structures
            if isinstance(value, (dict, list)):
                continue
                
            # Format the value based on type
            if isinstance(value, (int, float)) and key.endswith('progress'):
                formatted_value = "{{value:.1f}}%"
            elif isinstance(value, bool):
                formatted_value = "Yes" if value else "No"
            else:
                formatted_value = str(value)
                
            html += "<tr><td>{{key.replace('_', ' ').title()}}</td><td>{{formatted_value}}</td></tr>"
        
        html += "</table>"
        return mark_safe(html)
    
    progress_data_display.short_description = "Progress Data"

    def bulk_delete_selected(self, request, queryset):
        """Delete selected topic progress records"""
        deleted_count = 0
        for progress in queryset:
            # Log the delete action
            logger.info("Admin action: Deleting topic progress for topic {{progress.topic.id}} and user {{progress.user.id}}")
            progress.delete()
            deleted_count += 1
            
        if deleted_count > 0:
            self.message_user(request, "Successfully deleted {{deleted_count}} topic progress records.")
        else:
            self.message_user(request, "No topic progress records were deleted.")
    
    bulk_delete_selected.short_description = "Delete selected topic progress"

    def change_view(self, request, object_id, form_url='', extra_context=None):
        """Override to handle record viewing"""
        return super().change_view(request, object_id, form_url, extra_context=extra_context)

    def sync_removed_data(self, request, queryset):
        """Manually sync selected records with removed Cloud"""
        # Define logger at the beginning of the method for consistent access
        logger = logging.getLogger(__name__)
        try:
            # Import removed Cloud utilities
            from removed_cloud.utils.api import get_removed_client
            
            # Filter only removed topics with registration IDs
            removed_records = queryset.filter(
                topic__content_type='removed',
                removed_registration__isnull=False
            )
            
            if not removed_records.exists():
                self.message_user(
                    request, 
                    "No valid removed progress records found to sync.", 
                    level=messages.WARNING
                )
                return
            
            synced_count = 0
            errors = []
            
            for progress in removed_records:
                try:
                    # Use transaction.atomic for each record to isolate failures
                    with transaction.atomic():
                        try:
                            # Get the latest data from removed Cloud
                            result = removed_cloud.get_registration_status(progress.removed_registration)
                            
                            if result:
                                # Initialize progress_data if needed
                                if not isinstance(progress.progress_data, dict):
                                    progress.progress_data = {}
                                
                                # Ensure required fields exist
                                if 'first_viewed_at' not in progress.progress_data:
                                    progress.progress_data['first_viewed_at'] = timezone.now().isoformat()
                                if 'last_updated_at' not in progress.progress_data:
                                    progress.progress_data['last_updated_at'] = timezone.now().isoformat()
                                
                                completion_status = result.get('registrationCompletion', '').lower()
                                success_status = result.get('registrationSuccess', '').lower()
                                
                                # Compute completion percentage based on objectives if available
                                completion_percent = 0
                                objectives = result.get('objectives', [])
                                
                                if objectives and len(objectives) > 0:
                                    completed_objectives = sum(1 for obj_data in objectives if obj_data.get('success') == 'PASSED')
                                    completion_percent = (completed_objectives / len(objectives)) * 100
                                elif completion_status == 'completed':
                                    completion_percent = 100
                                
                                # Update progress_data
                                progress.progress_data.update({
                                    'completion_status': completion_status,
                                    'success_status': success_status,
                                    'completion_percent': completion_percent,
                                    'last_updated': timezone.now().isoformat(),
                                    'removed_sync': True,
                                    'manual_sync': True,
                                    'status': completion_status if completion_status else 'not_attempted'
                                })
                                
                                # Capture runtime data for bookmark
                                runtime_data = result.get('runtime', {})
                                if runtime_data and not progress.bookmark:
                                    progress.bookmark = {}
                                
                                if runtime_data:
                                    progress.bookmark.update({
                                        'suspendData': runtime_data.get('suspendData'),
                                        'lessonLocation': runtime_data.get('lessonLocation'),
                                        'lessonStatus': runtime_data.get('completionStatus'),
                                        'entry': runtime_data.get('entry'),
                                        'updated_at': timezone.now().isoformat()
                                    })
                                
                                # Update completion status if needed
                                if completion_status in ['completed', 'passed'] and not progress.completed:
                                    progress.completed = True
                                    progress.completion_method = 'removed'
                                    progress.completed_at = timezone.now()
                                    
                                    # Update completion data
                                    if not progress.completion_data:
                                        progress.completion_data = {}
                                    
                                    progress.completion_data.update({
                                        'removed_completion': True,
                                        'completed_at': progress.completed_at.isoformat(),
                                        'completion_method': 'removed'
                                    })
                                
                            # Update score using unified scoring service
                            if 'score' in result:
                                from core.utils.scoring import ScoreCalculationService
                                
                                score_data = result.get('score', {})
                                normalized_score = ScoreCalculationService.handle_removed_score(score_data)
                                
                                if normalized_score is not None:
                                    progress.last_score = normalized_score
                                    if progress.best_score is None or normalized_score > progress.best_score:
                                        progress.best_score = normalized_score
                                
                                # Save the updated object
                                progress.save()
                                
                                synced_count += 1
                        except Exception as e:
                            logger.error("Error in removed Cloud API call for record {{progress.id}}: {{str(e)}}")
                            raise  # Re-raise to be caught by outer try/except
                
                except Exception as e:
                    logger.error("Error syncing removed data for progress {{progress.id}}: {{str(e)}}")
                    errors.append("Error with {{progress.topic.title}} for {{progress.user.username}}: {{str(e)}}")
            
            # Report results
            if synced_count > 0:
                self.message_user(
                    request,
                    "Successfully synchronized {{synced_count}} of {{removed_records.count()}} removed progress records.",
                    level=messages.SUCCESS
                )
            
            if errors:
                self.message_user(
                    request,
                    "Encountered {{len(errors)}} errors during synchronization: {{', '.join(errors[:3])}}{{'...' if len(errors) > 3 else ''}}",
                    level=messages.WARNING
                )
                
        except Exception as e:
            logger.error("Error in sync_removed_data action: {{str(e)}}")
            self.message_user(
                request,
                "Error synchronizing removed data: {{str(e)}}",
                level=messages.ERROR
            )

    sync_removed_data.short_description = "Sync selected records with removed Cloud"

@admin.register(CourseEnrollment)
class CourseEnrollmentAdmin(admin.ModelAdmin):
    list_display = ('user', 'course', 'enrolled_at', 'completed', 'last_accessed')
    list_filter = ('completed', 'enrolled_at')
    search_fields = ('user__username', 'course__title')
    raw_id_fields = ('user', 'course')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if request.user.role == 'admin':
            return qs.filter(course__branch=request.user.branch)
        if request.user.role == 'instructor':
            return qs.filter(
                course__instructor=request.user
            ) | qs.filter(
                course__accessible_groups__memberships__user=request.user,
                course__accessible_groups__memberships__is_active=True
            ).distinct()
        return qs.none()

# CourseTopic admin temporarily disabled - model import issues
# @admin.register(CourseTopic)
class CourseTopicAdmin(admin.ModelAdmin):
    list_display = ('course', 'topic', 'order')
    list_filter = ('course', 'topic')
    search_fields = ('course__title', 'topic__title')
    ordering = ('course', 'order')

def get_topic_course(topic):
    """Helper function to get course for a topic through CourseTopic"""
    return Course.objects.filter(coursetopic__topic=topic).first()
