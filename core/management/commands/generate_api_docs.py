"""
Generate comprehensive API documentation for 100% Frontend-Backend Alignment
"""

from django.core.management.base import BaseCommand
from django.urls import get_resolver
from django.conf import settings
import os
import json
import re
from typing import Dict, List, Any

class Command(BaseCommand):
    help = 'Generate comprehensive API documentation for frontend-backend alignment'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            type=str,
            default='api_documentation.json',
            help='Output file for API documentation'
        )
        parser.add_argument(
            '--format',
            type=str,
            choices=['json', 'markdown', 'html'],
            default='json',
            help='Output format for documentation'
        )

    def handle(self, *args, **options):
        self.stdout.write('🔍 Analyzing API endpoints for documentation...')
        
        # Get all URL patterns
        resolver = get_resolver()
        api_endpoints = self.extract_api_endpoints(resolver)
        
        # Generate documentation
        if options['format'] == 'json':
            self.generate_json_docs(api_endpoints, options['output'])
        elif options['format'] == 'markdown':
            self.generate_markdown_docs(api_endpoints, options['output'])
        elif options['format'] == 'html':
            self.generate_html_docs(api_endpoints, options['output'])
        
        self.stdout.write(
            self.style.SUCCESS(f'✅ API documentation generated: {options["output"]}')
        )

    def extract_api_endpoints(self, resolver, namespace=''):
        """Extract all API endpoints from URL resolver"""
        endpoints = []
        
        for pattern in resolver.url_patterns:
            if hasattr(pattern, 'url_patterns'):
                # Namespace
                sub_endpoints = self.extract_api_endpoints(
                    pattern, 
                    f"{namespace}:{pattern.namespace}" if pattern.namespace else namespace
                )
                endpoints.extend(sub_endpoints)
            else:
                # Individual URL pattern
                if 'api' in str(pattern.pattern):
                    endpoint = {
                        'url': str(pattern.pattern),
                        'name': pattern.name,
                        'namespace': namespace,
                        'methods': self.get_supported_methods(pattern),
                        'description': self.get_endpoint_description(pattern),
                        'parameters': self.get_endpoint_parameters(pattern),
                        'response_format': self.get_response_format(pattern),
                        'authentication_required': self.requires_authentication(pattern),
                        'csrf_protection': self.requires_csrf(pattern)
                    }
                    endpoints.append(endpoint)
        
        return endpoints

    def get_supported_methods(self, pattern):
        """Determine supported HTTP methods for endpoint"""
        # This would need to be enhanced to read from view decorators
        return ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']

    def get_endpoint_description(self, pattern):
        """Get description from view or generate default"""
        return f"API endpoint: {pattern.name or 'unnamed'}"

    def get_endpoint_parameters(self, pattern):
        """Extract parameters from URL pattern"""
        params = []
        url_str = str(pattern.pattern)
        
        # Extract path parameters
        path_params = re.findall(r'<(\w+):(\w+)>', url_str)
        for param_name, param_type in path_params:
            params.append({
                'name': param_name,
                'type': param_type,
                'location': 'path',
                'required': True,
                'description': f'{param_name} parameter'
            })
        
        return params

    def get_response_format(self, pattern):
        """Get expected response format"""
        return {
            'success': {
                'success': True,
                'status': 'success',
                'message': 'string',
                'data': 'object|array',
                'timestamp': 'string (ISO 8601)',
                'version': 'string'
            },
            'error': {
                'success': False,
                'status': 'error',
                'message': 'string',
                'errors': 'object',
                'error_code': 'string (optional)',
                'details': 'object (optional)',
                'timestamp': 'string (ISO 8601)',
                'version': 'string'
            }
        }

    def requires_authentication(self, pattern):
        """Check if endpoint requires authentication"""
        return True  # Most API endpoints require auth

    def requires_csrf(self, pattern):
        """Check if endpoint requires CSRF protection"""
        return True  # Most API endpoints require CSRF

    def generate_json_docs(self, endpoints, output_file):
        """Generate JSON documentation"""
        docs = {
            'api_version': '1.0.0',
            'generated_at': '2025-01-27T00:00:00Z',
            'total_endpoints': len(endpoints),
            'endpoints': endpoints,
            'response_formats': {
                'standard_success': {
                    'success': True,
                    'status': 'success',
                    'message': 'string',
                    'data': 'object|array',
                    'timestamp': 'string (ISO 8601)',
                    'version': 'string'
                },
                'standard_error': {
                    'success': False,
                    'status': 'error',
                    'message': 'string',
                    'errors': 'object',
                    'error_code': 'string (optional)',
                    'details': 'object (optional)',
                    'timestamp': 'string (ISO 8601)',
                    'version': 'string'
                }
            },
            'error_codes': {
                'VALIDATION_ERROR': 'Form validation failed',
                'UNAUTHORIZED': 'Authentication required',
                'FORBIDDEN': 'Access denied',
                'NOT_FOUND': 'Resource not found',
                'SERVER_ERROR': 'Internal server error',
                'INVALID_RESPONSE_FORMAT': 'Response format does not match API specification'
            },
            'authentication': {
                'type': 'Session-based with CSRF protection',
                'csrf_token': 'Required for all non-GET requests',
                'session_cookie': 'lms_sessionid'
            }
        }
        
        with open(output_file, 'w') as f:
            json.dump(docs, f, indent=2)

    def generate_markdown_docs(self, endpoints, output_file):
        """Generate Markdown documentation"""
        md_content = f"""# LMS API Documentation

Generated for 100% Frontend-Backend Alignment

## Overview
- **API Version**: 1.0.0
- **Total Endpoints**: {len(endpoints)}
- **Authentication**: Session-based with CSRF protection
- **Response Format**: Standardized JSON

## Standard Response Format

### Success Response
```json
{{
    "success": true,
    "status": "success",
    "message": "string",
    "data": "object|array",
    "timestamp": "string (ISO 8601)",
    "version": "string"
}}
```

### Error Response
```json
{{
    "success": false,
    "status": "error",
    "message": "string",
    "errors": "object",
    "error_code": "string (optional)",
    "details": "object (optional)",
    "timestamp": "string (ISO 8601)",
    "version": "string"
}}
```

## API Endpoints

"""
        
        for endpoint in endpoints:
            md_content += f"""### {endpoint['name'] or 'Unnamed Endpoint'}

- **URL**: `{endpoint['url']}`
- **Methods**: {', '.join(endpoint['methods'])}
- **Authentication**: {'Required' if endpoint['authentication_required'] else 'Not required'}
- **CSRF Protection**: {'Required' if endpoint['csrf_protection'] else 'Not required'}

**Description**: {endpoint['description']}

**Parameters**:
"""
            for param in endpoint['parameters']:
                md_content += f"- `{param['name']}` ({param['type']}): {param['description']}\n"
            
            md_content += "\n---\n\n"
        
        with open(output_file, 'w') as f:
            f.write(md_content)

    def generate_html_docs(self, endpoints, output_file):
        """Generate HTML documentation"""
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LMS API Documentation</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
        .endpoint {{ border: 1px solid #ddd; margin: 20px 0; padding: 20px; border-radius: 5px; }}
        .method {{ background: #007bff; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px; }}
        .url {{ font-family: monospace; background: #f8f9fa; padding: 5px; border-radius: 3px; }}
        pre {{ background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto; }}
    </style>
</head>
<body>
    <h1>LMS API Documentation</h1>
    <p><strong>API Version:</strong> 1.0.0</p>
    <p><strong>Total Endpoints:</strong> {len(endpoints)}</p>
    <p><strong>Authentication:</strong> Session-based with CSRF protection</p>
    
    <h2>Standard Response Format</h2>
    <h3>Success Response</h3>
    <pre><code>{{
    "success": true,
    "status": "success",
    "message": "string",
    "data": "object|array",
    "timestamp": "string (ISO 8601)",
    "version": "string"
}}</code></pre>
    
    <h3>Error Response</h3>
    <pre><code>{{
    "success": false,
    "status": "error",
    "message": "string",
    "errors": "object",
    "error_code": "string (optional)",
    "details": "object (optional)",
    "timestamp": "string (ISO 8601)",
    "version": "string"
}}</code></pre>
    
    <h2>API Endpoints</h2>
"""
        
        for endpoint in endpoints:
            methods_html = ' '.join([f'<span class="method">{method}</span>' for method in endpoint['methods']])
            html_content += f"""
    <div class="endpoint">
        <h3>{endpoint['name'] or 'Unnamed Endpoint'}</h3>
        <p><strong>URL:</strong> <span class="url">{endpoint['url']}</span></p>
        <p><strong>Methods:</strong> {methods_html}</p>
        <p><strong>Authentication:</strong> {'Required' if endpoint['authentication_required'] else 'Not required'}</p>
        <p><strong>CSRF Protection:</strong> {'Required' if endpoint['csrf_protection'] else 'Not required'}</p>
        <p><strong>Description:</strong> {endpoint['description']}</p>
        <h4>Parameters:</h4>
        <ul>
"""
            for param in endpoint['parameters']:
                html_content += f"            <li><code>{param['name']}</code> ({param['type']}): {param['description']}</li>\n"
            
            html_content += "        </ul>\n    </div>\n"
        
        html_content += """
</body>
</html>"""
        
        with open(output_file, 'w') as f:
            f.write(html_content)
