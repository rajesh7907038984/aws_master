from django import forms
from .models import Assignment, Topic, TextQuestion, AssignmentAttachment, SupportingDocQuestion, StudentAnswer, AssignmentCourse, TopicAssignment
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from core.utils.forms import CustomTinyMCEFormField, BaseModelFormWithQuill
import mimetypes
from lms_rubrics.models import Rubric
from django.utils import timezone
from multiupload.fields import MultiFileField
from tinymce_editor.forms import TinyMCEFormField
from tinymce_editor.widgets import TinyMCEWidget
from django.db.models import Q


class DateTimeLocalInput(forms.DateTimeInput):
    """Custom widget to properly format datetime for HTML datetime-local input"""
    input_type = 'datetime-local'
    
    def format_value(self, value):
        if value is None:
            return ''
        if hasattr(value, 'strftime'):
            # Format as YYYY-MM-DDTHH:MM for datetime-local input
            return value.strftime('%Y-%m-%dT%H:%M')
        return value

class AssignmentForm(forms.ModelForm):
    attachments = MultiFileField(
        required=False,
        min_num=0,
        max_num=10,
        max_file_size=104857600,  # 100 MB
        help_text='You can upload multiple supporting documents for the assignment (Optional for instructors)'
    )
    
    # Add a default value for max_file_size to prevent validation errors
    max_file_size = forms.IntegerField(
        required=False,  # Make it optional
        initial=104857600,  # Default 100MB
        widget=forms.NumberInput(attrs={
            'class': 'block w-full rounded-lg border border-gray-300 bg-white text-gray-900 px-4 py-2.5 focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 transition-colors duration-200',
            'placeholder': '104857600',
        })
    )
    
    # Multiple courses field
    course_ids = forms.MultipleChoiceField(
        required=False,
        widget=forms.SelectMultiple(attrs={
            'class': 'block w-full rounded-lg border border-gray-300 bg-white text-gray-900 px-4 py-2.5 focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 transition-colors duration-200',
        }),
        help_text='Select one or more courses for this assignment'
    )
    
    # Multiple topics field
    topic_ids = forms.MultipleChoiceField(
        required=False,
        widget=forms.SelectMultiple(attrs={
            'class': 'block w-full rounded-lg border border-gray-300 bg-white text-gray-900 px-4 py-2.5 focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 transition-colors duration-200',
        }),
        help_text='Select one or more topics for this assignment'
    )
    
    # Status field - checked by default
    status = forms.BooleanField(
        required=False,
        initial=True,
        label='Status',
        help_text='Check to make this assignment active',
        widget=forms.CheckboxInput(attrs={
            'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 focus:ring-opacity-50 transition-colors duration-200',
            'checked': True
        })
    )
    
    description = TinyMCEFormField(
        required=True,
        widget=TinyMCEWidget(attrs={
            'class': 'block w-full rounded-lg border border-gray-300 bg-white text-gray-900 px-4 py-2.5 focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 transition-colors duration-200',
            'rows': 6,
            'placeholder': 'Enter assignment description',
            'required': 'required'
        }),
    )
    
    instructions = TinyMCEFormField(
        required=True,
        widget=TinyMCEWidget(attrs={
            'class': 'block w-full rounded-lg border border-gray-300 bg-white text-gray-900 px-4 py-2.5 focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 transition-colors duration-200',
            'rows': 8,
            'placeholder': 'Enter detailed instructions for students',
            'required': 'required'
        }),
    )
    
    class Meta:
        model = Assignment
        fields = [
            'title', 'description', 'instructions', 'rubric', 'due_date', 'max_score',
            'submission_type', 'allowed_file_types', 'status', 'course_ids', 'topic_ids'
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'block w-full rounded-lg border border-gray-300 bg-white text-gray-900 px-4 py-2.5 focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 transition-colors duration-200',
                'placeholder': 'Enter assignment title',
                'required': 'required'
            }),
            'course': forms.Select(attrs={
                'class': 'block w-full rounded-lg border border-gray-300 bg-white text-gray-900 px-4 py-2.5 focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 transition-colors duration-200'
            }),
            'due_date': DateTimeLocalInput(attrs={
                'class': 'block w-full rounded-lg border border-gray-300 bg-white text-gray-900 px-4 py-2.5 focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 transition-colors duration-200'
            }),
            'max_score': forms.NumberInput(attrs={
                'class': 'block w-full rounded-lg border border-gray-300 bg-white text-gray-900 px-4 py-2.5 focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 transition-colors duration-200',
                'min': '0',
                'step': '0.01'
            }),
            'submission_type': forms.Select(attrs={
                'class': 'block w-full rounded-lg border border-gray-300 bg-white text-gray-900 px-4 py-2.5 focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 transition-colors duration-200'
            }),
            'allowed_file_types': forms.TextInput(attrs={
                'class': 'block w-full rounded-lg border border-gray-300 bg-white text-gray-900 px-4 py-2.5 focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 transition-colors duration-200',
                'placeholder': '.pdf,.doc,.docx'
            }),
            'rubric': forms.Select(attrs={
                'class': 'block w-full rounded-lg border border-gray-300 bg-white text-gray-900 px-4 py-2.5 focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 transition-colors duration-200'
            }),
            'attachment': forms.ClearableFileInput(attrs={
                'class': 'hidden',
                'accept': '.pdf,.doc,.docx,.txt,.ppt,.pptx,.mp4,.mov,.avi,.wmv'
            }),

        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)  # Get the user from kwargs
        super().__init__(*args, **kwargs)
        # Populate course choices from the database
        from courses.models import Course, Topic
        
        # Filter courses based on user role and access
        if user:
            if user.role == 'instructor':
                # Get courses where user is instructor or enrolled as instructor
                instructor_courses = Course.objects.filter(
                    Q(instructor=user) |
                    Q(enrolled_users=user)
                ).distinct().order_by('title')
                self.fields['course_ids'].choices = [(str(course.id), course.title) for course in instructor_courses]
            elif user.role == 'admin':
                # Branch admin sees courses in their branch
                if user.branch:
                    branch_courses = Course.objects.filter(branch=user.branch).order_by('title')
                    self.fields['course_ids'].choices = [(str(course.id), course.title) for course in branch_courses]
            else:
                # Superadmin and globaladmin see all courses
                self.fields['course_ids'].choices = [(str(course.id), course.title) for course in Course.objects.all().order_by('title')]
        else:
            # Fallback to all courses if no user provided
            self.fields['course_ids'].choices = [(str(course.id), course.title) for course in Course.objects.all().order_by('title')]
        
        # Populate topic choices
        self.fields['topic_ids'].choices = [(str(topic.id), f"{topic.title} ({topic.get_content_type_display()})") for topic in Topic.objects.all().order_by('title')]
        
        # Filter rubrics based on user role using centralized function
        from lms_rubrics.utils import get_filtered_rubrics_for_user
        
        # Get the course if available (for edit mode)
        course = None
        if self.instance and self.instance.pk:
            # For existing assignment, check if it has a course
            if self.instance.course:
                course = self.instance.course
            elif self.instance.courses.exists():
                course = self.instance.courses.first()
        
        # Apply rubric filtering
        self.fields['rubric'].queryset = get_filtered_rubrics_for_user(user, course)
        
        # If we're editing an existing assignment, set the initial course_ids and topic_ids
        if self.instance and self.instance.pk:
            self.fields['course_ids'].initial = [str(course_id) for course_id in self.instance.courses.values_list('id', flat=True)]
            self.fields['topic_ids'].initial = [str(topic_id) for topic_id in self.instance.topics.values_list('id', flat=True)]
            # Set the status field based on the current is_active value
            self.fields['status'].initial = self.instance.is_active
    
    def clean_attachments(self):
        """
        Custom validation for attachments field to handle optional file uploads properly.
        This method ensures that attachments are truly optional and don't cause validation errors
        when no files are uploaded, especially in edit mode.
        """
        # Get the attachments from the request
        attachments = self.files.getlist('attachments') if hasattr(self, 'files') else []
        
        # If no files are uploaded, that's perfectly fine - attachments are optional
        if not attachments:
            return []
        
        # If files are uploaded, return them for further validation in clean()
        return attachments
    
    def clean(self):
        cleaned_data = super().clean()
        attachment = cleaned_data.get('attachment')
        attachments = self.files.getlist('attachments') if hasattr(self, 'files') else []
        allowed_file_types = cleaned_data.get('allowed_file_types', '')
        max_file_size = cleaned_data.get('max_file_size')
        course_ids = cleaned_data.get('course_ids', [])
        
        # Course selection is optional - instructors can create assignments without course associations
        # if not course_ids:
        #     self.add_error('course_ids', "Please select at least one course for this assignment.")
        
        # Set a default value if max_file_size is None
        if max_file_size is None:
            max_file_size = 104857600  # Default 100MB
        
        # Handle required fields - but more lenient for instructor assignment creation
        # Only validate if fields are completely empty (Django will handle basic required validation)
        for field_name in ['description', 'instructions']:
            field_value = cleaned_data.get(field_name)
            if field_value is not None:
                # Trim the value
                cleaned_data[field_name] = field_value.strip()
                if not cleaned_data[field_name]:
                    self.add_error(field_name, "This field is required.")
        
        # Handle attachment (single file) validation
        if attachment and hasattr(attachment, 'name'):
            # Check file type
            if allowed_file_types and not any(attachment.name.lower().endswith(ext.lower()) for ext in allowed_file_types.split(',')):
                self.add_error('attachment', f"File type not allowed. Allowed types: {allowed_file_types}")
            
            # Check file size
            if attachment.size > max_file_size:
                max_size_mb = max_file_size / (1024 * 1024)
                self.add_error('attachment', f"File size exceeds the maximum allowed size ({max_size_mb:.1f}MB)")
            
            # Set content type
            content_type, encoding = mimetypes.guess_type(attachment.name)
            if content_type:
                cleaned_data['content_type'] = content_type
            else:
                cleaned_data['content_type'] = 'application/octet-stream'
        
        # Handle attachments (multiple files) validation - ONLY if files are actually uploaded
        # This prevents validation errors when editing assignments without uploading new files
        if attachments and len(attachments) > 0:
            invalid_files = []
            for file in attachments:
                # Check file type only if allowed_file_types is specified
                if allowed_file_types and allowed_file_types.strip():
                    file_extensions = [ext.strip() for ext in allowed_file_types.split(',')]
                    if not any(file.name.lower().endswith(ext.lower()) for ext in file_extensions):
                        invalid_files.append(f"{file.name} (invalid file type)")
                    
                # Check file size
                if file.size > max_file_size:
                    max_size_mb = max_file_size / (1024 * 1024)
                    invalid_files.append(f"{file.name} (exceeds {max_size_mb:.1f}MB size limit)")
            
            if invalid_files:
                error_message = "File upload validation failed: " + "; ".join(invalid_files)
                self.add_error('attachments', error_message)
                
            # Additional file validation for common issues
            total_size = sum(file.size for file in attachments)
            max_total_size = max_file_size * 10  # Allow up to 10x the individual file limit for total
            if total_size > max_total_size:
                total_mb = total_size / (1024 * 1024)
                max_total_mb = max_total_size / (1024 * 1024)
                self.add_error('attachments', f"Total file size ({total_mb:.1f}MB) exceeds maximum allowed ({max_total_mb:.1f}MB)")
        
        # Validate due date is in the future if provided (only for new assignments)
        due_date = cleaned_data.get('due_date')
        if due_date:
            # Only validate future dates for new assignments
            # For existing assignments, allow any due date (past or future)
            if not self.instance.pk and due_date < timezone.now():
                self.add_error('due_date', "Due date must be in the future")
            
        return cleaned_data
    
    def clean_due_date(self):
        """Ensure due_date is timezone-aware to avoid naive datetime warnings"""
        due_date = self.cleaned_data.get('due_date')
        if due_date:
            from django.utils import timezone
            if due_date.tzinfo is None:
                # Convert naive datetime to timezone-aware
                due_date = timezone.make_aware(due_date)
        return due_date
    
    def save(self, commit=True, user=None):
        instance = super().save(commit=False)
        if instance.max_score is not None:
            instance.points = int(float(instance.max_score) * 100)
        else:
            instance.points = 10000
        
        # Map the status field to is_active
        instance.is_active = self.cleaned_data.get('status', True)
        

        
        if commit:
            instance.save()
            
            # Handle multiple course associations
            course_ids = self.cleaned_data.get('course_ids', [])
            
            if course_ids:
                # Clear existing courses if we have new selections
                if hasattr(instance, 'assignmentcourse_set'):
                    instance.assignmentcourse_set.all().delete()
                
                # Set the first course as primary
                is_first = True
                from courses.models import Course
                
                for course_id in course_ids:
                    try:
                        course = Course.objects.get(id=course_id)
                        AssignmentCourse.objects.create(
                            assignment=instance,
                            course=course,
                            is_primary=is_first
                        )
                        is_first = False
                    except Course.DoesNotExist:
                        pass
            elif instance.course:
                # If we have a course in the legacy field but no course_ids selected,
                # make sure it's in the many-to-many relationship too
                if hasattr(instance, 'assignmentcourse_set'):
                    # Only create a relationship if one doesn't already exist
                    if not instance.assignmentcourse_set.filter(course=instance.course).exists():
                        AssignmentCourse.objects.get_or_create(
                            assignment=instance,
                            course=instance.course,
                            defaults={'is_primary': True}
                        )
            else:
                # No course_ids and no instance.course - ensure any existing relationships are removed
                if hasattr(instance, 'assignmentcourse_set'):
                    instance.assignmentcourse_set.all().delete()
            
            # Handle multiple topic associations
            topic_ids = self.cleaned_data.get('topic_ids', [])
            
            if topic_ids:
                # Clear existing topics if we have new selections
                if hasattr(instance, 'topicassignment_set'):
                    instance.topicassignment_set.all().delete()
                
                from courses.models import Topic
                
                for order, topic_id in enumerate(topic_ids):
                    try:
                        topic = Topic.objects.get(id=topic_id)
                        TopicAssignment.objects.update_or_create(
                            assignment=instance,
                            topic=topic,
                            defaults={'order': order}
                        )
                        
                        # Make sure the course is added to the assignment's courses
                        topic_courses = Course.objects.filter(coursetopic__topic=topic)
                        for topic_course in topic_courses:
                            # Check if already associated
                            if not AssignmentCourse.objects.filter(assignment=instance, course=topic_course).exists():
                                # Determine if this should be the primary course
                                is_primary = not AssignmentCourse.objects.filter(assignment=instance, is_primary=True).exists()
                                AssignmentCourse.objects.create(
                                    assignment=instance,
                                    course=topic_course,
                                    is_primary=is_primary
                                )
                                
                    except Topic.DoesNotExist:
                        pass
            
            # Handle multiple file uploads
            attachments = self.files.getlist('attachments')
            if attachments:
                for attachment in attachments:
                    attachment_obj = AssignmentAttachment.objects.create(
                        assignment=instance,
                        file=attachment,
                        file_name=attachment.name,
                        user=user
                    )
                    
                    # Register file in media database for tracking
                    try:
                        from lms_media.utils import register_media_file
                        register_media_file(
                            file_path=str(attachment_obj.file),
                            uploaded_by=user,
                            source_type='assignment_submission',
                            source_model='AssignmentAttachment',
                            source_object_id=attachment_obj.id,
                            course=instance.course if hasattr(instance, 'course') else None,
                            filename=attachment.name,
                            description=f'Assignment attachment for: {instance.title}'
                        )
                    except Exception as e:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.error(f"Error registering assignment attachment in media database: {str(e)}")
                    
        return instance

class TextQuestionForm(BaseModelFormWithQuill):
    question_text = CustomTinyMCEFormField(required=True)
    
    class Meta:
        model = TextQuestion
        fields = ['question_text', 'order']
        widgets = {
            'order': forms.NumberInput(attrs={
                'class': 'block w-full rounded-lg border border-gray-300 bg-white text-gray-900 px-4 py-2.5 focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 transition-colors duration-200',
                'min': '0',
                'step': '1'
            })
        }

class SupportingDocQuestionForm(forms.ModelForm):
    class Meta:
        model = SupportingDocQuestion
        fields = ['question', 'answer']
        widgets = {
            'question': forms.Textarea(attrs={
                'class': 'block w-full rounded-lg border border-gray-300 bg-white text-gray-900 px-4 py-2.5 focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 transition-colors duration-200',
                'placeholder': 'Enter your question here',
                'rows': 3
            }),
            'answer': forms.Textarea(attrs={
                'class': 'block w-full rounded-lg border border-gray-300 bg-white text-gray-900 px-4 py-2.5 focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 transition-colors duration-200',
                'placeholder': 'Enter your answer here',
                'rows': 5
            })
        }

class StudentAnswerForm(forms.ModelForm):
    answer = TinyMCEFormField(
        required=True,
        widget=TinyMCEWidget(attrs={
            'class': 'block w-full rounded-lg border border-gray-300 bg-white text-gray-900 px-4 py-2.5 focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 transition-colors duration-200',
            'placeholder': 'Type your answer here',
            'rows': 4
        }),
    )
    
    class Meta:
        model = StudentAnswer
        fields = ['answer']

class AssignmentGradingForm(forms.Form):
    """
    Form for grading assignment submissions with proper TinyMCE widget integration
    """
    grade = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500',
            'step': '0.01',
            'min': '0'
        })
    )
    
    status = forms.ChoiceField(
        choices=[
            ('not_graded', 'Not Graded'),
            ('graded', 'Graded'),
            ('returned', 'Returned for Revision'),
            ('late', 'Late'),
            ('missing', 'Missing'),
            ('excused', 'Excused'),
        ],
        widget=forms.Select(attrs={
            'class': 'w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500'
        })
    )
    
    feedback = TinyMCEFormField(
        required=False,
        widget=TinyMCEWidget(attrs={
            'class': 'w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500',
            'placeholder': 'Type your feedback here...',
            'rows': 8,
        }, config={
            'height': 300,
            'menubar': 'edit view insert format tools table',
            'plugins': [
                'advlist', 'autolink', 'lists', 'link', 'image', 'charmap', 'preview',
                'anchor', 'searchreplace', 'visualblocks', 'code', 'fullscreen',
                'insertdatetime', 'media', 'table', 'wordcount', 'aiwriter'
            ],
            'toolbar': 'undo redo | blocks | ' +
                      'bold italic forecolor | alignleft aligncenter ' +
                      'alignright alignjustify | bullist numlist outdent indent | ' +
                      'removeformat | image media | code fullscreen | aiwriter',
            'skin': 'oxide',
            'content_css': 'default',
            'toolbar_mode': 'wrap',
            'toolbar_sticky': False,
            'toolbar_location': 'top',
            'fixed_toolbar_container': None,
            'inline': False,
            'branding': False,
            'promotion': False,
            'statusbar': True,
            'resize': True,
            'browser_spellcheck': True,
            'contextmenu': False,
            'automatic_uploads': True,
            'images_upload_url': '/tinymce/upload_image/',
            'media_upload_url': '/tinymce/upload_media_file/',
            'media_live_embeds': True,
            'media_filter_html': False,
            'file_picker_types': 'image media',
            'image_advtab': True,
            'image_uploadtab': True,
            'content_style': 'body { font-family:Helvetica,Arial,sans-serif; font-size:14px }',
            # Additional positioning fixes
            'forced_root_block': 'p',
            'force_br_newlines': False,
            'force_p_newlines': False,
            'relative_urls': False,
            'remove_script_host': False,
            'document_base_url': '/'
        })
    )
    
    audio_feedback = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(attrs={
            'accept': 'audio/*,.mp3,.wav,.m4a,.aac,.ogg',
            'class': 'block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100'
        })
    )
    
    video_feedback = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(attrs={
            'accept': 'video/*,.mp4,.mov,.avi,.wmv,.mkv',
            'class': 'block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100'
        })
    )
    
    def __init__(self, *args, **kwargs):
        self.assignment = kwargs.pop('assignment', None)
        self.submission = kwargs.pop('submission', None)
        self.current_user = kwargs.pop('current_user', None)
        super().__init__(*args, **kwargs)
        
        # Set max grade based on assignment max score
        if self.assignment and self.assignment.max_score:
            self.fields['grade'].widget.attrs['max'] = str(self.assignment.max_score)
            
        # Set initial values if submission exists
        if self.submission:
            self.fields['grade'].initial = self.submission.grade
            self.fields['status'].initial = self.submission.status
            
            # Get existing feedback if any
            from .models import AssignmentFeedback
            try:
                feedback_qs = AssignmentFeedback.objects.filter(submission=self.submission)
                if self.current_user:
                    feedback_qs = feedback_qs.filter(created_by=self.current_user)
                feedback = feedback_qs.order_by('-created_at').first()
                if feedback:
                    self.fields['feedback'].initial = feedback.feedback
            except AssignmentFeedback.DoesNotExist:
                pass
    
    def clean_grade(self):
        grade = self.cleaned_data.get('grade')
        if grade is not None and self.assignment and self.assignment.max_score:
            if grade > self.assignment.max_score:
                raise forms.ValidationError(f"Grade cannot exceed maximum score of {self.assignment.max_score}")
        return grade
    
    def clean_audio_feedback(self):
        audio_file = self.cleaned_data.get('audio_feedback')
        if audio_file:
            # Check file size (50MB limit)
            if audio_file.size > 50 * 1024 * 1024:
                raise forms.ValidationError("Audio file size cannot exceed 50MB")
            
            # Check file type
            allowed_types = ['audio/mpeg', 'audio/wav', 'audio/mp4', 'audio/aac', 'audio/ogg']
            if not any(audio_file.content_type.startswith(t) for t in ['audio/']):
                raise forms.ValidationError("Please select a valid audio file")
        return audio_file
    
    def clean_video_feedback(self):
        video_file = self.cleaned_data.get('video_feedback')
        if video_file:
            # Check file size (100MB limit)
            if video_file.size > 100 * 1024 * 1024:
                raise forms.ValidationError("Video file size cannot exceed 100MB")
            
            # Check file type
            if not any(video_file.content_type.startswith(t) for t in ['video/']):
                raise forms.ValidationError("Please select a valid video file")
        return video_file 