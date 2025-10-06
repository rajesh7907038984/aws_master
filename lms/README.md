# LMS Production Server

A comprehensive Learning Management System with server-independent configuration.

##  Quick Start

### Initial Setup
```bash
# 1. Copy and configure environment
cp env_template .env
nano .env  # Edit with your server configuration

# 2. Run automated setup
./setup_server.sh

# 3. Start the server
./restart_server.sh
```

## 📁 Project Structure

```
lms/
├── manage.py                    # Django management script
├── requirements.txt             # Python dependencies
├── gunicorn.conf.py            # Gunicorn server configuration
├── env_template                 # Environment configuration template
│
├── setup_server.sh             # ⭐ Initial server setup script
├── restart_server.sh           # ⭐ Server restart script
├── server_manager.sh           # Server management utilities
│
├── docs/                        # 📚 Documentation
│   ├── SERVER_SETUP_GUIDE.md               # Comprehensive setup guide
│   ├── QUICK_REFERENCE.md                  # Quick command reference
│   ├── SERVER_INDEPENDENCE_OVERVIEW.md     # Architecture overview
│   ├── DEPLOYMENT_SUMMARY.md               # What changed and why
│   └── PROJECT_CHANGES_SUMMARY.txt         # Text summary
│
├── config/                      # Server configuration templates
│   ├── nginx.conf                          # Nginx configuration reference
│   └── lms-production.service              # Systemd service reference
│
├── archive/                     # Archived/legacy files
│   ├── old_scripts/                        # Old deployment scripts
│   ├── old_env_files/                      # Legacy environment files
│   ├── old_docs/                           # Superseded documentation
│   └── one_time_fixes/                     # One-time fix scripts
│
├── scripts/                     # Utility scripts
│
├── LMS_Project/                # Django project settings
│   └── settings/
│       ├── __init__.py
│       ├── base.py                        # Base settings
│       └── production.py                  # Production overrides
│
├── core/                       # Core app (includes env_loader.py)
├── users/                      # User management app
├── courses/                    # Course management app
├── [... 30+ other Django apps ...]
│
├── static/                     # Static files (CSS, JS, images)
├── templates/                  # Global templates
└── venv/                       # Python virtual environment
```

## 📖 Documentation

All documentation is in the `docs/` folder:

- **[SERVER_SETUP_GUIDE.md](docs/SERVER_SETUP_GUIDE.md)** - Complete setup and deployment guide
- **[QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md)** - Quick command reference
- **[SERVER_INDEPENDENCE_OVERVIEW.md](docs/SERVER_INDEPENDENCE_OVERVIEW.md)** - Architecture and design
- **[DEPLOYMENT_SUMMARY.md](docs/DEPLOYMENT_SUMMARY.md)** - Detailed change log

##  Common Commands

### Server Management
```bash
# Quick restart (fast - no migrations)
./restart_server.sh quick

# Full restart (with migrations and checks)
./restart_server.sh full

# Check server status
./server_manager.sh status

# View logs
tail -f $LOGS_DIR/gunicorn_error.log
```

### Django Management
```bash
# Activate virtual environment
source venv/bin/activate

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Collect static files
python manage.py collectstatic

# Run Django shell
python manage.py shell
```

## ⚙️ Configuration

All server-specific configuration is in the `.env` file. Key variables:

```bash
# Server Paths
PROJECT_ROOT=/your/project/path
STATIC_ROOT=/your/static/path
LOGS_DIR=/your/logs/path

# Server Configuration
SERVER_USER=your-user
PRIMARY_DOMAIN=your-domain.com
GUNICORN_BIND=0.0.0.0:8000

# Database
AWS_DB_HOST=your-database-host
AWS_DB_PASSWORD=your-password

# ... see env_template for complete list
```

##  Server Independence

This project is **fully server-independent**:

 All paths configurable via `.env`  
 No hardcoded server paths in code  
 Dynamic nginx configuration generation  
 Dynamic systemd service generation  
 One-command setup and restart  

To deploy on a new server, simply:
1. Edit `.env` with new server paths
2. Run `./setup_server.sh`
3. Run `./restart_server.sh`

No code changes needed!

## 🔐 Security

- Keep `.env` file secure: `chmod 600 .env`
- Never commit `.env` to version control (it's in .gitignore)
- Use different secrets for each environment
- Use strong, unique `DJANGO_SECRET_KEY`

## 📊 Requirements

- Python 3.8+
- PostgreSQL 12+
- Redis 6+ (for caching)
- Nginx (recommended)
- 4GB+ RAM recommended

## 🆘 Support

### Troubleshooting
```bash
# Validate configuration
./setup_server.sh

# Check Django configuration
python manage.py check --deploy

# View error logs
tail -50 $LOGS_DIR/gunicorn_error.log
```

### Documentation
- See `docs/` folder for comprehensive guides
- Check `env_template` for all configuration options
- Review archived scripts in `archive/` if needed

## 📞 Quick Links

- **Setup Guide**: [docs/SERVER_SETUP_GUIDE.md](docs/SERVER_SETUP_GUIDE.md)
- **Quick Reference**: [docs/QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md)
- **Configuration Template**: [env_template](env_template)
- **Gunicorn Config**: [gunicorn.conf.py](gunicorn.conf.py)

## 🎯 Production Checklist

Before going live:

- [ ] Configure `.env` with production settings
- [ ] Run `./setup_server.sh` successfully
- [ ] Database migrations applied
- [ ] Static files collected
- [ ] SSL certificate configured (via ALB or nginx)
- [ ] Backup strategy in place
- [ ] Monitoring configured
- [ ] Error logging reviewed
- [ ] Security headers configured
- [ ] Rate limiting set up (if needed)

##  License

[Your License Here]

## 🤝 Contributing

[Your Contributing Guidelines]

---

**Status**:  Production Ready  
**Version**: 1.0  
**Last Updated**: October 1, 2025

