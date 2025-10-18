"""
System Health Monitoring Command
Comprehensive system health check and monitoring
"""

from django.core.management.base import BaseCommand
from django.db import connection
from django.core.cache import cache
from core.monitoring.performance_monitor import get_performance_monitor
from core.utils.memory_monitor import get_memory_monitor
from core.security.hardening import validate_security_settings
import logging
import time

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Comprehensive system health check and monitoring'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--detailed',
            action='store_true',
            help='Show detailed system information',
        )
        parser.add_argument(
            '--monitor',
            action='store_true',
            help='Start continuous monitoring',
        )
        parser.add_argument(
            '--duration',
            type=int,
            default=60,
            help='Monitoring duration in seconds (default: 60)',
        )
    
    def handle(self, *args, **options):
        if options['monitor']:
            self.start_monitoring(options['duration'])
        else:
            self.run_health_check(options['detailed'])
    
    def run_health_check(self, detailed=False):
        """Run comprehensive health check"""
        self.stdout.write('🔍 Running LMS System Health Check...')
        self.stdout.write('=' * 50)
        
        # Database health
        self.check_database_health()
        
        # Memory health
        self.check_memory_health()
        
        # Performance health
        self.check_performance_health()
        
        # Security health
        self.check_security_health()
        
        # Cache health
        self.check_cache_health()
        
        # System resources
        if detailed:
            self.check_system_resources()
        
        self.stdout.write('=' * 50)
        self.stdout.write(self.style.SUCCESS('✅ System health check completed'))
    
    def check_database_health(self):
        """Check database connectivity and performance"""
        self.stdout.write('\n📊 Database Health:')
        try:
            with connection.cursor() as cursor:
                # Test basic connectivity
                cursor.execute("SELECT 1")
                self.stdout.write('  ✅ Database connection: OK')
                
                # Check database size
                cursor.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
                db_size = cursor.fetchone()[0]
                self.stdout.write(f'  📏 Database size: {db_size}')
                
                # Check table count
                cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'")
                table_count = cursor.fetchone()[0]
                self.stdout.write(f'  📋 Total tables: {table_count}')
                
                # Check index count
                cursor.execute("SELECT COUNT(*) FROM pg_indexes WHERE schemaname = 'public'")
                index_count = cursor.fetchone()[0]
                self.stdout.write(f'  🔍 Total indexes: {index_count}')
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ❌ Database error: {e}'))
    
    def check_memory_health(self):
        """Check memory usage and optimization"""
        self.stdout.write('\n🧠 Memory Health:')
        try:
            memory_monitor = get_memory_monitor()
            memory_stats = memory_monitor.get_memory_usage()
            
            self.stdout.write(f'  📊 Current memory: {memory_stats["rss_mb"]:.2f}MB')
            self.stdout.write(f'  📈 Memory percent: {memory_stats["percent"]:.1f}%')
            self.stdout.write(f'  💾 Available memory: {memory_stats["available_mb"]:.2f}MB')
            
            if memory_monitor.should_trigger_cleanup():
                self.stdout.write('  ⚠️  High memory usage detected')
                cleanup_result = memory_monitor.cleanup_memory()
                if cleanup_result.get('cleaned'):
                    self.stdout.write(f'  🧹 Memory cleanup: {cleanup_result.get("memory_freed_mb", 0):.2f}MB freed')
            else:
                self.stdout.write('  ✅ Memory usage: Normal')
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ❌ Memory check error: {e}'))
    
    def check_performance_health(self):
        """Check performance metrics"""
        self.stdout.write('\n⚡ Performance Health:')
        try:
            performance_monitor = get_performance_monitor()
            stats = performance_monitor.get_performance_stats()
            
            if stats.get('status') == 'No data available':
                self.stdout.write('  📊 No performance data available yet')
                return
            
            self.stdout.write(f'  🚀 Performance score: {stats.get("performance_score", 0)}/100')
            self.stdout.write(f'  ⏱️  Avg response time: {stats.get("avg_response_time_ms", 0):.2f}ms')
            self.stdout.write(f'  📈 Total requests: {stats.get("total_requests", 0)}')
            self.stdout.write(f'  ❌ Error rate: {stats.get("error_rate_percent", 0):.2f}%')
            self.stdout.write(f'  💾 Avg memory per request: {stats.get("avg_memory_usage_mb", 0):.2f}MB')
            self.stdout.write(f'  🗄️  Avg DB queries per request: {stats.get("avg_db_queries_per_request", 0):.1f}')
            self.stdout.write(f'  🎯 Cache hit rate: {stats.get("cache_hit_rate_percent", 0):.1f}%')
            
            # Show recommendations
            recommendations = performance_monitor.get_recommendations()
            if recommendations:
                self.stdout.write('  💡 Recommendations:')
                for rec in recommendations:
                    self.stdout.write(f'    - {rec}')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ❌ Performance check error: {e}'))
    
    def check_security_health(self):
        """Check security configuration"""
        self.stdout.write('\n🔒 Security Health:')
        try:
            security_status = validate_security_settings()
            self.stdout.write(f'  🛡️  Security score: {security_status["security_score"]}/100')
            
            if security_status['issues']:
                self.stdout.write('  ⚠️  Security issues found:')
                for issue in security_status['issues']:
                    self.stdout.write(f'    - {issue}')
            else:
                self.stdout.write('  ✅ Security configuration: Good')
            
            if security_status['recommendations']:
                self.stdout.write('  💡 Security recommendations:')
                for rec in security_status['recommendations']:
                    self.stdout.write(f'    - {rec}')
                    
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ❌ Security check error: {e}'))
    
    def check_cache_health(self):
        """Check cache functionality"""
        self.stdout.write('\n💾 Cache Health:')
        try:
            # Test cache functionality
            test_key = 'health_check_test'
            test_value = 'test_value'
            
            cache.set(test_key, test_value, 30)
            retrieved_value = cache.get(test_key)
            
            if retrieved_value == test_value:
                self.stdout.write('  ✅ Cache functionality: OK')
                cache.delete(test_key)
            else:
                self.stdout.write('  ❌ Cache functionality: Failed')
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ❌ Cache check error: {e}'))
    
    def check_system_resources(self):
        """Check system resource usage"""
        self.stdout.write('\n🖥️  System Resources:')
        try:
            import psutil
            
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            self.stdout.write(f'  🖥️  CPU usage: {cpu_percent}%')
            
            # Memory usage
            memory = psutil.virtual_memory()
            self.stdout.write(f'  🧠 Memory usage: {memory.percent}%')
            self.stdout.write(f'  💾 Available memory: {memory.available / 1024 / 1024 / 1024:.2f}GB')
            
            # Disk usage
            disk = psutil.disk_usage('/')
            self.stdout.write(f'  💿 Disk usage: {disk.percent}%')
            self.stdout.write(f'  📁 Free disk space: {disk.free / 1024 / 1024 / 1024:.2f}GB')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ❌ System resources check error: {e}'))
    
    def start_monitoring(self, duration):
        """Start continuous monitoring"""
        self.stdout.write(f'🔄 Starting continuous monitoring for {duration} seconds...')
        self.stdout.write('Press Ctrl+C to stop')
        
        try:
            # Start monitoring services
            performance_monitor = get_performance_monitor()
            memory_monitor = get_memory_monitor()
            
            performance_monitor.start_monitoring()
            memory_monitor.start_monitoring()
            
            start_time = time.time()
            while time.time() - start_time < duration:
                self.stdout.write('\n' + '=' * 50)
                self.stdout.write(f'📊 Monitoring Update - {int(time.time() - start_time)}s elapsed')
                
                # Quick health check
                self.run_health_check(detailed=False)
                
                time.sleep(30)  # Update every 30 seconds
                
        except KeyboardInterrupt:
            self.stdout.write('\n🛑 Monitoring stopped by user')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Monitoring error: {e}'))
        finally:
            # Stop monitoring services
            performance_monitor.stop_monitoring()
            memory_monitor.stop_monitoring()
