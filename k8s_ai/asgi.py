"""
ASGI config for k8s_ai project.
"""

import os
import django
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'k8s_ai.settings')
django.setup()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from chat.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})