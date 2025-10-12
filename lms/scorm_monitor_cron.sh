# SCORM System Monitoring - Run every hour
cd /home/ec2-user/lms && source venv/bin/activate && python manage.py monitor_scorm_system --validate-recent=1 --fix-issues >> /home/ec2-user/lmslogs/scorm_monitor.log 2>&1
