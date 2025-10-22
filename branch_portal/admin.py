from django.contrib import admin
from .models import (
    BranchPortal, Order, OrderItem, Cart, CartItem,
    MainContentSection, FeatureGridSection, FeatureGridItem,
    PreFooterSection, CustomMenuLink, SocialMediaIcon
)

@admin.register(BranchPortal)
class BranchPortalAdmin(admin.ModelAdmin):
    list_display = ('branch', 'business_name', 'slug', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('branch__name', 'business_name', 'slug')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Branch Information', {
            'fields': ('branch', 'business_name', 'slug', 'is_active')
        }),
        ('Branding', {
            'fields': ('logo', 'banner_image', 'primary_color', 'secondary_color', 'font_family')
        }),
        ('Contact Information', {
            'fields': ('address_line1', 'address_line2', 'city', 'state_province', 
                      'postal_code', 'country', 'phone', 'email')
        }),
        ('Content', {
            'fields': ('welcome_message', 'about_text')
        }),
        ('Social Media', {
            'fields': ('facebook_url', 'twitter_url', 'instagram_url', 'linkedin_url')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    prepopulated_fields = {'slug': ('business_name',)}

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('subtotal', 'total')

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'user', 'branch', 'status', 'payment_status', 
                   'total', 'created_at')
    list_filter = ('status', 'payment_status', 'created_at', 'branch')
    search_fields = ('order_number', 'user__username', 'user__email', 'branch__name')
    readonly_fields = ('order_number', 'created_at', 'updated_at', 'paid_at', 'completed_at')
    inlines = [OrderItemInline]
    fieldsets = (
        ('Order Information', {
            'fields': ('order_number', 'user', 'branch', 'status', 'payment_status')
        }),
        ('Financial Details', {
            'fields': ('subtotal', 'discount_amount', 'tax_amount', 'total', 'coupon_code')
        }),
        ('Payment Information', {
            'fields': ('transaction_id', 'payment_method')
        }),
        ('Notes', {
            'fields': ('admin_notes', 'user_notes')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'paid_at', 'completed_at')
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if request.user.role == 'admin':
            return qs.filter(branch=request.user.branch)
        return qs.none()

class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ('subtotal', 'total')

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('user', 'total_items', 'total', 'created_at')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at', 'total_items', 'subtotal', 
                      'total_discount', 'total')
    inlines = [CartItemInline]
    fieldsets = (
        ('Cart Information', {
            'fields': ('user', 'total_items')
        }),
        ('Totals', {
            'fields': ('subtotal', 'total_discount', 'total')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )


@admin.register(MainContentSection)
class MainContentSectionAdmin(admin.ModelAdmin):
    list_display = ('portal', 'title', 'order', 'is_active', 'created_at')
    list_filter = ('is_active', 'portal', 'created_at')
    search_fields = ('title', 'description', 'portal__business_name')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Section Information', {
            'fields': ('portal', 'title', 'description', 'order', 'is_active')
        }),
        ('Media', {
            'fields': ('image', 'video', 'video_url')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    list_editable = ('order', 'is_active')
    ordering = ('portal', 'order')


class FeatureGridItemInline(admin.TabularInline):
    model = FeatureGridItem
    extra = 3
    max_num = 3  # Maximum 3 items per row
    fields = ('title', 'description', 'image', 'link_url', 'link_text', 'order', 'is_active')
    ordering = ('order',)


@admin.register(FeatureGridSection)
class FeatureGridSectionAdmin(admin.ModelAdmin):
    list_display = ('portal', 'section_title', 'order', 'is_active', 'created_at')
    list_filter = ('is_active', 'portal', 'created_at')
    search_fields = ('section_title', 'section_description', 'portal__business_name')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [FeatureGridItemInline]
    fieldsets = (
        ('Section Information', {
            'fields': ('portal', 'section_title', 'section_description', 'order', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    list_editable = ('order', 'is_active')
    ordering = ('portal', 'order')


@admin.register(FeatureGridItem)
class FeatureGridItemAdmin(admin.ModelAdmin):
    list_display = ('feature_section', 'title', 'order', 'is_active', 'created_at')
    list_filter = ('is_active', 'feature_section__portal', 'created_at')
    search_fields = ('title', 'description', 'feature_section__portal__business_name')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Item Information', {
            'fields': ('feature_section', 'title', 'description', 'order', 'is_active')
        }),
        ('Media & Link', {
            'fields': ('image', 'link_url', 'link_text')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    list_editable = ('order', 'is_active')
    ordering = ('feature_section', 'order')


class CustomMenuLinkInline(admin.TabularInline):
    model = CustomMenuLink
    extra = 1
    fields = ('title', 'url', 'order', 'is_active')
    ordering = ('order',)


class SocialMediaIconInline(admin.TabularInline):
    model = SocialMediaIcon
    extra = 1
    fields = ('platform_name', 'icon', 'url', 'order', 'is_active')
    ordering = ('order',)


@admin.register(PreFooterSection)
class PreFooterSectionAdmin(admin.ModelAdmin):
    list_display = ('portal', 'is_active', 'created_at')
    list_filter = ('is_active', 'portal', 'created_at')
    search_fields = ('description', 'portal__business_name')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [CustomMenuLinkInline, SocialMediaIconInline]
    fieldsets = (
        ('Pre-Footer Information', {
            'fields': ('portal', 'description', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )


@admin.register(CustomMenuLink)
class CustomMenuLinkAdmin(admin.ModelAdmin):
    list_display = ('pre_footer', 'title', 'url', 'order', 'is_active')
    list_filter = ('is_active', 'pre_footer__portal', 'created_at')
    search_fields = ('title', 'url', 'pre_footer__portal__business_name')
    readonly_fields = ('created_at',)
    fieldsets = (
        ('Link Information', {
            'fields': ('pre_footer', 'title', 'url', 'order', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at',)
        }),
    )
    list_editable = ('order', 'is_active')
    ordering = ('pre_footer', 'order')


@admin.register(SocialMediaIcon)
class SocialMediaIconAdmin(admin.ModelAdmin):
    list_display = ('pre_footer', 'platform_name', 'url', 'order', 'is_active')
    list_filter = ('is_active', 'pre_footer__portal', 'created_at')
    search_fields = ('platform_name', 'url', 'pre_footer__portal__business_name')
    readonly_fields = ('created_at',)
    fieldsets = (
        ('Icon Information', {
            'fields': ('pre_footer', 'platform_name', 'icon', 'url', 'order', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at',)
        }),
    )
    list_editable = ('order', 'is_active')
    ordering = ('pre_footer', 'order')
