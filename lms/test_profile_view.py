from django.shortcuts import render

def test_profile_dropdown(request):
    return render(request, 'test_profile_simple.html')
