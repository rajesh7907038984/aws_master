# SCORM Topic Functionality Bug Report
**Date:** 2025-01-27  
**Environment:** Staging (https://staging.nexsy.io)  
**Course:** New Course 34 (ID: 34)  
**Test Account:** learner1_branch1_test / test123  
**Browser:** Chrome

---

## Executive Summary

Testing SCORM topic functionality for Course 34 revealed **1 critical bug** preventing progress tracking and **additional issues** affecting user experience.

**Topics Tested:**
- Topic 235: "wef" (SCORM)
- Topic 236: "edc" (SCORM)

---

## Critical Bug #1: SCORM Progress Not Saving

### Severity: **CRITICAL** 🔴
### Impact: **HIGH** - Progress data is not persisted to the database

### Description
SCORM content loads and initializes, but progress updates (scores, completion status, time spent, bookmarking) are not saved to the database because the SCORM API is configured with `null` values for `progressUpdateUrl` and `topicId`.

### Steps to Reproduce
1. Log in as `learner1_branch1_test` / `test123`
2. Navigate to Course 34: https://staging.nexsy.io/courses/34/details/
3. Click on topic "wef" (Topic ID: 235)
4. Click "Launch SCORM Player"
5. Open browser DevTools Console
6. Observe console warnings/errors

### Evidence
**Console Logs:**
```
[WARNING] SCORM: No progress update URL configured @ https://staging.nexsy.io/static/scorm/js/scorm-api.js:126
[LOG] SCORM: Configured {version: 2004, progressUpdateUrl: null, topicId: null, progressData: Object}
[LOG] SCORM 2004: Commit - sending update
[WARNING] SCORM: No progress update URL configured
```

**Expected Behavior:**
- SCORM API should be configured with:
  - `progressUpdateUrl: '/courses/api/update_scorm_progress/235/'`
  - `topicId: 235`
- Progress commits should successfully POST to the update endpoint
- Progress should be saved to `TopicProgress` model

**Actual Behavior:**
- Both `progressUpdateUrl` and `topicId` are `null`
- Commit operations fail silently
- Progress is not persisted
- Score, completion status, time, and bookmark data are lost

### Root Cause Analysis

**File:** `/home/ec2-user/lms/scorm/views.py`

1. **In `scorm_player` view (line 207):**
   ```python
   topic_id = request.GET.get('topic_id', '')
   ```
   The view checks for `topic_id` in query string but it's never passed.

2. **In `scorm_player` view (line 251):**
   ```python
   var topicId = {topic_id if topic_id else 'null'};
   ```
   When `topic_id` is an empty string (`''`), this evaluates to JavaScript `null` because empty strings are falsy in Python.

3. **In `launcher.html` template (line 282):**
   ```javascript
   const contentUrl = '{% url "scorm:player" package.id entry_point %}';
   ```
   The URL is built without adding `topic_id` as a query parameter.

**Files Involved:**
- `/home/ec2-user/lms/scorm/templates/scorm/launcher.html` (line 282)
- `/home/ec2-user/lms/scorm/views.py` (lines 207, 251-252)

### Fix Required

1. **Update `launcher.html` to pass `topic_id` in query string:**
   ```javascript
   const params = new URLSearchParams({
       _no_api: '1',
       topic_id: '{{ topic.id }}'  // ADD THIS
   });
   ```

2. **Update `scorm_player` view to handle empty string properly:**
   ```python
   topic_id = request.GET.get('topic_id', None)
   # ... later in script injection ...
   var topicId = {topic_id if topic_id else 'null'};
   ```

---

## Additional Issues Found

### Issue #2: Progress Display Shows 0/0 (0%)

**Severity:** Medium  
**Location:** Topic view page, "Your Progress" indicator

**Description:**
Progress indicator shows "0/0 (0%)" instead of meaningful progress when no data exists or when progress hasn't been initialized.

**Evidence:**
- Topic view shows: "Your Progress: 0/0 (0%)"
- This appears for both topics even after launching SCORM content

**Expected:**
- Should show "0/1 (0%)" or "Not Started" if progress hasn't been initialized
- Should update to reflect actual progress once tracking begins

---

### Issue #3: Quiz Results Show "undefined%"

**Severity:** Medium  
**Location:** SCORM content iframe (observed in first topic "wef")

**Description:**
When viewing quiz results screen, score displays as "Your score: undefined%" instead of a numeric value.

**Evidence from page snapshot:**
```yaml
- generic:
  - heading "Quiz Results" [level=1]
  - generic:
    - generic: "PASSING: 80%"
    - generic: "Your score: undefined%"
    - generic: Failed
```

**Note:** This may be a SCORM content issue (third-party content), but worth investigating if it's related to API communication.

---

## Test Coverage Summary

✅ **Completed:**
- Course page loaded successfully
- Both SCORM topics found and accessible
- SCORM launcher page loads
- SCORM content iframe loads
- SCORM API initializes correctly
- SCORM API is accessible from iframe

❌ **Failed:**
- Progress tracking (no URL configured)
- Progress persistence (commits fail)
- Progress display updates

⚠️ **Partial/Uncertain:**
- Quiz scoring (results show undefined - may be content issue)
- Completion status tracking (can't verify without progress saving)

---

## Recommendations

### Immediate Action Required:
1. **Fix Bug #1 (Critical)** - Add `topic_id` parameter to SCORM player URL
2. **Verify Fix** - Test that progress commits successfully reach the backend
3. **Check Database** - Verify `TopicProgress` records are being created/updated

### Additional Improvements:
1. Add error handling/retry logic for failed progress commits
2. Improve progress display logic to handle edge cases (0/0)
3. Add console logging/debugging mode for SCORM operations
4. Consider adding progress save confirmation feedback to users

---

## Technical Details

### SCORM Configuration Flow:
1. User clicks "Launch SCORM Player" → `/scorm/launch/{topic_id}/`
2. `scorm_launcher` view renders `launcher.html`
3. `launcher.html` loads content via `/scorm/player/{package_id}/{entry_point}`
4. `scorm_player` view injects SCORM API configuration script
5. SCORM API attempts to commit progress via `progressUpdateUrl`

### Current Broken Flow:
Step 3 doesn't pass `topic_id`, causing Steps 4-5 to fail.

### Fixed Flow Should Be:
Step 3 passes `topic_id` in query string → `/scorm/player/{package_id}/{entry_point}?topic_id={topic_id}`
Step 4-5 can now properly configure API with topic ID and update URL.

---

**End of Report**

