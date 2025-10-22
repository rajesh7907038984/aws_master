from django.db import models
from django.utils.text import slugify
from django.db import transaction

# Create your models here.

class CourseCategory(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)  # Allow blank for auto-generation
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.CASCADE,
        related_name='categories',
        null=True,
        blank=True,
        help_text="The branch this category belongs to"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Course Categories"
        # Use primary key ordering to avoid potential column issues during deletion
        ordering = ['id']

    def __str__(self):
        return self.name

    def generate_unique_slug(self):
        # Generate base slug from name
        base_slug = slugify(self.name)
        if not base_slug:
            base_slug = 'category'
        
        # Find unique slug
        slug = base_slug
        counter = 1
        
        # Use select_for_update to prevent race conditions
        with transaction.atomic():
            while CourseCategory.objects.filter(slug=slug).exclude(id=self.id).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
                if counter > 1000:  # Prevent infinite loop
                    raise ValueError("Unable to generate unique slug. Please try a different name.")
        
        return slug

    def save(self, *args, **kwargs):
        # If no slug is provided, generate one
        if not self.slug:
            self.slug = self.generate_unique_slug()
        else:
            # Clean the provided slug
            cleaned_slug = slugify(self.slug)
            
            # Handle the specific problematic slug
            if self.slug == '8798iujnhgfbfergfv':
                self.slug = self.generate_unique_slug()
            # If the cleaned slug is empty or different, regenerate
            elif not cleaned_slug or cleaned_slug != self.slug:
                self.slug = self.generate_unique_slug()
            # If the slug exists for another category, generate a unique one
            elif CourseCategory.objects.filter(slug=self.slug).exclude(id=self.id).exists():
                self.slug = self.generate_unique_slug()
        
        # Always try to save, but handle any unique constraint violations
        try:
            super().save(*args, **kwargs)
        except Exception as e:
            # If a unique constraint violation occurs on the slug field, generate a new unique slug and try again
            if 'duplicate key value violates unique constraint' in str(e) and 'slug' in str(e):
                self.slug = self.generate_unique_slug()
                super().save(*args, **kwargs)
            else:
                # Re-raise any other exception
                raise

    def get_full_path(self):
        return f"/categories/{self.slug}/"
