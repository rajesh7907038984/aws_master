from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from users.models import PasswordResetToken, EmailVerificationToken


class Command(BaseCommand):
    help = 'Clean up expired password reset and email verification tokens'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Delete tokens older than this many days (default: 7)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        
        cutoff_date = timezone.now() - timedelta(days=days)
        
        # Find expired password reset tokens
        expired_reset_tokens = PasswordResetToken.objects.filter(
            created_at__lt=cutoff_date
        )
        
        # Find expired email verification tokens
        expired_verification_tokens = EmailVerificationToken.objects.filter(
            created_at__lt=cutoff_date
        )
        
        reset_count = expired_reset_tokens.count()
        verification_count = expired_verification_tokens.count()
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f'DRY RUN: Would delete {reset_count} password reset tokens')
            )
            self.stdout.write(
                self.style.WARNING(f'DRY RUN: Would delete {verification_count} email verification tokens')
            )
            
            if reset_count > 0:
                self.stdout.write('\nPassword reset tokens to be deleted:')
                for token in expired_reset_tokens[:10]:  # Show first 10
                    self.stdout.write(f'  - {token.user.email} (created: {token.created_at})')
                if reset_count > 10:
                    self.stdout.write(f'  ... and {reset_count - 10} more')
            
            if verification_count > 0:
                self.stdout.write('\nEmail verification tokens to be deleted:')
                for token in expired_verification_tokens[:10]:  # Show first 10
                    self.stdout.write(f'  - {token.user.email} (created: {token.created_at})')
                if verification_count > 10:
                    self.stdout.write(f'  ... and {verification_count - 10} more')
        else:
            # Actually delete the tokens
            deleted_reset = expired_reset_tokens.delete()
            deleted_verification = expired_verification_tokens.delete()
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully deleted {deleted_reset[0]} password reset tokens '
                    f'and {deleted_verification[0]} email verification tokens '
                    f'older than {days} days'
                )
            )
            
        # Also clean up truly expired tokens (past their expiry date)
        expired_by_date_reset = PasswordResetToken.objects.filter(
            expires_at__lt=timezone.now(),
            is_used=False
        )
        
        expired_by_date_verification = EmailVerificationToken.objects.filter(
            expires_at__lt=timezone.now(),
            is_used=False
        )
        
        expired_reset_count = expired_by_date_reset.count()
        expired_verification_count = expired_by_date_verification.count()
        
        if not dry_run and (expired_reset_count > 0 or expired_verification_count > 0):
            deleted_expired_reset = expired_by_date_reset.delete()
            deleted_expired_verification = expired_by_date_verification.delete()
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Additionally deleted {deleted_expired_reset[0]} expired password reset tokens '
                    f'and {deleted_expired_verification[0]} expired email verification tokens'
                )
            )
        elif dry_run and (expired_reset_count > 0 or expired_verification_count > 0):
            self.stdout.write(
                self.style.WARNING(
                    f'DRY RUN: Would also delete {expired_reset_count} expired password reset tokens '
                    f'and {expired_verification_count} expired email verification tokens'
                )
            ) 