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

from users.models import Branch, CustomUser
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
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if request.user.role == 'admin':
            return qs.filter(course__branch=request.user.branch)
        if request.user.role == 'instructor':
            return qs.filter(course__instructor=request.user)
        return qs.none()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "user" and not request.user.is_superuser:
            kwargs["queryset"] = CustomUser.objects.filter(
                role='learner',
                branch=request.user.branch
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

class CourseTopicInline(admin.TabularInline):
    model = CourseTopic
    extra = 1

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'instructor', 'branch', 'is_active', 'created_at', 'view_progress')
    list_filter = ('is_active', 'branch', 'instructor')
    search_fields = ('title', 'description')
    inlines = [CourseTopicInline]
    readonly_fields = ('created_at', 'updated_at')
    
    def view_progress(self, obj):
        """Link to view course progress"""
        return format_html(
            '<a href="{}" class="button">View Progress</a>',
            reverse('courses:course_progress', args=[obj.id])
        )
    view_progress.short_description = 'Progress'

    fieldsets = (
        (None, {
            'fields': ('title', 'course_code', 'description', 'course_image')
        }),
        ('Course Details', {
            'fields': ('instructor', 'branch', 'category')
        }),
        ('Pricing', {
            'fields': ('price', 'coupon_code', 'discount_percentage'),
            'description': 'Important: Paid courses must be assigned to a branch to appear in branch portals.'
        }),
        ('Status', {
            'fields': ('is_active', 'created_at', 'updated_at')
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not (request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']):
            # Branch handling
            if 'branch' in form.base_fields:
                if request.user.branch:
                    form.base_fields['branch'].queryset = Branch.objects.filter(
                        id=request.user.branch.id
                    )
                    form.base_fields['branch'].initial = request.user.branch
                    form.base_fields['branch'].disabled = True
                else:
                    # If user has no branch, show a message and disable the field
                    form.base_fields['branch'].queryset = Branch.objects.none()
                    form.base_fields['branch'].disabled = True
                    messages.warning(request, "You need to be assigned to a branch to manage courses.")

            # Category handling
            if 'category' in form.base_fields:
                form.base_fields['category'].queryset = CourseCategory.objects.filter(
                    is_active=True
                )

            # Instructor handling
            if 'instructor' in form.base_fields:
                if request.user.role == 'instructor':
                    form.base_fields['instructor'].disabled = True
                    form.base_fields['instructor'].initial = request.user
                elif request.user.role == 'admin' and request.user.branch:
                    form.base_fields['instructor'].queryset = CustomUser.objects.filter(
                        role='instructor',
                        branch=request.user.branch
                    )

        form.current_user = request.user
        return form

    def save_model(self, request, obj, form, change):
        is_new_course = obj.pk is None
        
        if not (request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']):
            if not request.user.branch:
                raise PermissionDenied("You need to be assigned to a branch to manage courses.")
            if obj.branch != request.user.branch:
                raise PermissionDenied("You can only manage courses in your branch.")
            obj.branch = request.user.branch
            if request.user.role == 'instructor':
                obj.instructor = request.user

        # First save the object to get an ID
        super().save_model(request, obj, form, change)
        
        # If this is a new course, ensure the creator is enrolled
        if is_new_course:
            CourseEnrollment.objects.get_or_create(
                course=obj,
                user=request.user,
                defaults={
                    'enrollment_source': 'manual'
                }
            )

        # Now check group access since we have an ID
        if hasattr(obj, 'accessible_groups'):
            for group in obj.accessible_groups.all():
                if group.branch != obj.branch:
                    raise PermissionDenied("Groups must belong to the same branch as the course.")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        
        # Global Admin: FULL access
        if request.user.role == 'globaladmin' or request.user.is_superuser:
            return qs
            
        if isinstance(request.user, AnonymousUser):
            return qs.none()
            
        # Super Admin: CONDITIONAL access (courses within their assigned businesses)
        if request.user.role == 'superadmin':
            if hasattr(request.user, 'business_assignments'):
                assigned_businesses = request.user.business_assignments.filter(is_active=True).values_list('business', flat=True)
                return qs.filter(branch__business__in=assigned_businesses)
            return qs.none()
            
        # Branch Admin: CONDITIONAL access (courses within their effective branch, supports branch switching)
        if request.user.role == 'admin':
            from core.branch_filters import BranchFilterManager
            effective_branch = BranchFilterManager.get_effective_branch(request.user, request)
            if effective_branch:
                return qs.filter(branch=effective_branch)
            return qs.none()
            
        # Instructor: CONDITIONAL access (courses they created or assigned to by admin)
        if request.user.role == 'instructor':
            return qs.filter(
                instructor=request.user
            ) | qs.filter(
                accessible_groups__memberships__user=request.user,
                accessible_groups__memberships__is_active=True
            ).distinct()
            
        # Learner: NONE access to admin interface
        return qs.none()

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return True
        if isinstance(request.user, AnonymousUser):
            return False
        if obj is None:
            return True
        if request.user.role == 'admin':
            return obj.branch == request.user.branch
        if request.user.role == 'instructor':
            return obj.instructor == request.user or obj.accessible_groups.filter(
                memberships__user=request.user,
                memberships__is_active=True
            ).exists()
        return False

    def has_change_permission(self, request, obj=None):
        return self.has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
            return True
        if isinstance(request.user, AnonymousUser):
            return False
        if obj is None:
            return False
        if request.user.role == 'admin':
            return obj.branch == request.user.branch
        if request.user.role == 'instructor':
            return obj.instructor == request.user
        return False

    def has_add_permission(self, request):
        if isinstance(request.user, AnonymousUser):
            return False
        return request.user.is_superuser or request.user.role in ['superadmin', 'admin', 'instructor']

@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    form = TopicAdminForm
    list_display = ('title', 'content_type', 'status', 'order')
    list_filter = ('content_type', 'status')
    search_fields = ('title', 'description')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (None, {
            'fields': ('title', 'description', 'course')
        }),
        ('Content', {
            'fields': ('content_type', 'content_file', 'text_content', 'web_url', 'embed_code')
        }),
        ('Settings', {
            'fields': ('status', 'order', 'start_date', 'end_date', 'alignment')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not request.user.is_superuser:
            if request.user.role == 'admin':
                form.base_fields['course'].queryset = Course.objects.filter(branch=request.user.branch)
            elif request.user.role == 'instructor':
                form.base_fields['course'].queryset = Course.objects.filter(instructor=request.user)
        return form

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        
        # Handle course-topic relationship
        course = form.cleaned_data.get('course')
        if course:
            CourseTopic.objects.get_or_create(course=course, topic=obj)

    class Media:
        css = {
            'all': ('admin/css/topic_admin.css',)
        }
        js = ('admin/js/topic_admin.js',)

    add_form_template = 'admin/courses/topic/add_form.html'
    change_form_template = 'admin/courses/topic/change_form.html'


class TopicProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'topic', 'completed', 'completion_method', 'manually_completed', 'last_accessed', 'get_progress_display', 'get_status_display')
    list_filter = ('completed', 'completion_method', 'manually_completed')
    search_fields = ('user__username', 'topic__title')
    raw_id_fields = ('user', 'topic')
    readonly_fields = ('last_accessed', 'first_accessed', 'completion_data_display', 'progress_data_display')

    # Remove default actions (including delete_selected) to avoid duplication
    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'topic', 'completed', 'completion_method', 'manually_completed', 'completed_at')
        }),
        ('Progress Data', {
            'fields': ('progress_data_display', 'progress_data', 'bookmark')
        }),
        ('Completion Details', {
            'fields': ('completion_data_display', 'completion_data')
        }),
        ('Scoring', {
            'fields': ('last_score', 'best_score', 'attempts')
        }),
        ('Timing', {
            'fields': ('total_time_spent', 'last_accessed', 'first_accessed')
        }),
        ('Audio Progress', {
            'fields': ('audio_progress', 'last_audio_position')
        })
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        
        # Apply permission filtering
        if request.user.is_superuser:
            filtered_qs = qs
        elif request.user.role == 'admin':
            # Update the query to first get topics through CourseTopic
            filtered_qs = qs.filter(
                topic__coursetopic__course__branch=request.user.branch
            ).select_related(
                'user',
                'topic'
            ).distinct()
        elif request.user.role == 'instructor':
            filtered_qs = qs.filter(
                models.Q(topic__coursetopic__course__instructor=request.user) |
                models.Q(
                    topic__coursetopic__course__accessible_groups__memberships__user=request.user,
                    topic__coursetopic__course__accessible_groups__memberships__is_active=True
                )
            ).distinct()
        else:
            filtered_qs = qs.none()
        
        # Check if auto sync is requested and not disabled
        if request.GET.get('sync') != 'false':
            # Define logger at the beginning of this section for consistent access
            logger = logging.getLogger(__name__)
            try:
                for progress in filtered_qs:
                    try:
                        # Use a separate transaction for each record to isolate failures
                        with transaction.atomic():
                            # Skip if synced in the last hour to avoid excessive API calls
                            if progress.progress_data and isinstance(progress.progress_data, dict):
                                last_sync = progress.progress_data.get('last_updated')
                                if last_sync:
                                    try:
                                        from dateutil.parser import parse
                                        from datetime import timedelta
                                        sync_time = parse(last_sync)
                                        if timezone.now() - sync_time < timedelta(hours=1):
                                            continue
                                    except (ImportError, ValueError):
                                        pass  # If we can't parse the date, proceed with sync
                            
                            result = None
                            
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
                                    progress.completed_at = timezone.now()
                                    
                                    # Update completion data
                                    if not progress.completion_data:
                                        progress.completion_data = {}
                                    
                                    progress.completion_data.update({
                                        'completed_at': progress.completed_at.isoformat(),
                                    })
                                
                            # Update score using unified scoring service
                            if 'score' in result:
                                from core.utils.scoring import ScoreCalculationService
                                
                                score_data = result.get('score', {})
                                
                                if normalized_score is not None:
                                    progress.last_score = normalized_score
                                    if progress.best_score is None or normalized_score > progress.best_score:
                                        progress.best_score = normalized_score
                                
                                # Save the updated object
                                progress.save()
                                
                                # Log the sync
                    except Exception as e:
                        # Log but continue processing other records
                        logger.warning(f"Error syncing progress {progress.id}: {e}")
            
            except Exception as e:
                logger.error(f"Error in auto sync: {e}")
        
        return filtered_qs

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
        """Enhanced progress display"""
        return f"{obj.get_progress_percentage()}%%"

    get_progress_display.short_description = 'Progress'

    def get_status_display(self, obj):
        if obj.completed:
            return f'Completed ({obj.completion_method})'
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
                logger.info(f"Admin completion update for topic {obj.topic.id}, user {obj.user.id}")
                logger.info(f"Setting progress_data to: {obj.progress_data}")
        
        # Handle direct edits to progress_data field (for superusers)
        if 'progress_data' in form.changed_data and request.user.is_superuser:
            # Add logging for tracking changes
            logger.info(f"Direct progress_data update by admin for topic {obj.topic.id}, user {obj.user.id}")
            logger.info(f"New progress_data: {obj.progress_data}")
            
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
                
                logger.info(f"Auto-setting completed=True based on progress_data value")
            
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
            html += f"<tr><td>Completed At</td><td>{obj.completion_data['completed_at']}</td></tr>"
        
        if 'completion_method' in obj.completion_data:
            method = obj.completion_data['completion_method']
            html += f"<tr><td>Method</td><td>{method.title()}</td></tr>"
            
        if 'final_score' in obj.completion_data:
            html += f"<tr><td>Final Score</td><td>{obj.completion_data['final_score']}%%</td></tr>"
            
        if 'best_score' in obj.completion_data and obj.completion_data['best_score'] is not None:
            html += f"<tr><td>Best Score</td><td>{obj.completion_data['best_score']}%%</td></tr>"
            
        if 'total_attempts' in obj.completion_data:
            html += f"<tr><td>Attempts</td><td>{obj.completion_data['total_attempts']}</td></tr>"
            
        if 'total_time' in obj.completion_data:
            seconds = obj.completion_data['total_time']
            minutes = seconds // 60
            remaining_seconds = seconds % 60
            html += f"<tr><td>Total Time</td><td>{minutes}m {remaining_seconds}s</td></tr>"
        
        # Add last attempt details if available
        if 'last_attempt' in obj.completion_data:
            last = obj.completion_data['last_attempt']
            html += "<tr><td colspan='2'><b>Last Attempt:</b></td></tr>"
            html += f"<tr><td>Date</td><td>{last.get('date', 'N/A')}</td></tr>"
            
            if 'score' in last and last['score'] is not None:
                html += f"<tr><td>Score</td><td>{last['score']}%%</td></tr>"
                
            if 'status' in last:
                html += f"<tr><td>Status</td><td>{last['status'].title()}</td></tr>"
                
            if 'time_spent' in last:
                seconds = last['time_spent']
                minutes = seconds // 60
                remaining_seconds = seconds % 60
                html += f"<tr><td>Time</td><td>{minutes}m {remaining_seconds}s</td></tr>"
        
        html += "</table>"
        return mark_safe(html)
    
    completion_data_display.short_description = "Completion Data"

    def progress_data_display(self, obj):
        """Format progress data as readable HTML"""
        if not obj.progress_data:
            return "No progress data available"
            
        html = "<table class='progress-data'>"
        html += "<tr><th>Property</th><th>Value</th></tr>"
        
        # Handle Audio progress special case
        if obj.topic and obj.topic.content_type == 'Audio':
            html += f"<tr><td>Audio Progress</td><td>{obj.audio_progress:.1f}%</td></tr>"
            html += f"<tr><td>Last Position</td><td>{obj.last_audio_position:.1f}s</td></tr>"
            html += "</table>"
            return mark_safe(html)
        
        # Handle Discussion progress special case
        if obj.topic and obj.topic.content_type == 'Discussion':
            # Display completion status
            html += f"<tr><td>Discussion Completed</td><td>{'Yes' if obj.completed else 'No'}</td></tr>"
            
            # Display view count if available
            view_count = obj.progress_data.get('view_count', 0)
            html += f"<tr><td>Views</td><td>{view_count}</td></tr>"
            
            # Display interaction count if available
            comment_count = obj.progress_data.get('comment_count', 0)
            html += f"<tr><td>Comments</td><td>{comment_count}</td></tr>"
            
            # Display timestamps
            if 'first_viewed_at' in obj.progress_data:
                html += f"<tr><td>First Viewed</td><td>{obj.progress_data['first_viewed_at']}</td></tr>"
                
            if 'last_updated_at' in obj.progress_data:
                html += f"<tr><td>Last Updated</td><td>{obj.progress_data['last_updated_at']}</td></tr>"
                
            if 'completed_at' in obj.progress_data:
                html += f"<tr><td>Completed At</td><td>{obj.progress_data['completed_at']}</td></tr>"
            
            html += "</table>"
            return mark_safe(html)
        
        # Handle Video progress special case
        if obj.topic and obj.topic.content_type in ['Video', 'EmbedVideo']:
            # Display percentage progress
            progress_value = obj.progress_data.get('progress', 0)
            html += f"<tr><td>Progress</td><td>{progress_value:.1f}%</td></tr>"
            
            # Display duration if available
            if 'duration' in obj.progress_data:
                duration = obj.progress_data['duration']
                minutes = int(duration // 60)
                seconds = int(duration % 60)
                html += f"<tr><td>Duration</td><td>{minutes}m {seconds}s</td></tr>"
            
            # Display last position if available
            if 'last_position' in obj.progress_data:
                position = obj.progress_data['last_position']
                minutes = int(position // 60)
                seconds = int(position % 60)
                html += f"<tr><td>Last Position</td><td>{minutes}m {seconds}s</td></tr>"
                
            # Display view count
            view_count = obj.progress_data.get('view_count', 0)
            html += f"<tr><td>Views</td><td>{view_count}</td></tr>"
            
            # Display total viewing time if available
            if 'total_viewing_time' in obj.progress_data:
                seconds = obj.progress_data['total_viewing_time']
                minutes = int(seconds // 60)
                remaining_seconds = int(seconds % 60)
                html += f"<tr><td>Total Time</td><td>{minutes}m {remaining_seconds}s</td></tr>"
                
            # Display timestamps
            if 'first_viewed_at' in obj.progress_data:
                html += f"<tr><td>First Viewed</td><td>{obj.progress_data['first_viewed_at']}</td></tr>"
                
            if 'last_updated_at' in obj.progress_data:
                html += f"<tr><td>Last Updated</td><td>{obj.progress_data['last_updated_at']}</td></tr>"
                
            if 'completed_at' in obj.progress_data:
                html += f"<tr><td>Completed At</td><td>{obj.progress_data['completed_at']}</td></tr>"
                
            # If we have viewing sessions, show the latest
            if 'viewing_sessions' in obj.progress_data and obj.progress_data['viewing_sessions']:
                sessions = obj.progress_data['viewing_sessions']
                if len(sessions) > 0:
                    latest = sessions[-1]
                    html += "<tr><td colspan='2'><b>Latest Session:</b></td></tr>"
                    
                    if 'progress' in latest:
                        html += f"<tr><td>Progress</td><td>{latest['progress']:.1f}%</td></tr>"
                        
                    if 'position' in latest:
                        pos = latest['position']
                        min_pos = int(pos // 60)
                        sec_pos = int(pos % 60)
                        html += f"<tr><td>Position</td><td>{min_pos}m {sec_pos}s</td></tr>"
                        
                    if 'started_at' in latest:
                        html += f"<tr><td>Started</td><td>{latest['started_at']}</td></tr>"
                        
                    if 'updated_at' in latest:
                        html += f"<tr><td>Updated</td><td>{latest['updated_at']}</td></tr>"
            
            html += "</table>"
            return mark_safe(html)
        
        # Default rendering for other content types
        for key, value in obj.progress_data.items():
            # Skip complex nested structures
            if isinstance(value, (dict, list)):
                continue
                
            # Format the value based on type
            if isinstance(value, (int, float)) and key.endswith('progress'):
                formatted_value = f"{value:.1f}%"
            elif isinstance(value, bool):
                formatted_value = "Yes" if value else "No"
            else:
                formatted_value = str(value)
                
            html += f"<tr><td>{key.replace('_', ' ').title()}</td><td>{formatted_value}</td></tr>"
        
        html += "</table>"
        return mark_safe(html)
    
    progress_data_display.short_description = "Progress Data"

    def bulk_delete_selected(self, request, queryset):
        """Delete selected topic progress records"""
        deleted_count = 0
        for progress in queryset:
            # Log the delete action
            logger.info(f"Admin action: Deleting topic progress for topic {progress.topic.id} and user {progress.user.id}")
            progress.delete()
            deleted_count += 1
            
        if deleted_count > 0:
            self.message_user(request, f"Successfully deleted {deleted_count} topic progress records.")
        else:
            self.message_user(request, "No topic progress records were deleted.")
    
    bulk_delete_selected.short_description = "Delete selected topic progress"

    def change_view(self, request, object_id, form_url='', extra_context=None):
        return super().change_view(request, object_id, form_url, extra_context)
    
admin.site.unregister(Topic)
admin.site.register(Topic, TopicAdmin)

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
