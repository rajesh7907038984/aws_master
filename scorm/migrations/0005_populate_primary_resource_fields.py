# Generated migration to populate primary_resource_* fields for existing packages
from django.db import migrations
import logging

logger = logging.getLogger(__name__)


def populate_primary_resource_fields(apps, schema_editor):
    """
    Populate primary_resource_* fields for existing SCORM packages
    that have NULL values but have manifest_data
    """
    ScormPackage = apps.get_model('scorm', 'ScormPackage')
    
    packages = ScormPackage.objects.filter(
        primary_resource_href__isnull=True,
        manifest_data__isnull=False
    ).exclude(manifest_data={})
    
    count = packages.count()
    logger.info(f"Found {count} SCORM packages to update")
    
    updated_count = 0
    for package in packages:
        try:
            manifest_data = package.manifest_data
            if not isinstance(manifest_data, dict):
                continue
            
            resources = manifest_data.get('resources', [])
            if not resources:
                continue
            
            # Find first SCO resource
            primary_resource = None
            for resource in resources:
                scorm_type = resource.get('scormType', '').lower()
                resource_type = resource.get('type', '').lower()
                
                if scorm_type == 'sco' or 'sco' in scorm_type or 'sco' in resource_type:
                    primary_resource = resource
                    break
            
            # If no SCO, use first resource with href
            if not primary_resource:
                for resource in resources:
                    if resource.get('href'):
                        primary_resource = resource
                        break
            
            if primary_resource:
                package.primary_resource_identifier = primary_resource.get('identifier', '')[:128]
                package.primary_resource_type = 'webcontent'
                
                scorm_type = primary_resource.get('scormType', '').lower()
                if scorm_type == 'sco' or 'sco' in scorm_type:
                    package.primary_resource_scorm_type = 'sco'
                else:
                    package.primary_resource_scorm_type = 'sco'
                
                href = primary_resource.get('href', '')
                base = primary_resource.get('base', '')
                
                if href:
                    href_clean = href.lstrip('/').lstrip('\\')
                    if base:
                        base_clean = base.strip('/').strip('\\')
                        combined = f"{base_clean}/{href_clean}" if base_clean else href_clean
                    else:
                        combined = href_clean
                    
                    parts = [p for p in combined.replace('\\', '/').split('/') if p]
                    package.primary_resource_href = '/'.join(parts)[:2048]
                
                # Also update resources field if empty
                if not package.resources:
                    package.resources = resources
                
                package.save(update_fields=[
                    'primary_resource_identifier',
                    'primary_resource_type',
                    'primary_resource_scorm_type',
                    'primary_resource_href',
                    'resources',
                ])
                
                updated_count += 1
                logger.info(f"Updated package {package.id}: {package.title}")
        
        except Exception as e:
            logger.error(f"Error updating package {package.id}: {e}")
            continue
    
    logger.info(f"Successfully updated {updated_count}/{count} SCORM packages")


def reverse_populate(apps, schema_editor):
    """Reverse migration - no action needed"""
    pass


class Migration(migrations.Migration):
    
    dependencies = [
        ('scorm', '0004_add_resource_fields'),
    ]
    
    operations = [
        migrations.RunPython(populate_primary_resource_fields, reverse_populate),
    ]

