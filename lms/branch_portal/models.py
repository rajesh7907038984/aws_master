from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify
from django.urls import reverse
from decimal import Decimal

from branches.models import Branch
from users.models import CustomUser
from courses.models import Course

class BranchPortal(models.Model):
    """Model for branch custom landing pages"""
    branch = models.OneToOneField(
        Branch,
        on_delete=models.CASCADE,
        related_name='portal',
        help_text="The branch this portal belongs to"
    )
    # Branding
    logo = models.ImageField(
        upload_to='branch_portals/logos/',
        null=True,
        blank=True,
        help_text="Branch business logo"
    )
    business_name = models.CharField(
        max_length=255,
        help_text="Business name to display on the landing page"
    )
    # Contact Information
    address_line1 = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Address line 1"
    )
    address_line2 = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Address line 2"
    )
    city = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="City"
    )
    state_province = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="State/Province"
    )
    postal_code = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="Postal/Zip code"
    )
    country = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Country"
    )
    phone = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Contact phone number"
    )
    email = models.EmailField(
        null=True,
        blank=True,
        help_text="Contact email address"
    )
    
    # Theme Settings
    primary_color = models.CharField(
        max_length=20,
        default="#3B82F6",
        help_text="Primary color (Hex code)"
    )
    secondary_color = models.CharField(
        max_length=20,
        default="#1E40AF",
        help_text="Secondary color (Hex code)"
    )
    font_family = models.CharField(
        max_length=100,
        default="Inter, sans-serif",
        help_text="Font family"
    )
    
    # Content
    welcome_message = models.TextField(
        null=True,
        blank=True,
        help_text="Welcome message displayed at the top of the landing page"
    )
    about_text = models.TextField(
        null=True,
        blank=True,
        help_text="About section text"
    )
    
    # Banner Image
    banner_image = models.ImageField(
        upload_to='branch_portals/banners/',
        null=True,
        blank=True,
        help_text="Banner image for the landing page"
    )
    
    # Banner Text
    banner_text = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Text to display over the banner image"
    )
    
    # URL/Permalink Settings
    slug = models.SlugField(
        max_length=255,
        unique=True,
        help_text="URL slug for the landing page"
    )
    
    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this portal is active"
    )
    
    # Social Media Links
    facebook_url = models.URLField(
        null=True,
        blank=True,
        help_text="Facebook URL"
    )
    twitter_url = models.URLField(
        null=True,
        blank=True,
        help_text="Twitter URL"
    )
    instagram_url = models.URLField(
        null=True,
        blank=True,
        help_text="Instagram URL"
    )
    linkedin_url = models.URLField(
        null=True,
        blank=True,
        help_text="LinkedIn URL"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Branch Portal"
        verbose_name_plural = "Branch Portals"
    
    def __str__(self):
        return f"{self.branch.name} Portal"
    
    def save(self, *args, **kwargs):
        # Generate slug if not provided
        if not self.slug:
            base_slug = slugify(self.branch.name)
            slug = base_slug
            counter = 1
            
            # Make sure slug is unique
            while BranchPortal.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            
            self.slug = slug
        
        super().save(*args, **kwargs)
    
    def get_absolute_url(self):
        return reverse('branch_portal:portal_landing', kwargs={'slug': self.slug})

class Order(models.Model):
    """Model for managing course enrollment orders"""
    ORDER_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending Payment'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
        ('waived', 'Payment Waived'),
    ]
    
    # Order identification
    order_number = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique order number"
    )
    
    # User information
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='orders',
        help_text="User who placed the order"
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        related_name='orders',
        help_text="Branch associated with this order"
    )
    
    # Status fields
    status = models.CharField(
        max_length=20,
        choices=ORDER_STATUS_CHOICES,
        default='pending',
        help_text="Current status of the order"
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='pending',
        help_text="Payment status"
    )
    
    # Financial information
    subtotal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text="Order subtotal before discounts"
    )
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text="Discount amount"
    )
    tax_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text="Tax amount"
    )
    total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text="Order total"
    )
    coupon_code = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Coupon code used"
    )
    
    # Transaction details
    transaction_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Payment gateway transaction ID"
    )
    payment_method = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Payment method used"
    )
    
    # Notes
    admin_notes = models.TextField(
        null=True,
        blank=True,
        help_text="Admin notes about this order"
    )
    user_notes = models.TextField(
        null=True,
        blank=True,
        help_text="Notes from the user"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When payment was received"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When order was completed"
    )
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return f"Order {self.order_number} - {self.user.username}"
    
    def save(self, *args, **kwargs):
        # Generate order number if not provided
        if not self.order_number:
            timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
            random_suffix = str(hash(self.user.username + timestamp))[-4:]
            self.order_number = f"ORD-{timestamp}-{random_suffix}"
        
        # Convert tax_amount to Decimal if it's not already
        if not isinstance(self.tax_amount, Decimal):
            self.tax_amount = Decimal(str(self.tax_amount))
        
        # Calculate total
        self.total = self.subtotal - self.discount_amount + self.tax_amount
        
        super().save(*args, **kwargs)
    
    def mark_as_paid(self, transaction_id=None, payment_method=None):
        self.payment_status = 'paid'
        self.paid_at = timezone.now()
        
        if transaction_id:
            self.transaction_id = transaction_id
        
        if payment_method:
            self.payment_method = payment_method
        
        self.save()
    
    def mark_as_completed(self):
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save()
        
        # Enroll user in courses
        for item in self.items.all():
            # Import here to avoid circular imports
            from courses.models import CourseEnrollment
            
            # Check if enrollment already exists
            enrollment, created = CourseEnrollment.objects.get_or_create(
                course=item.course,
                user=self.user
            )
            
            if created:
                # Log enrollment
                print(f"User {self.user.username} enrolled in course {item.course.title}")

class OrderItem(models.Model):
    """Model for individual items in an order"""
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items',
        help_text="Order this item belongs to"
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='order_items',
        help_text="Course being ordered"
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Price at time of order"
    )
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text="Discount amount for this item"
    )
    quantity = models.PositiveIntegerField(
        default=1,
        help_text="Quantity (usually 1 for courses)"
    )
    
    class Meta:
        unique_together = ['order', 'course']
        
    def __str__(self):
        return f"{self.course.title} - {self.order.order_number}"
    
    @property
    def subtotal(self):
        return self.price * self.quantity
    
    @property
    def total(self):
        return self.subtotal - self.discount_amount

class Cart(models.Model):
    """Model for shopping cart"""
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='cart',
        help_text="User who owns this cart"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Cart"
        verbose_name_plural = "Carts"
        
    def __str__(self):
        return f"Cart for {self.user.username}"
    
    @property
    def total_items(self):
        return self.items.count()
    
    @property
    def subtotal(self):
        return sum(item.subtotal for item in self.items.all())
    
    @property
    def total_discount(self):
        return sum(item.discount_amount for item in self.items.all())
    
    @property
    def total(self):
        return self.subtotal - self.total_discount
    
    def add_item(self, course):
        """Add a course to the cart"""
        # Calculate discount if applicable
        discount_amount = 0
        if course.discount_percentage > 0:
            discount_amount = (course.price * (Decimal(course.discount_percentage) / Decimal('100'))).quantize(Decimal('0.01'))
            
        item, created = CartItem.objects.get_or_create(
            cart=self,
            course=course,
            defaults={
                'price': course.price,
                'discount_amount': discount_amount
            }
        )
        
        if not created:
            # Update price and discount in case they changed
            item.price = course.price
            if course.discount_percentage > 0:
                item.discount_amount = (course.price * (Decimal(course.discount_percentage) / Decimal('100'))).quantize(Decimal('0.01'))
            else:
                item.discount_amount = 0
            item.save()
        
        return item
    
    def remove_item(self, course):
        """Remove a course from the cart"""
        try:
            item = self.items.get(course=course)
            item.delete()
            return True
        except CartItem.DoesNotExist:
            return False
    
    def clear(self):
        """Remove all items from the cart"""
        self.items.all().delete()
    
    def create_order(self, branch):
        """Create an order from cart items"""
        if not self.items.exists():
            raise ValueError("Cannot create order with empty cart")
        
        # Create the order
        order = Order.objects.create(
            user=self.user,
            branch=branch,
            subtotal=self.subtotal,
            discount_amount=self.total_discount,
            total=self.total
        )
        
        # Add items to the order
        for cart_item in self.items.all():
            OrderItem.objects.create(
                order=order,
                course=cart_item.course,
                price=cart_item.price,
                discount_amount=cart_item.discount_amount
            )
        
        # Clear the cart
        self.clear()
        
        return order

class CartItem(models.Model):
    """Model for individual items in a cart"""
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name='items',
        help_text="Cart this item belongs to"
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='cart_items',
        help_text="Course in the cart"
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Price at time of adding to cart"
    )
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text="Discount amount for this item"
    )
    added_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['cart', 'course']
        
    def __str__(self):
        return f"{self.course.title} in {self.cart}"
    
    @property
    def subtotal(self):
        return self.price
    
    @property
    def total(self):
        return self.subtotal - self.discount_amount


class MainContentSection(models.Model):
    """Model for main content sections with title, description, image and video"""
    portal = models.ForeignKey(
        BranchPortal,
        on_delete=models.CASCADE,
        related_name='main_content_sections',
        help_text="The portal this section belongs to"
    )
    title = models.CharField(
        max_length=255,
        help_text="Section title"
    )
    description = models.TextField(
        help_text="Section description/content"
    )
    image = models.ImageField(
        upload_to='branch_portals/main_content/',
        null=True,
        blank=True,
        help_text="Section image"
    )
    video = models.FileField(
        upload_to='branch_portals/main_content_videos/',
        null=True,
        blank=True,
        help_text="Section video (mp4, avi, mov, wmv)"
    )
    video_url = models.URLField(
        null=True,
        blank=True,
        help_text="External video URL (YouTube, Vimeo, etc.)"
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Order of display"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this section is active"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'created_at']
        verbose_name = "Main Content Section"
        verbose_name_plural = "Main Content Sections"
    
    def __str__(self):
        return f"{self.portal.business_name} - {self.title}"


class FeatureGridSection(models.Model):
    """Model for feature grid sections with 3-column layout"""
    portal = models.ForeignKey(
        BranchPortal,
        on_delete=models.CASCADE,
        related_name='feature_grid_sections',
        help_text="The portal this section belongs to"
    )
    section_title = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Optional section title"
    )
    section_description = models.TextField(
        null=True,
        blank=True,
        help_text="Optional section description"
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Order of display"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this section is active"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'created_at']
        verbose_name = "Feature Grid Section"
        verbose_name_plural = "Feature Grid Sections"
    
    def __str__(self):
        return f"{self.portal.business_name} - Feature Grid {self.id}"


class FeatureGridItem(models.Model):
    """Model for individual items in feature grid (3 per row)"""
    feature_section = models.ForeignKey(
        FeatureGridSection,
        on_delete=models.CASCADE,
        related_name='items',
        help_text="The feature section this item belongs to"
    )
    title = models.CharField(
        max_length=255,
        help_text="Feature title"
    )
    description = models.TextField(
        help_text="Feature description"
    )
    image = models.ImageField(
        upload_to='branch_portals/feature_grid/',
        null=True,
        blank=True,
        help_text="Feature image"
    )
    link_url = models.URLField(
        null=True,
        blank=True,
        help_text="Custom link URL"
    )
    link_text = models.CharField(
        max_length=100,
        default="Learn More",
        help_text="Custom link button text"
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Order within the grid"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this item is active"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'created_at']
        verbose_name = "Feature Grid Item"
        verbose_name_plural = "Feature Grid Items"
    
    def __str__(self):
        return f"{self.feature_section} - {self.title}"


class PreFooterSection(models.Model):
    """Model for pre-footer section configuration"""
    portal = models.OneToOneField(
        BranchPortal,
        on_delete=models.CASCADE,
        related_name='pre_footer',
        help_text="The portal this pre-footer belongs to"
    )
    # Column 1 - Logo and description (auto-loads website logo)
    description = models.TextField(
        null=True,
        blank=True,
        help_text="Short description to display with logo"
    )
    
    # Configuration
    is_active = models.BooleanField(
        default=True,
        help_text="Whether pre-footer is active"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Pre-Footer Section"
        verbose_name_plural = "Pre-Footer Sections"
    
    def __str__(self):
        return f"{self.portal.business_name} - Pre-Footer"


class CustomMenuLink(models.Model):
    """Model for custom menu links in pre-footer (Column 2)"""
    pre_footer = models.ForeignKey(
        PreFooterSection,
        on_delete=models.CASCADE,
        related_name='menu_links',
        help_text="The pre-footer this link belongs to"
    )
    title = models.CharField(
        max_length=100,
        help_text="Link title/text"
    )
    url = models.URLField(
        help_text="Link URL"
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Order of display"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this link is active"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['order', 'created_at']
        verbose_name = "Custom Menu Link"
        verbose_name_plural = "Custom Menu Links"
    
    def __str__(self):
        return f"{self.pre_footer} - {self.title}"


class SocialMediaIcon(models.Model):
    """Model for social media icons in pre-footer (Column 3)"""
    pre_footer = models.ForeignKey(
        PreFooterSection,
        on_delete=models.CASCADE,
        related_name='social_icons',
        help_text="The pre-footer this icon belongs to"
    )
    platform_name = models.CharField(
        max_length=50,
        help_text="Platform name (e.g., Facebook, Twitter, Instagram)"
    )
    icon = models.ImageField(
        upload_to='branch_portals/social_icons/',
        null=True,
        blank=True,
        help_text="Custom social media icon (SVG, PNG preferred)"
    )
    url = models.URLField(
        help_text="Social media profile URL"
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Order of display"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this icon is active"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['order', 'created_at']
        verbose_name = "Social Media Icon"
        verbose_name_plural = "Social Media Icons"
    
    def __str__(self):
        return f"{self.pre_footer} - {self.platform_name}"
