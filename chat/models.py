from django.db import models
from django.contrib.auth.models import User
import json


class KubernetesCluster(models.Model):
    """Model to store Kubernetes cluster configurations."""
    name = models.CharField(max_length=100)
    kubeconfig = models.TextField()  # Store the kubeconfig as JSON/YAML text
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    last_connection_check = models.DateTimeField(null=True, blank=True)
    connection_status = models.CharField(
        max_length=20,
        choices=[
            ('connected', 'Connected'),
            ('disconnected', 'Disconnected'),
            ('error', 'Error'),
            ('pending', 'Pending'),
        ],
        default='pending'
    )
    connection_error = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.connection_status})"


class ChatSession(models.Model):
    """Model to store individual chat sessions with clusters."""
    cluster = models.ForeignKey(KubernetesCluster, on_delete=models.CASCADE, related_name='chat_sessions')
    session_id = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-last_activity']

    def __str__(self):
        return f"{self.name} - {self.cluster.name}"


class CommandHistory(models.Model):
    """Model to store command history for each chat session."""
    chat_session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='command_history')
    command = models.TextField()
    output = models.TextField()
    exit_code = models.IntegerField(default=0)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.chat_session.name}: {self.command[:50]}..." 