# Deployment Guide: Email Uniqueness Implementation

## ⚠️ IMPORTANT: Read Before Deploying

Your database currently has **10 email addresses** that are used by **21 users** (duplicates). You **MUST** fix these duplicates before applying the migration, or the migration will fail.

## Pre-Deployment Status

### Current Database Status
- **10 duplicate email addresses found**
- **21 total users affected**

### Duplicate Emails Found:
1. `jerin121@gmail.com` - 3 users (IDs: 255, 315, 316)
2. `admin@example.com` - 2 users (IDs: 292, 297)
3. `eudenesukwah7@yahoo.co.uk` - 2 users (IDs: 244, 346)
4. `hari2987@gmail.com` - 2 users (IDs: 232, 311)
5. `hari2987@yahoo.com` - 2 users (IDs: 256, 310)
6. `hari@nexsy.co.uk` - 2 users (IDs: 223, 309)
7. `hari@nexsy.io` - 2 users (IDs: 352, 353)
8. `hi@nexsy.io` - 2 users
9. (2 more duplicates...)

## Step-by-Step Deployment

### Step 1: Backup Database (CRITICAL!)
```bash
# Create a backup before making any changes
# (Use your preferred backup method)
```

### Step 2: Review Duplicate Details
Get detailed information about the duplicates:
```bash
cd /home/ec2-user/lms
python3 manage.py find_duplicate_emails --show-details
```

This will show:
- User ID
- Username
- Email
- Full name
- Role
- Branch
- Active status
- Date joined
- Last login

### Step 3: Export Duplicate Report (Optional but Recommended)
```bash
python3 manage.py find_duplicate_emails --export-csv duplicate_report.csv
```

This creates a CSV file you can review and share with your team.

### Step 4: Dry Run - See What Will Change
```bash
python3 manage.py fix_duplicate_emails --dry-run --auto-fix
```

This shows what emails will be changed without actually changing them.

### Step 5: Fix Duplicates
After reviewing the changes, apply the fixes:
```bash
python3 manage.py fix_duplicate_emails --auto-fix
```

**What this does:**
- Keeps the **oldest account** (by date_joined) with the original email
- Changes newer duplicate accounts to: `username+duplicate1@domain.com`
- Example: If user "john" has duplicate email `john@example.com`, the second account becomes `john+duplicate1@example.com`

### Step 6: Verify Duplicates Are Fixed
```bash
python3 manage.py find_duplicate_emails
```

Expected output: `✅ No duplicate email addresses found!`

### Step 7: Run Migration
Once all duplicates are fixed, apply the migration:
```bash
python3 manage.py migrate users
```

Expected output:
```
Running migrations:
  Applying users.0002_add_email_unique_constraint... OK
```

### Step 8: Test the System

#### Test 1: Registration with Existing Email
1. Go to registration page
2. Try to register with an existing email
3. Expected: Error message "This email address is already registered..."

#### Test 2: Registration with New Email
1. Go to registration page
2. Register with a new, unique email
3. Expected: Registration succeeds

#### Test 3: OAuth Registration
1. Try Google/Microsoft login with existing email
2. Expected: Logs into existing account
3. Try Google/Microsoft login with new email
4. Expected: Creates new account

#### Test 4: Admin User Creation
1. Login as admin
2. Try to create user with duplicate email
3. Expected: Error message

### Step 9: Notify Affected Users
Users whose emails were changed need to be notified. You can generate a list:

```bash
# Get the list of users with modified emails from Step 5 output
# Create a notification email template
# Send emails to affected users with their new email addresses
```

**Email Template Suggestion:**
```
Subject: Your LMS Account Email Address Has Been Updated

Dear [User Name],

We have updated our system to ensure each email address is unique across all accounts. 
As you had multiple accounts with the same email address, we have updated one of your 
account emails to maintain uniqueness.

Your account details:
- Username: [username]
- Previous Email: [old_email]
- New Email: [new_email]

You can continue to log in with your username and password.
If you prefer to use your original email address, please contact support.

Best regards,
LMS Admin Team
```

## What Changed in the System

### For Users:
- Can no longer create multiple accounts with the same email
- Clear error messages when attempting to use duplicate email
- OAuth login properly prevents duplicate accounts

### For Administrators:
- Cannot create users with duplicate emails
- Better data integrity
- New management commands to handle duplicates

## Rollback Plan

If something goes wrong:

### Option 1: Rollback Migration Only
```bash
python3 manage.py migrate users 0001_initial
```

### Option 2: Restore from Backup
```bash
# Restore your database backup from Step 1
```

## Common Issues and Solutions

### Issue 1: Migration Fails with "Cannot apply constraint"
**Solution:** You still have duplicate emails. Go back to Step 2 and fix them.

### Issue 2: User Can't Login After Email Change
**Solution:** Users should login with their username, not email. Verify the username hasn't changed.

### Issue 3: OAuth Login Creates Duplicate Instead of Logging In
**Solution:** Check if the email comparison is case-sensitive. The implementation normalizes to lowercase, so this shouldn't happen.

## Monitoring After Deployment

### Check Logs
```bash
tail -f /home/ec2-user/lmslogs/server.log
```

Look for:
- Email uniqueness validation errors
- OAuth login issues
- User registration problems

### Monitor User Registrations
Keep an eye on new user registrations for the first few days to ensure the validation is working correctly.

## Support Contacts

If you encounter issues during deployment:
1. Check the logs in `/home/ec2-user/lmslogs/`
2. Review the detailed documentation in `EMAIL_UNIQUENESS_IMPLEMENTATION.md`
3. Check for error messages in the Django admin logs
4. Contact the development team if issues persist

## Final Checklist

Before going live:
- [ ] Database backup created
- [ ] Duplicate emails identified and documented
- [ ] Dry run completed and reviewed
- [ ] Duplicates fixed successfully
- [ ] Migration applied successfully
- [ ] All tests passed
- [ ] Affected users notified
- [ ] System monitoring in place

## Timeline Estimate

- Step 1 (Backup): 5-15 minutes
- Step 2-3 (Review): 10-30 minutes
- Step 4 (Dry Run): 5 minutes
- Step 5 (Fix): 5 minutes
- Step 6 (Verify): 2 minutes
- Step 7 (Migration): 2 minutes
- Step 8 (Testing): 15-30 minutes
- Step 9 (Notifications): 30-60 minutes

**Total Estimated Time: 1.5 - 2.5 hours**

## Post-Deployment

After successful deployment:
1. Update your deployment documentation
2. Train support staff on the new behavior
3. Update user documentation/FAQ if needed
4. Monitor for any issues for 1-2 weeks

---

**Implementation Date:** November 8, 2025  
**Author:** AI Assistant  
**Version:** 1.0

