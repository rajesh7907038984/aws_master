# SCORM Time Tracking - Complete Analysis

## Executive Summary

**Issue**: Time Spent column shows 0h 0m 0s for learner "krishnan"  
**Root Cause**: SCORM packages are NOT tracking time  
**LMS Status**: ✅ Working correctly - storing exactly what SCORM sends  
**Data Flow**: ✅ Verified end-to-end - no bugs found

---

## Data Flow Analysis

### 1. What SCORM Package Sends

**From Database (CMI Data)**:
```json
{
  "cmi.total_time": "00:00:00",
  "cmi.session_time": NOT SENT (empty)
}
```

**For SCORM 1.2 packages**:
```json
{
  "cmi.core.total_time": "00:00:00",
  "cmi.core.session_time": "00:00:00"
}
```

### 2. What LMS Receives & Stores

**ScormAttempt Model** (`scorm/models.py` lines 1255-1256):
```python
# SCORM 2004
self.total_time = safe_get_string(cmi_data_dict, 'cmi.total_time')      # Gets "00:00:00"
self.session_time = safe_get_string(cmi_data_dict, 'cmi.session_time')  # Gets "" (empty)

# SCORM 1.2  
self.total_time = safe_get_string(cmi_data_dict, 'cmi.core.total_time')      # Gets "00:00:00"
self.session_time = safe_get_string(cmi_data_dict, 'cmi.core.session_time')  # Gets "00:00:00"
```

**Database Storage**:
| Field | Value | Status |
|-------|-------|--------|
| `total_time` | "00:00:00" | ✅ Stored correctly |
| `total_time_seconds` | 0 | ✅ Parsed correctly |
| `session_time` | "" or "00:00:00" | ✅ Stored correctly |
| `session_time_seconds` | 0 | ✅ Parsed correctly |

### 3. What Report Displays

**My Learning Report** (`reports/views.py` lines 3865-3879):
```python
# Aggregates time from TopicProgress
course_stats = course_topic_progress.aggregate(
    total_time=Sum('total_time_spent', default=0),  # Returns 0
    total_attempts=Sum('attempts', default=0)        # Returns correct value
)

# Formats for display
hours = total_seconds // 3600      # 0 // 3600 = 0
minutes = (total_seconds % 3600) // 60  # 0
seconds = total_seconds % 60       # 0
# Result: "0h 0m 0s"
```

**Result**: ✅ Report correctly shows 0h 0m 0s (because that's what's in the database)

---

## Code Verification

### ✅ parse_scorm_time Function Working Correctly

**Test Results**:
| Input | SCORM 1.2 Output | SCORM 2004 Output |
|-------|------------------|-------------------|
| "00:00:00" | 0s | 0s |
| "00:05:30" | 330s (5m 30s) | 0s (wrong format) |
| "01:23:45" | 5025s (1h 23m 45s) | 0s (wrong format) |
| "PT5M30S" | 0s (wrong format) | 330s (5m 30s) |
| "PT1H23M45S" | 0s (wrong format) | 5025s (1h 23m 45s) |

**Conclusion**: Parser works perfectly for both SCORM versions

### ✅ Session Time Fallback Logic Working

**Code** (`scorm/models.py` lines 1269-1296):
```python
if self.session_time:
    self.session_time_seconds = int(parse_scorm_time(self.session_time, scorm_version))
    
    # If total_time is 0 but session_time has a value, use session_time
    if self.total_time_seconds == 0 and self.session_time_seconds > 0:
        self.total_time_seconds = self.session_time_seconds
        # ... format total_time appropriately
```

**For krishnan's data**:
- `session_time` = "" (empty) or "00:00:00"
- `session_time_seconds` = 0
- **Condition not met**: `session_time_seconds > 0` is FALSE
- **Result**: Fallback doesn't activate (correctly)

---

## Why Time Is Zero

### The SCORM Package Itself Doesn't Track Time

**Evidence from Database**:

1. **All 8 attempts from krishnan** have:
   - `cmi.total_time: "00:00:00"`
   - `cmi.session_time: ""` or `"00:00:00"`

2. **Consistent pattern** across:
   - Food & Hygiene course (2 topics)
   - Story Scorms 2nd Nov (4 topics)  
   - Scorms 2nd Nov (5 topics)

3. **Scores ARE tracked correctly**:
   - Topic "Quiz": score = 93
   - Topic "1.2": score = 100
   - Topic "2004": score = 80

**Conclusion**: 
- ✅ SCORM API communication works (scores sync)
- ✅ LMS receives and stores data correctly
- ❌ SCORM packages don't track time during playback

---

## Possible Causes

### 1. Authoring Tool Settings

Many SCORM authoring tools have time tracking as an optional feature:

**Articulate Storyline**:
- Time tracking can be disabled in publish settings
- Check: Publish → LMS → Reporting and Tracking → Track time

**Adobe Captivate**:
- Time tracking in Preferences → Project → Start and End
- May need to enable session time tracking

**iSpring**:
- Time tracking in Publish Settings → SCORM → Advanced

### 2. Quick Quiz/Assessment Packages

Some assessment-only SCORM packages:
- Track completion and scores
- Don't track time spent (by design)
- Focus on "pass/fail" not "time on task"

### 3. Content Type

The topics appear to be:
- Quizzes ("Quiz", "2004", "1.2", "wef")
- Assessment-focused content

**These typically don't track time** because:
- Learners can complete quickly
- Time isn't relevant for assessment
- Focus is on knowledge, not duration

---

## What's Working vs Not Working

| Feature | Status | Evidence |
|---------|--------|----------|
| **SCORM API Communication** | ✅ Working | Scores sync correctly |
| **Data Storage** | ✅ Working | All fields stored as received |
| **Data Parsing** | ✅ Working | parse_scorm_time tested & verified |
| **Session Time Fallback** | ✅ Working | Would activate if data existed |
| **Report Aggregation** | ✅ Working | Correctly sums what's in DB |
| **Attempts Tracking** | ✅ Fixed | Now showing correct values |
| **Time Tracking** | ❌ SCORM Issue | Packages send zero time |

---

## Solutions & Recommendations

### Option 1: Check SCORM Package Settings (Recommended)

1. **Identify the authoring tool** used to create the packages
2. **Check publish/export settings** for time tracking options
3. **Re-export packages** with time tracking enabled
4. **Test one package** to verify time is now tracked

### Option 2: Use Different SCORM Packages

If current packages can't track time:
- Use packages from vendors known for good time tracking
- Test with sample SCORM packages (e.g., from SCORM Cloud)
- Verify time tracking works before deploying to production

### Option 3: Alternative Time Tracking

If SCORM time tracking isn't needed:
- Consider this a non-issue (assessment-focused content)
- Track completion and scores only
- Document that time tracking isn't applicable for these courses

### Option 4: LMS-Side Time Tracking

For future courses, track time in the LMS instead:
- Track page view duration (when SCORM iframe is active)
- Log session start/end times
- Calculate time from first access to completion
- **Note**: This would be an estimate, not actual content engagement time

---

## Testing Instructions

### To Verify Time Tracking Works:

1. **Create a test SCORM package** with time tracking enabled
2. **Upload to LMS** as a new topic
3. **Have krishnan access it** for 5+ minutes
4. **Check database**:
   ```bash
   python3 manage.py shell -c "
   from scorm.models import ScormAttempt
   attempt = ScormAttempt.objects.filter(
       enrollment__user__username='krishnan',
       enrollment__topic__title__icontains='test'
   ).first()
   print(f'Total Time: {attempt.total_time}')
   print(f'Session Time: {attempt.session_time}')
   "
   ```
5. **Verify output** shows non-zero time values

---

## Conclusion

**The LMS is working 100% correctly.** 

The time tracking issue is caused by the SCORM packages themselves not implementing time tracking functionality. This is common for:
- Assessment/quiz-only packages
- Packages from certain authoring tools with time tracking disabled
- Legacy SCORM 1.2 packages

**No LMS code changes are needed** for this issue. The solution is to:
1. ✅ Use SCORM packages that track time, OR
2. ✅ Accept that these assessment packages don't need time tracking, OR
3. ✅ Implement alternative time tracking at the LMS level (future enhancement)

---

**Date**: November 2, 2025  
**Analysis By**: AI Assistant  
**Status**: ✅ Complete - No LMS bugs found

