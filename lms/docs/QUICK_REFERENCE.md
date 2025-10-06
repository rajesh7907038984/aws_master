# LMS Server - Quick Reference Guide

##  Quick Commands

### Initial Setup (First Time Only)
```bash
cp env_template .env
nano .env  # Edit with your server config
./setup_server.sh
sudo cp nginx_generated.conf /etc/nginx/sites-available/lms
sudo ln -sf /etc/nginx/sites-available/lms /etc/nginx/sites-enabled/lms
sudo systemctl restart nginx
./restart_server.sh
```

### Restart Server
```bash
# Quick restart (fastest)
./restart_server.sh quick

# Full restart (with migrations)
./restart_server.sh full
```

### Check Status
```bash
./server_manager.sh status
```

### View Logs
```bash
# Error logs
tail -f $LOGS_DIR/gunicorn_error.log

# Production logs
tail -f $LOGS_DIR/production.log

# Access logs
tail -f $LOGS_DIR/gunicorn_access.log
```

---

## ⚙️ Essential .env Variables

```bash
# Must Configure These:
PROJECT_ROOT=/your/project/path
STATIC_ROOT=/your/static/path
LOGS_DIR=/your/logs/path
PRIMARY_DOMAIN=your-domain.com
DJANGO_SECRET_KEY=your-secret-key
AWS_DB_PASSWORD=your-db-password
AWS_DB_HOST=your-db-host.rds.amazonaws.com

# Optional (have defaults):
SERVER_USER=ec2-user
SERVER_GROUP=ec2-user
GUNICORN_BIND=0.0.0.0:8000
GUNICORN_WORKERS=auto
```

---

##  Common Tasks

### Change Server Port
```bash
# 1. Edit .env
nano .env
# Change: GUNICORN_BIND=0.0.0.0:9000

# 2. Regenerate nginx config
./setup_server.sh

# 3. Update nginx
sudo cp nginx_generated.conf /etc/nginx/sites-available/lms
sudo systemctl restart nginx

# 4. Restart server
./restart_server.sh
```

### Move to New Server
```bash
# 1. Copy project files
# 2. Copy .env and edit paths
# 3. Run setup
./setup_server.sh
# 4. Start server
./restart_server.sh
```

### Apply Database Changes
```bash
# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Or use full restart
./restart_server.sh full
```

### Collect Static Files
```bash
python manage.py collectstatic --noinput
# Or use full restart
./restart_server.sh full
```

---

## 🐛 Troubleshooting

### Server Won't Start
```bash
# Check logs
tail -50 $LOGS_DIR/gunicorn_error.log

# Verify config
./setup_server.sh

# Check Django
python manage.py check --deploy

# Check port
lsof -i :8000
```

### Can't Connect to Database
```bash
# Test connection
python manage.py dbshell

# Check credentials in .env
grep AWS_DB .env
```

### Static Files Not Loading
```bash
# Recollect static files
python manage.py collectstatic --noinput --clear

# Check nginx config
sudo nginx -t
```

---

## 📋 File Locations

```
$PROJECT_ROOT/          - Project files
$STATIC_ROOT/           - Static files (CSS, JS)
$MEDIA_ROOT/            - Uploaded media files
$LOGS_DIR/              - Log files
$SCORM_ROOT_FOLDER/     - SCORM uploads
```

---

## 🔗 Access Points

- **Production**: https://$PRIMARY_DOMAIN
- **Local**: http://localhost:8000 (or your GUNICORN_BIND port)
- **Health Check**: https://$PRIMARY_DOMAIN/health/

---

## 📞 Support

1. Check logs in `$LOGS_DIR`
2. Run `./setup_server.sh` to validate config
3. Review `SERVER_SETUP_GUIDE.md` for detailed instructions
4. Review `DEPLOYMENT_SUMMARY.md` for what changed

---

**Remember**: Edit `.env` → Run setup (if needed) → Restart → Done! 

