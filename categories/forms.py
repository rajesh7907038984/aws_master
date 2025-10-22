from django import forms
from django.utils.text import slugify
from .models import CourseCategory

class CourseCategoryForm(forms.ModelForm):
    class Meta:
        model = CourseCategory
        fields = ['name', 'slug', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500',
                'placeholder': 'Enter category name'
            }),
            'slug': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 bg-gray-50',
                'placeholder': 'Auto-generated from name'
            }),
            'description': forms.Textarea(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500',
                'rows': 4,
                'placeholder': 'Enter category description'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500'
            })
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make slug optional in the form
        self.fields['slug'].required = False
        
    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise forms.ValidationError('Category name is required')
        return name
        
    def clean_slug(self):
        slug = self.cleaned_data.get('slug', '').strip()
        if not slug:
            # If no slug provided, let the model handle it
            return ''
        # Check for the problematic slug
        if slug == '8798iujnhgfbfergfv':
            # Return empty string to let model generate a new one
            return ''
        return slugify(slug)
        
    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        slug = cleaned_data.get('slug')
        
        if name:
            # If no slug provided, let the model handle it
            if not slug:
                cleaned_data['slug'] = ''
            else:
                # Clean the provided slug
                cleaned_slug = slugify(slug)
                if cleaned_slug != slug:
                    cleaned_data['slug'] = cleaned_slug
            
        return cleaned_data 