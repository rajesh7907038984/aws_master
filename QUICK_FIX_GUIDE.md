# Quick Fix Guide - Survey 500 Error

## Immediate Actions

### 1️⃣ Deploy the Updated Code
```bash
# On your staging server
cd /path/to/lms
git pull  # or your deployment method
sudo systemctl restart gunicorn  # restart your web server
```

### 2️⃣ Run Diagnostic Command
```bash
python manage.py diagnose_survey 34
```

This will tell you EXACTLY what's wrong!

## Most Likely Issues & Quick Fixes

### ❌ Course 34 has no survey assigned
```bash
# Fix in Django Admin:
# 1. Go to: https://staging.nexsy.io/admin/courses/course/34/change/
# 2. Select a survey from the "Survey" dropdown
# 3. Click "Save"
```

### ❌ Survey has no fields/questions
```bash
# Fix in LMS:
# 1. Go to: https://staging.nexsy.io/course-reviews/surveys/
# 2. Find the survey assigned to course 34
# 3. Click "Edit" and add fields/questions
# 4. Click "Save"
```

### ❌ User not enrolled or hasn't completed course
```text
This is expected behavior - users must:
1. Be enrolled in the course
2. Complete the course
3. Then they can submit a survey
```

## Check Logs
```bash
# The enhanced code now logs detailed information
tail -f /var/log/your-app/django.log | grep "submit_course_survey"
```

Look for lines like:
- `"User X accessing survey for course 34"`
- `"Course 34 not found"`
- `"Course 34 has no survey assigned"`
- `"Survey X for course 34 has no fields"`

## Test the Fix
```bash
# As an authenticated user, try accessing:
https://staging.nexsy.io/course-reviews/course/34/survey/

# You should now see:
# - A proper error message (if something is wrong)
# - OR the survey form (if everything is correct)
# 
# Instead of a generic 500 error page
```

## Need More Help?
Check the detailed guide: `SURVEY_500_ERROR_FIX.md`

