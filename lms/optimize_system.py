#!/usr/bin/env python
"""
LMS System Optimization Script
Applies all performance, security, and monitoring optimizations
"""

import os
import sys
import subprocess
import logging

# Add the project root to Python path
sys.path.insert(0, '/home/ec2-user/lms')

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_command(command, description):
    """Run a command and log the result"""
    logger.info(f"Running: {description}")
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, cwd='/home/ec2-user/lms')
        if result.returncode == 0:
            logger.info(f"✅ {description} - Success")
            if result.stdout:
                logger.info(f"Output: {result.stdout.strip()}")
        else:
            logger.error(f"❌ {description} - Failed")
            if result.stderr:
                logger.error(f"Error: {result.stderr.strip()}")
        return result.returncode == 0
    except Exception as e:
        logger.error(f"❌ {description} - Exception: {e}")
        return False

def main():
    """Main optimization function"""
    logger.info("🚀 Starting LMS System Optimization")
    logger.info("=" * 60)
    
    # Activate virtual environment
    venv_activate = "source /home/ec2-user/lms/venv/bin/activate"
    
    # List of optimization commands
    optimizations = [
        (f"{venv_activate} && python manage.py check --deploy", "Django System Check"),
        (f"{venv_activate} && python manage.py collectstatic --noinput", "Collect Static Files"),
        (f"{venv_activate} && python manage.py migrate", "Apply Database Migrations"),
        (f"{venv_activate} && python manage.py optimize_database", "Optimize Database Performance"),
        (f"{venv_activate} && python manage.py security_audit --fix", "Apply Security Hardening"),
        (f"{venv_activate} && python manage.py system_health --detailed", "System Health Check"),
    ]
    
    # Track results
    results = []
    
    # Run all optimizations
    for command, description in optimizations:
        success = run_command(command, description)
        results.append((description, success))
        logger.info("-" * 40)
    
    # Summary
    logger.info("=" * 60)
    logger.info("📊 OPTIMIZATION SUMMARY")
    logger.info("=" * 60)
    
    successful = 0
    failed = 0
    
    for description, success in results:
        status = "✅ SUCCESS" if success else "❌ FAILED"
        logger.info(f"{status} - {description}")
        if success:
            successful += 1
        else:
            failed += 1
    
    logger.info("-" * 40)
    logger.info(f"Total optimizations: {len(results)}")
    logger.info(f"Successful: {successful}")
    logger.info(f"Failed: {failed}")
    logger.info(f"Success rate: {(successful/len(results)*100):.1f}%")
    
    if failed == 0:
        logger.info("🎉 All optimizations completed successfully!")
        logger.info("🚀 LMS system is now fully optimized!")
    else:
        logger.warning(f"⚠️  {failed} optimization(s) failed. Please check the logs above.")
    
    # Final system status
    logger.info("=" * 60)
    logger.info("🔍 FINAL SYSTEM STATUS")
    logger.info("=" * 60)
    
    # Run final health check
    run_command(f"{venv_activate} && python manage.py system_health", "Final System Health Check")
    
    logger.info("=" * 60)
    logger.info("🏁 LMS System Optimization Complete!")
    logger.info("=" * 60)

if __name__ == "__main__":
    main()
