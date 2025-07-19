from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    path('', views.index, name='index'),
    path('clusters/create/', views.create_cluster, name='create_cluster'),
    path('clusters/', views.list_clusters, name='list_clusters'),
    path('terminal/<str:session_id>/execute/', views.execute_command, name='execute_command'),
    path('terminal/<str:session_id>/history/', views.get_chat_history, name='get_chat_history'),
] 