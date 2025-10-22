"""
Management command to set up log directories after deployment.
This ensures that production logging directories exist and are writable.
"""
import os
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Set up log directories for the application'

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
        self.stdout.write("LMS Log Directory Setup")
        self.stdout.write("=" * 60)
        
        # Define log directories that need to exist
        log_dirs = self._get_log_directories()
        
        if options['check_only']:
            self._check_directories_only(log_dirs)
            return
        
        success_count = 0
        error_count = 0
        
        self.stdout.write("\nCreating log directories...")
        for directory in log_dirs:
            try:
                if not os.path.exists(directory) or options['force']:
                    os.makedirs(directory, exist_ok=True)
                    
                    # Try to set permissions (755 for directories)
                    try:
                        os.chmod(directory, 0o755)
                    except Exception as chmod_error:
                        self.stdout.write(
                            self.style.WARNING(
                                f"Note: Cannot set permissions for {directory}: {str(chmod_error)}"
                            )
                        )
                    
                    self.stdout.write(
                        self.style.SUCCESS(f"✓ Created log directory: {directory}")
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
            self._provide_troubleshooting_help()
        else:
            self.stdout.write(self.style.SUCCESS("All log directories set up successfully!"))

    def _get_log_directories(self):
        """Get list of log directories that need to be created"""
        log_dirs = []
        
        # Add standard log directory from BASE_DIR/logs
        if hasattr(settings, 'BASE_DIR'):
            base_log_dir = os.path.join(settings.BASE_DIR, 'logs')
            log_dirs.append(base_log_dir)
        
        # Add production-specific log directories
        if hasattr(settings, 'LOGGING') and isinstance(settings.LOGGING, dict):
            handlers = settings.LOGGING.get('handlers', {})
            for handler_name, handler_config in handlers.items():
                if 'filename' in handler_config:
                    log_file_path = handler_config['filename']
                    log_dir = os.path.dirname(log_file_path)
                    if log_dir and log_dir not in log_dirs:
                        log_dirs.append(log_dir)
        
        # Remove duplicates and sort
        return sorted(list(set(log_dirs)))

    def _check_directories_only(self, log_dirs):
        """Check directory accessibility without creating them"""
        self.stdout.write("\nChecking log directories...")
        all_good = True
        
        for directory in log_dirs:
            if os.path.exists(directory):
                writable = os.access(directory, os.W_OK)
                if writable:
                    self.stdout.write(
                        self.style.SUCCESS(f"✓ Directory exists and is writable: {directory}")
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f"! Directory exists but not writable: {directory}")
                    )
                    all_good = False
            else:
                self.stdout.write(
                    self.style.ERROR(f"✗ Directory does not exist: {directory}")
                )
                all_good = False
        
        self.stdout.write("\n" + "="*50)
        if all_good:
            self.stdout.write(self.style.SUCCESS("All log directories are ready!"))
        else:
            self.stdout.write(self.style.WARNING("Some log directories need attention."))

    def _provide_troubleshooting_help(self):
        """Provide troubleshooting guidance"""
        self.stdout.write("\n" + self.style.WARNING(" TROUBLESHOOTING TIPS"))
        self.stdout.write(self.style.WARNING("━" * 40))
        self.stdout.write("If log directory creation failed:")
        self.stdout.write("")
        self.stdout.write("1. 🗂️  Check filesystem permissions")
        self.stdout.write("2.  Ensure sufficient disk space")
        self.stdout.write("3. 🔒 Verify the application has write access")
        self.stdout.write("4.  For production: check if directories need to be created as root")
        self.stdout.write("")
        self.stdout.write("Alternative: Use console logging only by setting DEBUG=True temporarily")
        self.stdout.write("")
