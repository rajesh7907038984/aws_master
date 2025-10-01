from django.urls import path
from . import views

app_name = 'certificates'

urlpatterns = [
    path('', views.certificates_view, name='certificates'),
    path('', views.certificates_view, name='certificate_list'),  # Alias for consistency
    path('create/', views.certificates_view, name='certificate_create'),  # Alias for consistency
    path('templates/', views.templates_view, name='templates'),
    path('templates/<int:template_id>/save-element/', views.save_element, name='save_element'),
    path('templates/<int:template_id>/data/', views.get_template_data, name='get_template_data'),
    path('templates/<int:template_id>/update/', views.update_template, name='update_template'),
    path('templates/<int:template_id>/delete/', views.delete_template, name='delete_template'),
    path('elements/<int:element_id>/delete/', views.delete_element, name='delete_element'),
    path('templates/<int:template_id>/generate/', views.generate_certificate, name='generate_certificate'),
    path('templates/<int:template_id>/preview/', views.preview_certificate, name='preview_certificate'),
    path('view/<int:certificate_id>/', views.view_certificate, name='view_certificate'),
    path('delete/<int:certificate_id>/', views.delete_certificate, name='delete_certificate'),
    path('save-image/<int:certificate_id>/', views.save_certificate_image, name='save_certificate_image'),
    path('save-template/', views.save_template, name='save_template'),
    path('regenerate/<int:certificate_id>/', views.regenerate_certificate_file, name='regenerate_certificate'),
] 