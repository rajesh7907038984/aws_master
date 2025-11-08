# Email Uniqueness Implementation

## Overview
This document describes the implementation of email uniqueness constraints in the LMS project to prevent users from creating multiple accounts with the same email address.

## What Changed

### 1. Model Changes (`users/models.py`)
- **Added email field override**: The `CustomUser` model now explicitly defines the email field with `unique=True`
- **Updated clean() method**: Simplified email validation to check for email uniqueness across all users, regardless of role or branch
- **Email normalization**: All emails are now automatically converted to lowercase for consistency

### 2. Form Changes (`users/forms.py`)
Updated the following forms to validate email uniqueness:
- `CustomUserCreationForm`: Main user creation form for admin/staff use
- `TabbedUserCreationForm`: Advanced user creation form with tabbed interface
- `SimpleRegistrationForm`: Public learner registration form

Each form now includes a `clean_email()` method that:
- Normalizes email to lowercase
- Checks for existing users with the same email (case-insensitive)
- Excludes the current user when editing
- Provides clear error messages

### 3. OAuth Integration Changes (`users/views.py`)
Updated OAuth callback functions to handle email uniqueness:
- `google_callback()`: Added try-except block around user creation
- `microsoft_callback()`: Added try-except block around user creation

Both functions now:
- Catch email uniqueness constraint violations
- Display user-friendly error messages
- Redirect to appropriate pages

### 4. Database Migration (`users/migrations/0002_add_email_unique_constraint.py`)
Created a migration that:
- Checks for existing duplicate emails before applying the constraint
- Provides clear error messages if duplicates are found
- Adds the unique constraint to the email field

### 5. Management Commands

#### New Command: `fix_duplicate_emails.py`
Helps administrators handle existing duplicate emails before migration.

**Usage:**
```bash
# List all duplicate emails
python3 manage.py find_duplicate_emails

# See what would be changed (dry run)
python3 manage.py fix_duplicate_emails --dry-run --auto-fix

# Automatically fix duplicates
python3 manage.py fix_duplicate_emails --auto-fix
```

**How it works:**
- Finds all duplicate emails in the database
- Keeps the oldest account with the original email
- Appends a counter to newer duplicate accounts (e.g., `username+duplicate1@domain.com`)

#### Existing Command: `find_duplicate_emails.py`
Lists all users with duplicate email addresses.

**Usage:**
```bash
# List duplicates
python3 manage.py find_duplicate_emails

# Show detailed information
python3 manage.py find_duplicate_emails --show-details

# Export to CSV
python3 manage.py find_duplicate_emails --export-csv duplicates.csv
```

## Deployment Steps

### Step 1: Check for Existing Duplicates
Before deploying, check if there are any duplicate emails:
```bash
python3 manage.py find_duplicate_emails
```

### Step 2: Fix Duplicates (if any)
If duplicates are found, fix them:
```bash
# Review what will be changed
python3 manage.py fix_duplicate_emails --dry-run --auto-fix

# Apply fixes
python3 manage.py fix_duplicate_emails --auto-fix
```

### Step 3: Run Migration
Apply the database migration:
```bash
python3 manage.py migrate users
```

If the migration fails due to duplicates, go back to Step 2.

### Step 4: Notify Affected Users
If you had to fix duplicate emails, notify the affected users of their new email addresses.

### Step 5: Test Registration
Test the registration process:
1. Try to register with an existing email → Should fail with clear error message
2. Try to register with a new email → Should succeed
3. Test OAuth registration with existing email → Should log in existing user
4. Test OAuth registration with new email → Should create new account

## Technical Details

### Email Normalization
All emails are automatically normalized to lowercase in:
- Model's `clean()` method
- Form's `clean_email()` method

This ensures case-insensitive uniqueness (e.g., `user@example.com` and `User@Example.com` are treated as the same).

### Database Constraint
The migration adds a unique constraint at the database level, providing an additional layer of protection beyond Django's application-level validation.

### Error Handling
The implementation handles errors at multiple levels:
1. **Form validation**: User-friendly error messages before submission
2. **Model validation**: Validation errors with clear instructions
3. **Database constraint**: Prevents race conditions with try-except blocks in OAuth flows

### Backward Compatibility
- The `clean()` method in `CustomUser` was updated to remove the old email+role+branch uniqueness logic
- Old validation logic that allowed same email with different roles/branches has been removed
- The new constraint is more strict: one email = one account

## User-Facing Changes

### Registration Forms
When a user tries to register with an existing email, they will see:
> "This email address is already registered. Each email can only be used for one account. Please use a different email or log in to your existing account."

### OAuth Login
When a user tries to create an account via OAuth with an existing email:
> "An account with email {email} already exists. Please log in instead."

### Admin Interface
When an admin tries to create/edit a user with a duplicate email:
> "A user with email address '{email}' already exists. Each email address can only be used for one account. Please use a different email address or contact support if you need help accessing your existing account."

## Testing Checklist

- [ ] Test standard registration with existing email
- [ ] Test standard registration with new email
- [ ] Test Google OAuth with existing email
- [ ] Test Google OAuth with new email
- [ ] Test Microsoft OAuth with existing email
- [ ] Test Microsoft OAuth with new email
- [ ] Test admin user creation with duplicate email
- [ ] Test user editing without changing email
- [ ] Test user editing to an existing email
- [ ] Verify migration runs successfully
- [ ] Verify duplicate detection works
- [ ] Verify duplicate fixing works

## Rollback Plan

If you need to rollback this change:

### Step 1: Revert Migration
```bash
python3 manage.py migrate users 0001_initial
```

### Step 2: Revert Code Changes
```bash
git revert <commit-hash>
```

### Step 3: Test System
Ensure all registration and authentication flows work correctly.

## Support

If you encounter issues:
1. Check the application logs for detailed error messages
2. Run `python3 manage.py find_duplicate_emails` to identify problematic emails
3. Use `python3 manage.py fix_duplicate_emails --auto-fix` to resolve duplicates
4. If issues persist, contact the development team

## Files Modified

1. `/home/ec2-user/lms/users/models.py`
   - Added email field override with unique=True
   - Updated clean() method

2. `/home/ec2-user/lms/users/forms.py`
   - Added clean_email() to CustomUserCreationForm
   - Added clean_email() to TabbedUserCreationForm
   - Added clean_email() to SimpleRegistrationForm

3. `/home/ec2-user/lms/users/views.py`
   - Updated google_callback() function
   - Updated microsoft_callback() function

4. `/home/ec2-user/lms/users/migrations/0002_add_email_unique_constraint.py`
   - New migration file

5. `/home/ec2-user/lms/users/management/commands/fix_duplicate_emails.py`
   - New management command

## Date Implemented
November 8, 2025

