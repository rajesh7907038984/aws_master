from django import forms
from .models import Conference
import pytz
from tinymce_editor.widgets import TinyMCEWidget

class ConferenceForm(forms.ModelForm):
    """
    Form for creating and editing conferences
    """
    description = forms.CharField(
        widget=TinyMCEWidget(config={
            'height': 300,
            'menubar': 'edit view insert format',
            'plugins': [
                'advlist', 'autolink', 'lists', 'link', 'charmap', 'preview',
                'searchreplace', 'visualblocks', 'code', 'fullscreen',
                'insertdatetime', 'table', 'wordcount'
            ],
            'toolbar': 'undo redo | blocks | bold italic forecolor | alignleft aligncenter alignright alignjustify | bullist numlist outdent indent | removeformat | code',
            'placeholder': 'Describe the purpose of this conference...',
            'content_style': 'body { font-family:Helvetica,Arial,sans-serif; font-size:14px }',
            'branding': False,
            'promotion': False,
        }),
        required=False
    )
    
    # Get timezone choices
    common_timezones = [
        ('UTC', 'UTC (Coordinated Universal Time)'),
        ('US/Eastern', 'US/Eastern (New York, Atlanta, Miami)'),
        ('US/Central', 'US/Central (Chicago, Dallas, Houston)'),
        ('US/Mountain', 'US/Mountain (Denver, Phoenix, Salt Lake City)'),
        ('US/Pacific', 'US/Pacific (Los Angeles, San Francisco, Seattle)'),
        ('Europe/London', 'Europe/London (UK, Ireland)'),
        ('Europe/Paris', 'Europe/Paris (Paris, Berlin, Rome)'),
        ('Europe/Berlin', 'Europe/Berlin (Berlin, Amsterdam, Prague)'),
        ('Asia/Tokyo', 'Asia/Tokyo (Tokyo, Seoul, Osaka)'),
        ('Asia/Shanghai', 'Asia/Shanghai (Beijing, Shanghai, Hong Kong)'),
        ('Asia/Kolkata', 'Asia/Kolkata (Mumbai, Delhi, Bangalore)'),
        ('Australia/Sydney', 'Australia/Sydney (Sydney, Melbourne, Brisbane)'),
    ]
    
    # Get all timezone choices from pytz and sort them
    all_timezones = [(tz, tz) for tz in sorted(pytz.common_timezones)]
    
    # Combine common timezones first, then separator, then all timezones
    timezone_choices = common_timezones + [('', '--- All Timezones ---')] + all_timezones
    
    timezone = forms.ChoiceField(
        choices=timezone_choices,
        initial='UTC',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Select the timezone for this conference"
    )
    
    class Meta:
        model = Conference
        fields = [
            'title', 'description', 'date', 'start_time', 'end_time', 'timezone',
            'meeting_link', 'meeting_password', 'meeting_id', 'host_url',
            'meeting_platform', 'visibility', 'status', 'rubric'
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
            'meeting_link': forms.URLInput(attrs={'placeholder': 'Optional meeting link'}),
            'meeting_password': forms.TextInput(attrs={'placeholder': 'Optional meeting password'}),
            'meeting_id': forms.TextInput(attrs={'placeholder': 'Optional meeting ID'}),
            'host_url': forms.URLInput(attrs={'placeholder': 'Optional host URL'}),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter rubrics based on user role using centralized function
        if user:
            from lms_rubrics.utils import get_filtered_rubrics_for_user
            
            # Get the course if available (for edit mode)
            course = None
            if self.instance and self.instance.pk and self.instance.course:
                course = self.instance.course
            
            # Apply rubric filtering
            self.fields['rubric'].queryset = get_filtered_rubrics_for_user(user, course)
        
        # Make meeting-related fields optional for all users
        self.fields['meeting_platform'].required = False
        self.fields['meeting_link'].required = False
        self.fields['meeting_password'].required = False
        self.fields['meeting_id'].required = False
        self.fields['host_url'].required = False
        
        # Make visibility and status optional with defaults
        self.fields['visibility'].required = False
        self.fields['status'].required = False
        
        # Set default values for fields if they're not set
        if not self.instance.pk:  # Only for new conferences
            self.fields['visibility'].initial = 'public'
            self.fields['status'].initial = 'draft'
        
        # Always force visibility to be public and hide the field
        self.fields['visibility'].initial = 'public'
        self.fields['visibility'].widget = forms.HiddenInput()
            
    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        
        # Validate start and end times
        if start_time and end_time and start_time >= end_time:
            raise forms.ValidationError("End time must be after start time.")
        
        # If meeting platform is provided, ensure it's valid
        meeting_platform = cleaned_data.get('meeting_platform')
        valid_platforms = ['zoom', 'teams', 'google_meet', 'webex', 'other']
        if meeting_platform and meeting_platform not in valid_platforms:
            cleaned_data['meeting_platform'] = 'other'
        
        # Always force visibility to be 'public'
        cleaned_data['visibility'] = 'public'
            
        return cleaned_data 


class ConferenceFileUploadForm(forms.Form):
    """
    Form for participants to upload files during a conference
    """
    file = forms.FileField(
        label='Select file to share',
        help_text='Max file size: 100MB. Allowed formats: PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT, JPG, PNG, ZIP',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.jpg,.jpeg,.png,.zip'
        })
    )
    description = forms.CharField(
        label='File description (optional)',
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Brief description of the file'
        })
    )
    
    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            # Check file size (100MB limit)
            if file.size > 100 * 1024 * 1024:
                raise forms.ValidationError('File size cannot exceed 100MB.')
            
            # Check file extension
            allowed_extensions = [
                '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', 
                '.txt', '.jpg', '.jpeg', '.png', '.zip'
            ]
            ext = file.name.lower().split('.')[-1] if '.' in file.name else ''
            if not any(file.name.lower().endswith(ext) for ext in allowed_extensions):
                raise forms.ValidationError(
                    f'Invalid file type. Allowed types: {", ".join(allowed_extensions)}'
                )
        return file 