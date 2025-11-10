# Time Slot Unselect Feature - User Guide

## What's New?

Learners can now **cancel their time slot selection** for conferences with time slot options.

## How It Works

### Step 1: View Your Selected Time Slot
When you've selected a time slot, you'll see a **green success alert** showing:
```
✓ You have selected: December 15, 2024 10:00 - 11:00 (UTC)
[✓ Added to Outlook] (if applicable)
[Cancel Selection] ← NEW BUTTON
```

### Step 2: Cancel Your Selection
1. Click the **red "Cancel Selection"** button
2. A confirmation dialog will appear asking: *"Are you sure you want to cancel your time slot selection?"*
3. Click **OK** to confirm or **Cancel** to keep your selection

### Step 3: Confirmation
After cancellation:
- You'll see a success message: *"Successfully cancelled your time slot selection: [date/time]"*
- The slot becomes available for others
- If the event was in your Outlook calendar, it will be automatically removed
- You can now select a different time slot or leave it unselected

## Visual Layout

```
┌─────────────────────────────────────────────────────┐
│  ✓ Select Your Time Slot                           │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ✓ You have selected:                              │
│  December 15, 2024                                  │
│  10:00 - 11:00 (UTC)                               │
│  [✓ Added to Outlook]                              │
│                                                     │
│  [✗ Cancel Selection]  ← Click to unselect         │
│                                                     │
└─────────────────────────────────────────────────────┘

Available Time Slots:
┌─────────────────────────────────────────────────────┐
│  December 15, 2024                                  │
│  10:00 - 11:00 (UTC)                               │
│  2/10 participants (8 spots remaining)             │
│                               [✓ Select] or [Selected] │
└─────────────────────────────────────────────────────┘
```

## Benefits

✅ **Flexibility**: Change your mind or free up a spot for others
✅ **Calendar Integration**: Automatically removes the event from Outlook
✅ **Transparency**: See participant count update in real-time
✅ **Safety**: Confirmation dialog prevents accidental cancellations
✅ **Feedback**: Clear success/error messages

## Technical Details

- **Secure**: Requires login and CSRF protection
- **Safe**: Only you can cancel your own selection
- **Reliable**: Proper error handling if something goes wrong
- **Fast**: AJAX support for seamless experience

## FAQ

**Q: Can I select a different slot after cancelling?**
A: Yes! After cancelling, all available slots become selectable again.

**Q: Will the cancellation remove the event from my calendar?**
A: Yes, if the event was added to your Outlook calendar, it will be automatically removed.

**Q: What happens to the participant count?**
A: The participant count for that slot decreases by 1, making the spot available for others.

**Q: Can I cancel my selection right before the conference?**
A: Currently yes, but this may be restricted in future updates (e.g., no cancellations within 24 hours).

**Q: What if I accidentally cancel?**
A: You'll see a confirmation dialog before the cancellation is processed. If you cancel by mistake, just select the slot again (if still available).

## For Administrators

This feature automatically:
- Decrements the `current_participants` count on the time slot
- Deletes the `ConferenceTimeSlotSelection` record
- Removes the Outlook calendar event via Microsoft Graph API (if applicable)
- Logs all actions for audit purposes

## Support

If you encounter any issues with this feature, please contact your system administrator or refer to:
- Feature documentation: `SLOT_UNSELECT_FEATURE.md`
- Conference documentation: Check with your course instructor

