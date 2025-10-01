from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from conferences.utils.sync_resilience import SyncHealthChecker, SyncRecoveryManager
from conferences.models import Conference
import logging
import json

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Monitor conference sync health and automatically fix issues'

    def add_arguments(self, parser):
        parser.add_argument(
            '--auto-fix',
            action='store_true',
            help='Automatically attempt to fix detected issues',
        )
        parser.add_argument(
            '--conference-id',
            type=int,
            help='Monitor specific conference ID',
        )
        parser.add_argument(
            '--send-alerts',
            action='store_true',
            help='Send email alerts for critical issues',
        )
        parser.add_argument(
            '--recent-days',
            type=int,
            default=7,
            help='Number of recent days to check (default: 7)',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )

    def handle(self, *args, **options):
        auto_fix = options['auto_fix']
        conference_id = options['conference_id']
        send_alerts = options['send_alerts']
        recent_days = options['recent_days']
        verbose = options['verbose']
        
        self.stdout.write("🔍 Conference Sync Health Monitor")
        self.stdout.write("=" * 50)
        
        if conference_id:
            # Monitor specific conference
            self.monitor_single_conference(conference_id, auto_fix, send_alerts, verbose)
        else:
            # Monitor all recent conferences
            self.monitor_all_conferences(recent_days, auto_fix, send_alerts, verbose)

    def monitor_single_conference(self, conference_id, auto_fix, send_alerts, verbose):
        """Monitor a single conference"""
        try:
            conference = Conference.objects.get(id=conference_id)
            health = SyncHealthChecker.check_conference_sync_health(conference_id)
            
            self.stdout.write(f"\n📋 Conference: {health['conference_title']} (ID: {conference_id})")
            self.stdout.write(f"Status: {health['overall_status'].upper()}")
            
            if verbose:
                self.stdout.write(f"Last Sync: {health['last_sync']}")
                self.stdout.write(f"Recordings: {health['recordings_status']}")
                self.stdout.write(f"Chat: {health['chat_status']}")
            
            if health['issues']:
                self.stdout.write(self.style.WARNING(f"⚠️  Issues Found: {len(health['issues'])}"))
                for issue in health['issues']:
                    self.stdout.write(f"  • {issue}")
                
                if auto_fix:
                    self.stdout.write("\n🔧 Attempting automatic recovery...")
                    recovery_result = SyncRecoveryManager.auto_recover_conference(conference_id)
                    
                    if recovery_result['success']:
                        self.stdout.write(self.style.SUCCESS("✅ Recovery successful!"))
                        for action in recovery_result['actions_taken']:
                            self.stdout.write(f"  ✓ {action}")
                    else:
                        self.stdout.write(self.style.ERROR("❌ Recovery failed"))
                        for error in recovery_result['errors']:
                            self.stdout.write(f"  ✗ {error}")
                
                if send_alerts and health['overall_status'] == 'critical':
                    self.send_alert_email([health])
                    
            else:
                self.stdout.write(self.style.SUCCESS("✅ No issues found"))
                
        except Conference.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Conference {conference_id} not found"))

    def monitor_all_conferences(self, recent_days, auto_fix, send_alerts, verbose):
        """Monitor all recent conferences"""
        # Get system-wide health
        system_health = SyncHealthChecker.get_system_wide_health()
        
        self.stdout.write(f"\n📊 System-Wide Health Summary")
        self.stdout.write(f"Total Conferences (last {recent_days} days): {system_health['total_conferences']}")
        self.stdout.write(f"Healthy: {system_health['healthy']}")
        self.stdout.write(f"Warning: {system_health['warning']}")
        self.stdout.write(f"Critical: {system_health['critical']}")
        
        if system_health['issues_by_type']:
            self.stdout.write(f"\n⚠️  Common Issues:")
            for issue, count in system_health['issues_by_type'].items():
                self.stdout.write(f"  • {issue}: {count} conferences")
        
        # Check individual conferences with issues
        conferences_to_check = Conference.objects.filter(
            date__gte=timezone.now().date() - timezone.timedelta(days=recent_days)
        ).order_by('-date')
        
        critical_conferences = []
        warning_conferences = []
        fixed_conferences = []
        
        for conference in conferences_to_check:
            health = SyncHealthChecker.check_conference_sync_health(conference.id)
            
            if health['overall_status'] == 'critical':
                critical_conferences.append(health)
            elif health['overall_status'] == 'warning':
                warning_conferences.append(health)
            
            if health['issues'] and auto_fix:
                if verbose:
                    self.stdout.write(f"\n🔧 Auto-fixing: {health['conference_title']}")
                
                recovery_result = SyncRecoveryManager.auto_recover_conference(conference.id)
                
                if recovery_result['success']:
                    fixed_conferences.append({
                        'conference': health,
                        'recovery': recovery_result
                    })
                    if verbose:
                        self.stdout.write(self.style.SUCCESS(f"  ✅ Fixed {len(recovery_result['actions_taken'])} issues"))
        
        # Report results
        if critical_conferences:
            self.stdout.write(f"\n🚨 Critical Issues ({len(critical_conferences)} conferences):")
            for health in critical_conferences[:5]:  # Show top 5
                self.stdout.write(f"  • {health['conference_title']} (ID: {health['conference_id']})")
                for issue in health['issues'][:2]:  # Show top 2 issues
                    self.stdout.write(f"    - {issue}")
        
        if warning_conferences and verbose:
            self.stdout.write(f"\n⚠️  Warnings ({len(warning_conferences)} conferences):")
            for health in warning_conferences[:3]:  # Show top 3
                self.stdout.write(f"  • {health['conference_title']}")
        
        if fixed_conferences:
            self.stdout.write(f"\n🔧 Auto-Fixed ({len(fixed_conferences)} conferences):")
            for fix_info in fixed_conferences:
                health = fix_info['conference']
                recovery = fix_info['recovery']
                self.stdout.write(f"  • {health['conference_title']}")
                for action in recovery['actions_taken']:
                    self.stdout.write(f"    ✓ {action}")
        
        # Send alerts if needed
        if send_alerts and critical_conferences:
            self.send_alert_email(critical_conferences)
        
        # Summary
        self.stdout.write(f"\n📈 Monitoring Summary:")
        self.stdout.write(f"  • {len(critical_conferences)} critical issues")
        self.stdout.write(f"  • {len(warning_conferences)} warnings")
        if auto_fix:
            self.stdout.write(f"  • {len(fixed_conferences)} auto-fixed")

    def send_alert_email(self, critical_conferences):
        """Send email alert for critical issues"""
        try:
            if not hasattr(settings, 'EMAIL_HOST') or not settings.EMAIL_HOST:
                self.stdout.write(self.style.WARNING("Email not configured, skipping alerts"))
                return
            
            subject = f"Conference Sync Alert - {len(critical_conferences)} Critical Issues"
            
            message = "Conference Sync Health Alert\n"
            message += "="*40 + "\n\n"
            message += f"Found {len(critical_conferences)} conferences with critical sync issues:\n\n"
            
            for health in critical_conferences:
                message += f"Conference: {health['conference_title']} (ID: {health['conference_id']})\n"
                message += f"Status: {health['overall_status']}\n"
                message += f"Issues:\n"
                for issue in health['issues']:
                    message += f"  - {issue}\n"
                message += f"Recommendations:\n"
                for rec in health['recommendations']:
                    message += f"  - {rec}\n"
                message += "\n"
            
            message += "Please check the conference sync system and take appropriate action.\n"
            message += f"Alert generated at: {timezone.now()}\n"
            
            # Send to admins
            admin_emails = [email for name, email in getattr(settings, 'ADMINS', [])]
            if admin_emails:
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    admin_emails,
                    fail_silently=False,
                )
                self.stdout.write(self.style.SUCCESS(f"📧 Alert sent to {len(admin_emails)} admins"))
            else:
                self.stdout.write(self.style.WARNING("No admin emails configured"))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to send email alert: {e}")) 