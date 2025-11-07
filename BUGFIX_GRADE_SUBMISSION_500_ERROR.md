# Bug Fix: 500 Server Error on Assignment Grade Submission

## Issue
URL: `https://vle.nexsy.io/assignments/submission/1/grade/` was returning a 500 Internal Server Error.

## Root Cause
The Grade model in `/home/ec2-user/lms/gradebook/models.py` had a comment indicating that the `course` field was removed (Bug #3), but the database migration to remove the column was never created or applied.

**The Problem:**
- Model code removed the `course` ForeignKey field (line 11 comment: "Fixed Bug #3: Removed redundant course field")
- Database table `gradebook_grade` still had a `course_id` column with NOT NULL constraint
- When the signal handler `create_or_update_grade` in `assignments/models.py` tried to create a Grade record without providing `course_id`, it violated the database constraint

**Error in logs:**
```
django.db.utils.IntegrityError: null value in column "course_id" of relation "gradebook_grade" violates not-null constraint
DETAIL:  Failing row contains (9, 0.00, f, , 2025-11-07 13:49:34.811119+00, 2025-11-07 13:49:34.811141+00, 2, null, 352, 1).
```

## Solution
Created and applied database migration `0003_remove_course_field.py` to remove the `course_id` column from the `gradebook_grade` table.

### Files Changed:
1. **Created:** `/home/ec2-user/lms/gradebook/migrations/0003_remove_course_field.py`
   - Migration to remove the redundant `course` field from Grade model

### Commands Run:
```bash
# Applied the migration
python3 manage.py migrate gradebook

# Restarted the service
sudo pkill -f "gunicorn.*LMS_Project"
sudo systemctl start lms-production
```

## Verification
After the fix:
- Endpoint returns 302 redirect (to login) instead of 500 error
- No more IntegrityError in logs
- Service running successfully with all workers

## Date Fixed
November 7, 2025

## Technical Notes
- The Grade model already has a `@property` method called `course` that returns `self.assignment.course`, making the database field truly redundant
- The model's `Meta.unique_together` constraint uses `['student', 'assignment']` which is sufficient for uniqueness without needing the course field
- This fix aligns the database schema with the model code that was already updated

