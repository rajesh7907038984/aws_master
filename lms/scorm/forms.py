"""
SCORM Forms
"""
from django import forms
from .models import SCORMPackage, SCORMPackageType
from courses.models import Topic


class SCORMPackageForm(forms.ModelForm):
    """Form for uploading SCORM packages"""
    
    class Meta:
        model = SCORMPackage
        fields = ['title', 'description', 'package_type', 'package_file', 'topic']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter package title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter package description (optional)'
            }),
            'package_type': forms.Select(attrs={
                'class': 'form-control'
            }),
            'package_file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.zip'
            }),
            'topic': forms.Select(attrs={
                'class': 'form-control'
            }),
        }
    
    def clean_package_file(self):
        """Validate package file"""
        package_file = self.cleaned_data.get('package_file')
        
        if package_file:
            # Check file extension
            if not package_file.name.lower().endswith('.zip'):
                raise forms.ValidationError('Only ZIP files are allowed.')
            
            # Check file size (2GB max)
            if package_file.size > 2 * 1024 * 1024 * 1024:
                raise forms.ValidationError('File size cannot exceed 2GB.')
        
        return package_file


class TopicSCORMForm(forms.Form):
    """Simplified form for adding SCORM to a topic"""
    
    scorm_file = forms.FileField(
        label='SCORM Package (ZIP)',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.zip'
        }),
        help_text='Upload a SCORM package as a ZIP file (max 2GB)'
    )
    
    package_type = forms.ChoiceField(
        label='Package Type',
        choices=SCORMPackageType.choices,
        initial=SCORMPackageType.AUTO,
        widget=forms.Select(attrs={
            'class': 'form-control'
        }),
        help_text='Select package type or leave as Auto-detect'
    )
    
    def clean_scorm_file(self):
        """Validate SCORM file"""
        scorm_file = self.cleaned_data.get('scorm_file')
        
        if scorm_file:
            # Check file extension
            if not scorm_file.name.lower().endswith('.zip'):
                raise forms.ValidationError('Only ZIP files are allowed.')
            
            # Check file size
            if scorm_file.size > 2 * 1024 * 1024 * 1024:
                raise forms.ValidationError('File size cannot exceed 2GB.')
        
        return scorm_file

