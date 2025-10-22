from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

# Authentication URLs that can be used both globally and branch-specifically
# These URLs are included in the main URLconf with optional branch_slug parameter

urlpatterns = [
    # Login URLs
    path('login/', views.branch_login, name='branch_login'),
    # Note: logout is handled at the global level in main urls.py
    path('verify-otp/', views.verify_otp, name='verify_otp_branch'),
    
    # Registration URLs  
    path('register/', views.register, name='register'),
    
    # Password Reset URLs
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('reset-password/<uuid:token>/', views.reset_password, name='reset_password'),
    
    # Email Verification URLs
    path('verify-email/<uuid:token>/', views.verify_email, name='verify_email'),
    path('resend-verification/', views.resend_verification, name='resend_verification'),
    
    # Success/Status pages
    path('verification-sent/', views.verification_sent, name='verification_sent'),
    path('verification-success/', views.verification_success, name='verification_success'),
    path('password-reset-sent/', views.password_reset_sent, name='password_reset_sent'),
    path('password-reset-success/', views.password_reset_success, name='password_reset_success'),
] 