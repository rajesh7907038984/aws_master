# Generated migration to add email uniqueness constraint
from django.db import migrations, models


def check_for_duplicate_emails(apps, schema_editor):
    """
    Check for duplicate emails before applying the unique constraint.
    If duplicates are found, raise an error with instructions.
    """
    CustomUser = apps.get_model('users', 'CustomUser')
    db_alias = schema_editor.connection.alias
    
    # Find duplicate emails (case-insensitive)
    from django.db.models import Count
    from django.db.models.functions import Lower
    
    duplicates = (
        CustomUser.objects.using(db_alias)
        .annotate(email_lower=Lower('email'))
        .values('email_lower')
        .annotate(count=Count('id'))
        .filter(count__gt=1)
    )
    
    if duplicates.exists():
        duplicate_count = duplicates.count()
        raise Exception(
            f"\n\n"
            f"❌ Cannot apply email uniqueness constraint!\n"
            f"   Found {duplicate_count} email address(es) with duplicates in the database.\n\n"
            f"   Please run this command first to fix duplicates:\n"
            f"   python3 manage.py fix_duplicate_emails --auto-fix\n\n"
            f"   Or to see what would be changed:\n"
            f"   python3 manage.py fix_duplicate_emails --dry-run --auto-fix\n\n"
            f"   Or to just list duplicates:\n"
            f"   python3 manage.py find_duplicate_emails\n"
        )


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        # First check for duplicates
        migrations.RunPython(
            check_for_duplicate_emails,
            reverse_code=migrations.RunPython.noop,
        ),
        # Then alter the email field to be unique
        migrations.AlterField(
            model_name='customuser',
            name='email',
            field=models.EmailField(
                help_text='Email address - must be unique across all users',
                max_length=254,
                unique=True,
                verbose_name='email address'
            ),
        ),
    ]

