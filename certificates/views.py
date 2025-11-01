from django.shortcuts import render
import os
import uuid
import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.conf import settings
from django.utils import timezone
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import base64
from django.contrib import messages
from django.template.loader import render_to_string
from django.db import models
from django.http import HttpResponseRedirect
from django.contrib.staticfiles.storage import staticfiles_storage

from .models import CertificateTemplate, CertificateElement, IssuedCertificate
from users.models import CustomUser
from core.utils.business_filtering import get_superadmin_business_filter
from core.utils.pdf_processor import get_weasyprint
from role_management.utils import require_capability, require_any_capability, PermissionManager

logger = logging.getLogger(__name__)

@login_required
@require_capability('view_certificates_templates')
def certificates_view(request):
    """View for displaying the certificates list."""
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'label': 'Certificates', 'icon': 'fa-certificate'}
    ]
    
    # For regular users/learners, only show their certificates
    if request.user.role in ['learner', 'student']:
        issued_certificates = IssuedCertificate.objects.filter(recipient=request.user)
        
        return render(request, 'certificates/learner_certificates.html', {
            'breadcrumbs': breadcrumbs,
            'issued_certificates': issued_certificates
        })
    
    # For admins and other roles, show the template management UI
    # Global admin can see all templates
    if request.user.is_superuser or request.user.role == 'globaladmin':
        templates = CertificateTemplate.objects.filter(is_active=True)
    # Superadmins can only see templates created by users within their assigned businesses
    elif request.user.role == 'superadmin':
        assigned_businesses = get_superadmin_business_filter(request.user)
        if assigned_businesses:
            # Get users from branches within assigned businesses
            business_users = CustomUser.objects.filter(
                branch__business__in=assigned_businesses
            )
            templates = CertificateTemplate.objects.filter(
                created_by__in=business_users,
                is_active=True
            )
        else:
            templates = CertificateTemplate.objects.none()
    # Admin can see templates from users in their branch
    elif request.user.role == 'admin' and request.user.branch:
        # Get all users in the admin's branch
        branch_users = CustomUser.objects.filter(branch=request.user.branch)
        templates = CertificateTemplate.objects.filter(
            created_by__in=branch_users,
            is_active=True
        )
    # Instructors have no certificate template access (per role management capabilities)
    elif request.user.role == 'instructor':
        templates = CertificateTemplate.objects.none()
    # Regular users can only see their own templates
    else:
        templates = CertificateTemplate.objects.filter(
            created_by=request.user,
            is_active=True
        )
    
    # For issued certificates, users should only see their own
    issued_certificates = IssuedCertificate.objects.filter(recipient=request.user)
    
    # Determine if user can create certificate templates
    can_create_templates = PermissionManager.user_has_capability(request.user, 'manage_certificates')
    
    return render(request, 'certificates/certificates.html', {
        'breadcrumbs': breadcrumbs,
        'templates': templates,
        'issued_certificates': issued_certificates,
        'can_create_templates': can_create_templates,
    })

@login_required
@require_capability('view_certificates_templates')
def templates_view(request):
    """View for displaying the certificate templates list."""
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('certificates:certificates'), 'label': 'Certificates', 'icon': 'fa-certificate'},
        {'label': 'Templates', 'icon': 'fa-file-image'}
    ]
    
    # Global admin can see all templates
    if request.user.is_superuser or request.user.role == 'globaladmin':
        templates = CertificateTemplate.objects.filter(is_active=True).order_by('-created_at')
    # Superadmins can only see templates created by users within their assigned businesses
    elif request.user.role == 'superadmin':
        assigned_businesses = get_superadmin_business_filter(request.user)
        if assigned_businesses:
            # Get users from branches within assigned businesses
            business_users = CustomUser.objects.filter(
                branch__business__in=assigned_businesses
            )
            templates = CertificateTemplate.objects.filter(
                created_by__in=business_users,
                is_active=True
            ).order_by('-created_at')
        else:
            templates = CertificateTemplate.objects.none()
    # Admin can see templates from users in their branch
    elif request.user.role == 'admin' and request.user.branch:
        # Get all users in the admin's branch
        branch_users = CustomUser.objects.filter(branch=request.user.branch)
        templates = CertificateTemplate.objects.filter(
            created_by__in=branch_users,
            is_active=True
        ).order_by('-created_at')
    # Instructors have no certificate template access (per role management capabilities)
    elif request.user.role == 'instructor':
        templates = CertificateTemplate.objects.none()
    # Regular users can only see their own templates
    else:
        templates = CertificateTemplate.objects.filter(
            created_by=request.user,
            is_active=True
        ).order_by('-created_at')
    
    return render(request, 'certificates/templates.html', {
        'breadcrumbs': breadcrumbs,
        'templates': templates
    })

@login_required
def create_template(request):
    """View for creating a new certificate template. Redirects to main certificates page."""
    # This page is not needed anymore, redirect to certificates main page
    return redirect('certificates:certificates')

@login_required
@require_capability('view_certificates_templates')
def preview_certificate(request, template_id):
    """View for previewing a certificate before issuing."""
    template = get_object_or_404(CertificateTemplate, id=template_id)
    
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('certificates:certificates'), 'label': 'Certificates', 'icon': 'fa-certificate'},
        {'label': f'Preview {template.name}', 'icon': 'fa-eye'}
    ]
    
    # Get all template elements
    elements = CertificateElement.objects.filter(template=template)
    
    # Get all potential recipients
    users = CustomUser.objects.all()
    
    return render(request, 'certificates/preview_certificate.html', {
        'breadcrumbs': breadcrumbs,
        'template': template,
        'elements': elements,
        'users': users
    })

@login_required
@require_capability('manage_certificates')
@require_POST
def generate_certificate(request, template_id):
    """API endpoint to generate a certificate for a user."""
    template = get_object_or_404(CertificateTemplate, id=template_id)
    
    try:
        # Get form data
        recipient_id = request.POST.get('recipient')
        course_name = request.POST.get('course_name', '')
        grade = request.POST.get('grade', '')
        
        # Verify recipient
        recipient = get_object_or_404(CustomUser, id=recipient_id)
        
        # Generate unique certificate number
        certificate_number = f"CERT-{uuid.uuid4().hex[:8].upper()}"
        
        # Calculate expiry date based on template validity_days
        expiry_date = None
        if template.validity_days > 0:
            from datetime import timedelta
            expiry_date = timezone.now() + timedelta(days=template.validity_days)
        
        # Create issued certificate record
        certificate = IssuedCertificate.objects.create(
            template=template,
            recipient=recipient,
            issued_by=request.user,
            course_name=course_name,
            grade=grade,
            certificate_number=certificate_number,
            expiry_date=expiry_date
        )
        
        # Generate certificate file
        # Certificate generation logic
        # will be handled in the frontend with a canvas and save to server
        
        return redirect('certificates:view_certificate', certificate_id=certificate.id)
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)

@login_required
def view_certificate(request, certificate_id):
    """View for displaying an issued certificate."""
    try:
        certificate = get_object_or_404(IssuedCertificate, id=certificate_id)
        
        # Check if user has permission to view
        if (certificate.recipient != request.user and 
            certificate.issued_by != request.user and 
            not request.user.is_superuser and 
            request.user.role not in ['globaladmin', 'superadmin']):
            messages.error(request, "You don't have permission to view this certificate.")
            return redirect('certificates:certificates')
        
        # Check if we need to generate a PDF certificate
        if request.GET.get('generate') == 'true':
            try:
                # If certificate file already exists, redirect directly to it
                if certificate.certificate_file:
                    return redirect(certificate.certificate_file.url)
                    
                # Otherwise, create filename and path
                filename = f"certificate_{certificate.certificate_number}.pdf"
                file_path = f"issued_certificates/{timezone.now().strftime('%Y/%m/%d')}/{filename}"
                
                # Generate HTML for certificate
                context = {
                    'certificate': certificate,
                    'elements': CertificateElement.objects.filter(template=certificate.template),
                    'generate_pdf': True,
                    # No need for a landscape flag as we're always using landscape
                }
                html = render_to_string('certificates/view_certificate.html', context)
                
                # Generate PDF using weasyprint with landscape orientation
                HTML, CSS = get_weasyprint()
                if HTML is None or CSS is None:
                    messages.error(request, "PDF generation is not available. Please contact your administrator.")
                    return redirect('certificates:view_certificate', certificate_id=certificate_id)
                
                # Create CSS for landscape orientation - always use A4 landscape
                page_css = CSS(string='''
                    @page { 
                        size: A4 landscape; 
                        margin: 0; 
                    }
                    
                    /* Color correction for WeasyPrint 44 - preserve exact colors */
                    * {
                        -webkit-print-color-adjust: exact !important;
                        print-color-adjust: exact !important;
                        color-adjust: exact !important;
                    }
                    
                    img {
                        -webkit-print-color-adjust: exact !important;
                        print-color-adjust: exact !important;
                        color-rendering: optimizeQuality !important;
                        image-rendering: -webkit-optimize-contrast !important;
                    }
                    
                    .field-placeholder {
                        position: absolute !important;
                        background: transparent !important;
                        border: none !important;
                        z-index: 100 !important;
                        display: flex !important;
                        align-items: center !important;
                        justify-content: center !important;
                        transform: translate(-50%, -50%) !important;
                        text-align: center !important;
                        padding: 0 !important;
                        width: auto !important;
                    }
                    
                    /* Ensure fields appear exactly as styled in template */
                    .field-placeholder[data-element-type="name"],
                    .field-placeholder[data-element-type="course"],
                    .field-placeholder[data-element-type="grade"],
                    .field-placeholder[data-element-type="certificate_id"],
                    .field-placeholder[data-element-type="text"],
                    .field-placeholder[data-element-type="signature"] {
                        transform: translate(-50%, -50%) !important;
                    }
                ''')
                
                # Include the PDF-specific stylesheet to avoid WeasyPrint warnings
                pdf_css = CSS(filename=staticfiles_storage.path('core/css/pdf-print.css'))
                
                # Generate PDF with landscape orientation
                pdf_file = HTML(string=html, base_url=request.build_absolute_uri('/')).write_pdf(
                    stylesheets=[page_css, pdf_css],
                    presentational_hints=True
                )
                
                # Save to storage
                path = default_storage.save(file_path, ContentFile(pdf_file))
                
                # Update certificate record
                certificate.certificate_file.name = path
                certificate.save()
                
                # Redirect directly to the PDF file
                return redirect(certificate.certificate_file.url)
                
            except Exception as e:
                messages.error(request, f"Error generating certificate: {str(e)}")
    
    except Exception as e:
        messages.error(request, f"Error viewing certificate: {str(e)}")
    
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('certificates:certificates'), 'label': 'Certificates', 'icon': 'fa-certificate'},
        {'label': f'Certificate #{certificate.certificate_number}', 'icon': 'fa-file-pdf'}
    ]
    
    # Get template elements
    elements = CertificateElement.objects.filter(template=certificate.template)
    
    return render(request, 'certificates/view_certificate.html', {
        'breadcrumbs': breadcrumbs,
        'certificate': certificate,
        'elements': elements
    })

@login_required
@require_POST
def save_certificate_image(request, certificate_id):
    """API endpoint to save the certificate image data."""
    certificate = get_object_or_404(IssuedCertificate, id=certificate_id)
    
    try:
        # Get image data from POST
        image_data = request.POST.get('image_data')
        if not image_data:
            return JsonResponse({
                'status': 'error',
                'message': 'No image data provided.'
            }, status=400)
        
        # Remove header from base64 data
        if ',' in image_data:
            header, image_data = image_data.split(',', 1)
        
        # Decode base64 data
        image_binary = base64.b64decode(image_data)
        
        # Check if a custom path was provided
        custom_path = request.POST.get('file_path')
        if custom_path:
            # Sanitize the custom path to prevent directory traversal
            import os.path
            # Remove any directory traversal attempts
            safe_path = os.path.basename(custom_path.replace('..', '').replace('/', '').replace('\\', ''))
            # Only allow alphanumeric, hyphens, underscores, and periods
            safe_path = ''.join(c for c in safe_path if c.isalnum() or c in '-_.')
            if safe_path:
                file_path = f"issued_certificates/{timezone.now().strftime('%Y/%m/%d')}/{safe_path}"
                # Make sure it has the correct file extension
                if not file_path.endswith('.pdf'):
                    file_path = f"{file_path}.pdf"
            else:
                # Fallback to default if path is invalid
                filename = f"certificate_{certificate.certificate_number}.pdf"
                file_path = f"issued_certificates/{timezone.now().strftime('%Y/%m/%d')}/{filename}"
        else:
            # Generate default filename and path using date structure
            filename = f"certificate_{certificate.certificate_number}.pdf"
            file_path = f"issued_certificates/{timezone.now().strftime('%Y/%m/%d')}/{filename}"
        
        # Save file to storage (directory creation is handled by storage backend)
        path = default_storage.save(file_path, ContentFile(image_binary))
        
        # Update certificate record
        certificate.certificate_file.name = path
        certificate.save()
        
        return JsonResponse({
            'status': 'success',
            'url': certificate.certificate_file.url
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)

@login_required
@require_capability('manage_certificates')
def save_template(request):
    """API endpoint to save a certificate template."""
    
    # Handle GET requests by redirecting to certificates page
    if request.method == 'GET':
        return redirect('certificates:certificates')
    
    if request.method != 'POST':
        return JsonResponse({
            'status': 'error',
            'message': 'Method not allowed'
        }, status=405)
    
    try:
        # Get form data
        name = request.POST.get('name', '')
        fields_json = request.POST.get('fields', '[]')
        validity_days = request.POST.get('validity_days', '0')
        
        # Parse fields JSON
        fields = json.loads(fields_json)
        
        # Verify required fields
        if not name:
            messages.error(request, 'Template name is required')
            return redirect('certificates:certificates')
        
        if not fields:
            messages.error(request, 'No fields added to the template')
            return redirect('certificates:certificates')
        
        # Convert validity_days to int
        try:
            validity_days = int(validity_days)
        except (ValueError, TypeError):
            validity_days = 0
        
        # Create template record
        template = CertificateTemplate.objects.create(
            name=name,
            created_by=request.user,
            validity_days=validity_days
        )
        
        # Process image upload
        if 'image' in request.FILES:
            image = request.FILES['image']
            template.image = image
            template.save()
        
        # Create elements for each field
        for field in fields:
            element = CertificateElement.objects.create(
                template=template,
                element_type=field['type'],
                label=field['type'].capitalize(),  # Use field type as label
                position_x=field['x'],
                position_y=field['y'],
                font_family=field.get('fontFamily', 'Arial, sans-serif'),
                font_size=int(field.get('fontSize', '14px').replace('px', '')),
                font_weight=field.get('fontWeight', 'normal'),
                color=field.get('fontColor', '#000000')
            )
        
        messages.success(request, 'Certificate template created successfully')
        return redirect('certificates:certificates')
        
    except Exception as e:
        messages.error(request, f'Error creating template: {str(e)}')
        return redirect('certificates:certificates')

@login_required
def get_template_data(request, template_id):
    """API endpoint to get template data for editing."""
    try:
        template = get_object_or_404(CertificateTemplate, id=template_id)
        
        # Serialize template data
        template_data = {
            'id': template.id,
            'name': template.name,
            'image': template.image.url if template.image else None,
            'created_by': template.created_by.id,
            'validity_days': template.validity_days,
            'is_active': template.is_active,
            'created_at': template.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Get elements
        elements = CertificateElement.objects.filter(template=template)
        element_data = []
        
        for element in elements:
            element_data.append({
                'id': element.id,
                'element_type': element.element_type,
                'label': element.label,
                'position_x': element.position_x,
                'position_y': element.position_y,
                'width': element.width,
                'height': element.height,
                'font_size': element.font_size,
                'font_family': element.font_family,
                'font_weight': element.font_weight,
                'color': element.color,
                'default_value': element.default_value
            })
        
        return JsonResponse({
            'status': 'success',
            'template': template_data,
            'elements': element_data
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)

@login_required
@require_POST
def update_template(request, template_id):
    """API endpoint to update an existing certificate template."""
    try:
        # Get template object
        template = get_object_or_404(CertificateTemplate, id=template_id)
        
        # Check if user has permission to edit
        has_permission = False
        
        # Global admin can edit all templates
        if request.user.is_superuser or request.user.role == 'globaladmin':
            has_permission = True
        # Superadmins can only edit templates created by users within their assigned businesses
        elif request.user.role == 'superadmin':
            assigned_businesses = get_superadmin_business_filter(request.user)
            if assigned_businesses and template.created_by.branch and template.created_by.branch.business_id in assigned_businesses:
                has_permission = True
        # Template creator always has access
        elif template.created_by == request.user:
            has_permission = True
        # Admins can edit templates created by users in their branch
        elif request.user.role == 'admin' and request.user.branch:
            # Check if template creator is in the same branch as the admin
            if template.created_by.branch == request.user.branch:
                has_permission = True
        
        if not has_permission:
            return JsonResponse({
                'status': 'error',
                'message': 'You do not have permission to edit this template'
            }, status=403)
        
        # Get form data
        name = request.POST.get('name', '')
        fields_json = request.POST.get('fields', '[]')
        validity_days = request.POST.get('validity_days', '0')
        
        # Parse fields JSON
        fields = json.loads(fields_json)
        
        # Verify required fields
        if not name:
            return JsonResponse({
                'status': 'error',
                'message': 'Template name is required'
            }, status=400)
        
        # Convert validity_days to int
        try:
            validity_days = int(validity_days)
        except (ValueError, TypeError):
            validity_days = 0
        
        # Update template data
        template.name = name
        template.validity_days = validity_days
        
        # Process image upload if new image provided
        if 'image' in request.FILES:
            # Delete old image
            if template.image:
                # Delete old file
                try:
                    try:
                        old_image_path = template.image.path
                        if os.path.exists(old_image_path):
                            os.remove(old_image_path)
                    except NotImplementedError:
                        # Cloud storage doesn't support absolute paths, skip local file deletion
                        pass
                except:
                    pass  # Ignore any errors with file deletion
            
            # Save new image
            template.image = request.FILES['image']
        
        template.save()
        
        # Delete existing elements
        CertificateElement.objects.filter(template=template).delete()
        
        # Create elements for each field
        for field in fields:
            element = CertificateElement.objects.create(
                template=template,
                element_type=field['type'],
                label=field['type'].capitalize(),  # Use field type as label
                position_x=field['x'],
                position_y=field['y'],
                font_family=field.get('fontFamily', 'Arial, sans-serif'),
                font_size=int(field.get('fontSize', '14px').replace('px', '')),
                font_weight=field.get('fontWeight', 'normal'),
                color=field.get('fontColor', '#000000')
            )
        
        messages.success(request, 'Certificate template updated successfully')
        return redirect('certificates:certificates')
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)

@login_required
@require_POST
def save_element(request, template_id):
    """API endpoint to save a certificate element."""
    template = get_object_or_404(CertificateTemplate, id=template_id)
    
    # Check if user has permission to edit
    has_permission = False
    
    # Global admin can edit all templates
    if request.user.is_superuser or request.user.role == 'globaladmin':
        has_permission = True
    # Superadmins can only edit templates created by users within their assigned businesses
    elif request.user.role == 'superadmin':
        assigned_businesses = get_superadmin_business_filter(request.user)
        if assigned_businesses and template.created_by.branch and template.created_by.branch.business_id in assigned_businesses:
            has_permission = True
    # Template creator always has access
    elif template.created_by == request.user:
        has_permission = True
    # Admins can access templates created by users in their branch  
    elif request.user.role == 'admin' and request.user.branch:
        # Check if template creator is in the same branch as the admin
        if template.created_by.branch == request.user.branch:
            has_permission = True
    
    if not has_permission:
        return JsonResponse({
            'status': 'error',
            'message': 'You do not have permission to edit this template.'
        }, status=403)
    
    try:
        element_type = request.POST.get('element_type')
        label = request.POST.get('label')
        position_x = float(request.POST.get('position_x', 0))
        position_y = float(request.POST.get('position_y', 0))
        
        element = CertificateElement.objects.create(
            template=template,
            element_type=element_type,
            label=label,
            position_x=position_x,
            position_y=position_y,
            width=20.0,
            height=10.0,
            font_size=14,
            font_family="Arial, sans-serif",
            font_weight="normal",
            color="#000000"
        )
        
        return JsonResponse({
            'status': 'success',
            'element_id': element.id
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)

@login_required
@require_POST
def delete_element(request, element_id):
    """API endpoint to delete a certificate element."""
    element = get_object_or_404(CertificateElement, id=element_id)
    template = element.template
    
    # Check if user has permission to delete
    has_permission = False
    
    # Global admin can delete all templates
    if request.user.is_superuser or request.user.role == 'globaladmin':
        has_permission = True
    # Superadmins can only delete templates created by users within their assigned businesses
    elif request.user.role == 'superadmin':
        assigned_businesses = get_superadmin_business_filter(request.user)
        if assigned_businesses and template.created_by.branch and template.created_by.branch.business_id in assigned_businesses:
            has_permission = True
    # Template creator always has access
    elif template.created_by == request.user:
        has_permission = True
    # Admins can access templates created by users in their branch  
    elif request.user.role == 'admin' and request.user.branch:
        # Check if template creator is in the same branch as the admin
        if template.created_by.branch == request.user.branch:
            has_permission = True
    
    if not has_permission:
        return JsonResponse({
            'status': 'error',
            'message': 'You do not have permission to edit this template.'
        }, status=403)
    
    try:
        element.delete()
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)

@login_required
@require_POST
def delete_template(request, template_id):
    """API endpoint to delete a certificate template."""
    template = get_object_or_404(CertificateTemplate, id=template_id)
    
    # Check if user has permission to delete
    has_permission = False
    
    # Global admin can delete all templates
    if request.user.is_superuser or request.user.role == 'globaladmin':
        has_permission = True
    # Superadmins can only delete templates created by users within their assigned businesses
    elif request.user.role == 'superadmin':
        assigned_businesses = get_superadmin_business_filter(request.user)
        if assigned_businesses and template.created_by.branch and template.created_by.branch.business_id in assigned_businesses:
            has_permission = True
    # Template creator always has access
    elif template.created_by == request.user:
        has_permission = True
    # Admins can delete templates created by users in their branch
    elif request.user.role == 'admin' and request.user.branch:
        # Check if template creator is in the same branch as the admin
        if template.created_by.branch == request.user.branch:
            has_permission = True
    
    if not has_permission:
        messages.error(request, 'You do not have permission to delete this template.')
        return HttpResponseRedirect(reverse('certificates:certificates'))
    
    try:
        # First, check if there are any issued certificates using this template
        issued_certificates = IssuedCertificate.objects.filter(template=template)
        if issued_certificates.exists():
            # Instead of deleting, mark as inactive
            template.is_active = False
            template.save()
            messages.success(request, 'Template marked as inactive because certificates have been issued with it.')
        else:
            # Safe to delete if no certificates have been issued
            template.delete()
            messages.success(request, 'Template deleted successfully.')
        
        # Redirect to certificates page
        return HttpResponseRedirect(reverse('certificates:certificates'))
            
    except Exception as e:
        messages.error(request, f'Error deleting template: {str(e)}')
        return HttpResponseRedirect(reverse('certificates:certificates'))

@login_required
@require_POST
def delete_certificate(request, certificate_id):
    """API endpoint to delete an issued certificate."""
    try:
        logger.info(f"Deleting certificate with ID: {certificate_id}")
        certificate = get_object_or_404(IssuedCertificate, id=certificate_id)
        
        # Check if user has permission to delete
        if certificate.issued_by != request.user and not request.user.is_superuser and request.user.role != 'superadmin':
            messages.error(request, 'You do not have permission to delete this certificate.')
            logger.warning(f"Permission denied for user {request.user.id} to delete certificate {certificate_id}")
            return HttpResponseRedirect(reverse('certificates:certificates'))
        
        certificate_number = certificate.certificate_number
        
        # Delete the certificate file if it exists
        if certificate.certificate_file:
            try:
                if os.path.isfile(certificate.certificate_file.path):
                    os.remove(certificate.certificate_file.path)
            except Exception as e:
                # Log the error but continue with deletion
                logger.error(f"Error removing certificate file: {str(e)}")
        
        # Delete the certificate from the database
        certificate.delete()
        
        messages.success(request, f'Certificate #{certificate_number} has been deleted.')
        # Ensure correct redirection by using reverse to generate the full URL
        redirect_url = reverse('certificates:certificates')
        logger.info(f"Certificate #{certificate_number} deleted successfully by user {request.user.id}")
        return HttpResponseRedirect(redirect_url)
    except Exception as e:
        messages.error(request, f'Error deleting certificate: {str(e)}')
        logger.error(f"Error during certificate deletion: {str(e)}")
        return HttpResponseRedirect(reverse('certificates:certificates'))

@login_required
def regenerate_certificate_file(request, certificate_id):
    """Regenerate a certificate file if it's missing."""
    certificate = get_object_or_404(IssuedCertificate, id=certificate_id)
    
    # Check if user has permission
    if not (request.user.is_superuser or certificate.issued_by == request.user):
        messages.error(request, "You don't have permission to regenerate this certificate.")
        return redirect('certificates:certificates')
    
    try:
        # Check if a custom path was provided
        custom_path = request.GET.get('file_path')
        
        if custom_path:
            # Use the custom path provided
            file_path = custom_path
            # Make sure it has the correct file extension
            if not file_path.endswith('.pdf'):
                file_path = f"{file_path}.pdf"
        else:
            # Create default filename and path
            filename = f"certificate_{certificate.certificate_number}.pdf"
            file_path = f"issued_certificates/{timezone.now().strftime('%Y/%m/%d')}/{filename}"
        
        # Directory creation is handled by storage backend
        
        # Generate HTML for certificate
        context = {
            'certificate': certificate,
            'elements': CertificateElement.objects.filter(template=certificate.template),
            'generate_pdf': True,
        }
        html = render_to_string('certificates/view_certificate.html', context)
        
        # Generate PDF using weasyprint with landscape orientation
        HTML, CSS = get_weasyprint()
        if HTML is None or CSS is None:
            messages.error(request, "PDF generation is not available. Please contact your administrator.")
            return redirect('certificates:certificates')
        
        # Create CSS for landscape orientation - always use A4 landscape
        page_css = CSS(string='''
            @page { 
                size: A4 landscape; 
                margin: 0; 
            }
            
            /* Color correction for WeasyPrint 44 - preserve exact colors */
            * {
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
                color-adjust: exact !important;
            }
            
            img {
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
                color-rendering: optimizeQuality !important;
                image-rendering: -webkit-optimize-contrast !important;
            }
            
            .field-placeholder {
                position: absolute !important;
                background: transparent !important;
                border: none !important;
                z-index: 100 !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                transform: translate(-50%, -50%) !important;
                text-align: center !important;
                padding: 0 !important;
                width: auto !important;
            }
            
            /* Ensure fields appear exactly as styled in template */
            .field-placeholder[data-element-type="name"],
            .field-placeholder[data-element-type="course"],
            .field-placeholder[data-element-type="grade"],
            .field-placeholder[data-element-type="certificate_id"],
            .field-placeholder[data-element-type="text"],
            .field-placeholder[data-element-type="signature"] {
                transform: translate(-50%, -50%) !important;
            }
        ''')
        
        # Include the PDF-specific stylesheet to avoid WeasyPrint warnings
        pdf_css = CSS(filename=staticfiles_storage.path('core/css/pdf-print.css'))
        
        # Generate PDF with landscape orientation
        pdf_file = HTML(string=html, base_url=request.build_absolute_uri('/')).write_pdf(
            stylesheets=[page_css, pdf_css],
            presentational_hints=True
        )
        
        # Save to storage
        path = default_storage.save(file_path, ContentFile(pdf_file))
        
        # Update certificate record
        certificate.certificate_file.name = path
        certificate.save()
        
        messages.success(request, f"Certificate #{certificate.certificate_number} has been regenerated successfully.")
        
    except Exception as e:
        messages.error(request, f"Error regenerating certificate: {str(e)}")
    
    # Redirect back to referrer or certificates list
    return redirect(request.META.get('HTTP_REFERER', reverse('certificates:certificates')))
