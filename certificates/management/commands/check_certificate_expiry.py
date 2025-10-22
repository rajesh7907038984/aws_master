"""
Management command to check for expiring certificates and send notifications
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from certificates.models import IssuedCertificate
from lms_notifications.models import NotificationSettings, NotificationType
from lms_notifications.utils import send_notification
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Check for expiring certificates and send reminder notifications to learners'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run in dry-run mode without sending notifications',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        
        if dry_run:
            self.stdout.write(self.style.WARNING('Running in DRY-RUN mode - no notifications will be sent'))
        
        # Get certificate expiry notification type
        try:
            notification_type = NotificationType.objects.get(name='certificate_expiry_reminder')
        except NotificationType.DoesNotExist:
            self.stdout.write(self.style.ERROR('Certificate expiry notification type not found'))
            return
        
        # Get all active certificates that have an expiry date
        certificates = IssuedCertificate.objects.filter(
            expiry_date__isnull=False,
            is_revoked=False
        ).select_related('recipient', 'template')
        
        notifications_sent = 0
        certificates_checked = 0
        
        for certificate in certificates:
            certificates_checked += 1
            
            # Get user's notification settings
            settings, created = NotificationSettings.objects.get_or_create(
                user=certificate.recipient,
                defaults={
                    'certificate_expiry_reminder_days': 30,
                    'certificate_expiry_reminder_intervals': [30, 7, 1]
                }
            )
            
            # Get reminder intervals (use intervals if available, fallback to single day setting)
            reminder_intervals = settings.certificate_expiry_reminder_intervals
            if not reminder_intervals or not isinstance(reminder_intervals, list) or len(reminder_intervals) == 0:
                # Fallback to single day setting for backward compatibility
                if settings.certificate_expiry_reminder_days > 0:
                    reminder_intervals = [settings.certificate_expiry_reminder_days]
                else:
                    continue  # Skip if no reminders configured
            
            today = timezone.now().date()
            
            # Check each interval to see if we should send a reminder today
            for interval_days in reminder_intervals:
                # Calculate the reminder date for this interval
                reminder_date = certificate.expiry_date - timedelta(days=interval_days)
                
                # Check if we should send a reminder today for this interval
                # Send reminder if today is the reminder date and certificate hasn't expired yet
                if reminder_date.date() == today and certificate.expiry_date.date() > today:
                    days_until_expiry = (certificate.expiry_date.date() - today).days
                    
                    # Prepare notification message
                    title = f'Your {certificate.course_name} Certificate is Expiring Soon'
                    message = f'''
                <h3>Certificate Expiry Reminder</h3>
                <p>Dear {certificate.recipient.get_full_name()},</p>
                
                <p>This is a friendly reminder that your certificate is expiring soon.</p>
                
                <h4>Certificate Details:</h4>
                <ul>
                    <li><strong>Course:</strong> {certificate.course_name}</li>
                    <li><strong>Certificate Number:</strong> {certificate.certificate_number}</li>
                    <li><strong>Issue Date:</strong> {certificate.issue_date.strftime("%B %d, %Y")}</li>
                    <li><strong>Expiry Date:</strong> {certificate.expiry_date.strftime("%B %d, %Y")}</li>
                    <li><strong>Days Until Expiry:</strong> {days_until_expiry} day{"s" if days_until_expiry != 1 else ""}</li>
                </ul>
                
                <p>Please take action to renew your certificate before it expires to maintain your credentials.</p>
                
                <p>Best regards,<br>The LMS Team</p>
                    '''
                    
                    short_message = (
                        f'Your {certificate.course_name} certificate expires in {days_until_expiry} '
                        f'day{"s" if days_until_expiry != 1 else ""}. Renew before {certificate.expiry_date.strftime("%B %d, %Y")}.'
                    )
                    
                    if not dry_run:
                        # Send notification
                        try:
                            notification = send_notification(
                                recipient=certificate.recipient,
                                notification_type_name='certificate_expiry_reminder',
                                title=title,
                                message=message,
                                short_message=short_message,
                                send_email=True,
                                priority='high',
                                action_url=f'/certificates/view/{certificate.id}/',
                                action_text='View Certificate'
                            )
                            
                            if notification:
                                notifications_sent += 1
                                self.stdout.write(
                                    self.style.SUCCESS(
                                        f'Sent {days_until_expiry}-day expiry reminder for certificate #{certificate.certificate_number} to {certificate.recipient.email}'
                                    )
                                )
                            else:
                                self.stdout.write(
                                    self.style.WARNING(
                                        f'Failed to send notification for certificate #{certificate.certificate_number}'
                                    )
                                )
                        except Exception as e:
                            logger.error(f'Error sending notification for certificate #{certificate.certificate_number}: {str(e)}')
                            self.stdout.write(
                                self.style.ERROR(
                                    f'Error sending notification for certificate #{certificate.certificate_number}: {str(e)}'
                                )
                            )
                    else:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'[DRY-RUN] Would send {days_until_expiry}-day expiry reminder for certificate #{certificate.certificate_number} to {certificate.recipient.email}'
                            )
                        )
                        notifications_sent += 1
                    
                    # Break after sending one reminder to avoid duplicate notifications for the same certificate on the same day
                    break
        
        # Summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS(f'Certificate Expiry Check Complete'))
        self.stdout.write(f'Certificates checked: {certificates_checked}')
        self.stdout.write(f'Notifications {"would be " if dry_run else ""}sent: {notifications_sent}')
        self.stdout.write('='*60)

