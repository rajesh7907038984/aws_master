# Generated manually for Azure AD Group Import feature

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('groups', '0002_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='AzureADGroupImport',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('azure_group_id', models.CharField(help_text='Azure AD Group ID', max_length=255)),
                ('azure_group_name', models.CharField(help_text='Azure AD Group Name', max_length=255)),
                ('assigned_role', models.CharField(choices=[('learner', 'Learner'), ('instructor', 'Instructor')], default='learner', help_text='Role assigned to imported users', max_length=50)),
                ('imported_at', models.DateTimeField(auto_now_add=True)),
                ('last_synced_at', models.DateTimeField(blank=True, help_text='Last time this group was synced', null=True)),
                ('is_active', models.BooleanField(default=True, help_text='Whether this import is active for syncing')),
                ('branch', models.ForeignKey(help_text='Branch this import belongs to', on_delete=django.db.models.deletion.CASCADE, related_name='azure_group_imports', to='branches.Branch')),
                ('imported_by', models.ForeignKey(help_text='Branch admin who imported this group', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='azure_imports', to=settings.AUTH_USER_MODEL)),
                ('lms_group', models.ForeignKey(help_text='Linked LMS Group', on_delete=django.db.models.deletion.CASCADE, related_name='azure_imports', to='groups.BranchGroup')),
            ],
            options={
                'ordering': ['-imported_at'],
            },
        ),
        migrations.CreateModel(
            name='AzureADUserMapping',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('azure_user_id', models.CharField(help_text='Azure AD User ID', max_length=255)),
                ('azure_email', models.EmailField(help_text='Azure AD User Email', max_length=254)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('azure_group_import', models.ForeignKey(help_text='The Azure group import this user belongs to', on_delete=django.db.models.deletion.CASCADE, related_name='user_mappings', to='groups.AzureADGroupImport')),
                ('lms_user', models.ForeignKey(help_text='Linked LMS User', on_delete=django.db.models.deletion.CASCADE, related_name='azure_mappings', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='azureadusermapping',
            constraint=models.UniqueConstraint(fields=('azure_user_id', 'azure_group_import'), name='groups_azureadusermapping_azure_user_id_azure_group_import_uniq'),
        ),
        migrations.AddConstraint(
            model_name='azureadgroupimport',
            constraint=models.UniqueConstraint(fields=('azure_group_id', 'branch'), name='groups_azureadgroupimport_azure_group_id_branch_uniq'),
        ),
    ]

