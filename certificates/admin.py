from django.contrib import admin
from .models import CertificateTemplate, CertificateElement, IssuedCertificate

class CertificateElementInline(admin.TabularInline):
    model = CertificateElement
    extra = 1

@admin.register(CertificateTemplate)
class CertificateTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_by', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'description')
    inlines = [CertificateElementInline]

@admin.register(CertificateElement)
class CertificateElementAdmin(admin.ModelAdmin):
    list_display = ('label', 'element_type', 'template', 'created_at')
    list_filter = ('element_type', 'created_at')
    search_fields = ('label', 'template__name')

@admin.register(IssuedCertificate)
class IssuedCertificateAdmin(admin.ModelAdmin):
    list_display = ('certificate_number', 'recipient', 'template', 'issue_date', 'is_revoked')
    list_filter = ('is_revoked', 'issue_date')
    search_fields = ('certificate_number', 'recipient__username', 'recipient__email', 'course_name')
    date_hierarchy = 'issue_date'
