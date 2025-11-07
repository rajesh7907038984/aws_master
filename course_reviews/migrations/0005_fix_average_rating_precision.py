# Generated migration to fix average_rating field precision
from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('course_reviews', '0004_recalculate_normalized_ratings'),
    ]

    operations = [
        migrations.AlterField(
            model_name='coursereview',
            name='average_rating',
            field=models.DecimalField(
                decimal_places=2,
                help_text='Average rating from all rating fields (normalized to 0-10 scale)',
                max_digits=4,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(10)
                ]
            ),
        ),
    ]

