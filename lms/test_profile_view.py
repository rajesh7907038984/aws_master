from django.shortcuts import render
from django.http import HttpResponse

def test_profile_dropdown_fixed(request):
    """Test view for the fixed profile dropdown"""
    return render(request, 'test_profile_dropdown_fixed.html')
