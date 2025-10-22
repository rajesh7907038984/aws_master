from django import forms
from django.core.exceptions import ValidationError
from tinymce_editor.widgets import TinyMCEWidget
from tinymce_editor.forms import TinyMCEFormField
from .models import RubricOverallFeedback, Rubric
from users.models import CustomUser


class RubricOverallFeedbackForm(forms.ModelForm):
    """
    Form for creating/editing overall feedback on rubric evaluations
    with support for text, audio, and video feedback
    """
    
    feedback = TinyMCEFormField(
        required=False,
        widget=TinyMCEWidget(attrs={
            'class': 'w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500',
            'placeholder': 'Provide overall feedback about the rubric evaluation...',
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
    
    class Meta:
        model = RubricOverallFeedback
        fields = ['feedback', 'audio_feedback', 'video_feedback']
    
    def __init__(self, *args, **kwargs):
        self.context_type = kwargs.pop('context_type', None)  # 'assignment', 'discussion', 'conference', or 'quiz'
        self.context_object = kwargs.pop('context_object', None)
        self.student = kwargs.pop('student', None)
        self.rubric = kwargs.pop('rubric', None)
        self.current_user = kwargs.pop('current_user', None)
        super().__init__(*args, **kwargs)
        
        # Set initial values if we have an existing instance
        if self.instance and self.instance.pk:
            self.fields['feedback'].initial = self.instance.feedback
    
    def clean(self):
        cleaned_data = super().clean()
        feedback = cleaned_data.get('feedback')
        audio_feedback = cleaned_data.get('audio_feedback')
        video_feedback = cleaned_data.get('video_feedback')
        
        # Ensure at least one type of feedback is provided
        if not any([feedback, audio_feedback, video_feedback]):
            raise ValidationError(
                "At least one type of feedback (text, audio, or video) must be provided."
            )
        
        return cleaned_data
    
    def clean_audio_feedback(self):
        audio_file = self.cleaned_data.get('audio_feedback')
        if audio_file:
            # Check file size (600MB limit)
            if audio_file.size > 600 * 1024 * 1024:
                raise ValidationError("Audio file size cannot exceed 600MB")
            
            # Check file type
            if not audio_file.content_type.startswith('audio/'):
                raise ValidationError("Please select a valid audio file")
        return audio_file
    
    def clean_video_feedback(self):
        video_file = self.cleaned_data.get('video_feedback')
        if video_file:
            # Check file size (600MB limit)
            if video_file.size > 600 * 1024 * 1024:
                raise ValidationError("Video file size cannot exceed 600MB")
            
            # Check file type
            if not video_file.content_type.startswith('video/'):
                raise ValidationError("Please select a valid video file")
        return video_file
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Set the required relationships
        if self.student:
            instance.student = self.student
        if self.rubric:
            instance.rubric = self.rubric
        if self.current_user:
            instance.created_by = self.current_user
        
        # Set the context relationship
        if self.context_type == 'assignment' and self.context_object:
            instance.submission = self.context_object
        elif self.context_type == 'discussion' and self.context_object:
            instance.discussion = self.context_object
        elif self.context_type == 'conference' and self.context_object:
            instance.conference = self.context_object
        elif self.context_type == 'quiz' and self.context_object:
            instance.quiz_attempt = self.context_object
        
        if commit:
            instance.save()
        
        return instance


class RubricOverallFeedbackEditForm(RubricOverallFeedbackForm):
    """
    Form for editing existing overall feedback on rubric evaluations
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # If we're editing an existing feedback, show current files
        if self.instance and self.instance.pk:
            if self.instance.audio_feedback:
                self.fields['audio_feedback'].help_text = f"Current: {self.instance.audio_feedback.name}"
            if self.instance.video_feedback:
                self.fields['video_feedback'].help_text = f"Current: {self.instance.video_feedback.name}"


class RubricOverallFeedbackDisplayForm(forms.ModelForm):
    """
    Read-only form for displaying overall feedback on rubric evaluations
    """
    
    class Meta:
        model = RubricOverallFeedback
        fields = ['feedback', 'audio_feedback', 'video_feedback']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Make all fields read-only
        for field in self.fields.values():
            field.widget.attrs['readonly'] = True
            field.widget.attrs['disabled'] = True
        
        # Special handling for file fields
        if self.instance:
            if self.instance.audio_feedback:
                self.fields['audio_feedback'].widget = forms.TextInput(attrs={
                    'readonly': True,
                    'value': self.instance.audio_feedback.name,
                    'class': 'w-full px-3 py-2 border border-gray-300 rounded-md bg-gray-50'
                })
            if self.instance.video_feedback:
                self.fields['video_feedback'].widget = forms.TextInput(attrs={
                    'readonly': True,
                    'value': self.instance.video_feedback.name,
                    'class': 'w-full px-3 py-2 border border-gray-300 rounded-md bg-gray-50'
                }) 