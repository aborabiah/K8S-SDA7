from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from .models import KubernetesCluster, ChatSession, CommandHistory
import json
import yaml
import uuid
import subprocess
import tempfile
import os
from kubernetes import client, config
from kubernetes.client.rest import ApiException


def index(request):
    """Render the main chat interface."""
    clusters = KubernetesCluster.objects.filter(is_active=True)
    return render(request, 'chat/index.html', {'clusters': clusters})


@csrf_exempt
@require_http_methods(["POST"])
def create_cluster(request):
    """Create a new Kubernetes cluster configuration."""
    try:
        data = json.loads(request.body)
        cluster_name = data.get('name', '').strip()
        kubeconfig_content = data.get('kubeconfig', '').strip()
        
        if not cluster_name or not kubeconfig_content:
            return JsonResponse({
                'success': False, 
                'error': 'Both cluster name and kubeconfig are required'
            })
        
        # Validate kubeconfig format
        try:
            kubeconfig_data = yaml.safe_load(kubeconfig_content)
            if not isinstance(kubeconfig_data, dict) or 'clusters' not in kubeconfig_data:
                raise ValueError("Invalid kubeconfig format")
        except (yaml.YAMLError, ValueError) as e:
            return JsonResponse({
                'success': False, 
                'error': f'Invalid kubeconfig format: {str(e)}'
            })
        
        # Create cluster object
        cluster = KubernetesCluster.objects.create(
            name=cluster_name,
            kubeconfig=kubeconfig_content
        )
        
        # Test connection
        connection_result = test_cluster_connection(cluster)
        cluster.connection_status = connection_result['status']
        cluster.connection_error = connection_result.get('error', '')
        cluster.last_connection_check = timezone.now()
        cluster.save()
        
        if connection_result['status'] == 'connected':
            # Create a chat session
            session_id = str(uuid.uuid4())
            chat_session = ChatSession.objects.create(
                cluster=cluster,
                session_id=session_id,
                name=f"{cluster_name} Terminal"
            )
            
            return JsonResponse({
                'success': True,
                'cluster_id': cluster.id,
                'session_id': session_id,
                'message': 'Cluster connected successfully!'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': f'Failed to connect to cluster: {connection_result.get("error", "Unknown error")}'
            })
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Server error: {str(e)}'
        })


def test_cluster_connection(cluster):
    """Test connection to a Kubernetes cluster."""
    try:
        # Create a temporary kubeconfig file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(cluster.kubeconfig)
            kubeconfig_path = f.name
        
        try:
            # Load the kubeconfig
            config.load_kube_config(config_file=kubeconfig_path)
            
            # Test connection by getting cluster info
            v1 = client.CoreV1Api()
            v1.list_namespace(limit=1)
            
            return {'status': 'connected'}
            
        except ApiException as e:
            return {'status': 'error', 'error': f'API Error: {e.reason}'}
        except Exception as e:
            return {'status': 'error', 'error': str(e)}
        finally:
            # Clean up temp file
            os.unlink(kubeconfig_path)
            
    except Exception as e:
        return {'status': 'error', 'error': f'Configuration error: {str(e)}'}


@csrf_exempt
@require_http_methods(["POST"])
def execute_command(request, session_id):
    """Execute a kubectl command for a specific chat session."""
    try:
        chat_session = get_object_or_404(ChatSession, session_id=session_id)
        data = json.loads(request.body)
        command = data.get('command', '').strip()
        
        if not command:
            return JsonResponse({
                'success': False,
                'error': 'Command is required'
            })
        
        # Handle help command
        if command.strip() == 'help':
            help_text = """Available commands:
• ls, cat, mkdir, rm - File operations
• vim <filename> - Edit files with vim
• nano <filename> - Edit files with nano  
• wget <url> - Download files
• kubectl - Kubernetes commands
• clear - Clear terminal
• pwd, cd - Navigation
• All standard Linux commands supported

Navigation:
• ↑↓ Arrow keys - Command history
• Tab - Auto completion (coming soon)

Vim shortcuts:
• ESC - Normal mode
• i - Insert mode
• :w - Save file
• :q - Quit
• :wq - Save and quit"""
            
            # Store help command in history
            CommandHistory.objects.create(
                chat_session=chat_session,
                command=command,
                output=help_text,
                exit_code=0
            )
            
            return JsonResponse({
                'success': True,
                'output': help_text,
                'exit_code': 0
            })
        
        # Handle clear command
        if command.strip() == 'clear':
            return JsonResponse({
                'success': True,
                'output': '',
                'clear': True
            })
        
        # Allow all commands - let them run naturally and show their output/errors
        
        # Execute command with the cluster's kubeconfig
        result = execute_shell_command(chat_session.cluster, command)
        
        # Store command history
        CommandHistory.objects.create(
            chat_session=chat_session,
            command=command,
            output=result['output'],
            exit_code=result['exit_code']
        )
        
        # Update session last activity
        chat_session.last_activity = timezone.now()
        chat_session.save()
        
        return JsonResponse({
            'success': True,
            'output': result['output'],
            'exit_code': result['exit_code']
        })
        
    except ChatSession.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Chat session not found'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error executing command: {str(e)}'
        })


def execute_shell_command(cluster, command):
    """Execute a shell command. For kubectl commands, use the cluster's kubeconfig."""
    try:
        # Create a temporary kubeconfig file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(cluster.kubeconfig)
            kubeconfig_path = f.name
        
        try:
            # Set environment variables for command execution
            env = os.environ.copy()
            
            # Only set KUBECONFIG for kubectl commands
            if command.strip().startswith('kubectl'):
                env['KUBECONFIG'] = kubeconfig_path
            
            result = subprocess.run(
                command,
                shell=True,  # Use shell to support complex commands with pipes, etc.
                capture_output=True,
                text=True,
                env=env,
                timeout=30,  # Shorter timeout - most commands should complete quickly
                cwd=os.path.expanduser('~'),  # Start in home directory
                stdin=subprocess.PIPE  # Allow stdin for interactive commands
            )
            
            output = result.stdout
            if result.stderr:
                output += f"\nError: {result.stderr}"
            
            return {
                'output': output,
                'exit_code': result.returncode
            }
            
        finally:
            # Clean up temp file
            os.unlink(kubeconfig_path)
            
    except subprocess.TimeoutExpired:
        return {
            'output': 'Command timed out after 30 seconds (use Ctrl+C to interrupt)',
            'exit_code': 124
        }
    except Exception as e:
        return {
            'output': f'Error executing command: {str(e)}',
            'exit_code': 1
        }


@require_http_methods(["GET"])
def get_chat_history(request, session_id):
    """Get command history for a chat session."""
    try:
        chat_session = get_object_or_404(ChatSession, session_id=session_id)
        history = CommandHistory.objects.filter(chat_session=chat_session).order_by('timestamp')
        
        history_data = [{
            'command': cmd.command,
            'output': cmd.output,
            'exit_code': cmd.exit_code,
            'timestamp': cmd.timestamp.isoformat()
        } for cmd in history]
        
        return JsonResponse({
            'success': True,
            'history': history_data,
            'cluster_name': chat_session.cluster.name
        })
        
    except ChatSession.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Chat session not found'
        })


@require_http_methods(["GET"])
def list_clusters(request):
    """List all active clusters."""
    clusters = KubernetesCluster.objects.filter(is_active=True)
    clusters_data = [{
        'id': cluster.id,
        'name': cluster.name,
        'connection_status': cluster.connection_status,
        'created_at': cluster.created_at.isoformat(),
        'chat_sessions': [{
            'id': session.id,
            'session_id': session.session_id,
            'name': session.name,
            'last_activity': session.last_activity.isoformat()
        } for session in cluster.chat_sessions.filter(is_active=True)]
    } for cluster in clusters]
    
    return JsonResponse({
        'success': True,
        'clusters': clusters_data
    }) 