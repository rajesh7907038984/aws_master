#!/usr/bin/env python3
"""
Test Django email sending using the configured OAuth2 backend
This script uses Django's email system to test the actual email configuration
"""

import os
import sys
import django

# Setup Django environment
sys.path.insert(0, '/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.production')
django.setup()

from django.core.mail import send_mail, EmailMultiAlternatives
from django.conf import settings
import datetime

def send_test_email(recipient_email):
    """Send a test email via Django's email system"""
    
    print("=" * 70)
    print("📧 Testing Django Email System (OAuth2 Backend)")
    print("=" * 70)
    print()
    
    print(f"📋 Configuration:")
    print(f"   EMAIL_BACKEND: {settings.EMAIL_BACKEND}")
    print(f"   DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")
    print(f"   OUTLOOK_FROM_EMAIL: {getattr(settings, 'OUTLOOK_FROM_EMAIL', 'Not set')}")
    print()
    
    # Prepare email
    subject = "Test Email from Nexsy LMS - OAuth2 Configuration ✅"
    from_email = settings.DEFAULT_FROM_EMAIL
    
    # Text version
    text_content = """
Hello!

This is a test email from your Nexsy LMS system.

✅ SUCCESS! Your OAuth2 email configuration is working correctly.

Configuration Details:
- From Email: {from_email}
- Authentication: Microsoft 365 OAuth2
- Date: {date}
- Backend: {backend}

Your email system is now properly configured and ready to send notifications to users.

---
Nexsy Learning Management System
https://vle.nexsy.io
    """.format(
        from_email=from_email,
        date=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC'),
        backend=settings.EMAIL_BACKEND
    ).strip()
    
    # HTML version
    html_content = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px 10px 0 0;
            text-align: center;
        }}
        .content {{
            background: #f9f9f9;
            padding: 30px;
            border: 1px solid #e0e0e0;
        }}
        .success-icon {{
            font-size: 48px;
            text-align: center;
            margin: 20px 0;
        }}
        .details {{
            background: white;
            padding: 20px;
            border-radius: 5px;
            margin: 20px 0;
            border-left: 4px solid #667eea;
        }}
        .details dt {{
            font-weight: bold;
            color: #667eea;
            margin-top: 10px;
        }}
        .details dd {{
            margin-left: 0;
            margin-bottom: 10px;
            color: #666;
        }}
        .footer {{
            background: #333;
            color: #999;
            padding: 20px;
            text-align: center;
            border-radius: 0 0 10px 10px;
            font-size: 12px;
        }}
        .footer a {{
            color: #667eea;
            text-decoration: none;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🎉 Email Configuration Success!</h1>
    </div>
    
    <div class="content">
        <div class="success-icon">✅</div>
        
        <h2 style="text-align: center; color: #667eea;">OAuth2 Email System is Working!</h2>
        
        <p>Hello,</p>
        
        <p>This is a test email from your <strong>Nexsy Learning Management System</strong>.</p>
        
        <p>If you're receiving this email, it means your Microsoft 365 OAuth2 email configuration is working correctly and the system is ready to send notifications to users.</p>
        
        <div class="details">
            <h3 style="margin-top: 0;">📋 Configuration Details</h3>
            <dl>
                <dt>From Email:</dt>
                <dd>{from_email}</dd>
                
                <dt>Authentication Method:</dt>
                <dd>Microsoft 365 OAuth2</dd>
                
                <dt>Email Backend:</dt>
                <dd>{backend}</dd>
                
                <dt>Test Date:</dt>
                <dd>{date}</dd>
            </dl>
        </div>
        
        <p><strong>What's Next?</strong></p>
        <ul>
            <li>All system notifications will now be sent via OAuth2</li>
            <li>Users will receive emails for course enrollments, assignments, and more</li>
            <li>No further configuration needed - the system is ready!</li>
        </ul>
    </div>
    
    <div class="footer">
        <p><strong>Nexsy Learning Management System</strong></p>
        <p><a href="https://vle.nexsy.io">https://vle.nexsy.io</a></p>
        <p>&copy; {year} Nexsy. All rights reserved.</p>
    </div>
</body>
</html>
    """.format(
        from_email=from_email,
        backend=settings.EMAIL_BACKEND,
        date=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC'),
        year=datetime.datetime.now().year
    ).strip()
    
    print(f"📨 Preparing to send email...")
    print(f"   From: {from_email}")
    print(f"   To: {recipient_email}")
    print(f"   Subject: {subject}")
    print()
    
    try:
        # Create email with both text and HTML versions
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=[recipient_email]
        )
        email.attach_alternative(html_content, "text/html")
        
        print("🚀 Sending email...")
        result = email.send(fail_silently=False)
        
        if result == 1:
            print()
            print("=" * 70)
            print("✅ SUCCESS! Email sent successfully!")
            print("=" * 70)
            print()
            print("📬 Please check the recipient inbox:")
            print(f"   {recipient_email}")
            print()
            print("📝 Next Steps:")
            print("   1. Verify the email was received")
            print("   2. Check spam/junk folder if not in inbox")
            print("   3. Your LMS is now ready to send emails!")
            print()
            return True
        else:
            print()
            print("⚠️  Email send returned unexpected result:", result)
            print("   Expected: 1, Got:", result)
            return False
            
    except Exception as e:
        print()
        print("=" * 70)
        print("❌ FAILED to send email")
        print("=" * 70)
        print()
        print(f"Error: {str(e)}")
        print()
        
        # Provide troubleshooting hints
        if "Mail.Send" in str(e) or "Insufficient privileges" in str(e):
            print("💡 Troubleshooting:")
            print("   The Azure AD application needs 'Mail.Send' permission:")
            print()
            print("   1. Go to Azure Portal (portal.azure.com)")
            print("   2. Navigate to: Azure Active Directory > App Registrations")
            print(f"   3. Find your app (Client ID: {getattr(settings, 'OUTLOOK_CLIENT_ID', 'N/A')})")
            print("   4. Go to 'API Permissions'")
            print("   5. Add 'Mail.Send' (Application permission)")
            print("   6. Grant Admin Consent")
            print()
            
        elif "MailboxNotFound" in str(e) or "MailboxNotEnabledForRESTAPI" in str(e):
            print("💡 Troubleshooting:")
            print(f"   The mailbox '{from_email}' may not exist or is not properly configured:")
            print()
            print("   1. Create the mailbox in Microsoft 365 Admin Center")
            print("   2. Assign an Exchange Online license")
            print("   3. Wait a few minutes for provisioning")
            print("   4. Try again")
            print()
            
        else:
            print("💡 Troubleshooting:")
            print("   - Check Azure AD application permissions")
            print("   - Verify the mailbox exists and is licensed")
            print("   - Ensure admin consent has been granted")
            print("   - Check application logs for more details")
            print()
        
        import traceback
        print("Full traceback:")
        traceback.print_exc()
        
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print()
        print("Usage: python3 test_django_email.py <recipient_email>")
        print()
        print("Example: python3 test_django_email.py admin@nexsy.io")
        print()
        sys.exit(1)
    
    recipient = sys.argv[1]
    
    try:
        success = send_test_email(recipient)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

