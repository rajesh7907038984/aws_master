# In forms.py
from django import forms
from django.core.exceptions import ValidationError
import os

class SCORMUploadForm(forms.Form):
    file = forms.FileField(
        widget=forms.FileInput(attrs={
            'accept': '.zip',
            'class': 'form-control'
        }),
        help_text='Upload SCORM package (ZIP file)',
        required=True
    )
    
    title = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter title for SCORM package'
        })
    )
    
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Enter description (optional)'
        })
    )

    def clean_file(self):
        """Validate uploaded file"""
        file = self.cleaned_data.get('file')
        if file:
            # Check file extension
            ext = os.path.splitext(file.name)[1].lower()
            if ext != '.zip':
                raise ValidationError('Only ZIP files are allowed.')
            
            # Check file size (e.g., 2GB limit)
            if file.size > 2 * 1024 * 1024 * 1024:  # 2GB in bytes
                raise ValidationError('File size must be under 2GB.')
                
            return file
        raise ValidationError('No file was submitted.')

    def clean_title(self):
        """Validate title"""
        title = self.cleaned_data.get('title')
        if not title:
            raise ValidationError('Title is required.')
        if len(title) < 3:
            raise ValidationError('Title must be at least 3 characters long.')
        return title