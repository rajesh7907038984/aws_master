"""
Management command to set up media directories after deployment.
This is useful for cloud deployments where the filesystem
may be read-only except for mounted storage.
"""
import os
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Set up media directories for the application'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force directory creation even if they exist',
        )
        parser.add_argument(
            '--check-only',
            action='store_true',
            help='Only check accessibility without creating directories',
        )

    def handle(self, *args, **options):
        self.stdout.write("=" * 60)
        self.stdout.write("LMS Media Directory Setup")
        self.stdout.write("=" * 60)
        
        # Check media root accessibility
        is_accessible, can_write = self.check_media_root_access()
        
        if options['check_only']:
            self.stdout.write("\n" + "=" * 50)
            if is_accessible and can_write:
                self.stdout.write(self.style.SUCCESS("✓ Media root is accessible and writable"))
            else:
                self.stdout.write(self.style.ERROR("✗ Media root is not accessible or writable"))
            return
        
        if not is_accessible:
            self.stdout.write(
                self.style.ERROR(f"✗ Media root is not accessible: {settings.MEDIA_ROOT}")
            )
            self.provide_render_help()
            return
        
        if not can_write:
            self.stdout.write(
                self.style.ERROR(f"✗ Media root is not writable: {settings.MEDIA_ROOT}")
            )
            self.provide_render_help()
            return
        
        self.stdout.write(
            self.style.SUCCESS(f"✓ Media root is accessible and writable: {settings.MEDIA_ROOT}")
        )
        
        # Define media directories that need to exist
        media_dirs = [
            settings.MEDIA_ROOT,
            os.path.join(settings.MEDIA_ROOT, 'temp'),
            os.path.join(settings.MEDIA_ROOT, 'course_images'),
            os.path.join(settings.MEDIA_ROOT, 'course_content'),
            os.path.join(settings.MEDIA_ROOT, 'course_content', 'course_images'),
            os.path.join(settings.MEDIA_ROOT, 'course_content', 'course_images', 'temp'),
            os.path.join(settings.MEDIA_ROOT, 'editor_uploads'),
            os.path.join(settings.MEDIA_ROOT, 'messages', 'uploads'),
            os.path.join(settings.MEDIA_ROOT, 'assignment_content'),
            # REMOVED: os.path.join(settings.MEDIA_ROOT, 'scorm_uploads') - SCORM now uses temporary files
            os.path.join(settings.MEDIA_ROOT, 'temp_uploads'),
            os.path.join(settings.MEDIA_ROOT, 'exports'),
            os.path.join(settings.MEDIA_ROOT, 'backups'),
        ]
        
        success_count = 0
        error_count = 0
        
        self.stdout.write("\nCreating media directories...")
        for directory in media_dirs:
            try:
                if not os.path.exists(directory) or options['force']:
                    os.makedirs(directory, exist_ok=True)
                    # Try to set permissions
                    try:
                        os.chmod(directory, 0o755)
                    except Exception as chmod_error:
                        self.stdout.write(
                            self.style.WARNING(
                                f"Note: Cannot set permissions for {directory}: {str(chmod_error)}"
                            )
                        )
                    self.stdout.write(
                        self.style.SUCCESS(f"✓ Created directory: {directory}")
                    )
                    success_count += 1
                else:
                    self.stdout.write(f"  Directory already exists: {directory}")
                    success_count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"✗ Failed to create {directory}: {str(e)}")
                )
                error_count += 1
        
        self.stdout.write("\n" + "="*50)
        self.stdout.write(
            self.style.SUCCESS(f"Successfully processed: {success_count} directories")
        )
        if error_count > 0:
            self.stdout.write(
                self.style.ERROR(f"Failed: {error_count} directories")
            )
            self.provide_render_help()
        else:
            self.stdout.write(self.style.SUCCESS("All media directories set up successfully!"))
            
    def check_media_root_access(self):
        """Check if MEDIA_ROOT exists and is writable"""
        media_root = settings.MEDIA_ROOT
        
        self.stdout.write(f"Checking media root: {media_root}")
        
        # Check if it exists
        exists = os.path.exists(media_root)
        if not exists:
            self.stdout.write(self.style.WARNING("  Media root does not exist"))
            return False, False
            
        # Check if it's writable
        writable = os.access(media_root, os.W_OK)
        if not writable:
            self.stdout.write(self.style.WARNING("  Media root exists but is not writable"))
            return True, False
            
        return True, True
        
    def provide_render_help(self):
        """Provide helpful instructions for cloud deployment"""
        if os.environ.get('RENDER'):
            self.stdout.write("\n" + self.style.WARNING(" CLOUD DEPLOYMENT SETUP REQUIRED"))
            self.stdout.write(self.style.WARNING("━" * 50))
            self.stdout.write("To fix media storage issues on cloud deployment:")
            self.stdout.write("")
            self.stdout.write("1. 📋 Check your deployment platform dashboard")
            self.stdout.write("2.  Configure persistent storage if needed")
            self.stdout.write("3. ➕ Ensure media directory is properly mounted")
            self.stdout.write("4.  Redeploy your application")
            self.stdout.write("")
            self.stdout.write("📖 Check your platform's documentation for persistent storage setup")
            self.stdout.write("")
        else:
            self.stdout.write("\n" + self.style.WARNING("Note: Ensure MEDIA_ROOT directory exists and is writable"))
            self.stdout.write("For cloud deployments, check your platform's storage configuration") 