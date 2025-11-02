# Survey 500 Error - Diagnosis & Fix

## Issue
500 Server Error occurring at: `https://staging.nexsy.io/course-reviews/course/34/survey/`

## Changes Made

### 1. Enhanced Error Handling in `course_reviews/views.py`
- Added comprehensive try-except blocks to catch and log runtime errors
- Added detailed logging for each step of the survey submission process
- Added validation checks for survey fields existence
- Improved error messages for better user experience

### 2. Created Diagnostic Tool
- **New file:** `course_reviews/management/commands/diagnose_survey.py`
- Command to diagnose survey configuration issues

## How to Diagnose the Issue on Staging

### Step 1: Check Server Logs
```bash
# SSH into staging server
ssh user@staging.nexsy.io

# Check Django/application logs
tail -f /var/log/django/error.log
# OR
tail -f /var/log/nginx/error.log
# OR check your specific log location
```

### Step 2: Run the Diagnostic Command
```bash
cd /path/to/lms
source venv/bin/activate  # if using virtual environment

# Diagnose course 34
python manage.py diagnose_survey 34

# Optional: Check for a specific user
python manage.py diagnose_survey 34 --user-id 123
```

### Step 3: Check Database
```bash
# Connect to the database
python manage.py dbshell

# Check if course 34 exists
SELECT id, title FROM courses_course WHERE id = 34;

# Check if course has a survey assigned
SELECT c.id, c.title, s.id as survey_id, s.title as survey_title 
FROM courses_course c 
LEFT JOIN course_reviews_survey s ON c.survey_id = s.id 
WHERE c.id = 34;

# Check survey fields
SELECT sf.id, sf.label, sf.field_type, sf.is_required 
FROM course_reviews_surveyfield sf 
JOIN course_reviews_survey s ON sf.survey_id = s.id 
JOIN courses_course c ON c.survey_id = s.id 
WHERE c.id = 34;
```

## Common Causes & Solutions

### Cause 1: Course Does Not Exist
**Symptom:** Course ID 34 not found in database
**Solution:** Verify the course ID or create the course

### Cause 2: No Survey Assigned
**Symptom:** Course exists but has no survey assigned
**Solution:** 
1. Go to Django Admin: `/admin/courses/course/34/change/`
2. Assign a survey to the "Survey" field
3. Save the course

### Cause 3: Survey Has No Fields
**Symptom:** Survey exists but has no questions/fields
**Solution:**
1. Go to: `/course-reviews/surveys/<survey_id>/edit/`
2. Add fields/questions to the survey
3. Ensure at least one field is added

### Cause 4: User Not Enrolled or Not Completed
**Symptom:** User accessing the survey page but gets redirected
**Solution:**
- User must be enrolled in the course
- User must have completed the course
- Check enrollment status in the database or admin panel

### Cause 5: Database Migration Issues
**Symptom:** Missing tables or columns
**Solution:**
```bash
python manage.py makemigrations
python manage.py migrate
python manage.py migrate course_reviews
```

### Cause 6: Permission/Capability Issues
**Symptom:** User lacks required permissions
**Solution:**
- The `submit_course_survey` view only requires `@login_required`
- Ensure user is authenticated
- Check user's role and capabilities

## Testing the Fix

### On Staging Server:
1. Deploy the updated code
2. Restart the application server:
   ```bash
   sudo systemctl restart gunicorn  # or your WSGI server
   # OR
   sudo systemctl restart uwsgi
   ```

3. Test the URL:
   ```bash
   curl -I https://staging.nexsy.io/course-reviews/course/34/survey/
   ```

4. Check the logs for new error messages with detailed context

### Expected Behavior:
- **If not logged in:** Redirect to login page (302)
- **If logged in but not enrolled:** Error message + redirect to home
- **If enrolled but not completed:** Error message + redirect to course details
- **If no survey:** Error message + redirect to course details
- **If survey has no fields:** Error message + redirect to course details
- **If all valid:** Display the survey form (200)

## Code Changes Summary

### Enhanced Validation Checks:
1. ✅ Course existence check with proper 404 handling
2. ✅ Enrollment verification
3. ✅ Course completion check
4. ✅ Survey assignment check
5. ✅ Survey fields existence check
6. ✅ Comprehensive exception handling with logging

### Logging Added:
- User access logging
- Course/survey validation logging
- Error logging with stack traces
- All logs include user and course context

## Monitoring

After deployment, monitor:
1. Application logs for new error entries
2. 500 error rate in application monitoring tools
3. User feedback/reports

## Additional Resources

- Course Reviews Documentation: `/docs/course-reviews/`
- Survey Management Guide: `/docs/surveys/`
- Django Admin Panel: `https://staging.nexsy.io/admin/`

## Next Steps

1. Deploy the changes to staging
2. Run the diagnostic command
3. Review logs for specific error details
4. Fix the root cause based on diagnostic output
5. Test the survey submission flow
6. Deploy to production once verified

---

**Date:** 2025-11-02  
**Fixed by:** AI Assistant  
**Files Modified:**
- `course_reviews/views.py` (enhanced error handling)
- `course_reviews/management/commands/diagnose_survey.py` (new diagnostic tool)

