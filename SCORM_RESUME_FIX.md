# SCORM Resume Issue - Fix Documentation

## Issue Summary
SCORM 1.2 Rise packages were not resuming properly. Users were being forced to start from the beginning each time they launched the course, despite progress being saved.

## Root Cause Analysis

### Problem Identified
The `scorm_launcher` view in `/home/ec2-user/lms/scorm/views.py` was **NOT loading resume data from the ScormAttempt model**. Instead, it was only loading from the `TopicProgress` model, which is a backwards-compatibility layer.

### Database Investigation Results
Testing with topic ID 279 revealed:
- **ScormAttempt** data was being saved correctly:
  - `suspend_data`: 1478 characters ✓
  - `lesson_location`: "" (empty - Rise packages may not use this field)
  - `completion_status`: "incomplete" ✓
  - `entry_mode`: "ab-initio" (should be "resume")

- **TopicProgress** bookmark data:
  - Had `suspend_data` in bookmark ✓
  - Missing `lesson_location` (not synced because it was empty)

### The Bug
When a user relaunched a SCORM course:
1. Launcher would check `TopicProgress.bookmark` for resume data
2. TopicProgress is only updated AFTER commits from the SCO
3. The launcher never checked for the most recent **incomplete ScormAttempt**
4. Result: Resume data existed but was not being loaded into the SCORM API
5. API would initialize with `entry: 'ab-initio'` instead of `entry: 'resume'`
6. Rise content would start from the beginning

## Changes Made

### 1. Updated `/home/ec2-user/lms/scorm/views.py`
**Location**: `scorm_launcher` function (lines 53-124)

**Changes**:
- Added logic to check for existing `ScormEnrollment`
- Retrieve the most recent incomplete `ScormAttempt` using `enrollment.get_current_attempt()`
- **Priority order for resume data**:
  1. **PRIMARY**: Load from `ScormAttempt` (if exists)
  2. **FALLBACK**: Load from `TopicProgress` (backwards compatibility)
- Pass `lesson_location`, `suspend_data`, and `entry` mode from the attempt to the SCORM API
- Added comprehensive logging for debugging

**Key Code Addition**:
```python
# Check for existing ScormAttempt for proper resume support
enrollment = ScormEnrollment.objects.filter(
    user=request.user,
    topic=topic
).first()

if enrollment:
    existing_attempt = enrollment.get_current_attempt()
    
if existing_attempt:
    # Load from most recent incomplete attempt (PRIMARY SOURCE)
    entry_mode = 'resume' if (existing_attempt.lesson_location or existing_attempt.suspend_data) else 'ab-initio'
    progress_data = {
        'entry': entry_mode,
        'lessonLocation': existing_attempt.lesson_location or '',
        'suspendData': existing_attempt.suspend_data or '',
        'lessonStatus': existing_attempt.completion_status or 'incomplete',
        'scoreRaw': float(existing_attempt.score_raw) if existing_attempt.score_raw else '',
        'scoreMax': float(existing_attempt.score_max) if existing_attempt.score_max else '',
        'totalTime': existing_attempt.total_time or '00:00:00',
    }
```

### 2. Updated `/home/ec2-user/lms/scorm/models_tracking.py`
**Location**: `ScormEnrollment.create_new_attempt()` method (lines 90-107)

**Changes**:
- Added `session_id` parameter to `create_new_attempt()` method
- Automatically generates UUID if session_id not provided
- Ensures session tracking works correctly

**Key Code Change**:
```python
def create_new_attempt(self, session_id=None):
    """Create a new attempt for this enrollment"""
    import uuid
    self.total_attempts += 1
    self.save()
    
    # Generate session_id if not provided
    if session_id is None:
        session_id = uuid.uuid4()
    
    return ScormAttempt.objects.create(
        enrollment=self,
        user=self.user,
        topic=self.topic,
        package=self.package,
        attempt_number=self.total_attempts,
        session_id=session_id
    )
```

## How It Works Now

### Resume Flow
1. User launches SCORM course via `/scorm/launch/279/`
2. Launcher checks for existing `ScormEnrollment` for this user+topic
3. If enrollment exists, retrieves the most recent **incomplete** `ScormAttempt`
4. Loads `suspend_data` and `lesson_location` from that attempt
5. Sets `entry` mode to `'resume'` (if suspend data or location exists)
6. Passes this data to the SCORM API wrapper
7. API initializes with resume data
8. Rise content uses `suspend_data` to restore user's position
9. User continues from where they left off ✓

### Data Flow
```
User Launch → scorm_launcher view
              ↓
         Check ScormEnrollment
              ↓
         Get incomplete ScormAttempt
              ↓
         Load: suspend_data, lesson_location, entry='resume'
              ↓
         Pass to SCORM API (scorm-api.js)
              ↓
         API initializes with resume data
              ↓
         LMSInitialize() called by Rise
              ↓
         LMSGetValue('cmi.suspend_data') returns saved data
              ↓
         Rise restores user position
              ↓
         User resumes from last position ✓
```

## Testing Verification

### Pre-Fix Behavior
- Entry mode: `'ab-initio'`
- Suspend data: Not loaded
- User experience: Always starts from beginning

### Post-Fix Behavior (Verified)
- Entry mode: `'resume'` ✓
- Suspend data: Loaded (1478 characters) ✓
- Lesson location: "" (empty - Rise uses suspend_data)
- User experience: Resumes from last position ✓

## Notes on Rise SCORM Packages

### Important Observations
1. **Rise uses SCORM 2004 CMI elements**:
   - `cmi.suspend_data` (not `cmi.core.suspend_data`)
   - `cmi.location` (not `cmi.core.lesson_location`)
   - `cmi.entry`, `cmi.completion_status`, etc.

2. **Rise may not use `cmi.location`**:
   - In testing, `cmi.location` was always empty (`""`)
   - Rise stores ALL resume data in `cmi.suspend_data`
   - This is valid per SCORM 2004 spec

3. **Resume detection**:
   - Should check for `suspend_data` OR `lesson_location`
   - If either exists, set `entry` to `'resume'`

## Impact

### What Was Fixed
✓ SCORM resume functionality now works correctly
✓ Rise packages properly resume where user left off
✓ Suspend data is loaded from the most recent incomplete attempt
✓ Entry mode correctly set to 'resume'

### Backwards Compatibility
✓ Fallback to TopicProgress for older content without ScormEnrollment
✓ Existing SCORM packages continue to work
✓ No database migrations required

## Files Modified
1. `/home/ec2-user/lms/scorm/views.py` - Added ScormAttempt resume logic
2. `/home/ec2-user/lms/scorm/models_tracking.py` - Added session_id parameter

## Deployment Notes
- No database changes required
- No restart required (Python code changes are picked up automatically)
- Test with topic ID 279 or any Rise SCORM 1.2 package
- Monitor logs for "Loading resume data from ScormAttempt" messages

## Related Components (No Changes Needed)
- `/home/ec2-user/lms/scorm/static/scorm/js/scorm-api.js` - Already handles resume data correctly
- `/home/ec2-user/lms/scorm/views_enrollment.py` - Already saves CMI data correctly
- `/home/ec2-user/lms/scorm/models.py` - ScormAttempt.update_from_cmi_data() already extracts data correctly
- `/home/ec2-user/lms/scorm/templates/scorm/launcher.html` - Already has Rise-specific fixes

## Future Enhancements (Optional)
1. Add unit tests for resume functionality
2. Add admin interface to view ScormAttempt data
3. Add debug mode to show what resume data is being loaded
4. Consider caching ScormAttempt data for performance

## Date
October 31, 2025

## Issue Reference
- URL: https://staging.nexsy.io/scorm/launch/279/
- Topic ID: 279
- Package: Rise SCORM 1.2

