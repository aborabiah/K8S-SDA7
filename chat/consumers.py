import json
import asyncio
import docker
import os
import fcntl
from channels.generic.websocket import AsyncWebsocketConsumer
from .models import ChatSession
from asgiref.sync import sync_to_async
import logging

logger = logging.getLogger(__name__)

class TerminalConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real terminal connections"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session_id = None
        self.container_name = None
        self.docker_client = None
        self.container = None
        self.exec_id = None
        self.socket = None
        self.read_task = None
        
    async def connect(self):
        """Handle WebSocket connection"""
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.container_name = f"k8s-terminal-{self.session_id}"
        
        await self.accept()
        await self.initialize_terminal()
        
    async def disconnect(self, close_code):
        """Handle WebSocket disconnect"""
        # Cancel read task
        if self.read_task:
            self.read_task.cancel()
            
        # Close socket
        if self.socket:
            try:
                await asyncio.get_event_loop().run_in_executor(None, self.socket.close)
            except:
                pass
                
    async def receive(self, text_data):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(text_data)
            
            if data['type'] == 'input':
                await self.send_to_terminal(data['data'])
            elif data['type'] == 'resize':
                await self.resize_terminal(data.get('rows', 24), data.get('cols', 80))
                
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            
    async def initialize_terminal(self):
        """Initialize Docker terminal connection"""
        try:
            # Get Docker client with error handling
            def get_docker_client():
                try:
                    return docker.from_env()
                except docker.errors.DockerException as e:
                    logger.error(f"Docker connection error: {e}")
                    raise Exception("Docker is not available or not running. Please start Docker Desktop.")
            
            self.docker_client = await asyncio.get_event_loop().run_in_executor(
                None, get_docker_client
            )
            
            # Get or create container
            try:
                self.container = await asyncio.get_event_loop().run_in_executor(
                    None, self.docker_client.containers.get, self.container_name
                )
                logger.info(f"Found existing container: {self.container_name}")
            except docker.errors.NotFound:
                logger.info(f"Container not found, using simple alpine container")
                # Use simple alpine container instead of building custom image
                await self.create_simple_container()
                
            # Start container if not running
            container_status = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.container.status
            )
            
            if container_status != 'running':
                await asyncio.get_event_loop().run_in_executor(
                    None, self.container.start
                )
                await asyncio.sleep(1)
                
            # Create exec instance that we can interact with - try bash first, fall back to sh
            shell_cmd = ['/bin/bash'] if self.container.image.tags and 'kubectl' in str(self.container.image.tags) else ['/bin/sh']
            
            exec_cmd = self.docker_client.api.exec_create(
                container=self.container.id,
                cmd=shell_cmd,
                stdin=True,
                stdout=True,
                stderr=True,
                tty=True
            )
            
            self.exec_id = exec_cmd['Id']
            
            # Start the exec instance
            self.socket = self.docker_client.api.exec_start(
                exec_id=self.exec_id,
                stream=True,
                socket=True
            )
            
            # Start reading from terminal
            self.read_task = asyncio.create_task(self.read_terminal_output())
            
            # Send welcome message
            await self.send(text_data=json.dumps({
                'type': 'output',
                'data': f'\r\nConnected to {self.container_name}\r\nKubectl and kubectl-ai are available!\r\n'
            }))
            
            # Send clean initialization
            await asyncio.sleep(0.3)
            await self.send_to_terminal('clear\n')
            await asyncio.sleep(0.1)
            await self.send_to_terminal('echo "=== K8S AI Terminal Ready ==="\n')
            await asyncio.sleep(0.1)
            await self.send_to_terminal('echo "kubectl and kubectl-ai are available!"\n')
            
        except Exception as e:
            logger.error(f"Error initializing terminal: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'data': str(e)
            }))
            
    async def create_simple_container(self):
        """Create container with kubectl and kubectl-ai"""
        try:
            # Get chat session for kubeconfig and API key
            chat_session = await sync_to_async(ChatSession.objects.get)(
                session_id=self.session_id
            )
            cluster = await sync_to_async(lambda: chat_session.cluster)()
            
            # Base64 encode kubeconfig
            import base64
            import os
            kubeconfig_b64 = base64.b64encode(cluster.kubeconfig.encode()).decode()
            gemini_api_key = os.getenv('GEMINI_API_KEY', '')
            
            # Try to use existing kubectl image first
            image_name = "your-kubectl-image:latest"
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, self.docker_client.images.get, image_name
                )
                logger.info(f"Using existing kubectl image: {image_name}")
            except:
                # If image doesn't exist, create Alpine with kubectl and kubectl-ai
                logger.info("Building kubectl image...")
                await self.build_kubectl_image(image_name)
            
            # Create container with kubectl image
            self.container = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.docker_client.containers.run(
                    image=image_name,
                    name=self.container_name,
                    command=["/bin/bash"],
                    environment={
                        'KUBECONFIG_B64': kubeconfig_b64,
                        'GEMINI_API_KEY': 'AIzaSyAus1bYeszdrau2WHY-OSJnfDSqPCqL47g',
                        'TERM': 'xterm-256color',
                        'HOME': '/root',
                        'KUBECONFIG': '/root/.kube/config'
                    },
                    stdin_open=True,
                    tty=True,
                    detach=True,
                    remove=False,
                    working_dir="/root"
                )
            )
            
            # Setup kubeconfig in container
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.container.exec_run(
                    cmd=['/bin/sh', '-c', 'mkdir -p /root/.kube && echo $KUBECONFIG_B64 | base64 -d > /root/.kube/config'],
                    environment={'KUBECONFIG_B64': kubeconfig_b64}
                )
            )
            
            logger.info(f"Created kubectl container: {self.container_name}")
            
        except Exception as e:
            logger.error(f"Error creating kubectl container: {e}")
            # Fall back to alpine if kubectl image fails
            self.container = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.docker_client.containers.run(
                    image="alpine:latest",
                    name=self.container_name,
                    command=["/bin/sh"],
                    stdin_open=True,
                    tty=True,
                    detach=True,
                    remove=False,
                    working_dir="/root"
                )
            )
            logger.info(f"Fell back to Alpine container: {self.container_name}")
    
    async def build_kubectl_image(self, image_name):
        """Build Docker image with kubectl and kubectl-ai using existing Dockerfile"""
        dockerfile_content = '''FROM alpine:3.18

# Install tools + download both binaries in one layer
RUN apk add --no-cache curl tar ca-certificates bash vim nano \\
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
ENV GEMINI_API_KEY=AIzaSyAus1bYeszdrau2WHY-OSJnfDSqPCqL47g

# Keep container running
CMD ["/bin/bash"]'''
        
        import tempfile
        import shutil
        temp_dir = tempfile.mkdtemp()
        dockerfile_path = os.path.join(temp_dir, 'Dockerfile')
        
        with open(dockerfile_path, 'w') as f:
            f.write(dockerfile_content)
            
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.docker_client.images.build(
                    path=temp_dir,
                    dockerfile='Dockerfile',
                    tag=image_name,
                    rm=True
                )
            )
            logger.info(f"Built kubectl image: {image_name}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    async def create_container(self):
        """Create Docker container"""
        try:
            # Get chat session for kubeconfig
            chat_session = await sync_to_async(ChatSession.objects.get)(
                session_id=self.session_id
            )
            cluster = await sync_to_async(lambda: chat_session.cluster)()
            
            # Base64 encode kubeconfig
            import base64
            kubeconfig_b64 = base64.b64encode(cluster.kubeconfig.encode()).decode()
            
            # Docker image
            image_name = "your-kubectl-image:latest"
            
            # Check if image exists, if not build it
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, self.docker_client.images.get, image_name
                )
            except docker.errors.ImageNotFound:
                # Build image
                dockerfile_content = '''FROM alpine:latest
RUN apk add --no-cache curl tar ca-certificates bash vim nano
RUN curl -sSL https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl -o /usr/local/bin/kubectl && chmod +x /usr/local/bin/kubectl
RUN mkdir -p /root/.kube
WORKDIR /root
ENV KUBECONFIG=/root/.kube/config
CMD ["/bin/bash"]'''
                
                import tempfile
                import os
                temp_dir = tempfile.mkdtemp()
                dockerfile_path = os.path.join(temp_dir, 'Dockerfile')
                
                with open(dockerfile_path, 'w') as f:
                    f.write(dockerfile_content)
                    
                try:
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self.docker_client.images.build(
                            path=temp_dir,
                            dockerfile='Dockerfile',
                            tag=image_name,
                            rm=True
                        )
                    )
                finally:
                    import shutil
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    
            # Create container
            self.container = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.docker_client.containers.run(
                    image=image_name,
                    name=self.container_name,
                    environment={
                        'KUBECONFIG_B64': kubeconfig_b64,
                        'TERM': 'xterm-256color'
                    },
                    command=["/bin/bash"],
                    stdin_open=True,
                    tty=True,
                    detach=True,
                    remove=False
                )
            )
            
            # Setup kubeconfig
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.container.exec_run(
                    cmd=['/bin/sh', '-c', 'echo $KUBECONFIG_B64 | base64 -d > /root/.kube/config'],
                    environment={'KUBECONFIG_B64': kubeconfig_b64}
                )
            )
            
        except Exception as e:
            logger.error(f"Error creating container: {e}")
            raise
            
    async def read_terminal_output(self):
        """Read output from terminal and send to WebSocket"""
        while True:
            try:
                # Check if socket is still valid
                if not self.socket or self.socket._sock.fileno() == -1:
                    logger.error("Socket connection lost")
                    break
                
                # Read from socket with timeout handling
                data = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, self.socket._sock.recv, 4096
                    ),
                    timeout=60.0  # Increased to 60 second timeout
                )
                
                if data:
                    # Send to WebSocket
                    await self.send(text_data=json.dumps({
                        'type': 'output',
                        'data': data.decode('utf-8', errors='replace')
                    }))
                else:
                    # Socket closed
                    break
                    
            except asyncio.TimeoutError:
                # Send keepalive on timeout and continue reading
                try:
                    await self.send(text_data=json.dumps({
                        'type': 'keepalive',
                        'data': ''
                    }))
                except Exception as keepalive_error:
                    logger.error(f"Error sending keepalive: {keepalive_error}")
                    break
                continue
            except BlockingIOError:
                # No data available, wait a bit
                await asyncio.sleep(0.01)
            except Exception as e:
                logger.error(f"Error reading terminal output: {e}")
                # Check if it's a recoverable error
                if "timed out" in str(e).lower():
                    # Send keepalive and continue
                    try:
                        await self.send(text_data=json.dumps({
                            'type': 'keepalive',
                            'data': ''
                        }))
                        continue
                    except:
                        pass
                
                # Non-recoverable error, notify client
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'data': 'Terminal connection lost. Please refresh to reconnect.'
                }))
                break
                
    async def send_to_terminal(self, data):
        """Send input to terminal"""
        try:
            if self.socket:
                await asyncio.get_event_loop().run_in_executor(
                    None, self.socket._sock.send, data.encode() if isinstance(data, str) else data
                )
        except Exception as e:
            logger.error(f"Error sending to terminal: {e}")
            
    async def resize_terminal(self, rows, cols):
        """Resize terminal"""
        try:
            if self.exec_id and self.docker_client:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.docker_client.api.exec_resize(
                        self.exec_id,
                        height=rows,
                        width=cols
                    )
                )
        except Exception as e:
            logger.error(f"Error resizing terminal: {e}")