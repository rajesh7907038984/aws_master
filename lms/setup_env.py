#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Environment Setup Script for LMS Project
This script helps create a proper .env file with all required variables.
"""

import os
import secrets
import string
from pathlib import Path

def generate_secret_key():
    """Generate a secure Django secret key"""
    chars = string.ascii_letters + string.digits + '!@#$%^&*(-_=+)'
    return ''.join(secrets.choice(chars) for _ in range(50))

def create_env_file():
    """Create a .env file with default values"""
    project_root = Path(__file__).parent
    env_file = project_root / '.env'
    env_example = project_root / 'env.example'
    
    if env_file.exists():
        response = input("Do you want to overwrite it? (y/N): ").strip().lower()
        if response != 'y':
            print("CANCELLED: No changes made.")
            return
    
    # Generate a new secret key
    secret_key = generate_secret_key()
    
    # Read the example file
    if env_example.exists():
        with open(env_example, 'r') as f:
            content = f.read()
        
        # Replace placeholder values
        content = content.replace('your-secret-key-here', secret_key)
        content = content.replace('your-database-host.amazonaws.com', 'localhost')
        content = content.replace('your-database-password', 'your_secure_password_here')
        content = content.replace('your-s3-bucket-name', 'your-s3-bucket-name')
        content = content.replace('your-access-key-id', 'your-aws-access-key-id')
        content = content.replace('your-secret-access-key', 'your-aws-secret-access-key')
        content = content.replace('noreply@yourdomain.com', 'noreply@example.com')
        
        # Write the .env file
        with open(env_file, 'w') as f:
            f.write(content)
        
        print(f"SUCCESS: Created .env file at {env_file}")
        print(f"SECRET_KEY: {secret_key[:20]}...")
        print("\nNext steps:")
        print("1. Edit the .env file with your actual configuration values")
        print("2. Set up your database credentials")
        print("3. Configure AWS S3 settings for production")
        print("4. Set up email configuration")
        print("5. Never commit the .env file to version control")
        
    else:
        print(f"❌ Example file not found at {env_example}")
        print("Please ensure env.example exists in the project root")

def validate_env_file():
    """Validate that the .env file has all required variables"""
    project_root = Path(__file__).parent
    env_file = project_root / '.env'
    
    if not env_file.exists():
        print(f"❌ .env file not found at {env_file}")
        return False
    
    required_vars = [
        'DJANGO_SECRET_KEY',
        'DJANGO_ENV',
        'DEBUG',
    ]
    
    missing_vars = []
    
    with open(env_file, 'r') as f:
        content = f.read()
        for var in required_vars:
            if f"{var}=" not in content:
                missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ Missing required variables: {', '.join(missing_vars)}")
        return False
    
    print("✅ .env file validation passed")
    return True

def main():
    """Main function"""
    print("🚀 LMS Environment Setup Script")
    print("=" * 40)
    
    while True:
        print("\nOptions:")
        print("1. Create .env file from template")
        print("2. Validate existing .env file")
        print("3. Exit")
        
        choice = input("\nEnter your choice (1-3): ").strip()
        
        if choice == '1':
            create_env_file()
        elif choice == '2':
            validate_env_file()
        elif choice == '3':
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice. Please enter 1, 2, or 3.")

if __name__ == "__main__":
    main()
