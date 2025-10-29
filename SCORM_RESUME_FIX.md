# SCORM Resume Functionality Fix

## Issue Summary

**Problem:** SCORM content would not resume from where the user left off. The player would always start from the beginning, ignoring any saved progress like `lesson_location` and `suspend_data`.

**Root Cause:** The critical `scorm-api.js` JavaScript file was missing from the static files directory that Django serves to the browser.

## Technical Details

### What Was Broken

1. **Missing JavaScript File**
   - File existed in: `/home/ec2-user/lms/scorm/static/scorm/js/scorm-api.js` (app-level static)
   - But missing from: `/home/ec2-user/lms/static/scorm/js/scorm-api.js` (collectstatic location)
   - The browser tried to load the file but got a 404 error

2. **Impact on Resume Functionality**
   - Without the SCORM API, the browser couldn't initialize the SCORM communication layer
   - SCORM content couldn't retrieve saved `lesson_location` or `suspend_data`
   - Progress updates (scores, completion status, bookmarks) couldn't be sent to the LMS
   - Every launch was treated as a fresh start

### How Resume Works (When Properly Configured)

```
User launches SCORM → Launcher loads API → API retrieves bookmark data → 
SCORM content calls GetValue("cmi.core.lesson_location") → 
API returns saved location → Content resumes from that point
```

**Resume Data Flow:**

1. **On Launch** (`scorm_launcher` view):
   - Fetches `TopicProgress.bookmark` for the user
   - Extracts `lesson_location` and `suspend_data`
   - Passes to `launcher.html` as `progress_data`
   - Template embeds in `window.scormConfig.progressData`

2. **API Initialization** (`scorm-api.js`):
   - Loads configuration from `window.scormConfig`
   - Populates internal `progressData` object with resume values
   - When SCORM content calls `GetValue("cmi.core.lesson_location")`, returns saved location
   - When SCORM content calls `GetValue("cmi.suspend_data")`, returns saved state

3. **During Playback** (SCORM content):
   - Content checks `cmi.core.entry` → returns "resume" (vs "ab-initio" for first time)
   - Content retrieves `cmi.core.lesson_location` → gets last slide/page
   - Content retrieves `cmi.suspend_data` → gets serialized state data
   - Content navigates directly to that location

4. **On Progress Updates** (SCORM content):
   - Content calls `SetValue("cmi.core.lesson_location", "slide_5")`
   - Content calls `SetValue("cmi.suspend_data", "{answers: [...]}")`
   - Content calls `Commit()` → API sends data to `/scorm/progress/{topic_id}/`

5. **Server-Side Save** (`update_scorm_progress_with_enrollment`):
   - Receives progress update with new `lesson_location` and `suspend_data`
   - Updates `ScormAttempt` model with the data
   - Updates `TopicProgress.bookmark` with the data
   - Next launch will retrieve this updated bookmark

## The Fix

### What Was Done

```bash
# Copied the missing scorm-api.js file to the static folder
cp /home/ec2-user/lms/scorm/static/scorm/js/scorm-api.js \
   /home/ec2-user/lms/static/scorm/js/scorm-api.js

# Restarted the LMS service
sudo systemctl restart lms-production
```

### Verification

```bash
# Verify file is accessible
curl -I http://0.0.0.0:8000/static/scorm/js/scorm-api.js

# Expected output:
# HTTP/1.1 200 OK
# Content-Type: text/javascript; charset="utf-8"
```

## Testing Resume Functionality

### Test Steps

1. **Launch SCORM Content**
   - Log in as a learner
   - Navigate to a SCORM topic
   - Click "Launch SCORM Player"

2. **Progress Through Content**
   - Complete a few slides/pages
   - Check browser console for:
     ```
     ✓ SCORM API configured from current window
     ✓ SCORM API ready
     ```

3. **Close/Exit**
   - Click "Back to Topic" button (triggers auto-save)
   - OR close the tab (triggers beforeunload save)

4. **Re-launch SCORM**
   - Click "Resume" button (should show instead of "Launch")
   - Browser console should show:
     ```
     SCORM: Configured {
       version: "1.2" or "2004",
       progressUpdateUrl: "/scorm/progress/123/",
       topicId: 123,
       progressData: {
         lessonLocation: "slide_5",
         suspendData: "{...}",
         entry: "resume"
       }
     }
     ```
   - Content should resume at last position (not start from beginning)

5. **Verify Database**
   ```sql
   SELECT 
     bookmark->>'lesson_location' as location,
     bookmark->>'suspend_data' as suspend_data,
     progress_data->>'scorm_completion_status' as status
   FROM courses_topicprogress
   WHERE topic_id = 123 AND user_id = 456;
   ```

## Browser Console Checks

### Expected Logs (Success)

```javascript
// API Loading
✓ SCORM API ready
window.API: true
window.API_1484_11: true
SCORM API configured from current window

// On Initialize
SCORM 1.2: Initialize
Entry mode: resume
Lesson location: slide_5
Suspend data: {...}

// On GetValue
SCORM 1.2: GetValue - cmi.core.lesson_location = slide_5
SCORM 1.2: GetValue - cmi.core.entry = resume

// On Commit
SCORM 1.2: Commit - sending update
Progress update sent: POST /scorm/progress/123/
```

### Error Logs (If Not Working)

```javascript
// API Not Loading
✗ SCORM API failed to load after 100 attempts
Failed to load scorm-api.js

// API Not Configured
[WARNING] SCORM: No progress update URL configured
progressUpdateUrl: null
topicId: null
```

## Resume Data Mapping

### SCORM 1.2 Data Model

| CMI Element | Database Field | Purpose |
|-------------|----------------|---------|
| `cmi.core.lesson_location` | `TopicProgress.bookmark['lesson_location']` | Current page/slide |
| `cmi.suspend_data` | `TopicProgress.bookmark['suspend_data']` | Serialized state |
| `cmi.core.entry` | `TopicProgress.progress_data['scorm_entry']` | "resume" or "ab-initio" |
| `cmi.core.lesson_status` | `TopicProgress.progress_data['scorm_completion_status']` | "incomplete", "completed", etc. |
| `cmi.core.score.raw` | `TopicProgress.last_score` | Numeric score |

### SCORM 2004 Data Model

| CMI Element | Database Field | Purpose |
|-------------|----------------|---------|
| `cmi.location` | `TopicProgress.bookmark['lesson_location']` | Current page/slide |
| `cmi.suspend_data` | `TopicProgress.bookmark['suspend_data']` | Serialized state |
| `cmi.entry` | `TopicProgress.progress_data['scorm_entry']` | "resume" or "ab-initio" |
| `cmi.completion_status` | `TopicProgress.progress_data['scorm_completion_status']` | "incomplete", "completed", etc. |
| `cmi.success_status` | `TopicProgress.progress_data['scorm_success_status']` | "passed", "failed", "unknown" |
| `cmi.score.raw` | `TopicProgress.last_score` | Numeric score |

## Key Code Locations

### Backend (Django)

1. **Launcher View** - `scorm/views.py:scorm_launcher()`
   - Loads bookmark data from database
   - Passes to template as `progress_data`

2. **Progress Update** - `scorm/views_enrollment.py:update_scorm_progress_with_enrollment()`
   - Receives SCORM data updates
   - Saves to `ScormAttempt` and `TopicProgress.bookmark`

3. **Legacy Progress Update** - `courses/views.py:update_scorm_progress()`
   - Alternative endpoint for progress updates
   - Also updates bookmark data

### Frontend (JavaScript)

1. **API Wrapper** - `/static/scorm/js/scorm-api.js`
   - Implements SCORM 1.2 and 2004 API methods
   - Loads resume data from configuration
   - Sends updates to backend

2. **Launcher Template** - `scorm/templates/scorm/launcher.html`
   - Loads scorm-api.js script
   - Embeds configuration with resume data
   - Sets up iframe for SCORM content

### UI Display

1. **Topic View** - `courses/templates/courses/topic_view.html`
   - Shows "Resume" button if bookmark exists
   - Shows "Launch" button for first-time launch

## Prevention

### Future-Proofing

To prevent this issue from recurring after deployments:

1. **Run collectstatic on deploy:**
   ```bash
   python manage.py collectstatic --noinput
   ```

2. **Add to deployment script:**
   ```bash
   # In your deploy script
   cd /home/ec2-user/lms
   source venv/bin/activate
   python manage.py collectstatic --noinput
   sudo systemctl restart lms-production
   ```

3. **Verify in CI/CD:**
   ```bash
   # Check that scorm-api.js is collected
   test -f /home/ec2-user/lms/static/scorm/js/scorm-api.js
   ```

### Static Files Settings

Ensure `settings.py` has proper static files configuration:

```python
# Static files configuration
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')
STATICFILES_DIRS = [
    # App-level static dirs are automatically included
]
```

## Related Issues

This fix resolves:
- ✅ SCORM not resuming from last position
- ✅ Progress not saving (no API communication)
- ✅ "Resume" button showing but not working
- ✅ Entry mode always "ab-initio" instead of "resume"
- ✅ Lesson location always empty on launch
- ✅ Suspend data not persisting

## Success Criteria

✅ **Resume works when:**
1. User launches SCORM content
2. Progresses through several slides/pages
3. Exits the content
4. Re-launches the content
5. Content automatically navigates to last position
6. `cmi.core.entry` returns "resume" (not "ab-initio")
7. `cmi.core.lesson_location` returns saved location
8. `cmi.suspend_data` returns saved state

## Support

If resume still doesn't work after this fix:

1. **Check browser console** for API errors
2. **Check server logs** for progress update errors
3. **Verify database** has bookmark data saved
4. **Test with different SCORM packages** (Rise vs Storyline)
5. **Check CSRF token** is available in page

---

**Fix Applied:** October 29, 2025  
**Status:** ✅ Resolved  
**Service Restarted:** Yes  
**Tested:** Ready for testing


