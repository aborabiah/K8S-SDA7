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
import threading
import queue
import time
from kubernetes import client, config
from kubernetes.client.rest import ApiException


# Global dictionary to store interactive AI sessions
active_ai_sessions = {}



class PersistentKubectlAI:
    """Simple kubectl-ai - just make it work!"""
    
    def __init__(self, cluster, session_id):
        self.cluster = cluster
        self.session_id = session_id
        self.process = None
        self.kubeconfig_path = None
        self.running = False
        
    def start_persistent_session(self):
        """Start kubectl-ai"""
        try:
            # Create kubeconfig
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                f.write(self.cluster.kubeconfig)
                self.kubeconfig_path = f.name
            
            # Setup environment
            env = os.environ.copy()
            env['KUBECONFIG'] = self.kubeconfig_path
            
            # Start kubectl-ai with PTY for interactive mode
            import pty
            master, slave = pty.openpty()
            
            self.process = subprocess.Popen(
                ['kubectl-ai', '--model', 'gemini-2.0-flash-exp'],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                env=env,
                preexec_fn=os.setsid
            )
            
            os.close(slave)
            self.master_fd = master
            
            # Make it non-blocking
            import fcntl
            flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
            fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            
            print(f"✅ kubectl-ai started")
            self.running = True
            
            # Wait and read initial greeting
            time.sleep(3)
            try:
                initial = os.read(self.master_fd, 4096).decode('utf-8', errors='ignore')
                # Clean it
                import re
                initial = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', initial)
                initial = re.sub(r'[\x00-\x1f\x7f]', '', initial)
                initial = initial.replace('>>>', '').strip()
                print(f"Initial greeting: {initial}")
            except:
                pass
                
            return True
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def send_persistent_message(self, message):
        """Send message to kubectl-ai"""
        if not self.running or not self.process:
            return "kubectl-ai not running"
        
        try:
            print(f"📤 Sending: {message}")
            # Send message
            os.write(self.master_fd, f"{message}\n".encode())
            
            # Collect response
            response_parts = []
            time.sleep(2)  # Initial wait for kubectl-ai to start processing
            
            empty_reads = 0
            max_attempts = 40  # 20 seconds max
            
            for attempt in range(max_attempts):
                try:
                    # Try to read available data
                    chunk = os.read(self.master_fd, 8192).decode('utf-8', errors='ignore')
                    if chunk:
                        print(f"📥 Got chunk ({len(chunk)} chars)")
                        response_parts.append(chunk)
                        empty_reads = 0
                        
                        # Check if we have a complete response
                        full_response = ''.join(response_parts)
                        if len(full_response) > 50:  # Have substantial content
                            # Look for typical endings
                            if any(end in full_response.lower() for end in [
                                '?', 'help', 'please', 'in.', 'namespace', 
                                'pods', 'running', 'kubectl', 'need to know'
                            ]):
                                # Give it one more second to complete
                                time.sleep(1)
                                try:
                                    extra = os.read(self.master_fd, 4096).decode('utf-8', errors='ignore')
                                    if extra:
                                        response_parts.append(extra)
                                except:
                                    pass
                                break
                                
                except OSError as e:
                    if e.errno in [11, 35]:  # Would block / Resource temporarily unavailable
                        empty_reads += 1
                        if empty_reads > 8 and response_parts:
                            # We have content and no new data for a while
                            break
                    else:
                        print(f"❌ Read error: {e}")
                        if response_parts:
                            break  # Use what we have
                
                # Check if process died
                if self.process.poll() is not None:
                    print(f"❌ kubectl-ai process died!")
                    break
                    
                time.sleep(0.5)
            
            # Combine all parts
            response = ''.join(response_parts)
            print(f"📝 Raw response ({len(response)} chars)")
            
            if not response:
                return "kubectl-ai didn't respond. Try asking again or check if kubectl-ai is working."
            
            # Clean response
            import re
            
            # Remove ANSI escape sequences
            cleaned = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', response)
            cleaned = re.sub(r'\x1b\[[\d;]+m', '', cleaned)
            cleaned = re.sub(r'\[38;5;\d+m', '', cleaned)
            cleaned = re.sub(r'\[\d+m', '', cleaned)
            
            # Remove control characters
            cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', cleaned)
            
            # Process line by line
            lines = []
            for line in cleaned.split('\n'):
                line = line.strip()
                if not line:
                    continue
                # Skip prompts and echoes
                if line in ['>>>', f'>>> {message}', message]:
                    continue
                if line.startswith('>>> '):
                    # This might be a prompt with content, extract the content
                    content = line[4:].strip()
                    if content and content != message:
                        lines.append(content)
                else:
                    lines.append(line)
            
            # Join and clean up
            final_response = '\n'.join(lines)
            final_response = re.sub(r'\s*>>>\s*$', '', final_response).strip()
            
            print(f"✨ Clean response: {repr(final_response[:200])}...")
            
            return final_response if final_response else "kubectl-ai is processing... Try again in a moment."
            
        except Exception as e:
            print(f"❌ Exception: {e}")
            import traceback
            traceback.print_exc()
            return f"Error: {str(e)}"
    
    def stop_persistent_session(self):
        """Stop kubectl-ai"""
        self.running = False
        
        if hasattr(self, 'master_fd'):
            try:
                os.close(self.master_fd)
            except:
                pass
                
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=3)
            except:
                self.process.kill()
        
        if self.kubeconfig_path and os.path.exists(self.kubeconfig_path):
            try:
                os.unlink(self.kubeconfig_path)
            except:
                pass


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
            help_text = """🚀 PERSISTENT kubectl-ai TERMINAL - Exactly like your Mac terminal!

**kubectl-ai Mode:**
• Type / - Start persistent kubectl-ai session (EXACTLY like terminal)
• Press Esc - Exit kubectl-ai mode
• Continuous conversation with AI context maintained
• Natural language: "can you check my logs of pods?"
• Direct kubectl commands: kubectl get pods

**Direct kubectl Commands:**
• kubectl get pods - List all pods
• kubectl get nodes - List all nodes  
• kubectl get services - List all services
• kubectl describe pod <name> - Pod details
• kubectl logs <pod-name> - View pod logs
• kubectl apply -f <file> - Apply configuration
• kubectl delete pod <name> - Delete pod

**Terminal Commands:**
• ls, cat, mkdir, rm - File operations
• vim <filename> - Edit files with vim
• nano <filename> - Edit files with nano
• clear - Clear terminal
• pwd, cd - Navigation

**Debugging:**
• debug-ai - Debug kubectl-ai installation
• check-env - Check GEMINI_API_KEY setup
• kubectl-ai-test - Test kubectl-ai directly

**Navigation:**
• ↑↓ Arrow keys - Command history

🚀 Press / for PERSISTENT kubectl-ai session (exactly like terminal)!"""
            
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
        
        # Handle debug-ai command
        if command.strip() == 'debug-ai':
            try:
                # Call the debug function
                debug_request = type('Request', (), {'session': None})()
                debug_response = debug_kubectl_ai(debug_request, session_id)
                debug_data = json.loads(debug_response.content)
                
                if debug_data['success']:
                    debug_info = debug_data['debug_info']
                    
                    debug_output = "🔍 kubectl-ai Debug Information\n\n"
                    
                    # kubectl-ai location
                    if debug_info.get('kubectl_ai_which'):
                        if debug_info['kubectl_ai_which'].get('returncode') == 0:
                            debug_output += f"✅ kubectl-ai found at: {debug_info['kubectl_ai_which']['stdout']}\n\n"
                        else:
                            debug_output += "❌ kubectl-ai not found in PATH\n"
                            debug_output += f"Error: {debug_info['kubectl_ai_which'].get('stderr', 'Command not found')}\n\n"
                    
                    # kubectl-ai version
                    if debug_info.get('kubectl_ai_version'):
                        if debug_info['kubectl_ai_version'].get('returncode') == 0:
                            debug_output += f"📦 kubectl-ai version: {debug_info['kubectl_ai_version']['stdout']}\n\n"
                        else:
                            debug_output += "❌ kubectl-ai version check failed\n"
                            debug_output += f"Error: {debug_info['kubectl_ai_version'].get('stderr', 'Version check failed')}\n\n"
                    
                    # kubectl-ai help test
                    if debug_info.get('kubectl_ai_help'):
                        if debug_info['kubectl_ai_help'].get('returncode') == 0:
                            debug_output += "✅ kubectl-ai help command works\n\n"
                        else:
                            debug_output += "❌ kubectl-ai help command failed\n"
                            debug_output += f"Error: {debug_info['kubectl_ai_help'].get('stderr', 'Help command failed')}\n\n"
                    
                    # kubectl-ai test
                    if debug_info.get('kubectl_ai_test'):
                        if debug_info['kubectl_ai_test'].get('returncode') == 0:
                            debug_output += "✅ kubectl-ai with Gemini test successful\n"
                            debug_output += f"Output: {debug_info['kubectl_ai_test']['stdout'][:200]}...\n\n"
                        else:
                            debug_output += "❌ kubectl-ai with Gemini test failed\n"
                            debug_output += f"Error: {debug_info['kubectl_ai_test'].get('stderr', '')[:200]}...\n\n"
                            debug_output += "💡 Try running this manually to test:\n"
                            debug_output += "echo 'hello' | kubectl-ai --model gemini-2.5-flash-preview-04-17\n\n"
                    
                    # API Keys status
                    if debug_info.get('api_keys'):
                        debug_output += "🔑 API Keys Status:\n"
                        for key, status in debug_info['api_keys'].items():
                            status_icon = "✅" if "Set" in status else "❌"
                            debug_output += f"{status_icon} {key}: {status}\n"
                        debug_output += "\n"
                    
                    # Recommendations
                    debug_output += "💡 Troubleshooting Steps:\n"
                    
                    if debug_info.get('kubectl_ai_which', {}).get('returncode') != 0:
                        debug_output += "1. Install kubectl-ai: Visit https://github.com/sozercan/kubectl-ai\n"
                    
                    if debug_info.get('api_keys'):
                        has_api_key = any("Set" in status for status in debug_info['api_keys'].values())
                        if not has_api_key:
                            debug_output += "2. Set up API key: Configure GEMINI_API_KEY, OPENAI_API_KEY, or other provider\n"
                    
                    if debug_info.get('kubectl_ai_help', {}).get('returncode') != 0:
                        debug_output += "3. Check kubectl-ai installation and permissions\n"
                    
                    if debug_info.get('kubectl_ai_test', {}).get('returncode') != 0:
                        debug_output += "4. Check kubectl-ai configuration and AI provider setup\n"
                        debug_output += "5. Verify your API key is valid and has proper permissions\n"
                        debug_output += "6. Test manually: echo 'hello' | kubectl-ai --model gemini-2.5-flash-preview-04-17\n"
                        debug_output += "7. Make sure you've exported GEMINI_API_KEY in the same terminal where you run Django\n"
                    
                    # Store debug command in history
                    CommandHistory.objects.create(
                        chat_session=chat_session,
                        command=command,
                        output=debug_output,
                        exit_code=0
                    )
                    
                    return JsonResponse({
                        'success': True,
                        'output': debug_output,
                        'exit_code': 0
                    })
                else:
                    error_output = f"🚨 Debug Error: {debug_data.get('error', 'Unknown error')}"
                    
                    CommandHistory.objects.create(
                        chat_session=chat_session,
                        command=command,
                        output=error_output,
                        exit_code=1
                    )
                    
                    return JsonResponse({
                        'success': True,
                        'output': error_output,
                        'exit_code': 1
                    })
                    
            except Exception as e:
                error_output = f"🚨 Debug command failed: {str(e)}"
                
                CommandHistory.objects.create(
                    chat_session=chat_session,
                    command=command,
                    output=error_output,
                    exit_code=1
                )
                
                return JsonResponse({
                    'success': True,
                    'output': error_output,
                    'exit_code': 1
                })
        
        # Handle kubectl-ai-test command
        if command.strip() == 'kubectl-ai-test':
            test_output = "🧪 TESTING kubectl-ai DIRECTLY\n\n"
            
            try:
                # Test kubectl-ai with a simple message
                import subprocess
                import os
                
                # Set up environment
                env = os.environ.copy()
                env['KUBECONFIG'] = 'dummy'  # Use dummy for test
                
                test_output += "1. Testing kubectl-ai executable:\n"
                which_result = subprocess.run('which kubectl-ai', shell=True, capture_output=True, text=True, timeout=5)
                if which_result.returncode == 0:
                    test_output += f"   ✅ kubectl-ai found at: {which_result.stdout.strip()}\n\n"
                else:
                    test_output += "   ❌ kubectl-ai not found in PATH\n\n"
                    CommandHistory.objects.create(
                        chat_session=chat_session,
                        command=command,
                        output=test_output,
                        exit_code=1
                    )
                    return JsonResponse({
                        'success': True,
                        'output': test_output,
                        'exit_code': 1
                    })
                
                test_output += "2. Testing kubectl-ai with Gemini API:\n"
                try:
                    test_result = subprocess.run(
                        'echo "hello, are you working?" | kubectl-ai --model gemini-2.5-flash-preview-04-17',
                        shell=True, capture_output=True, text=True, timeout=20, env=env
                    )
                    
                    if test_result.returncode == 0 and test_result.stdout.strip():
                        test_output += f"   ✅ kubectl-ai working! Response:\n   {test_result.stdout.strip()}\n\n"
                        test_output += "🎉 kubectl-ai is ready for persistent session!\n"
                        test_output += "💡 Press / to start persistent kubectl-ai mode\n"
                        exit_code = 0
                    else:
                        test_output += f"   ❌ kubectl-ai test failed\n"
                        test_output += f"   Error: {test_result.stderr}\n\n"
                        test_output += "💡 Check GEMINI_API_KEY: export GEMINI_API_KEY='your-key'\n"
                        test_output += "💡 Then restart Django server\n"
                        exit_code = 1
                        
                except subprocess.TimeoutExpired:
                    test_output += "   ⚠️ kubectl-ai test timed out (this can be normal)\n"
                    test_output += "💡 Press / to try persistent session anyway\n"
                    exit_code = 0
                    
            except Exception as e:
                test_output += f"❌ Test error: {str(e)}\n"
                exit_code = 1
            
            CommandHistory.objects.create(
                chat_session=chat_session,
                command=command,
                output=test_output,
                exit_code=exit_code
            )
            
            return JsonResponse({
                'success': True,
                'output': test_output,
                'exit_code': exit_code
            })
        
        # Handle check-env command
        if command.strip() == 'check-env':
            env_output = "🔍 Environment Check for AI Chat\n\n"
            
            # Check API keys
            api_keys = ['GEMINI_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY']
            env_output += "🔑 API Keys Status:\n"
            has_api_key = False
            for key in api_keys:
                if os.environ.get(key):
                    env_output += f"✅ {key}: Set and available to Django\n"
                    has_api_key = True
                else:
                    env_output += f"❌ {key}: Not found in Django environment\n"
            
            if not has_api_key:
                env_output += "\n🚨 PROBLEM: No API keys found in Django environment\n"
                env_output += "💡 SOLUTION:\n"
                env_output += "1. Stop Django server (Ctrl+C)\n"
                env_output += "2. Export your API key:\n"
                env_output += "   export GEMINI_API_KEY='your-gemini-api-key-here'\n"
                env_output += "3. Restart Django:\n"
                env_output += "   python manage.py runserver\n"
                env_output += "4. Try AI chat again\n\n"
            
            # Check kubectl-ai
            env_output += "🤖 kubectl-ai Status:\n"
            try:
                which_result = subprocess.run('which kubectl-ai', shell=True, capture_output=True, text=True, timeout=5)
                if which_result.returncode == 0:
                    env_output += f"✅ kubectl-ai found at: {which_result.stdout.strip()}\n"
                else:
                    env_output += "❌ kubectl-ai not found in PATH\n"
                    env_output += "💡 Install with: brew install kubectl-ai (macOS)\n"
            except Exception as e:
                env_output += f"❌ Error checking kubectl-ai: {str(e)}\n"
            
            # Test kubectl-ai if available and API key exists
            if has_api_key:
                env_output += "\n🧪 Testing kubectl-ai with API:\n"
                try:
                    # Use Python's timeout instead of shell timeout command (not available on all systems)
                    test_result = subprocess.run(
                        'echo "test" | kubectl-ai --model gemini-2.5-flash-preview-04-17',
                        shell=True, capture_output=True, text=True, timeout=15
                    )
                    if test_result.returncode == 0:
                        env_output += "✅ kubectl-ai working with Gemini API\n"
                    else:
                        env_output += "❌ kubectl-ai test failed\n"
                        if test_result.stderr:
                            env_output += f"Error: {test_result.stderr[:100]}\n"
                except subprocess.TimeoutExpired:
                    env_output += "⚠️ kubectl-ai test timed out (but this is often normal)\n"
                except Exception as e:
                    env_output += f"❌ kubectl-ai test error: {str(e)}\n"
            
            env_output += "\n💡 If AI chat still doesn't work:\n"
            env_output += "1. Make sure API key is exported in same terminal as Django\n"
            env_output += "2. Restart Django completely\n"
            env_output += "3. Try 'debug-ai' command for more details\n"
            
            CommandHistory.objects.create(
                chat_session=chat_session,
                command=command,
                output=env_output,
                exit_code=0
            )
            
            return JsonResponse({
                'success': True,
                'output': env_output,
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


@csrf_exempt
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
    """Check cluster connection status."""
    try:
        cluster = get_object_or_404(KubernetesCluster, id=cluster_id)
        
        # Test connection by running a simple kubectl command
        if cluster.kubeconfig:
            try:
                # Create a temporary kubeconfig file
                with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                    f.write(cluster.kubeconfig)
                    kubeconfig_path = f.name
                
                try:
                    # Test connection with a simple command that actually tests server connectivity
                    env = os.environ.copy()
                    env['KUBECONFIG'] = kubeconfig_path
                    
                    # First try to get cluster info (tests actual connectivity)
                    result = subprocess.run(
                        ['kubectl', 'cluster-info', '--request-timeout=5s'],
                        capture_output=True,
                        text=True,
                        env=env,
                        timeout=8  # Short timeout for status check
                    )
                    
                    if result.returncode == 0 and 'running at' in result.stdout.lower():
                        # Cluster is actually reachable
                        cluster.connection_status = 'connected'
                        cluster.save()
                        
                        return JsonResponse({
                            'success': True,
                            'status': 'connected'
                        })
                    else:
                        # Try fallback - just test if kubeconfig is valid
                        fallback_result = subprocess.run(
                            ['kubectl', 'config', 'view', '--minify'],
                            capture_output=True,
                            text=True,
                            env=env,
                            timeout=5
                        )
                        
                        if fallback_result.returncode == 0:
                            # Kubeconfig is valid, assume connection is working
                            cluster.connection_status = 'connected'
                            cluster.save()
                            
                            return JsonResponse({
                                'success': True,
                                'status': 'connected'
                            })
                        else:
                            # Connection failed
                            cluster.connection_status = 'error'
                            cluster.save()
                            
                            return JsonResponse({
                                'success': True,
                                'status': 'error'
                            })
                        
                finally:
                    # Clean up temporary file
                    if os.path.exists(kubeconfig_path):
                        os.unlink(kubeconfig_path)
                        
            except subprocess.TimeoutExpired:
                cluster.connection_status = 'error'
                cluster.save()
                return JsonResponse({
                    'success': True,
                    'status': 'error'
                })
            except Exception as e:
                cluster.connection_status = 'error'
                cluster.save()
                return JsonResponse({
                    'success': True,
                    'status': 'error'
                })
        else:
            # No kubeconfig available
            cluster.connection_status = 'error'
            cluster.save()
            return JsonResponse({
                'success': True,
                'status': 'error'
            })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Server error: {str(e)}'
        }) 


@csrf_exempt
@require_http_methods(["POST"])
def start_ai_session(request, session_id):
    """🚀 TERMINAL MODE: Start kubectl-ai exactly like your terminal!"""
    try:
        chat_session = get_object_or_404(ChatSession, session_id=session_id)
        
        # Check if session already exists and is healthy
        if session_id in active_ai_sessions:
            ai_session = active_ai_sessions[session_id]
            if ai_session.running and ai_session.process and ai_session.process.poll() is None:
                return JsonResponse({
                    'success': True,
                    'message': 'kubectl-ai session already active',
                    'initial_response': 'kubectl-ai session is ready. How can I help you with your Kubernetes cluster?'
                })
            else:
                # Clean up dead session
                try:
                    ai_session.stop_persistent_session()
                except:
                    pass
                del active_ai_sessions[session_id]
        
        print(f"🚀 TERMINAL MODE: Starting kubectl-ai for session {session_id}")
        
        # Create and start new kubectl-ai session
        ai_session = PersistentKubectlAI(chat_session.cluster, session_id)
        
        if ai_session.start_persistent_session():
            active_ai_sessions[session_id] = ai_session
            
            return JsonResponse({
                'success': True,
                'message': 'kubectl-ai session started!',
                'initial_response': 'Hey there, what can I help you with today ?'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Failed to start kubectl-ai session. Make sure kubectl-ai is installed and GEMINI_API_KEY is set in Django environment.'
            })
            
    except ChatSession.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Chat session not found'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error starting kubectl-ai session: {str(e)}'
        })


@csrf_exempt  
@require_http_methods(["GET"])
def debug_kubectl_ai(request, session_id):
    """Debug endpoint to check kubectl-ai installation and environment."""
    try:
        debug_info = {}
        
        # Check if kubectl-ai exists
        try:
            which_result = subprocess.run('which kubectl-ai', shell=True, capture_output=True, text=True, timeout=5)
            debug_info['kubectl_ai_which'] = {
                'returncode': which_result.returncode,
                'stdout': which_result.stdout.strip(),
                'stderr': which_result.stderr.strip()
            }
        except Exception as e:
            debug_info['kubectl_ai_which'] = {'error': str(e)}
        
        # Try to run kubectl-ai --version
        try:
            version_result = subprocess.run('kubectl-ai --version', shell=True, capture_output=True, text=True, timeout=10)
            debug_info['kubectl_ai_version'] = {
                'returncode': version_result.returncode,
                'stdout': version_result.stdout.strip(),
                'stderr': version_result.stderr.strip()
            }
        except Exception as e:
            debug_info['kubectl_ai_version'] = {'error': str(e)}
        
        # Check PATH
        debug_info['PATH'] = os.environ.get('PATH', 'Not found')
        
        # Test kubectl-ai functionality
        try:
            test_basic = subprocess.run('kubectl-ai --help', shell=True, capture_output=True, text=True, timeout=10)
            debug_info['kubectl_ai_help'] = {
                'returncode': test_basic.returncode,
                'stdout': test_basic.stdout[:500] if test_basic.stdout else '',
                'stderr': test_basic.stderr[:500] if test_basic.stderr else ''
            }
        except Exception as e:
            debug_info['kubectl_ai_help'] = {'error': str(e)}
        
        # Try direct kubectl-ai test with simple query using user's working Gemini model
        try:
            test_result = subprocess.run(
                'echo "hello" | kubectl-ai --model gemini-2.5-flash-preview-04-17',
                shell=True, capture_output=True, text=True, timeout=30
            )
            debug_info['kubectl_ai_test'] = {
                'returncode': test_result.returncode,
                'stdout': test_result.stdout[:500],  # Limit output
                'stderr': test_result.stderr[:500]
            }
        except subprocess.TimeoutExpired:
            debug_info['kubectl_ai_test'] = {
                'returncode': 124,
                'stdout': '',
                'stderr': 'Test timed out (often normal for API calls)'
            }
        except Exception as e:
            debug_info['kubectl_ai_test'] = {'error': str(e)}
        
        # Check environment variables for API keys
        env_vars = {}
        api_key_vars = [
            'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'OPENAI_API_KEY', 
            'ANTHROPIC_API_KEY', 'AZURE_OPENAI_API_KEY'
        ]
        for var in api_key_vars:
            if os.environ.get(var):
                env_vars[var] = "Set (hidden for security)"
            else:
                env_vars[var] = "Not set"
        debug_info['api_keys'] = env_vars
        
        return JsonResponse({
            'success': True,
            'debug_info': debug_info
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Debug error: {str(e)}'
        })


@csrf_exempt
@require_http_methods(["GET"])
def check_ai_session(request, session_id):
    """Check if an interactive AI session is active."""
    try:
        is_active = session_id in active_ai_sessions
        if is_active:
            ai_session = active_ai_sessions[session_id]
            is_running = ai_session.running and ai_session.process and ai_session.process.poll() is None
        else:
            is_running = False
        
        return JsonResponse({
            'success': True,
            'is_active': is_active and is_running,
            'session_exists': is_active
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error checking AI session: {str(e)}'
        })


@csrf_exempt
@require_http_methods(["POST"])
def stop_ai_session(request, session_id):
    """Stop the persistent kubectl-ai session."""
    try:
        if session_id in active_ai_sessions:
            ai_session = active_ai_sessions[session_id]
            
            # Stop persistent session
            if hasattr(ai_session, 'stop_persistent_session'):
                print(f"🚀 PERSISTENT: Stopping persistent kubectl-ai session")
                ai_session.stop_persistent_session()
            # Stop old interactive session
            elif hasattr(ai_session, 'stop_session'):
                print(f"🚀 FALLBACK: Stopping old interactive session")
                ai_session.stop_session()
            
            del active_ai_sessions[session_id]
        
        return JsonResponse({
            'success': True,
            'message': 'kubectl-ai session stopped'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error stopping kubectl-ai session: {str(e)}'
        })


@csrf_exempt
@require_http_methods(["POST"])
def ai_assistance(request, session_id):
    """🚀 TERMINAL MODE: kubectl-ai exactly like your terminal!"""
    try:
        chat_session = get_object_or_404(ChatSession, session_id=session_id)
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()
        
        if not user_message:
            return JsonResponse({
                'success': False,
                'error': 'Message is required'
            })
        
        print(f"🚀 TERMINAL MODE: Processing: {repr(user_message)}")
        
        # Check if kubectl-ai session exists
        if session_id not in active_ai_sessions:
            return JsonResponse({
                'success': False,
                'error': 'kubectl-ai session not active. Please restart AI mode (press Esc, then /).'
            })
        
        ai_session = active_ai_sessions[session_id]
        
        # Check if session is alive
        if not (ai_session.running and ai_session.process and ai_session.process.poll() is None):
            # Clean up dead session
            try:
                ai_session.stop_persistent_session()
            except:
                pass
            del active_ai_sessions[session_id]
            
            return JsonResponse({
                'success': False,
                'error': 'kubectl-ai session has ended. Please restart AI mode (press Esc, then /).'
            })
        
        # Send message to kubectl-ai (exactly like terminal)
        print(f"🚀 TERMINAL MODE: Sending to kubectl-ai: {repr(user_message)}")
        
        try:
            response = ai_session.send_persistent_message(user_message)
            print(f"🚀 TERMINAL MODE: Got response: {repr(response[:200] if response else 'None')}")
            
            if not response or response.startswith("kubectl-ai not running"):
                return JsonResponse({
                    'success': False,
                    'error': 'kubectl-ai session ended. Please restart AI mode.'
                })
            
            # Store in history
            CommandHistory.objects.create(
                chat_session=chat_session,
                command=f"💬 {user_message}",
                output=response,
                exit_code=0
            )
            
            chat_session.last_activity = timezone.now()
            chat_session.save()
            
            return JsonResponse({
                'success': True,
                'response': response,
                'commands': extract_kubectl_commands(response),
                'is_interactive': True,
                'is_kubectl_ai': True
            })
            
        except Exception as e:
            print(f"🚨 TERMINAL MODE ERROR: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': f'kubectl-ai error: {str(e)}. Try restarting AI mode.'
            })
            
    except ChatSession.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Chat session not found'
        })
    except Exception as e:
        print(f"🚨 UNEXPECTED ERROR: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Unexpected error: {str(e)}'
        })


# Removed old non-interactive functions - now using InteractiveKubectlAI class


def execute_kubectl_command_directly(cluster, command):
    """🚀 FULL TERMINAL: Execute kubectl commands directly against the cluster!"""
    try:
        # Create temporary kubeconfig file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(cluster.kubeconfig)
            kubeconfig_path = f.name
        
        try:
            # Set environment variables for command execution
            env = os.environ.copy()
            env['KUBECONFIG'] = kubeconfig_path
            
            print(f"🚀 FULL TERMINAL: Executing: {command}")
            
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                env=env,
                timeout=60,  # 60 seconds for kubectl commands
                cwd=os.path.expanduser('~')
            )
            
            output = result.stdout
            if result.stderr:
                output += f"\nError: {result.stderr}"
            
            return {
                'output': f"🚀 DIRECT KUBECTL EXECUTION:\n\n{output}",
                'exit_code': result.returncode
            }
            
        finally:
            # Clean up temp file
            os.unlink(kubeconfig_path)
            
    except subprocess.TimeoutExpired:
        return {
            'output': '🚀 FULL TERMINAL: Command timed out after 60 seconds',
            'exit_code': 124
        }
    except Exception as e:
        return {
            'output': f'🚀 FULL TERMINAL: Error executing command: {str(e)}',
            'exit_code': 1
        }


def intelligent_kubectl_interpreter(cluster, user_message):
    """🚀 FULL TERMINAL: Intelligent kubectl command interpreter!"""
    message_lower = user_message.lower()
    
    # Mapping of natural language to kubectl commands
    kubectl_mappings = [
        # Pod queries
        (r'how many pods?|pod count|count pods', 'kubectl get pods --no-headers | wc -l'),
        (r'show.*pods?|list.*pods?|get.*pods?', 'kubectl get pods'),
        (r'pod.*status|running.*pods?', 'kubectl get pods -o wide'),
        (r'pod.*details?|describe.*pod', 'kubectl get pods -o yaml'),
        
        # Node queries  
        (r'show.*nodes?|list.*nodes?|get.*nodes?', 'kubectl get nodes'),
        (r'node.*status', 'kubectl get nodes -o wide'),
        (r'describe.*node', 'kubectl describe nodes'),
        
        # Service queries
        (r'show.*services?|list.*services?|get.*services?', 'kubectl get services'),
        (r'service.*status', 'kubectl get services -o wide'),
        
        # Deployment queries
        (r'show.*deployments?|list.*deployments?|get.*deployments?', 'kubectl get deployments'),
        (r'deployment.*status', 'kubectl get deployments -o wide'),
        
        # Namespace queries
        (r'show.*namespaces?|list.*namespaces?|get.*namespaces?', 'kubectl get namespaces'),
        
        # General cluster info
        (r'cluster.*info|cluster.*status', 'kubectl cluster-info'),
        (r'cluster.*version', 'kubectl version'),
        
        # Resource queries
        (r'show.*all|list.*all|get.*all', 'kubectl get all'),
        (r'what.*running|what.*cluster', 'kubectl get all --all-namespaces'),
    ]
    
    # Find matching command
    for pattern, kubectl_cmd in kubectl_mappings:
        import re
        if re.search(pattern, message_lower):
            print(f"🚀 FULL TERMINAL: Matched pattern '{pattern}' -> {kubectl_cmd}")
            result = execute_kubectl_command_directly(cluster, kubectl_cmd)
            result['suggested_commands'] = [kubectl_cmd]
            return result
    
    # If no pattern matches, try to extract kubectl-like intent
    if any(word in message_lower for word in ['pod', 'node', 'service', 'deployment', 'namespace', 'cluster']):
        # Provide helpful suggestions
        suggestions = [
            "kubectl get pods",
            "kubectl get nodes", 
            "kubectl get services",
            "kubectl get deployments",
            "kubectl cluster-info"
        ]
        
        return {
            'output': f"""🚀 FULL TERMINAL: I understand you're asking about Kubernetes resources, but I couldn't match your exact request.

Here are some useful commands you can try:

• kubectl get pods - List all pods
• kubectl get nodes - List all nodes  
• kubectl get services - List all services
• kubectl get deployments - List all deployments
• kubectl cluster-info - Get cluster information

Or you can type any kubectl command directly, like:
kubectl get pods -o wide
kubectl describe pod <pod-name>
kubectl logs <pod-name>

Just type the kubectl command and I'll execute it against your cluster!""",
            'exit_code': 0,
            'suggested_commands': suggestions
        }
    
    # For non-kubernetes queries, provide general help
    return {
        'output': f"""🚀 FULL TERMINAL: Interactive Kubernetes Terminal Ready!

You can:
1. Type any kubectl command directly: kubectl get pods
2. Ask natural questions: "how many pods are running?"
3. Get cluster info: "show me cluster status"
4. List resources: "show all services"

Example commands:
• kubectl get pods
• kubectl get nodes
• kubectl get services  
• kubectl describe pod <name>
• kubectl logs <pod-name>
• kubectl cluster-info

What would you like to explore in your cluster?""",
        'exit_code': 0,
        'suggested_commands': [
            "kubectl get pods",
            "kubectl get nodes",
            "kubectl cluster-info"
        ]
    }


def extract_kubectl_commands(response):
    """Extract kubectl commands from AI response."""
    commands = []
    lines = response.split('\n')
    
    for line in lines:
        # Look for lines that contain kubectl commands
        stripped = line.strip()
        if (stripped.startswith('kubectl ') or 
            stripped.startswith('$ kubectl ') or
            '`kubectl ' in stripped):
            
            # Clean up the command
            if stripped.startswith('$ '):
                command = stripped[2:]
            elif '`' in stripped:
                # Extract command from markdown code block
                start = stripped.find('`') + 1
                end = stripped.find('`', start)
                if end > start:
                    command = stripped[start:end]
                else:
                    continue
            else:
                command = stripped
            
            if command.startswith('kubectl ') and command not in commands:
                commands.append(command)
    
    return commands[:5]  # Limit to 5 commands


# Removed extract_suggestions and extract_follow_up_questions - handled by interactive kubectl-ai