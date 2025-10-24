"""
Teams Integration Django App Configuration
"""

from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class TeamsIntegrationConfig(AppConfig):
    """Teams Integration app configuration"""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'teams_integration'
    verbose_name = 'Teams Integration'
    
    def ready(self):
        """Initialize Teams integration when Django starts"""
        try:
            # Import signal handlers
            from . import signals
            
            # Initialize Teams integration services
            self._initialize_teams_services()
            
            logger.info("Teams Integration app initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing Teams Integration app: {str(e)}")
    
    def _initialize_teams_services(self):
        """Initialize Teams integration services"""
        try:
            from .utils.teams_api import TeamsAPIClient
            from .utils.entra_sync import EntraSyncService
            
            # Check if Teams integrations are configured
            from account_settings.models import TeamsIntegration
            active_integrations = TeamsIntegration.objects.filter(is_active=True)
            
            if active_integrations.exists():
                logger.info(f"Found {active_integrations.count()} active Teams integrations")
                
                # Initialize API clients for each integration
                for integration in active_integrations:
                    try:
                        api_client = TeamsAPIClient(integration)
                        sync_service = EntraSyncService(integration)
                        logger.info(f"Initialized Teams services for integration: {integration.name}")
                    except Exception as e:
                        logger.warning(f"Failed to initialize Teams services for {integration.name}: {str(e)}")
            
        except Exception as e:
            logger.error(f"Error initializing Teams services: {str(e)}")
