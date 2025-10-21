from django.apps import AppConfig


class CourseReviewsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'course_reviews'
    verbose_name = 'Course Reviews & Surveys'
    
    def ready(self):
        # Import signals if needed
        pass