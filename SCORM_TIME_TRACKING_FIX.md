# SCORM Time Tracking Fix

## Problem

SCORM topic time values were not showing accurately in reports:
- `/reports/courses/34/users/` - Course users report showing incorrect time column values
- `/reports/users/174/overview/` - User overview report showing incorrect time spent

The issue was that only the **current attempt's time** was being saved instead of the **cumulative time across all attempts**.

## Root Cause

In `/home/ec2-user/lms/scorm/views_enrollment.py` at line 137, the code was setting:

```python
topic_progress.total_time_spent = attempt.total_time_seconds  # ❌ Only current attempt
```

This meant:
- Each time a user relaunched a SCORM topic, the time would reset
- Multiple attempts were not being accumulated
- The `ScormEnrollment.total_time_seconds` field was never being updated

## Solution

### 1. Fixed SCORM Progress Update Endpoint

**File: `/home/ec2-user/lms/scorm/views_enrollment.py`**

Changed the update logic to:

```python
# Update enrollment's cumulative time from all attempts
from django.db.models import Sum
total_time_all_attempts = ScormAttempt.objects.filter(
    enrollment=enrollment
).aggregate(total=Sum('total_time_seconds'))['total'] or 0
enrollment.total_time_seconds = total_time_all_attempts
enrollment.save(update_fields=['total_time_seconds'])

# Use enrollment's cumulative time across all attempts
topic_progress.total_time_spent = enrollment.total_time_seconds  # ✅ Cumulative
```

### 2. Updated SCORM Launcher Template

**File: `/home/ec2-user/lms/scorm/templates/scorm/launcher.html`**

Changed from old endpoint to new enrollment-based endpoint:

```javascript
// Before
progressUpdateUrl: '{% url "courses:update_scorm_progress" topic.id %}',

// After
progressUpdateUrl: '{% url "scorm:update_progress" topic.id %}',  // ✅ New endpoint
```

### 3. Created Data Migration Script

**File: `/home/ec2-user/lms/scorm/management/commands/fix_scorm_time.py`**

A management command to fix existing data:

```bash
# Preview changes
python manage.py fix_scorm_time --dry-run

# Apply changes
python manage.py fix_scorm_time
```

This script:
- Recalculates cumulative time for all `ScormEnrollment` records
- Updates corresponding `TopicProgress` records
- Shows before/after values for verification

## How It Works

### SCORM Time Tracking Flow

1. **User launches SCORM content**
   - Creates/gets `ScormEnrollment` (one per user per topic)
   - Creates new `ScormAttempt` or resumes existing

2. **SCORM content sends progress updates**
   - Each update includes `cmi.core.total_time` (for SCORM 1.2) or `cmi.total_time` (for SCORM 2004)
   - Time is parsed and stored in `ScormAttempt.total_time_seconds`

3. **Time accumulation (NEW)**
   - Sum all `ScormAttempt.total_time_seconds` for the enrollment
   - Update `ScormEnrollment.total_time_seconds` with cumulative total
   - Sync to `TopicProgress.total_time_spent` for reporting

4. **Reports display time**
   - Course reports read from `TopicProgress.total_time_spent`
   - User reports aggregate `TopicProgress.total_time_spent` across topics

## Affected Reports

All reports that display SCORM time are now fixed:

### Course Reports
- **URL**: `/reports/courses/{course_id}/users/`
- **Column**: "Time" 
- **Source**: `learner.time_spent_formatted` → `enrollment.total_time_spent` → `TopicProgress.total_time_spent`

### User Reports
- **URL**: `/reports/users/{user_id}/overview/`
- **Section**: Course list showing time spent per course
- **Source**: `enrollment.formatted_time_spent` → Sum of `TopicProgress.total_time_spent` for course topics

- **URL**: `/reports/users/{user_id}/learning-activities/`
- **Column**: Time per topic
- **Source**: `progress.formatted_time` → `TopicProgress.total_time_spent`

## Testing

### 1. Test New SCORM Sessions

1. Enroll a test user in a SCORM course
2. Launch SCORM content and complete it (e.g., 5 minutes)
3. Check reports - should show 5 minutes
4. Launch SCORM again and spend 3 more minutes
5. Check reports - should show **8 minutes total** ✅

### 2. Verify Time Parsing

SCORM time formats are correctly parsed:

**SCORM 1.2 Format**: `HH:MM:SS.SS`
```
00:05:30 → 330 seconds → "0h 5m"
01:23:45 → 5025 seconds → "1h 23m"
```

**SCORM 2004 Format**: `PT#H#M#S` (ISO 8601 duration)
```
PT5M30S → 330 seconds → "0h 5m"
PT1H23M45S → 5025 seconds → "1h 23m"
```

### 3. Fix Existing Data

```bash
# Preview what will be fixed
python manage.py fix_scorm_time --dry-run

# Apply fixes
python manage.py fix_scorm_time

# Verify in reports
# Visit /reports/courses/{course_id}/users/
# Visit /reports/users/{user_id}/overview/
```

## Database Schema

### ScormEnrollment
- `total_time_seconds` (IntegerField) - Cumulative time across ALL attempts

### ScormAttempt
- `total_time` (CharField) - SCORM time format string (e.g., "00:15:30" or "PT15M30S")
- `total_time_seconds` (IntegerField) - Parsed seconds for THIS attempt

### TopicProgress
- `total_time_spent` (IntegerField) - Synced from ScormEnrollment, used by reports

## API Endpoints

### New Endpoint (Recommended)
```
POST /scorm/progress/<topic_id>/
```
- Handles enrollment and attempt tracking
- Accumulates time correctly across attempts
- Returns detailed attempt information

### Old Endpoint (Legacy)
```
POST /courses/api/update_scorm_progress/<topic_id>/
```
- Still works for backward compatibility
- Does NOT accumulate time across attempts
- Should be migrated to new endpoint

## Migration Path

1. **Immediate**: New SCORM launches use the new endpoint ✅
2. **Run migration**: `python manage.py fix_scorm_time` ✅
3. **Verify**: Check reports show accurate cumulative time ✅
4. **Monitor**: Watch logs for any SCORM progress update errors

## Notes

- Time accumulation happens on **every SCORM commit** (LMSCommit call)
- Uses idempotent sequence numbers to prevent duplicate updates
- Backward compatible - existing TopicProgress records still work
- The fix is automatic for all new SCORM sessions after deployment

## Files Changed

1. `/home/ec2-user/lms/scorm/views_enrollment.py` - Fixed time accumulation logic
2. `/home/ec2-user/lms/scorm/templates/scorm/launcher.html` - Switched to new endpoint
3. `/home/ec2-user/lms/scorm/management/commands/fix_scorm_time.py` - Data migration script

## References

- SCORM 1.2 Runtime Specification: https://scorm.com/scorm-explained/technical-scorm/run-time/
- SCORM 2004 4th Edition: https://adlnet.gov/projects/scorm/
- ISO 8601 Duration Format: https://en.wikipedia.org/wiki/ISO_8601#Durations

