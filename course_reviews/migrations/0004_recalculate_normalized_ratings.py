# Generated manually to fix star rating consistency issues

from django.db import migrations


def recalculate_course_reviews(apps, schema_editor):
    """
    Recalculate all CourseReview average_rating values to ensure they are
    properly normalized to the 0-10 scale.
    """
    CourseReview = apps.get_model('course_reviews', 'CourseReview')
    SurveyResponse = apps.get_model('course_reviews', 'SurveyResponse')
    
    reviews = CourseReview.objects.all()
    
    for review in reviews:
        # Get all rating responses for this review
        responses = SurveyResponse.objects.filter(
            user=review.user,
            course=review.course,
            survey_field__survey=review.survey,
            survey_field__field_type='rating',
            rating_response__isnull=False
        ).select_related('survey_field')
        
        if responses.exists():
            # Recalculate with proper normalization
            normalized_ratings = []
            for r in responses:
                # Normalize rating to 0-10 scale based on the field's max_rating
                max_rating = r.survey_field.max_rating
                normalized_rating = (r.rating_response / max_rating) * 10
                normalized_ratings.append(normalized_rating)
            
            if normalized_ratings:
                avg_rating = sum(normalized_ratings) / len(normalized_ratings)
                review.average_rating = avg_rating
                review.save(update_fields=['average_rating'])


def reverse_func(apps, schema_editor):
    """
    No reverse operation - we can't undo the normalization since we don't know
    the original incorrect values.
    """
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('course_reviews', '0003_initial'),
    ]

    operations = [
        migrations.RunPython(recalculate_course_reviews, reverse_func),
    ]

