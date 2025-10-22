from django import forms
from django.forms import inlineformset_factory
from .models import Survey, SurveyField, SurveyResponse


class SurveyForm(forms.ModelForm):
    """Form for creating/editing surveys"""
    class Meta:
        model = Survey
        fields = ['title', 'description', 'is_active']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter survey title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter survey description (optional)'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }


class SurveyFieldForm(forms.ModelForm):
    """Form for creating/editing survey fields"""
    class Meta:
        model = SurveyField
        fields = ['label', 'field_type', 'is_required', 'order', 'placeholder', 'help_text', 'max_rating']
        widgets = {
            'label': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter question/label'
            }),
            'field_type': forms.Select(attrs={
                'class': 'form-select'
            }),
            'is_required': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'order': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0'
            }),
            'placeholder': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Placeholder text (optional)'
            }),
            'help_text': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Help text (optional)'
            }),
            'max_rating': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'max': '10',
                'value': '5'
            }),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        field_type = cleaned_data.get('field_type')
        max_rating = cleaned_data.get('max_rating')
        
        # Validate max_rating for rating fields
        if field_type == 'rating' and (not max_rating or max_rating < 1 or max_rating > 10):
            self.add_error('max_rating', 'Rating fields must have a max_rating between 1 and 10')
        
        return cleaned_data


# Inline formset for survey fields
SurveyFieldFormSet = inlineformset_factory(
    Survey,
    SurveyField,
    form=SurveyFieldForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
)


class SurveyResponseForm(forms.Form):
    """Dynamic form for survey responses"""
    
    def __init__(self, *args, survey=None, **kwargs):
        super().__init__(*args, **kwargs)
        
        if survey:
            # Dynamically add fields based on survey fields
            for field in survey.fields.all().order_by('order'):
                field_name = f'field_{field.id}'
                
                if field.field_type == 'text':
                    self.fields[field_name] = forms.CharField(
                        label=field.label,
                        required=field.is_required,
                        widget=forms.TextInput(attrs={
                            'class': 'form-control',
                            'placeholder': field.placeholder or ''
                        }),
                        help_text=field.help_text
                    )
                
                elif field.field_type == 'textarea':
                    self.fields[field_name] = forms.CharField(
                        label=field.label,
                        required=field.is_required,
                        widget=forms.Textarea(attrs={
                            'class': 'form-control',
                            'rows': 4,
                            'placeholder': field.placeholder or ''
                        }),
                        help_text=field.help_text
                    )
                
                elif field.field_type == 'rating':
                    self.fields[field_name] = forms.IntegerField(
                        label=field.label,
                        required=field.is_required,
                        min_value=1,
                        max_value=field.max_rating,
                        widget=forms.NumberInput(attrs={
                            'class': 'form-control rating-input',
                            'data-max': field.max_rating,
                            'style': 'display: none;'
                        }),
                        help_text=field.help_text
                    )
                
                elif field.field_type == 'number':
                    self.fields[field_name] = forms.IntegerField(
                        label=field.label,
                        required=field.is_required,
                        widget=forms.NumberInput(attrs={
                            'class': 'form-control',
                            'placeholder': field.placeholder or ''
                        }),
                        help_text=field.help_text
                    )
                
                elif field.field_type == 'email':
                    self.fields[field_name] = forms.EmailField(
                        label=field.label,
                        required=field.is_required,
                        widget=forms.EmailInput(attrs={
                            'class': 'form-control',
                            'placeholder': field.placeholder or 'email@example.com'
                        }),
                        help_text=field.help_text
                    )
