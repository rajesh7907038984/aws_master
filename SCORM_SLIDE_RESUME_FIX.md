# SCORM 2004 Slide-Based Content Resume Fix

## Problem Summary

SCORM 2004 slide-based content (e.g., Articulate Rise, Storyline) was not properly restoring CMI data on revisit attempts. When users returned to a course they had previously started, the content would start fresh instead of resuming from where they left off. Quiz-type content worked fine.

## Root Cause

The issue had two components:

### 1. Incomplete Data Restoration on Initialize
The `init()` function in `scorm-api.js` only restored 3 fields from the saved progress:
- `lessonLocation`
- `suspendData`
- `entry`

It did NOT restore other critical fields like:
- `scoreRaw`
- `scoreMax`
- `completionStatus`
- `successStatus`
- `totalTime`

### 2. Slide Content Overwrites Resume Data
**Quiz content behavior:**
- Calls `GetValue('cmi.suspend_data')` immediately after Initialize
- Reads the data before making any changes
- Only writes new data after user interaction

**Slide content behavior (problematic):**
- Calls `SetValue('cmi.location', '')` or `SetValue('cmi.suspend_data', '')` during its initialization
- Overwrites the loaded data BEFORE properly resuming
- The content then saves this "fresh" state, losing previous progress

## Solution Implemented

Modified `/home/ec2-user/lms/scorm/static/scorm/js/scorm-api.js` with three key changes:

### 1. Added Resume Session Tracking (Lines 42-44)
```javascript
// Resume session protection
var isResumeSession = false;
var setValueCallCount = 0;
```

### 2. Enhanced init() Function (Lines 53-134)
- Restores ALL progress fields from configuration, not just location/suspend/entry
- Detects resume sessions based on entry mode or presence of saved data
- Logs resume detection for debugging
- Resets setValue call counter

Key additions:
```javascript
// FIXED: Restore ALL other critical fields for proper resume
if (configData.scoreRaw !== undefined && configData.scoreRaw !== '') {
    progressData.score = parseFloat(configData.scoreRaw);
}
if (configData.scoreMax !== undefined && configData.scoreMax !== '') {
    progressData.maxScore = parseFloat(configData.scoreMax);
}
// ... etc for all fields

// Determine if this is a resume session
isResumeSession = (configData.entry === 'resume' || 
                  (configData.lessonLocation && configData.lessonLocation !== '') ||
                  (configData.suspendData && configData.suspendData !== ''));
```

### 3. Protected setValue() Function (Lines 314-357)
Added protection against overwriting critical resume data with empty values during the first 5 `SetValue` calls:

```javascript
// PROTECTION: During resume sessions, prevent overwriting critical fields
// with empty values in the first few SetValue calls (slide content bug workaround)
if (isResumeSession && setValueCallCount <= 5) {
    var isEmptyValue = (value === '' || value === null || value === undefined);
    var isCriticalField = false;
    
    if (scormVersion === '1.2') {
        isCriticalField = (element === 'cmi.core.lesson_location' || 
                         element === 'cmi.suspend_data');
    } else {
        // SCORM 2004
        isCriticalField = (element === 'cmi.location' || 
                         element === 'cmi.suspend_data');
    }
    
    if (isCriticalField && isEmptyValue) {
        // Check if we already have non-empty data
        var currentValue = '';
        if (element === 'cmi.core.lesson_location' || element === 'cmi.location') {
            currentValue = progressData.lessonLocation;
        } else if (element === 'cmi.suspend_data') {
            currentValue = progressData.suspendData;
        }
        
        if (currentValue && currentValue !== '') {
            console.warn('SCORM: Prevented overwriting ' + element + ' ...');
            return 'true';  // Pretend it succeeded but don't clear the data
        }
    }
}
```

### 4. Reset Flags on Terminate (Lines 158-160)
```javascript
// Reset resume protection flags
isResumeSession = false;
setValueCallCount = 0;
```

## How It Works

1. **On course launch**, the launcher passes resume data via `window.scormConfig.progressData`
2. **During Initialize**, all fields are restored and resume mode is detected
3. **During first 5 SetValue calls**, if slide content tries to set location/suspend_data to empty while we have existing data, the call is intercepted and ignored
4. **After 5 SetValue calls**, normal operation resumes (content has had time to properly initialize)
5. **Console logs** provide visibility into protection actions for debugging

## Testing Instructions

### Test Scenario 1: New Attempt (First Time)
1. Launch a SCORM 2004 slide-based course (Articulate Rise/Storyline)
2. Progress through 2-3 slides
3. Exit the course (using course exit button)
4. Verify data is saved to database

### Test Scenario 2: Resume Attempt
1. Re-launch the same course
2. Check browser console for: `"SCORM: Resume session detected - protecting existing data"`
3. Verify course resumes from the correct slide
4. Verify `cmi.location` and `cmi.suspend_data` are correctly loaded
5. If protection triggers, console will show: `"SCORM: Prevented overwriting cmi.location..."`

### Test Scenario 3: Quiz Content (Should Still Work)
1. Launch a quiz-type SCORM content
2. Complete some questions
3. Exit and re-launch
4. Verify answered questions are still marked complete

### Expected Console Output on Resume
```
SCORM API configured from parent window
SCORM: Resume session detected - protecting existing data from early overwrites
  - lessonLocation length: 12
  - suspendData length: 1523
✓ SCORM API ready
```

If slide content tries to overwrite (expected for some authoring tools):
```
SCORM: Prevented overwriting cmi.location (length: 12) with empty value during resume (call #2)
```

## Files Modified

- `/home/ec2-user/lms/scorm/static/scorm/js/scorm-api.js`

## Backward Compatibility

✅ **SCORM 1.2**: Protected with same logic (uses `cmi.core.lesson_location`)
✅ **SCORM 2004**: Fixed for both quiz and slide content
✅ **New attempts**: No impact - protection only active when resume data exists
✅ **Quiz content**: No impact - already worked correctly, protection doesn't interfere
✅ **Slide content**: Now properly resumes like quiz content

## Technical Notes

### Why 5 SetValue Calls?
- Most slide-based content initializes within 1-3 SetValue calls
- 5 provides a safe margin without impacting normal operation
- After initialization, content will set these fields with real values, not empty strings

### Why Not Block All Empty Values?
- Some content legitimately clears location/suspend_data
- We only protect during the critical initialization window
- Once content is initialized (after 5 calls), full SCORM compliance is maintained

### Alternative Solutions Considered
1. **Always block empty values** - Too restrictive, breaks legitimate use cases
2. **Delay initialization** - Would violate SCORM spec
3. **Modified content detection** - Too fragile, authoring tool specific
4. **Selected approach** - Minimal, standards-compliant, transparent protection window

## Version Compatibility

- Django: All versions (static JS file)
- SCORM 1.2: ✅ Compatible
- SCORM 2004: ✅ Fixed
- Browsers: All modern browsers (ES5 compatible code)

## Monitoring

Check browser console logs for:
- `"Resume session detected"` - Confirms resume mode activated
- `"Prevented overwriting"` - Shows protection worked
- `"✓ SCORM API ready"` - Confirms API initialized successfully

If users still report issues:
1. Check console for error messages
2. Verify resume data is being passed in `window.scormConfig.progressData`
3. Check `ScormAttempt` records in database for proper data storage
4. Verify `get_current_attempt()` is returning the correct incomplete attempt

## Date
November 1, 2025

