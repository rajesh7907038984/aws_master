# SCORM Quiz Fix - Testing Guide

## Important: Browser Cache

Since we updated JavaScript files (`scorm-api.js`), users MUST clear their browser cache or do a hard refresh to get the updated code.

### Hard Refresh Instructions:

**Chrome/Edge/Firefox (Windows/Linux):**
- Press `Ctrl + Shift + R`
- Or `Ctrl + F5`

**Chrome/Safari (Mac):**
- Press `Cmd + Shift + R`

**Alternative:**
- Open browser DevTools (F12)
- Right-click the refresh button
- Select "Empty Cache and Hard Reload"

## Testing Steps for learner1_branch1_test

1. **Clear browser cache** (critical!)

2. **Login:** https://staging.nexsy.io
   - Username: `learner1_branch1_test`
   - Password: `test123`

3. **Go to Topic 243:**
   - https://staging.nexsy.io/courses/topic/243/view/

4. **Launch SCORM Content:**
   - Click "Review Content" button
   - This will create a NEW attempt with the fixed code

5. **Complete the Quiz:**
   - Go through the Storyline content
   - Complete any quiz questions
   - Make sure to click "Submit" on quiz results
   - Wait for the SCORM content to save (watch browser console for "SCORM progress update" messages)

6. **Exit Properly:**
   - Click "Back to Topic" button (this triggers LMSCommit)
   - Or close the tab (also triggers save)

7. **Verify the Fix:**
   ```bash
   python3 /home/ec2-user/lms/verify_scorm_db.py learner1_branch1_test 243
   ```

   Expected output:
   - `last_score` should show the quiz score
   - `best_score` should match
   - `completed` should be `true` if quiz was passed

## Browser Console Debugging

If issues persist, open Browser Console (F12 → Console tab) and check for:

**Good signs:**
```
✓ SCORM API ready
✓ Progress committed
SCORM progress update succeeded
```

**Bad signs:**
```
✗ Failed to load scorm-api.js
SCORM progress update failed
CMI data not captured
```

## Database Verification (Admin)

```bash
cd /home/ec2-user/lms
python3 manage.py shell << 'EOFPY'
from users.models import CustomUser
from scorm.models import ScormAttempt
import json

user = CustomUser.objects.get(username='learner1_branch1_test')
attempt = ScormAttempt.objects.filter(user=user, topic_id=243).order_by('-started_at').first()

print(f"\n{'='*80}")
print(f"Latest Attempt for {user.username} on Topic 243")
print(f"{'='*80}")
print(f"Attempt ID: {attempt.id}")
print(f"Started: {attempt.started_at}")
print(f"Score: {attempt.score_raw}/{attempt.score_max}")
print(f"Completion: {attempt.completion_status}")
print(f"Success: {attempt.success_status}")
print(f"\nCMI Keys: {list(attempt.cmi_data.keys())}")
print(f"\n✅ FIXED if you see: cmi.core.score.raw, cmi.core.score.max")
print(f"❌ OLD BUG if you see: cmi.scoreRaw, cmi.scoreMax")
print(f"{'='*80}\n")
EOFPY
```

## Expected Results After Fix

### ✅ Good CMI Data (Fixed):
```json
{
    "cmi.core.score.raw": "85",
    "cmi.core.score.max": "100",
    "cmi.core.lesson_status": "passed",
    "cmi.suspend_data": "...",
    "cmi.core.exit": "suspend"
}
```

### ❌ Bad CMI Data (Old Bug):
```json
{
    "cmi.scoreRaw": "null",
    "cmi.scoreMax": "null",
    "cmi.lessonStatus": "incomplete"
}
```

## Troubleshooting

### Problem: Still seeing bad CMI keys
**Solution:** User didn't clear browser cache. Do a hard refresh (Ctrl+Shift+R)

### Problem: Score still showing as 0 or null
**Causes:**
1. User didn't complete/submit the quiz properly in Storyline
2. Storyline quiz didn't call LMSSetValue for scores
3. Browser cache not cleared

**Solution:**
1. Clear cache and try again
2. Make sure to click "Submit" button in quiz
3. Check browser console for JavaScript errors

### Problem: Old attempts showing in database
**This is normal:**
- Old attempts with bad data remain in the database
- New attempts (after fix) will have correct data
- The system uses the latest attempt for scoring

## Success Criteria

✅ CMI keys follow standard SCORM format  
✅ Scores are captured (not "null" or "0")  
✅ Completion status reflects quiz result  
✅ Gradebook shows quiz score  
✅ Topic marked as complete if quiz passed  

---

**Fix Applied:** October 29, 2025 20:35 UTC  
**Static Files Collected:** ✅ Completed  
**Server Restarted:** 20:33 UTC  
**Cache Clear Required:** YES (JavaScript changes)  
**Status:** 🟢 LIVE and ready for testing
