#!/usr/bin/env python3
"""
Create Test SCORM Package
Creates a minimal SCORM 1.2 package for testing
"""
import os
import sys
import django
import zipfile
import tempfile
from pathlib import Path

# Setup Django environment
sys.path.insert(0, '/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from scorm.models import ScormPackage
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

def create_test_scorm_package():
    """Create a minimal test SCORM package"""
    print("🔧 Creating test SCORM package...")
    
    # Create temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create basic SCORM structure
        scorm_dir = temp_path / "scorm_test"
        scorm_dir.mkdir()
        
        # Create imsmanifest.xml
        manifest_content = '''<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="test_scorm_package" version="1.2" 
          xmlns="http://www.imsglobal.org/xsd/imscp_v1p1"
          xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_v1p3"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://www.imsglobal.org/xsd/imscp_v1p1 imscp_v1p1.xsd
                              http://www.adlnet.org/xsd/adlcp_v1p3 adlcp_v1p3.xsd">
    <metadata>
        <schema>ADL SCORM</schema>
        <schemaversion>1.2</schemaversion>
    </metadata>
    <organizations default="test_org">
        <organization identifier="test_org">
            <title>Test SCORM Course</title>
            <item identifier="item_1" identifierref="resource_1">
                <title>Test Lesson</title>
                <adlcp:masteryscore>80</adlcp:masteryscore>
            </item>
        </organization>
    </organizations>
    <resources>
        <resource identifier="resource_1" type="webcontent" adlcp:scormtype="sco" href="index.html">
            <file href="index.html"/>
            <file href="scormdriver.js"/>
        </resource>
    </resources>
</manifest>'''
        
        with open(scorm_dir / "imsmanifest.xml", "w") as f:
            f.write(manifest_content)
        
        # Create index.html
        index_content = '''<!DOCTYPE html>
<html>
<head>
    <title>Test SCORM Course</title>
    <script src="scormdriver.js"></script>
</head>
<body>
    <h1>Test SCORM Course</h1>
    <p>This is a test SCORM package.</p>
    <button onclick="testScorm()">Test SCORM API</button>
    <div id="status"></div>
    
    <script>
        function testScorm() {
            if (typeof API !== 'undefined') {
                API.Initialize("");
                API.SetValue("cmi.core.lesson_status", "incomplete");
                API.SetValue("cmi.core.lesson_location", "test_location");
                API.Commit("");
                document.getElementById('status').innerHTML = 'SCORM API working!';
            } else {
                document.getElementById('status').innerHTML = 'SCORM API not found';
            }
        }
    </script>
</body>
</html>'''
        
        with open(scorm_dir / "index.html", "w") as f:
            f.write(index_content)
        
        # Create scormdriver.js (minimal SCORM API)
        scormdriver_content = '''// Minimal SCORM API for testing
var API = {
    Initialize: function(param) { return "true"; },
    Terminate: function(param) { return "true"; },
    GetValue: function(element) { return ""; },
    SetValue: function(element, value) { return "true"; },
    Commit: function(param) { return "true"; },
    GetLastError: function() { return "0"; },
    GetErrorString: function(code) { return "No error"; },
    GetDiagnostic: function(code) { return "No error"; }
};'''
        
        with open(scorm_dir / "scormdriver.js", "w") as f:
            f.write(scormdriver_content)
        
        # Create ZIP file
        zip_path = temp_path / "test_scorm.zip"
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in scorm_dir.rglob('*'):
                if file_path.is_file():
                    arcname = file_path.relative_to(scorm_dir)
                    zipf.write(file_path, arcname)
        
        print(f"✅ Created test SCORM package: {zip_path}")
        return zip_path

def upload_and_extract_package():
    """Upload and extract the test package"""
    print("📤 Uploading and extracting test package...")
    
    try:
        # Get existing package
        package = ScormPackage.objects.first()
        if not package:
            print("❌ No SCORM package found")
            return False
        
        # Create test package
        zip_path = create_test_scorm_package()
        
        # Read the ZIP file
        with open(zip_path, 'rb') as f:
            zip_content = f.read()
        
        # Upload to S3
        package_file_name = f"scorm_packages/test_scorm_{package.id}.zip"
        package.package_file.save(package_file_name, ContentFile(zip_content))
        
        print(f"✅ Uploaded package to S3: {package_file_name}")
        
        # Now extract it
        from scorm.parser import ScormParser
        parser = ScormParser(package.package_file)
        package_data = parser.parse()
        
        # Update package with extracted data
        package.extracted_path = package_data['extracted_path']
        package.launch_url = package_data['launch_url']
        package.manifest_data = package_data['manifest_data']
        package.mastery_score = package_data.get('mastery_score')
        package.save()
        
        print(f"✅ Package extracted successfully")
        print(f"   Extracted Path: {package.extracted_path}")
        print(f"   Launch URL: {package.launch_url}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error uploading/extracting package: {e}")
        return False

def verify_extraction():
    """Verify the package was extracted correctly"""
    print("🔍 Verifying extraction...")
    
    try:
        package = ScormPackage.objects.first()
        
        # Check if extracted path exists
        if default_storage.exists(package.extracted_path):
            print(f"✅ Extracted path exists: {package.extracted_path}")
        else:
            print(f"❌ Extracted path does not exist: {package.extracted_path}")
            return False
        
        # Check if launch file exists
        launch_file_path = f"{package.extracted_path}/{package.launch_url}"
        if default_storage.exists(launch_file_path):
            print(f"✅ Launch file exists: {package.launch_url}")
        else:
            print(f"❌ Launch file does not exist: {package.launch_url}")
            return False
        
        # List some files in the extracted directory
        try:
            dirs, files = default_storage.listdir(package.extracted_path)
            print(f"✅ Found {len(files)} files in extracted directory")
            for file in files[:5]:  # Show first 5 files
                print(f"   - {file}")
        except Exception as e:
            print(f"⚠️  Could not list directory contents: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error verifying extraction: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("CREATING TEST SCORM PACKAGE")
    print("=" * 60)
    
    if upload_and_extract_package():
        if verify_extraction():
            print("\n🎉 Test SCORM package created and extracted successfully!")
        else:
            print("\n⚠️  Package created but extraction verification failed")
    else:
        print("\n❌ Failed to create test SCORM package")
