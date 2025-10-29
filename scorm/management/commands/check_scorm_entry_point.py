"""
Django management command to check SCORM package entry point
"""
from django.core.management.base import BaseCommand
from scorm.models import ScormPackage
from courses.models import Topic
import json


class Command(BaseCommand):
    help = 'Check SCORM package entry point for a topic'

    def add_arguments(self, parser):
        parser.add_argument(
            'topic_id',
            type=int,
            help='Topic ID to check',
        )

    def handle(self, *args, **options):
        topic_id = options['topic_id']
        
        try:
            topic = Topic.objects.get(id=topic_id)
            self.stdout.write(f"\n=== Topic {topic_id} ===")
            self.stdout.write(f"Title: {topic.title}")
            self.stdout.write(f"Content Type: {topic.content_type}")
            
            if topic.content_type != 'SCORM':
                self.stdout.write(self.style.ERROR(f"Topic {topic_id} is not a SCORM topic"))
                return
            
            if not topic.scorm:
                self.stdout.write(self.style.ERROR(f"Topic {topic_id} has no SCORM package assigned"))
                return
            
            package = topic.scorm
            self.stdout.write(f"\n=== SCORM Package {package.id} ===")
            self.stdout.write(f"Title: {package.title}")
            self.stdout.write(f"Version: {package.version}")
            self.stdout.write(f"Authoring Tool: {package.get_authoring_tool_display() if package.authoring_tool else 'Unknown'}")
            self.stdout.write(f"Status: {package.processing_status}")
            self.stdout.write(f"Extracted Path: {package.extracted_path}")
            
            # Get entry point
            entry_point = package.get_entry_point()
            self.stdout.write(f"\nEntry Point Determined: {entry_point}")
            
            # Show launch URL
            launch_url = package.launch_url or package.get_launch_url()
            if launch_url:
                self.stdout.write(f"Launch URL: {launch_url}")
            else:
                self.stdout.write(self.style.WARNING("Launch URL: Not set"))
            
            # Verify entry point exists
            if package.extracted_path:
                exists, error = package.verify_entry_point_exists()
                if exists:
                    self.stdout.write(self.style.SUCCESS(f"✓ Entry point exists in S3"))
                else:
                    self.stdout.write(self.style.ERROR(f"✗ Entry point NOT found: {error}"))
                    
                    # Show what S3 key was checked
                    s3_key = f"{package.extracted_path}{entry_point}".replace('//', '/')
                    self.stdout.write(f"  Checked S3 key: {s3_key}")
            
            # Show manifest data structure
            self.stdout.write(f"\n=== Manifest Data ===")
            manifest = package.manifest_data or {}
            
            # Organizations
            orgs = manifest.get('organizations', [])
            self.stdout.write(f"Organizations: {len(orgs)}")
            if orgs:
                first_org = orgs[0]
                self.stdout.write(f"  First org title: {first_org.get('title', 'N/A')}")
                items = first_org.get('items', [])
                self.stdout.write(f"  First org items: {len(items)}")
                
                # Show first level items
                for i, item in enumerate(items[:3]):  # Show first 3
                    self.stdout.write(f"    Item {i+1}:")
                    self.stdout.write(f"      identifier: {item.get('identifier', 'N/A')}")
                    self.stdout.write(f"      identifierref: {item.get('identifierref', 'N/A')}")
                    self.stdout.write(f"      title: {item.get('title', 'N/A')}")
                    nested_items = item.get('items', [])
                    if nested_items:
                        self.stdout.write(f"      nested items: {len(nested_items)}")
            
            # Resources
            resources = manifest.get('resources', [])
            self.stdout.write(f"\nResources: {len(resources)}")
            
            # Show resources that might be the entry point
            identifierref = None
            if orgs and orgs[0].get('items'):
                first_item = orgs[0]['items'][0]
                identifierref = first_item.get('identifierref')
                if not identifierref:
                    # Try nested items
                    def find_identifierref(items):
                        for item in items:
                            if item.get('identifierref'):
                                return item.get('identifierref')
                            nested = item.get('items', [])
                            if nested:
                                result = find_identifierref(nested)
                                if result:
                                    return result
                        return None
                    identifierref = find_identifierref(orgs[0].get('items', []))
            
            if identifierref:
                self.stdout.write(f"\nLooking for resource with identifierref: {identifierref}")
                for resource in resources:
                    if resource.get('identifier') == identifierref:
                        self.stdout.write(self.style.SUCCESS(f"  ✓ Found matching resource:"))
                        self.stdout.write(f"    identifier: {resource.get('identifier')}")
                        self.stdout.write(f"    href: {resource.get('href', 'N/A')}")
                        self.stdout.write(f"    base: {resource.get('base', 'N/A')}")
                        self.stdout.write(f"    type: {resource.get('type', 'N/A')}")
                        break
                else:
                    self.stdout.write(self.style.ERROR(f"  ✗ No resource found with identifierref: {identifierref}"))
            
            # Show first few resources
            self.stdout.write(f"\nFirst 5 resources:")
            for i, resource in enumerate(resources[:5]):
                self.stdout.write(f"  Resource {i+1}:")
                self.stdout.write(f"    identifier: {resource.get('identifier', 'N/A')}")
                self.stdout.write(f"    href: {resource.get('href', 'N/A')}")
                self.stdout.write(f"    base: {resource.get('base', 'N/A')}")
            
            # Export full manifest if verbose
            self.stdout.write(f"\n=== Full Manifest (JSON) ===")
            self.stdout.write(json.dumps(manifest, indent=2))
            
        except Topic.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Topic {topic_id} does not exist"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {e}"))
            import traceback
            traceback.print_exc()

