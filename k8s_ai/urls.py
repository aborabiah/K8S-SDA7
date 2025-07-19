"""
URL configuration for k8s_ai project.
"""
from django.contrib import admin
from django.urls import path, include
 
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('chat.urls')),
] 