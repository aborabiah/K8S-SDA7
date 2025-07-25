from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    path('', views.index, name='index'),
    path('clusters/create/', views.create_cluster, name='create_cluster'),
    path('clusters/', views.list_clusters, name='list_clusters'),
    path('clusters/<int:cluster_id>/rename/', views.rename_cluster, name='rename_cluster'),
    path('clusters/<int:cluster_id>/kubeconfig/', views.get_kubeconfig, name='get_kubeconfig'),
    path('clusters/<int:cluster_id>/update-kubeconfig/', views.update_kubeconfig, name='update_kubeconfig'),
    path('clusters/<int:cluster_id>/status/', views.check_cluster_status, name='check_cluster_status'),
    path('clusters/<int:cluster_id>/delete/', views.delete_cluster, name='delete_cluster'),
    path('terminal/<str:session_id>/', views.terminal_view, name='terminal'),
    path('terminal/<str:session_id>/execute/', views.execute_command, name='execute_command'),
    path('terminal/<str:session_id>/ai-debug/', views.debug_kubectl_ai, name='debug_kubectl_ai'),
    path('terminal/<str:session_id>/history/', views.get_chat_history, name='get_chat_history'),
    path('terminal/<str:session_id>/clear-history/', views.clear_history, name='clear_history'),
    path('terminal/<str:session_id>/status/', views.container_status, name='container_status'),
] 