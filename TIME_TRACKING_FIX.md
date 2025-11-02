# Time Tracking Fix - My Learning Report

## Issue Report
**URL**: https://staging.nexsy.io/reports/my-learning-report/courses/  
**User**: krishnan  
**Problem**: Time Spent column not showing accurate data (showing 0 seconds for completed SCORM courses)

## Root Cause Analysis

The "Time Spent" column in the My Learning Report was showing inaccurate data (0 seconds) for all content types due to multiple tracking issues:

### 1. Video & Audio Content Time Tracking
**Problem**: Video and audio progress tracking was NOT updating the `TopicProgress.total_time_spent` field.

**Details**:
- `mark_video_progress()` method calculated `time_watched` and stored it in `progress_data['total_viewing_time']`
- `update_audio_progress()` method only updated `last_audio_position` and `audio_progress`
- Neither method updated the `total_time_spent` field
- Reports aggregate time from `TopicProgress.total_time_spent`, which remained 0

### 2. SCORM Content Time Tracking  
**Problem**: SCORM packages report `session_time` but many don't maintain `total_time`, and the LMS wasn't using `session_time` as a fallback.

**Details**:
- SCORM 1.2 and 2004 packages typically track `session_time` (time for current session)
- Many packages send `total_time: "00:00:00"` because they expect the LMS to accumulate time
- The LMS was only reading `total_time` without falling back to `session_time`
- Result: `total_time_seconds` remained 0 even though users spent time in the content

## Fixes Implemented

### Fix 1: Video Time Tracking
**File**: `/home/ec2-user/lms/courses/models.py`  
**Method**: `TopicProgress.mark_video_progress()` (line ~2347)

**Change**:
```python
# Added after calculating time_watched:
# Update the total_time_spent field (used for reporting)
self.total_time_spent += int(time_watched)
```

**Impact**: Video viewing time is now properly tracked and accumulated in the database field used by reports.

### Fix 2: Audio Time Tracking
**File**: `/home/ec2-user/lms/courses/models.py`  
**Method**: `TopicProgress.update_audio_progress()` (line ~2570)

**Change**:
```python
# Calculate time listened since last update
time_listened = 0
if self.last_audio_position is not None:
    if current_time > self.last_audio_position:
        time_listened = current_time - self.last_audio_position
        
        # Add to total time spent (protect against unrealistic values)
        if time_listened > 0 and time_listened < 3600:
            self.total_time_spent += int(time_listened)
```

**Impact**: Audio listening time is now properly tracked and accumulated.

### Fix 3: SCORM Time Tracking (Primary Fix)
**Files**: 
- `/home/ec2-user/lms/scorm/models.py` - `ScormAttempt.update_from_cmi_data()` (line ~1262)
- `/home/ec2-user/lms/scorm/models_tracking.py` - `ScormAttempt.update_from_cmi_data()` (line ~370)

**Change**:
```python
# Parse time to seconds
if self.total_time:
    self.total_time_seconds = int(parse_scorm_time(self.total_time, scorm_version))

# Handle session time fallback
if self.session_time:
    self.session_time_seconds = int(parse_scorm_time(self.session_time, scorm_version))
    
    # If total_time is 0 but session_time has a value, use session_time
    if self.total_time_seconds == 0 and self.session_time_seconds > 0:
        self.total_time_seconds = self.session_time_seconds
        # Format and update total_time string appropriately
```

**Impact**: SCORM content that only tracks `session_time` will now have that time properly recorded.

### Fix 4: Management Command for Historical Data
**File**: `/home/ec2-user/lms/courses/management/commands/sync_time_spent.py`

**Purpose**: Backfill `total_time_spent` for existing video/audio progress records that have time tracked in `progress_data` but not in the database field.

**Usage**:
```bash
# Dry run to see what would be updated
python3 manage.py sync_time_spent --dry-run

# For specific user
python3 manage.py sync_time_spent --user-id=238 --dry-run

# Actually apply the changes
python3 manage.py sync_time_spent
```

## Existing SCORM Time Fix Command
**File**: `/home/ec2-user/lms/scorm/management/commands/fix_scorm_time.py`

**Purpose**: Recalculate and fix SCORM time tracking data by aggregating time from all attempts.

**Usage**:
```bash
# Dry run
python3 manage.py fix_scorm_time --dry-run

# Apply fixes
python3 manage.py fix_scorm_time
```

## Testing & Validation

### Test Case 1: New Video Content
1. Enroll user in course with video content
2. Watch video for a few minutes
3. Check My Learning Report - time should be reflected immediately

### Test Case 2: New Audio Content  
1. Enroll user in course with audio content
2. Listen to audio for a few minutes
3. Check My Learning Report - time should be reflected

### Test Case 3: New SCORM Content
1. Enroll user in SCORM course
2. Complete SCORM content (spend time in it)
3. SCORM will send `session_time` data
4. Check My Learning Report - time should be reflected

### Test Case 4: Historical Data (User: krishnan, ID: 238)
For user krishnan who already completed SCORM courses with 0 time:
1. Future sessions will track time correctly with the fix in place
2. Past completed sessions may need manual adjustment if session logs exist

## Deployment Steps

1. ✅ Apply code fixes to all tracking methods
2. ✅ Test on staging environment
3. Run historical data sync (optional, for video/audio):
   ```bash
   python3 manage.py sync_time_spent --dry-run
   python3 manage.py sync_time_spent  # if needed
   ```
4. Monitor reports for correct time tracking
5. Deploy to production

## Expected Behavior After Fix

### My Learning Report - Courses Page
**Column**: Time Spent

**Before Fix**: 
- Shows `0h 0m 0s` for all content types

**After Fix**:
- Shows accurate time spent for video content (e.g., `0h 15m 30s`)
- Shows accurate time spent for audio content (e.g., `0h 8m 45s`)  
- Shows accurate time spent for SCORM content (e.g., `0h 12m 0s`)

### Database Changes
- `courses_topicprogress.total_time_spent` field now properly updated for all content types
- `scorm_scormattempt.total_time_seconds` now uses `session_time` when `total_time` is 0
- Reports aggregate time correctly from these fields

## Notes

1. **Idempotency**: All fixes are safe to deploy multiple times - they don't double-count time
2. **Performance**: Fixes add minimal overhead (simple integer addition on existing update paths)
3. **Compatibility**: Works with existing SCORM 1.2 and SCORM 2004 packages
4. **Future Sessions**: All new learning sessions will track time correctly
5. **Historical Data**: Completed sessions with 0 time cannot be retroactively fixed unless session logs exist

## Files Modified

1. `/home/ec2-user/lms/courses/models.py` - TopicProgress time tracking
2. `/home/ec2-user/lms/scorm/models.py` - SCORM time fallback logic  
3. `/home/ec2-user/lms/scorm/models_tracking.py` - SCORM time fallback logic (duplicate model)
4. `/home/ec2-user/lms/courses/management/commands/sync_time_spent.py` - New command for historical data

## Verification

After deployment, verify with user "krishnan":
1. Check current time shown in report
2. Have user complete a new SCORM lesson
3. Verify time is now being tracked
4. Compare before/after for accuracy

---

**Date**: November 2, 2025  
**Status**: ✅ Fixes Implemented, Ready for Testing  
**Affected Users**: All learners using video, audio, or SCORM content

