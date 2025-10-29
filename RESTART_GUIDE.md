# LMS Server Restart Guide

## ✅ Session Preservation - Auto-Logout Prevention

**All restart scripts now automatically preserve user sessions to prevent auto-logout!**

## Available Restart Methods

All methods below now include automatic session preservation:

### 1. Quick Restart (Recommended for most cases)
```bash
./restart_server.sh quick
```
- Fast restart without extensive checks
- ✅ Preserves user sessions
- Best for: Quick updates, configuration changes

### 2. Full Restart (Recommended for deployments)
```bash
./restart_server.sh full
# or
./restart_server.sh
```
- Complete restart with all checks
- ✅ Preserves user sessions
- Runs migrations, collects static files
- Best for: Code deployments, database changes

### 3. Deployment with Session Preservation (Legacy - now redundant)
```bash
./deploy_with_session_preservation.sh
```
- This script is now redundant since all restart methods preserve sessions
- Kept for backwards compatibility

### 4. Server Manager Commands
```bash
# Full restart with checks
./server_manager.sh restart

# Quick restart
./server_manager.sh quick

# Production service restart
./server_manager.sh service-restart
```
All commands automatically preserve sessions before restarting.

## What Happens During Restart

1. **🛡️ Session Preservation** - Extends all active user sessions by 24 hours
2. **🛑 Server Shutdown** - Gracefully stops the application
3. **🔍 Pre-checks** - Validates configuration (full restart only)
4. **📦 Migrations** - Applies database changes (full restart only)
5. **🎨 Static Files** - Collects static assets (full restart only)
6. **🚀 Server Start** - Starts the application server
7. **✅ Verification** - Confirms server is running

## Session Configuration

Current session settings:
- **Session Duration**: 24 hours
- **Extension on Restart**: 24 hours
- **Backend**: Database (Django sessions)
- **Auto-save**: Enabled on every request

## Troubleshooting

### If users report being logged out after restart:
This should no longer happen! All restart scripts now preserve sessions automatically.

### Check session status:
```bash
python manage.py preserve_sessions --check-only
```

### Manually preserve sessions:
```bash
python manage.py preserve_sessions
```

### View server status:
```bash
./server_manager.sh status
```

### View logs:
```bash
tail -f logs/gunicorn_error.log
```

## Best Practices

1. **Always use these scripts** instead of manual `systemctl restart` or `kill` commands
2. **Monitor logs** after restart to ensure clean startup
3. **Test in dev/staging** before production restarts
4. **Schedule restarts** during low-usage periods if possible
5. **Notify users** of planned maintenance (optional since sessions are preserved)

## Why Session Preservation Matters

Without session preservation, restarting the application server can cause:
- ❌ Users being unexpectedly logged out
- ❌ Loss of unsaved work
- ❌ Frustration and support tickets
- ❌ Interrupted learning sessions

With automatic session preservation:
- ✅ Users stay logged in through restarts
- ✅ Seamless experience during deployments
- ✅ No interruption to active sessions
- ✅ Happy users!

## Technical Details

Session preservation works by:
1. Querying all active sessions from the database
2. Extending their expiration time by 24 hours
3. Saving the updated sessions before server shutdown
4. Sessions persist through the restart in the database

This ensures continuity even when the application process restarts.

