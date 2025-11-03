# Generated migration to sync enforce_sequence with sequential_progression
from django.db import migrations


def sync_sequential_progression(apps, schema_editor):
    """Sync enforce_sequence field with sequential_progression for all courses"""
    Course = apps.get_model('courses', 'Course')
    
    # Update all courses to have enforce_sequence match sequential_progression
    updated_count = 0
    for course in Course.objects.all():
        if course.enforce_sequence != course.sequential_progression:
            course.enforce_sequence = course.sequential_progression
            course.save(update_fields=['enforce_sequence'])
            updated_count += 1
    
    print(f"Synced enforce_sequence field for {updated_count} courses")


def reverse_sync(apps, schema_editor):
    """Reverse operation - no action needed"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0005_add_course_to_topic_progress'),
    ]

    operations = [
        migrations.RunPython(sync_sequential_progression, reverse_sync),
    ]

