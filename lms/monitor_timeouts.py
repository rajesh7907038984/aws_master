#!/usr/bin/env python3
"""
Timeout Monitoring Script for LMS
Monitors Gunicorn worker timeouts and provides diagnostics
"""

import subprocess
import time
import psutil
import os
from datetime import datetime

def check_gunicorn_processes():
    """Check running Gunicorn processes"""
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent']):
        try:
            if 'gunicorn' in proc.info['name'].lower():
                processes.append({
                    'pid': proc.info['pid'],
                    'name': proc.info['name'],
                    'memory_mb': proc.info['memory_info'].rss / 1024 / 1024,
                    'cpu_percent': proc.info['cpu_percent']
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return processes

def check_memory_usage():
    """Check system memory usage"""
    memory = psutil.virtual_memory()
    return {
        'total_gb': memory.total / 1024 / 1024 / 1024,
        'available_gb': memory.available / 1024 / 1024 / 1024,
        'percent_used': memory.percent,
        'free_gb': memory.free / 1024 / 1024 / 1024
    }

def check_gunicorn_logs():
    """Check for timeout errors in Gunicorn logs"""
    log_file = '/home/ec2-user/lmslogs/gunicorn_error.log'
    if not os.path.exists(log_file):
        return []
    
    try:
        with open(log_file, 'r') as f:
            lines = f.readlines()
            # Get last 50 lines
            recent_lines = lines[-50:] if len(lines) > 50 else lines
            timeout_errors = [line for line in recent_lines if 'TIMEOUT' in line or 'timeout' in line.lower()]
            return timeout_errors
    except Exception as e:
        return ["Error reading log file: {{e}}"]

def main():
    """Main monitoring function"""
    print("=== LMS Timeout Monitor - {{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}} ===\n")
    
    # Check Gunicorn processes
    processes = check_gunicorn_processes()
    print("Gunicorn Processes: {{len(processes)}}")
    for proc in processes:
        print("  PID {{proc['pid']}}: {{proc['name']}} - Memory: {{proc['memory_mb']:.1f}}MB, CPU: {{proc['cpu_percent']:.1f}}%")
    
    # Check memory usage
    memory = check_memory_usage()
    print("\nMemory Usage:")
    print("  Total: {{memory['total_gb']:.1f}}GB")
    print("  Available: {{memory['available_gb']:.1f}}GB")
    print("  Used: {{memory['percent_used']:.1f}}%")
    print("  Free: {{memory['free_gb']:.1f}}GB")
    
    # Check for timeout errors
    timeout_errors = check_gunicorn_logs()
    if timeout_errors:
        print("\n⚠️  Recent Timeout Errors ({{len(timeout_errors)}}):")
        for error in timeout_errors[-5:]:  # Show last 5 errors
            print("  {{error.strip()}}")
    else:
        print("\n✅ No recent timeout errors found")
    
    # Recommendations
    print("\n📊 Recommendations:")
    if memory['percent_used'] > 80:
        print("  ⚠️  High memory usage - consider reducing workers or optimizing queries")
    if len(processes) > 3:
        print("  ⚠️  Multiple Gunicorn processes detected - check for duplicate instances")
    if timeout_errors:
        print("  ⚠️  Timeout errors detected - check database queries and file uploads")
    else:
        print("  ✅ System appears stable")

if __name__ == "__main__":
    main()
