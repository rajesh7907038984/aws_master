from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.utils.text import slugify
from branches.models import Branch
from .models import BranchPortal, Cart

User = get_user_model()

@receiver(post_save, sender=Branch)
def create_branch_portal(sender, instance, created, **kwargs):
    """Create a BranchPortal when a new Branch is created"""
    if created:
        # Auto-create portal with default settings
        # Use slugify to properly handle special characters including periods
        base_slug = slugify(instance.name)
        slug = base_slug
        counter = 1
        
        # Ensure slug is unique
        while BranchPortal.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        BranchPortal.objects.create(
            branch=instance,
            business_name=instance.name,
            slug=slug
        )

@receiver(post_save, sender=User)
def create_user_cart(sender, instance, created, **kwargs):
    """Create a Cart when a new User is created"""
    if created:
        Cart.objects.create(user=instance) 