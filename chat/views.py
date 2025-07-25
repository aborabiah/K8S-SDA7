from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from .models import KubernetesCluster, ChatSession, CommandHistory
import json
import yaml
import uuid
import tempfile
import os
import docker
import base64
import time
import io
import tarfile
import threading
import queue
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Global dictionary to store active containers
active_containers = {}

# Global dictionary to store active kubectl-ai sessions
active_ai_sessions = {}

# Docker image name
KUBECTL_IMAGE_NAME = "your-kubectl-image:latest"

def ensure_docker_image():
    """Ensure the kubectl Docker image exists, build it if it doesn't"""
    try:
        docker_client = docker.from_env()
    except docker.errors.DockerException as e:
        print(f"❌ Docker connection error: {e}")
        return False
        
    try:
        # Check if image exists
        try:
            docker_client.images.get(KUBECTL_IMAGE_NAME)
            print(f"✅ Docker image {KUBECTL_IMAGE_NAME} already exists")
            return True
        except docker.errors.ImageNotFound:
            print(f"🔨 Building Docker image {KUBECTL_IMAGE_NAME}...")
            return build_docker_image(docker_client)
            
    except Exception as e:
        print(f"❌ Error checking Docker image: {e}")
        return False

def build_docker_image(docker_client):
    """Build the kubectl Docker image"""
    try:
        # Create Dockerfile content
        dockerfile_content = """FROM alpine:3.18

# Install tools + download both binaries in one layer
RUN apk add --no-cache curl tar ca-certificates bash vim nano expect \\
    && curl -sSL https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl \\
       -o /usr/local/bin/kubectl \\
    && chmod +x /usr/local/bin/kubectl \\
    && curl -sSL https://github.com/GoogleCloudPlatform/kubectl-ai/releases/download/v0.0.18/kubectl-ai_Linux_x86_64.tar.gz \\
       | tar -xz -C /usr/local/bin \\
    && chmod +x /usr/local/bin/kubectl-ai

# Create kube directory
RUN mkdir -p /root/.kube

# Set working directory
WORKDIR /root

# Set environment variables
ENV TERM=xterm-256color
ENV KUBECONFIG=/root/.kube/config

# Keep container running
CMD ["/bin/sh"]
"""
        
        # Create a tar archive in memory with the Dockerfile
        dockerfile_tar = io.BytesIO()
        with tarfile.open(fileobj=dockerfile_tar, mode='w') as tar:
            dockerfile_info = tarfile.TarInfo(name='Dockerfile')
            dockerfile_info.size = len(dockerfile_content.encode('utf-8'))
            tar.addfile(dockerfile_info, io.BytesIO(dockerfile_content.encode('utf-8')))
        
        dockerfile_tar.seek(0)
        
        print("🔨 Starting Docker image build...")
        
        # Build the image
        image, build_logs = docker_client.images.build(
            fileobj=dockerfile_tar,
            custom_context=True,
            tag=KUBECTL_IMAGE_NAME,
            rm=True,
            nocache=False
        )
        
        # Print build logs
        for log in build_logs:
            if 'stream' in log:
                print(f"🔨 {log['stream'].strip()}")
        
        print(f"✅ Successfully built Docker image: {KUBECTL_IMAGE_NAME}")
        
        # Test the image
        test_container = docker_client.containers.run(
            image=KUBECTL_IMAGE_NAME,
            command="kubectl version --client",
            remove=True,
            detach=False
        )
        
        print("✅ Docker image test successful")
        return True
        
    except Exception as e:
        print(f"❌ Error building Docker image: {e}")
        return False


class KubectlAiSession:
    """Manage kubectl-ai sessions"""
    
    def __init__(self, container_manager, session_id):
        self.container_manager = container_manager
        self.session_id = session_id
        self.is_active = False
        self.conversation_history = []
        
    def start_session(self):
        """Start a kubectl-ai session"""
        try:
            print(f"🤖 Starting kubectl-ai session for {self.session_id}")
            
            # Get GEMINI_API_KEY from environment
            gemini_api_key = os.getenv('GEMINI_API_KEY')
            if not gemini_api_key:
                return {
                    'success': False,
                    'error': '❌ GEMINI_API_KEY not configured. Please check your environment variables.'
                }
            
            # Test kubectl-ai is working
            test_result = self.container_manager.execute_command('echo $GEMINI_API_KEY | wc -c')
            if test_result['exit_code'] != 0 or int(test_result['output'].strip()) < 10:
                return {
                    'success': False,
                    'error': '❌ GEMINI_API_KEY not properly configured in container.'
                }
            
            self.is_active = True
            print(f"✅ kubectl-ai session activated")
            
            return {
                'success': True,
                'output': "🤖 **Interactive AI session started!** 🚀\n\nYou can now chat with the Kubernetes AI assistant. Examples:\n• \"how many pods do I have?\"\n• \"show me all services\"\n• \"what's wrong with my cluster?\"\n• \"help me debug pod issues\"\n\n💡 **Type 'exit' to end the AI session**\n\n🎯 **AI is ready for your questions...**",
                'session_active': True,
                'ai_session_active': True
            }
            
        except Exception as e:
            print(f"❌ Error starting kubectl-ai session: {e}")
            self.is_active = False
            return {
                'success': False,
                'error': f'Failed to start AI session: {str(e)}'
            }
    
    
    def send_message(self, message):
        """Send a message to kubectl-ai"""
        try:
            print(f"🤖 Queuing message to kubectl-ai: {message}")
            
            # Check for exit command
            if message.lower().strip() in ['exit', 'quit', 'bye']:
                self.stop_session()
                return {
                    'success': True,
                    'output': "👋 **AI session ended.** You're back to the regular terminal.\n\nYou can:\n• Use regular kubectl commands\n• Type 'kubectl-ai' to start a new AI session\n• Type 'help' for more options",
                    'session_active': False,
                    'ai_session_ended': True
                }
            
            # Add to conversation history
            self.conversation_history.append({'role': 'user', 'content': message})
            
            # Execute kubectl-ai with the query
            print(f"🤖 Executing kubectl-ai with query: {message}")
            
            # Escape the message for shell
            escaped_message = message.replace('"', '\\"').replace("'", "'\\''")
            
            # Use kubectl-ai directly with the query
            ai_command = f'kubectl-ai "{escaped_message}"'
            result = self.container_manager.execute_command(ai_command)
            
            if result['exit_code'] == 0 and result['output']:
                ai_response = result['output']
                # Clean the response
                ai_response = self.clean_kubectl_ai_output(ai_response)
                
                self.conversation_history.append({'role': 'assistant', 'content': ai_response})
                
                return {
                    'success': True,
                    'output': ai_response,
                    'session_active': True
                }
            else:
                # Try fallback
                print(f"🤖 kubectl-ai returned error, trying fallback...")
                fallback_result = self._fallback_kubectl_command(message)
                
                return {
                    'success': True,
                    'output': fallback_result,
                    'session_active': True
                }
            
        except Exception as e:
            print(f"❌ Error sending message to kubectl-ai: {e}")
            return {
                'success': False,
                'error': f'Failed to send message to AI: {str(e)}',
                'session_active': False
            }
    
    def _is_response_complete(self, response):
        """Check if the AI response seems complete"""
        # Look for typical AI response endings
        lower_response = response.lower().strip()
        
        # If response ends with a prompt or question mark, it's probably complete
        if any(ending in lower_response[-50:] for ending in [
            'anything else', 'help you', 'questions?', 'more info', 
            'need help', 'kubectl', '?', '!', 'done', 'complete'
        ]):
            return True
            
        # If response is reasonably long and has periods, it's probably complete
        if len(response.strip()) > 100 and response.count('.') > 1:
            return True
            
        return False
    
    def _fallback_kubectl_command(self, query):
        """Provide fallback kubectl command for common queries"""
        query_lower = query.lower()
        
        try:
            if any(word in query_lower for word in ['how many pods', 'count pods', 'number of pods']):
                result = self.container_manager.execute_command('kubectl get pods --no-headers | wc -l')
                return f"Number of pods: {result['output'].strip()}"
            elif any(word in query_lower for word in ['show pods', 'list pods', 'get pods']):
                result = self.container_manager.execute_command('kubectl get pods')
                return result['output']
            elif any(word in query_lower for word in ['show services', 'list services']):
                result = self.container_manager.execute_command('kubectl get services')
                return result['output']
            elif any(word in query_lower for word in ['show nodes', 'list nodes']):
                result = self.container_manager.execute_command('kubectl get nodes')
                return result['output']
            else:
                # Try to extract intent and run a general query
                result = self.container_manager.execute_command('kubectl get all')
                return f"Here's the current cluster state:\n\n{result['output']}"
        except:
            return f"❌ Unable to execute fallback command for: {query}"
    
    def clean_kubectl_ai_output(self, output):
        """Clean and format kubectl-ai output"""
        if not output:
            return "🤖 kubectl-ai is processing your request..."
        
        # Remove ANSI escape codes
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        output = ansi_escape.sub('', output)
        
        # Remove common unwanted patterns
        lines = output.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Skip system messages and prompts
            if any(skip in line.lower() for skip in [
                'namespace?', 'which namespace', 'please specify',
                'would you like', 'do you want', 'press enter',
                'user@k8s-terminal'
            ]):
                continue
                
            cleaned_lines.append(line)
        
        result = '\n'.join(cleaned_lines).strip()
        
        if not result or len(result) < 10:
            return "🤖 AI is thinking... Try being more specific with your question."
        
        return result
    
    def stop_session(self):
        """Stop the kubectl-ai session"""
        try:
            print(f"🤖 Stopping kubectl-ai session for {self.session_id}")
            
            self.is_active = False
            
            print(f"✅ kubectl-ai session stopped for {self.session_id}")
            
        except Exception as e:
            print(f"❌ Error stopping kubectl-ai session: {e}")


class KubernetesContainer:
    """Manage Docker containers for each Kubernetes cluster"""
    
    def __init__(self, cluster, session_id):
        self.cluster = cluster
        self.session_id = session_id
        self.container = None
        try:
            self.docker_client = docker.from_env()
        except docker.errors.DockerException as e:
            print(f"❌ Docker connection error: {e}")
            self.docker_client = None
        self.container_name = f"k8s-terminal-{session_id}"
        self.running = False
        
    def create_container(self):
        """Create a Docker container with kubectl and kubectl-ai"""
        try:
            # Check if Docker client is available
            if self.docker_client is None:
                print(f"❌ Docker client not available - is Docker running?")
                return False
                
            # Ensure Docker image exists (build if needed)
            if not ensure_docker_image():
                print(f"❌ Failed to ensure Docker image exists")
                return False
            
            # Encode kubeconfig to base64 for passing to container
            kubeconfig_b64 = base64.b64encode(self.cluster.kubeconfig.encode()).decode()
            
            # Get GEMINI_API_KEY from environment
            gemini_api_key = os.getenv('GEMINI_API_KEY')
            if not gemini_api_key:
                print(f"❌ GEMINI_API_KEY not found in environment")
                return False
            
            print(f"🐳 Creating container: {self.container_name}")
            
            # Create container with kubectl and kubectl-ai
            self.container = self.docker_client.containers.run(
                image=KUBECTL_IMAGE_NAME,
                name=self.container_name,
                environment={
                    'KUBECONFIG_B64': kubeconfig_b64,
                    'GEMINI_API_KEY': gemini_api_key,
                    'TERM': 'xterm-256color'
                },
                command=["/bin/sh", "-c", "echo $KUBECONFIG_B64 | base64 -d > /root/.kube/config && mkdir -p /root/.kube && export KUBECONFIG=/root/.kube/config && tail -f /dev/null"],
                stdin_open=True,
                tty=True,
                detach=True,
                remove=False,
                working_dir="/root",
                volumes={}
            )
            
            # Wait a moment for container to initialize
            time.sleep(2)
            
            # Verify container is running
            self.container.reload()
            if self.container.status == 'running':
                self.running = True
                print(f"✅ Container created and running: {self.container_name}")
                return True
            else:
                print(f"❌ Container failed to start: {self.container.status}")
                return False
            
        except Exception as e:
            print(f"❌ Error creating container: {e}")
            return False
    
    def execute_command(self, command):
        """Execute command in the container"""
        if not self.container or not self.running:
            return {'output': '❌ Container not available', 'exit_code': 1}
            
        try:
            print(f"🐳 Executing in {self.container_name}: {command}")
            
            # Regular command execution
            timeout = 30  # 30 seconds for regular commands
            
            # Get GEMINI_API_KEY from environment
            gemini_api_key = os.getenv('GEMINI_API_KEY', '')
            
            # Execute command in container with proper environment and timeout
            exec_result = self.container.exec_run(
                cmd=['/bin/sh', '-c', f'cd /root && export KUBECONFIG=/root/.kube/config && export GEMINI_API_KEY={gemini_api_key} && timeout {timeout} {command}'],
                stdout=True,
                stderr=True,
                stdin=False,
                tty=False,
                workdir='/root'
            )
            
            # Get output
            output = exec_result.output.decode('utf-8', errors='ignore') if exec_result.output else ""
            
            # Handle timeout (exit code 124)
            if exec_result.exit_code == 124:
                output += f"\n⏱️ Command timed out after {timeout} seconds"
            
            print(f"🐳 Command exit code: {exec_result.exit_code}")
            print(f"🐳 Output: {output[:200]}...")
            
            return {
                'output': output,
                'exit_code': exec_result.exit_code
            }
            
        except Exception as e:
            print(f"❌ Error executing command: {e}")
            return {
                'output': f'❌ Error executing command: {str(e)}',
                'exit_code': 1
            }
    
    def is_running(self):
        """Check if container is still running"""
        try:
            if self.container:
                self.container.reload()
                return self.container.status == 'running'
            return False
        except:
            return False
    
    def stop_container(self):
        """Stop and remove the container"""
        try:
            self.running = False
            if self.container:
                print(f"🐳 Stopping container: {self.container_name}")
                self.container.stop(timeout=10)
                self.container.remove()
                print(f"✅ Container stopped and removed: {self.container_name}")
        except Exception as e:
            print(f"❌ Error stopping container: {e}")


def index(request):
    """Render the main chat interface."""
    clusters = KubernetesCluster.objects.filter(is_active=True)
    return render(request, 'chat/index.html', {'clusters': clusters})


def terminal_view(request, session_id):
    """Render the real terminal interface."""
    try:
        chat_session = get_object_or_404(ChatSession, session_id=session_id)
        
        # Ensure container exists
        if session_id not in active_containers:
            container_manager = KubernetesContainer(chat_session.cluster, session_id)
            if container_manager.docker_client and container_manager.create_container():
                active_containers[session_id] = container_manager
            else:
                return redirect('/')
        
        context = {
            'session_id': session_id,
            'cluster_name': chat_session.cluster.name,
            'cluster_id': chat_session.cluster.id
        }
        
        return render(request, 'chat/terminal.html', context)
        
    except Exception as e:
        print(f"Error in terminal view: {e}")
        return redirect('/')


@csrf_exempt
@require_http_methods(["POST"])
def create_cluster(request):
    """Create a new Kubernetes cluster configuration and container."""
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
        
        # Create a chat session
        session_id = str(uuid.uuid4())
        chat_session = ChatSession.objects.create(
            cluster=cluster,
            session_id=session_id,
            name=f"{cluster_name} Terminal"
        )
        
        # Create Docker container for this cluster
        container_manager = KubernetesContainer(cluster, session_id)
        if container_manager.create_container():
            # Store container manager
            active_containers[session_id] = container_manager
            
            # Test connection in the actual container
            print(f"🧪 Testing connection in container...")
            test_result = container_manager.execute_command('kubectl version --client')
            if test_result['exit_code'] == 0:
                cluster.connection_status = 'connected'
                cluster.connection_error = ''
                print(f"✅ Container ready with kubectl")
            else:
                cluster.connection_status = 'error'
                cluster.connection_error = test_result['output'][:500]
                print(f"❌ kubectl test failed: {test_result['output'][:100]}")
            
            cluster.last_connection_check = timezone.now()
            cluster.save()
            
            return JsonResponse({
                'success': True,
                'cluster_id': cluster.id,
                'session_id': session_id,
                'message': f'🐳 Container created! Status: {cluster.connection_status}'
            })
        else:
            cluster.delete()  # Clean up if container creation failed
            return JsonResponse({
                'success': False,
                'error': 'Failed to create Docker container. Please check Docker is running and try again.'
            })
            
    except Exception as e:
        print(f"❌ Error in create_cluster: {e}")
        return JsonResponse({
            'success': False,
            'error': f'Server error: {str(e)}'
        })


@csrf_exempt
@require_http_methods(["POST"])
def execute_command(request, session_id):
    """Execute a command in the cluster's Docker container."""
    try:
        chat_session = get_object_or_404(ChatSession, session_id=session_id)
        data = json.loads(request.body)
        command = data.get('command', '').strip()
        ai_mode = data.get('ai_mode', False)
        
        if not command:
            return JsonResponse({
                'success': False,
                'error': 'Command is required'
            })
        
        # Check if this is an AI mode message
        if ai_mode and session_id in active_ai_sessions:
            ai_session = active_ai_sessions[session_id]
            if ai_session.is_active:
                # Send message to AI session
                result = ai_session.send_message(command)
                
                # Store in command history
                CommandHistory.objects.create(
                    chat_session=chat_session,
                    command=f"[AI] {command}",
                    output=result.get('output', ''),
                    exit_code=0 if result.get('success') else 1
                )
                
                # Update session last activity
                chat_session.last_activity = timezone.now()
                chat_session.save()
                
                return JsonResponse(result)
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'AI session not active'
                })
        
        # Handle help command
        if command.strip() == 'help':
            help_text = """🐳 KUBERNETES CONTAINER TERMINAL

**kubectl Commands:**
• kubectl get pods - List all pods
• kubectl get nodes - List all nodes  
• kubectl get services - List all services
• kubectl describe pod <n> - Pod details
• kubectl logs <pod-name> - View pod logs
• kubectl apply -f <file> - Apply configuration
• kubectl delete pod <n> - Delete pod

**kubectl-ai Commands (Interactive AI):**
• kubectl-ai - Start interactive AI session
• "how many pods do I have?" (in AI session)
• "what's wrong with my cluster?" (in AI session)
• "exit" - End AI session

**Container Commands:**
• ls, cat, mkdir, rm - File operations
• vi <filename> - Edit files (vi editor)
• clear - Clear terminal
• pwd, cd - Navigation
• ps aux - Show running processes

**Examples:**
• kubectl get pods -o wide
• kubectl-ai (then chat naturally)
• ls -la /tmp
• cat /etc/os-release

This terminal runs in a dedicated Docker container with kubectl and kubectl-ai pre-installed.
Your GEMINI_API_KEY is configured for kubectl-ai usage."""
            
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
        
        # Handle AI session activation
        if command.strip() == 'kubectl-ai':
            return start_ai_session(request, session_id)
        
        # Get container for this session
        if session_id not in active_containers:
            return JsonResponse({
                'success': False,
                'error': '🐳 Container not found. Please refresh the page and try again.'
            })
        
        container_manager = active_containers[session_id]
        
        # Check if container is still running
        if not container_manager.is_running():
            # Try to recreate container
            print(f"🐳 Container not running, recreating...")
            if container_manager.create_container():
                print(f"✅ Container recreated successfully")
            else:
                return JsonResponse({
                    'success': False,
                    'error': '🐳 Container stopped and could not be restarted. Please refresh the page.'
                })
        
        # Check if this is an AI session message
        if session_id in active_ai_sessions:
            ai_session = active_ai_sessions[session_id]
            if ai_session.is_active:
                # Send message to AI session
                result = ai_session.send_message(command)
                
                # If AI session ended, remove it
                if result.get('ai_session_ended'):
                    del active_ai_sessions[session_id]
                
                # Store in command history
                CommandHistory.objects.create(
                    chat_session=chat_session,
                    command=command,
                    output=result.get('output', ''),
                    exit_code=0 if result.get('success') else 1
                )
                
                # Update session last activity
                chat_session.last_activity = timezone.now()
                chat_session.save()
                
                return JsonResponse({
                    'success': result.get('success', True),
                    'output': result.get('output', ''),
                    'exit_code': 0 if result.get('success') else 1,
                    'ai_session_active': result.get('session_active', False)
                })
        
        # Execute regular command in container
        result = container_manager.execute_command(command)
        
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
        print(f"❌ Error in execute_command: {e}")
        return JsonResponse({
            'success': False,
            'error': f'Error executing command: {str(e)}'
        })


def test_cluster_connection(cluster):
    """Simple connection test - just verify kubeconfig is valid YAML"""
    try:
        # Validate kubeconfig format
        kubeconfig_data = yaml.safe_load(cluster.kubeconfig)
        if isinstance(kubeconfig_data, dict) and 'clusters' in kubeconfig_data:
            return {'status': 'connected'}
        else:
            return {'status': 'error', 'error': 'Invalid kubeconfig format'}
    except Exception as e:
        return {'status': 'error', 'error': f'Kubeconfig validation failed: {str(e)}'}


@require_http_methods(["GET"])
def get_chat_history(request, session_id):
    """Get command history for a chat session and ensure container exists."""
    try:
        chat_session = get_object_or_404(ChatSession, session_id=session_id)
        
        # Ensure container exists for this session
        if session_id not in active_containers:
            print(f"🐳 Creating container for session {session_id} on history load...")
            try:
                container_manager = KubernetesContainer(chat_session.cluster, session_id)
                if container_manager.docker_client and container_manager.create_container():
                    active_containers[session_id] = container_manager
                    print(f"✅ Container created for session {session_id}")
                else:
                    print(f"❌ Failed to create container for session {session_id} - Docker may not be running")
            except Exception as e:
                print(f"❌ Error creating container for session {session_id}: {e}")
        
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


@csrf_exempt
@require_http_methods(["POST"])
def rename_cluster(request, cluster_id):
    """Rename a cluster/chat session."""
    try:
        cluster = get_object_or_404(KubernetesCluster, id=cluster_id)
        data = json.loads(request.body)
        new_name = data.get('name', '').strip()
        
        if not new_name:
            return JsonResponse({
                'success': False,
                'error': 'Name is required'
            })
        
        # Update cluster name
        cluster.name = new_name
        cluster.save()
        
        # Update related chat session names
        for session in cluster.chat_sessions.filter(is_active=True):
            session.name = f"{new_name} Terminal"
            session.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Chat renamed successfully'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Server error: {str(e)}'
        })



@require_http_methods(["GET"])
def container_status(request, session_id):
    """Check if container is running for the session."""
    try:
        chat_session = get_object_or_404(ChatSession, session_id=session_id)
        container_name = f"k8s-terminal-{session_id}"
        
        # Check if Docker is available
        if not hasattr(chat_session, '_kubernetes_container'):
            chat_session._kubernetes_container = KubernetesContainer(
                session_id=session_id,
                cluster=chat_session.cluster
            )
        
        k8s_container = chat_session._kubernetes_container
        
        if not k8s_container.docker_client:
            return JsonResponse({
                'success': False,
                'error': 'Docker is not available',
                'container_running': False
            })
        
        # Check if container exists and is running
        try:
            container = k8s_container.docker_client.containers.get(container_name)
            is_running = container.status == 'running'
            
            return JsonResponse({
                'success': True,
                'container_running': is_running,
                'container_status': container.status,
                'container_name': container_name
            })
        except docker.errors.NotFound:
            return JsonResponse({
                'success': True,
                'container_running': False,
                'container_status': 'not_found',
                'container_name': container_name
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e),
                'container_running': False
            })
            
    except ChatSession.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Chat session not found',
            'container_running': False
        })


@require_http_methods(["POST"])
def clear_history(request, session_id):
    """Clear command history for a chat session."""
    try:
        chat_session = get_object_or_404(ChatSession, session_id=session_id)
        
        # Delete all command history for this session
        CommandHistory.objects.filter(chat_session=chat_session).delete()
        
        return JsonResponse({
            'success': True,
            'message': 'History cleared successfully'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Server error: {str(e)}'
        })


@require_http_methods(["GET"])
def get_kubeconfig(request, cluster_id):
    """Get kubeconfig for a cluster."""
    try:
        cluster = get_object_or_404(KubernetesCluster, id=cluster_id)
        
        return JsonResponse({
            'success': True,
            'kubeconfig': cluster.kubeconfig
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Server error: {str(e)}'
        })


@csrf_exempt
@require_http_methods(["POST"])
def update_kubeconfig(request, cluster_id):
    """Update kubeconfig for a cluster."""
    try:
        cluster = get_object_or_404(KubernetesCluster, id=cluster_id)
        data = json.loads(request.body)
        kubeconfig_content = data.get('kubeconfig', '').strip()
        
        if not kubeconfig_content:
            return JsonResponse({
                'success': False,
                'error': 'Kubeconfig is required'
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
        
        # Update kubeconfig
        cluster.kubeconfig = kubeconfig_content
        
        # Test connection with new kubeconfig
        connection_result = test_cluster_connection(cluster)
        cluster.connection_status = connection_result['status']
        cluster.connection_error = connection_result.get('error', '')
        cluster.last_connection_check = timezone.now()
        cluster.save()
        
        # Update containers with new kubeconfig
        for session in cluster.chat_sessions.filter(is_active=True):
            if session.session_id in active_containers:
                print(f"🐳 Updating container for session {session.session_id}")
                # Stop old container and create new one
                active_containers[session.session_id].stop_container()
                
                new_container = KubernetesContainer(cluster, session.session_id)
                if new_container.create_container():
                    active_containers[session.session_id] = new_container
                    print(f"✅ Container updated for session {session.session_id}")
                else:
                    print(f"❌ Failed to update container for session {session.session_id}")
        
        if connection_result['status'] == 'connected':
            return JsonResponse({
                'success': True,
                'message': 'Kubeconfig updated successfully'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': f'Kubeconfig updated but connection failed: {connection_result.get("error", "Unknown error")}'
            })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Server error: {str(e)}'
        })


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_cluster(request, cluster_id):
    """Delete a cluster and all its data."""
    try:
        cluster = get_object_or_404(KubernetesCluster, id=cluster_id)
        
        # Stop and remove containers for this cluster
        for session in cluster.chat_sessions.filter(is_active=True):
            if session.session_id in active_containers:
                print(f"🐳 Stopping container for session {session.session_id}")
                active_containers[session.session_id].stop_container()
                del active_containers[session.session_id]
        
        # Mark cluster as inactive instead of deleting to preserve data
        cluster.is_active = False
        cluster.save()
        
        # Mark all chat sessions as inactive
        cluster.chat_sessions.update(is_active=False)
        
        return JsonResponse({
            'success': True,
            'message': 'Chat deleted successfully'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Server error: {str(e)}'
        })


@require_http_methods(["GET"])
def check_cluster_status(request, cluster_id):
    """Check cluster connection status via container."""
    try:
        cluster = get_object_or_404(KubernetesCluster, id=cluster_id)
        
        # Test connection via container
        connection_result = test_cluster_connection(cluster)
        cluster.connection_status = connection_result['status']
        cluster.connection_error = connection_result.get('error', '')
        cluster.last_connection_check = timezone.now()
        cluster.save()
        
        return JsonResponse({
            'success': True,
            'status': connection_result['status']
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Server error: {str(e)}'
        })


def start_ai_session(request, session_id):
    """Start an interactive kubectl-ai session"""
    try:
        chat_session = get_object_or_404(ChatSession, session_id=session_id)
        
        # Get container for this session
        if session_id not in active_containers:
            return JsonResponse({
                'success': False,
                'error': '🐳 Container not found. Please refresh the page and try again.'
            })
        
        container_manager = active_containers[session_id]
        
        # Check if container is still running
        if not container_manager.is_running():
            return JsonResponse({
                'success': False,
                'error': '🐳 Container not running. Please refresh the page and try again.'
            })
        
        # Create AI session if it doesn't exist
        if session_id not in active_ai_sessions:
            ai_session = KubectlAiSession(container_manager, session_id)
            active_ai_sessions[session_id] = ai_session
        else:
            ai_session = active_ai_sessions[session_id]
        
        # Start the AI session
        result = ai_session.start_session()
        
        # Store in command history
        CommandHistory.objects.create(
            chat_session=chat_session,
            command='kubectl-ai',
            output=result.get('output', ''),
            exit_code=0 if result.get('success') else 1
        )
        
        # Update session last activity
        chat_session.last_activity = timezone.now()
        chat_session.save()
        
        return JsonResponse({
            'success': result.get('success', True),
            'output': result.get('output', ''),
            'exit_code': 0 if result.get('success') else 1,
            'ai_session_active': True
        })
        
    except ChatSession.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Chat session not found'
        })
    except Exception as e:
        print(f"❌ Error starting AI session: {e}")
        return JsonResponse({
            'success': False,
            'error': f'Error starting AI session: {str(e)}'
        })


# Debug endpoint to check container status
@require_http_methods(["GET"])
def debug_kubectl_ai(request, session_id):
    """Debug container and kubectl-ai status"""
    try:
        debug_info = {}
        
        # Check if session has container
        if session_id in active_containers:
            container_manager = active_containers[session_id]
            debug_info['container_exists'] = True
            debug_info['container_running'] = container_manager.is_running()
            debug_info['container_name'] = container_manager.container_name
            
            if container_manager.is_running():
                # Test kubectl
                kubectl_result = container_manager.execute_command('kubectl version --client')
                debug_info['kubectl_test'] = {
                    'exit_code': kubectl_result['exit_code'],
                    'output': kubectl_result['output'][:200]
                }
                
                # Test kubectl-ai
                ai_result = container_manager.execute_command('kubectl-ai --help')
                debug_info['kubectl_ai_test'] = {
                    'exit_code': ai_result['exit_code'],
                    'output': ai_result['output'][:200]
                }
                
                # Test API key
                api_test = container_manager.execute_command('echo $GEMINI_API_KEY | wc -c')
                debug_info['api_key_length'] = api_test['output'].strip()
                
        else:
            debug_info['container_exists'] = False
            debug_info['container_running'] = False
        
        # Check AI session status
        if session_id in active_ai_sessions:
            ai_session = active_ai_sessions[session_id]
            debug_info['ai_session_exists'] = True
            debug_info['ai_session_active'] = ai_session.is_active
        else:
            debug_info['ai_session_exists'] = False
            debug_info['ai_session_active'] = False
        
        return JsonResponse({
            'success': True,
            'debug_info': debug_info
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Debug error: {str(e)}'
        })


# Cleanup function to stop containers on server shutdown
def cleanup_containers():
    """Stop all active containers"""
    print("🐳 Cleaning up containers...")
    for session_id, container_manager in active_containers.items():
        try:
            container_manager.stop_container()
        except Exception as e:
            print(f"❌ Error stopping container {session_id}: {e}")
    active_containers.clear()
    
    print("🤖 Cleaning up AI sessions...")
    for session_id, ai_session in active_ai_sessions.items():
        try:
            ai_session.stop_session()
        except Exception as e:
            print(f"❌ Error stopping AI session {session_id}: {e}")
    active_ai_sessions.clear()
    
    print("✅ Cleanup completed")


# Signal handler for Django shutdown
import signal
import atexit

def handle_shutdown(signum, frame):
    cleanup_containers()

# Register cleanup handlers
signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)
atexit.register(cleanup_containers)
