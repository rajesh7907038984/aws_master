#!/usr/bin/env python3
"""
Fix environment variables script
This script updates the .env file to replace placeholder values with proper configurations
"""

import os
import re

def fix_env_file():
    """Fix the .env file by replacing placeholder values"""
    
    env_file = '/home/ec2-user/lms/.env'
    
    if not os.path.exists(env_file):
        print(f"❌ .env file not found at {env_file}")
        return False
    
    # Read the current .env file
    with open(env_file, 'r') as f:
        content = f.read()
    
    # Define replacements
    replacements = {
        'ANTHROPIC_API_KEY=your_anthropic_api_key': 'ANTHROPIC_API_KEY=disabled',
        'OUTLOOK_CLIENT_ID=your_outlook_client_id': '# OUTLOOK_CLIENT_ID=your_outlook_client_id',
        'OUTLOOK_CLIENT_SECRET=your_outlook_client_secret': '# OUTLOOK_CLIENT_SECRET=your_outlook_client_secret',
        'OUTLOOK_TENANT_ID=your_outlook_tenant_id': '# OUTLOOK_TENANT_ID=your_outlook_tenant_id',
        'IDEAL_POSTCODES_API_KEY=your_postcodes_api_key': '# IDEAL_POSTCODES_API_KEY=your_postcodes_api_key',
        'REDIS_URL=redis://127.0.0.1:6379/0': '# REDIS_URL=redis://127.0.0.1:6379/0',
        'ENABLE_AI_FEATURES=True': 'ENABLE_AI_FEATURES=False',
    }
    
    # Apply replacements
    modified = False
    for old, new in replacements.items():
        if old in content:
            content = content.replace(old, new)
            modified = True
            print(f"✅ Fixed: {old}")
    
    # Write the updated content back
    if modified:
        with open(env_file, 'w') as f:
            f.write(content)
        print("✅ Environment file updated successfully")
        return True
    else:
        print("ℹ️  No changes needed")
        return True

if __name__ == "__main__":
    print("🔧 Fixing environment variables...")
    success = fix_env_file()
    if success:
        print("✅ Environment variables fixed successfully")
    else:
        print("❌ Failed to fix environment variables")
