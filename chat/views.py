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
    """🚀 PERSISTENT kubectl-ai SESSION: Exactly like running kubectl-ai in terminal!"""
    
    def __init__(self, cluster, session_id):
        self.cluster = cluster
        self.session_id = session_id
        self.process = None
        self.input_queue = queue.Queue()
        self.output_queue = queue.Queue()
        self.running = False
        self.kubeconfig_path = None
        self.conversation_history = []
        self.session_context = ""
    
    def start_persistent_session(self):
        """Start a persistent kubectl-ai session that stays alive like terminal."""
        try:
            print(f"🚀 PERSISTENT: Starting kubectl-ai session like terminal...")
            
            # Create temporary kubeconfig file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                f.write(self.cluster.kubeconfig)
                self.kubeconfig_path = f.name
            
            # Find kubectl-ai executable
            kubectl_ai_path = self._find_kubectl_ai()
            if not kubectl_ai_path:
                print("kubectl-ai not found in PATH")
                return False
            
            # Set up environment exactly like terminal
            import os
            import pty
            
            env = os.environ.copy()
            env['KUBECONFIG'] = self.kubeconfig_path
            env['TERM'] = 'xterm-256color'
            env['COLUMNS'] = '120'
            env['LINES'] = '30'
            
            # Ensure GEMINI_API_KEY is available
            if 'GEMINI_API_KEY' not in env and 'GEMINI_API_KEY' in os.environ:
                env['GEMINI_API_KEY'] = os.environ['GEMINI_API_KEY']
            
            print(f"🚀 PERSISTENT: Using kubectl-ai at: {kubectl_ai_path}")
            print(f"🚀 PERSISTENT: GEMINI_API_KEY available: {'GEMINI_API_KEY' in env}")
            
            # Create PTY pair for terminal emulation
            master_fd, slave_fd = pty.openpty()
            
            # Start kubectl-ai in persistent mode
            cmd = f'{kubectl_ai_path} --model gemini-2.5-flash-preview-04-17'
            
            self.process = subprocess.Popen(
                cmd,
                shell=True,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                env=env,
                cwd=os.path.expanduser('~'),
                preexec_fn=os.setsid
            )
            
            os.close(slave_fd)
            self.master_fd = master_fd
            
            # Wait for process to start
            time.sleep(2)
            if self.process.poll() is not None:
                print(f"🚀 PERSISTENT: kubectl-ai process failed to start. Exit code: {self.process.returncode}")
                return False
            
            print(f"🚀 PERSISTENT: kubectl-ai process started successfully. PID: {self.process.pid}")
            
            self.running = True
            
            # Start communication threads
            self.input_thread = threading.Thread(target=self._persistent_input_handler, daemon=True)
            self.output_thread = threading.Thread(target=self._persistent_output_handler, daemon=True)
            self.monitor_thread = threading.Thread(target=self._session_monitor, daemon=True)
            
            self.input_thread.start()
            self.output_thread.start()
            self.monitor_thread.start()
            
            print(f"🚀 PERSISTENT: All threads started successfully")
            
            # Wait for initial kubectl-ai greeting and clean it properly
            print(f"⏰ WAITING FOR INITIAL kubectl-ai GREETING...")
            for i in range(10):  # Wait up to 10 seconds for greeting
                time.sleep(1)
                try:
                    initial_response = self.output_queue.get(timeout=1)
                    if initial_response and initial_response.strip():
                        print(f"✅ CAPTURED INITIAL GREETING: {repr(initial_response[:100])}")
                        # Put it back for the frontend to receive
                        self.output_queue.put(initial_response)
                        break
                except queue.Empty:
                    continue
            else:
                print(f"⚠️ NO INITIAL GREETING RECEIVED")
            
            return True
            
        except Exception as e:
            print(f"🚀 PERSISTENT: Failed to start session: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _find_kubectl_ai(self):
        """Find kubectl-ai executable."""
        possible_paths = [
            'kubectl-ai',
            '/usr/local/bin/kubectl-ai',
            '/opt/homebrew/bin/kubectl-ai',
            os.path.expanduser('~/.local/bin/kubectl-ai'),
            os.path.expanduser('~/go/bin/kubectl-ai'),
            '/usr/bin/kubectl-ai'
        ]
        
        for path in possible_paths:
            try:
                result = subprocess.run(['which', path], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    return result.stdout.strip()
                if os.path.isfile(path) and os.access(path, os.X_OK):
                    return path
            except Exception:
                continue
        
        try:
            result = subprocess.run('which kubectl-ai', shell=True, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
            
        return None
    
    def _persistent_input_handler(self):
        """Handle sending messages to persistent kubectl-ai session."""
        import os
        
        while self.running and self.process and self.process.poll() is None:
            try:
                message = self.input_queue.get(timeout=1)
                if message is None:  # Shutdown signal
                    break
                
                if self.process.poll() is not None:
                    break
                
                print(f"🚀 PERSISTENT: Sending to kubectl-ai: {repr(message)}")
                
                # Send message to kubectl-ai (just like typing in terminal)
                full_message = f"{message}\n"
                os.write(self.master_fd, full_message.encode('utf-8'))
                
                # Add to conversation history
                self.conversation_history.append(f"User: {message}")
                
            except queue.Empty:
                if self.process.poll() is not None:
                    break
                continue
            except Exception as e:
                print(f"🚀 PERSISTENT: Input handler error: {e}")
                break
    
    def _persistent_output_handler(self):
        """Handle receiving responses from persistent kubectl-ai session."""
        import select
        import os
        import re
        import fcntl
        
        try:
            fcntl.fcntl(self.master_fd, fcntl.F_SETFL, os.O_NONBLOCK)
        except:
            pass
        
        response_buffer = ""
        last_activity = time.time()
        
        while self.running and self.process and self.process.poll() is None:
            try:
                ready, _, _ = select.select([self.master_fd], [], [], 0.5)
                
                if ready:
                    try:
                        data = os.read(self.master_fd, 4096).decode('utf-8', errors='ignore')
                        if data:
                            response_buffer += data
                            last_activity = time.time()
                            
                            # Check if response is complete
                            if self._is_persistent_response_complete(response_buffer):
                                cleaned = self._clean_persistent_response(response_buffer)
                                if cleaned.strip():
                                    print(f"🚀 PERSISTENT: Complete response detected")
                                    self.conversation_history.append(f"AI: {cleaned}")
                                    self.output_queue.put(cleaned)
                                    response_buffer = ""
                    
                    except OSError as e:
                        if e.errno in [5, 11]:  # I/O error or would block
                            break
                        continue
                
                # More aggressive timeout handling for terminal-like responsiveness
                elif response_buffer.strip() and (time.time() - last_activity) > 1.5:  # Shorter timeout
                    cleaned = self._clean_persistent_response(response_buffer)
                    if cleaned.strip() and len(cleaned.strip()) > 5:  # Lower threshold
                        print(f"🚀 PERSISTENT: Timeout response (1.5s)")
                        self.conversation_history.append(f"AI: {cleaned}")
                        self.output_queue.put(cleaned)
                        response_buffer = ""
                    elif len(response_buffer.strip()) > 15:  # Send even unclean content if substantial
                        print(f"🚀 PERSISTENT: Sending raw substantial content")
                        raw_content = response_buffer.strip()
                        # Basic cleaning only
                        import re
                        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
                        raw_content = ansi_escape.sub('', raw_content)
                        control_sequences = re.compile(r'\d+;[\d?]*;?\??')
                        raw_content = control_sequences.sub('', raw_content)
                        
                        if raw_content.strip():
                            self.conversation_history.append(f"AI: {raw_content}")
                            self.output_queue.put(raw_content)
                            response_buffer = ""
                
            except Exception as e:
                print(f"🚀 PERSISTENT: Output handler error: {e}")
                break
    
    def _is_persistent_response_complete(self, buffer):
        """Check if kubectl-ai response is complete - EXACTLY like terminal detection!"""
        import re
        
        # Remove control sequences for analysis
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        clean_buffer = ansi_escape.sub('', buffer)
        
        # Remove those pesky control sequences like "11;?11;?"
        control_sequences = re.compile(r'\d+;[\d?]*;?\??')
        clean_buffer = control_sequences.sub('', clean_buffer)
        
        print(f"🔍 COMPLETION CHECK: {repr(clean_buffer[:150])}")
        
        if len(clean_buffer.strip()) < 3:  # Very low threshold
            return False
        
        # Look for typical kubectl-ai completion patterns (be more liberal)
        completion_patterns = [
            # Common kubectl-ai phrases
            r"How can I help you",
            r"What would you like to know",
            r"Is there anything else",
            r"Any other questions",
            r"Let me know if you need",
            r"Feel free to ask",
            r"anything else I can help",
            r"What can I do for you",
            r"I can help you with",
            
            # kubectl command patterns
            r"kubectl get", r"kubectl describe", r"kubectl logs", r"kubectl apply",
            r"Running:", r"command failed", r"Error from server",
            r"No resources found", r"connection.*refused", r"not configured",
            
            # Status words
            r"running", r"pending", r"succeeded", r"failed", r"ready",
            r"created", r"deleted", r"scaled",
            
            # Kubernetes resource types
            r"pods?", r"nodes?", r"services?", r"deployments?", r"namespaces?",
            
            # Error patterns
            r"error:", r"failed", r"unable to", r"cannot", r"refused",
            
            # Helpful responses
            r"make sure", r"please", r"try", r"check"
        ]
        
        for pattern in completion_patterns:
            if re.search(pattern, clean_buffer, re.IGNORECASE):
                print(f"✅ FOUND COMPLETION PATTERN: {pattern}")
                return True
        
        # Check for natural sentence endings (be liberal)
        lines = [line.strip() for line in clean_buffer.split('\n') if line.strip()]
        if lines:
            last_line = lines[-1]
            if len(last_line) > 5:  # Lower threshold
                # Check for sentence endings
                if any(last_line.endswith(punct) for punct in ['.', '?', '!', ':', ')', ';']):
                    print(f"✅ FOUND SENTENCE ENDING: {repr(last_line)}")
                    return True
                
                # Check for common kubectl-ai phrase endings
                if any(phrase in last_line.lower() for phrase in ['help you', 'try', 'check', 'make sure', 'please']):
                    print(f"✅ FOUND HELPFUL PHRASE: {repr(last_line)}")
                    return True
        
        # If we have substantial content and it looks like complete thoughts
        if len(clean_buffer.strip()) > 20:
            # Count sentences (very liberal)
            sentence_count = len([line for line in lines if len(line) > 10])
            if sentence_count >= 1:  # Even just one substantial line
                print(f"✅ SUBSTANTIAL CONTENT: {sentence_count} lines")
                return True
        
        print(f"❌ NOT COMPLETE YET: {len(clean_buffer)} chars, {len(lines)} lines")
        return False
    
    def _clean_persistent_response(self, response):
        """Clean kubectl-ai response for persistent session - EXACTLY like terminal output!"""
        import re
        
        print(f"🧹 CLEANING RAW RESPONSE: {repr(response[:200])}")
        
        # Step 1: Remove ALL terminal control sequences and escape codes
        # Remove ANSI escape sequences
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        cleaned = ansi_escape.sub('', response)
        
        # Remove those specific control sequences like "11;?11;?"
        control_sequences = re.compile(r'\d+;[\d?]*;?\??')
        cleaned = control_sequences.sub('', cleaned)
        
        # Remove other control characters but preserve newlines and basic punctuation
        control_chars = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]+')
        cleaned = control_chars.sub('', cleaned)
        
        # Remove cursor positioning and other terminal codes
        cursor_codes = re.compile(r'\[\d+[ABCDK]|\[\d+;\d+[Hf]|\[J|\[2K|\[K')
        cleaned = cursor_codes.sub('', cleaned)
        
        print(f"🧹 AFTER CONTROL CLEANING: {repr(cleaned[:200])}")
        
        # Step 2: Split into lines and filter out prompts/echoes
        lines = cleaned.split('\n')
        good_lines = []
        
        for line in lines:
            original_line = line
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
                
            # Skip prompts, echoes, and terminal artifacts
            skip_patterns = [
                r'^>>>',              # kubectl-ai prompts
                r'^user@',           # User prompts  
                r'^kubectl-ai:',     # App prompts
                r'^\$',              # Shell prompts
                r'^#',               # Comments
                r'^\w{1,3}$',        # Very short artifacts
                r'^\d+$',            # Just numbers
                r'^[;:]+$',          # Just punctuation
                r'^J$',              # Terminal clear commands
                # Skip user input echoes
                r'^hi$',
                r'^how many pods$',
                r'^hello$'
            ]
            
            should_skip = False
            for pattern in skip_patterns:
                if re.match(pattern, line, re.IGNORECASE):
                    should_skip = True
                    break
            
            if should_skip:
                print(f"🗑️ SKIPPING LINE: {repr(line)}")
                continue
                
            # Keep substantial content
            if len(line) > 3:  # More liberal threshold
                good_lines.append(line)
                print(f"✅ KEEPING LINE: {repr(line)}")
        
        # Step 3: Join and clean up spacing
        if good_lines:
            result = '\n'.join(good_lines)
            # Clean up excessive whitespace
            result = re.sub(r' +', ' ', result)
            result = re.sub(r'\n\s*\n\s*\n+', '\n\n', result)
            result = result.strip()
            
            print(f"🎯 FINAL CLEANED RESULT: {repr(result[:200])}")
            return result
        
        # Step 4: If no good lines, return raw cleaned content (fallback)
        raw_cleaned = re.sub(r' +', ' ', cleaned.strip())
        print(f"🔄 FALLBACK RESULT: {repr(raw_cleaned[:200])}")
        
        if len(raw_cleaned) > 10:
            return raw_cleaned
        
        return ""
    
    def _session_monitor(self):
        """Monitor persistent session health."""
        while self.running and self.process and self.process.poll() is None:
            time.sleep(5)
            if self.process.poll() is not None:
                print(f"🚀 PERSISTENT: Session ended with exit code: {self.process.poll()}")
                self.running = False
                break
    
    def send_persistent_message(self, message):
        """Send message to persistent kubectl-ai session and get response - EXACTLY like terminal!"""
        if not self.running or not self.process or self.process.poll() is not None:
            print(f"🚨 SESSION NOT RUNNING: running={self.running}, process={self.process}, poll={self.process.poll() if self.process else None}")
            return "Session not running. Please restart AI mode."
        
        print(f"🚀 SENDING MESSAGE: {repr(message)}")
        
        # Clear any old responses
        old_responses = []
        while not self.output_queue.empty():
            try:
                old = self.output_queue.get_nowait()
                old_responses.append(old)
            except queue.Empty:
                break
        
        if old_responses:
            print(f"🗑️ CLEARED OLD RESPONSES: {len(old_responses)} items")
        
        # Send message to kubectl-ai
        self.input_queue.put(message)
        print(f"📤 MESSAGE QUEUED FOR kubectl-ai")
        
        # Wait for response with multiple attempts
        for attempt in range(3):  # Try 3 times
            try:
                print(f"⏰ WAITING FOR RESPONSE (attempt {attempt + 1}/3, timeout=20s)")
                response = self.output_queue.get(timeout=20)  # Longer timeout
                
                if response and response.strip():
                    print(f"✅ GOT RESPONSE: {repr(response[:100])}")
                    return response
                else:
                    print(f"⚠️ EMPTY RESPONSE on attempt {attempt + 1}")
                    if attempt < 2:  # If not last attempt
                        time.sleep(2)  # Wait before retry
                        continue
                        
            except queue.Empty:
                print(f"⏰ TIMEOUT on attempt {attempt + 1}")
                
                # Check if process is still alive
                if self.process.poll() is not None:
                    print(f"🚨 PROCESS DIED during response wait")
                    return "kubectl-ai process has ended. Please restart AI mode."
                
                if attempt < 2:  # If not last attempt
                    print(f"🔄 RETRYING... (attempt {attempt + 2})")
                    time.sleep(1)
                    continue
        
        # All attempts failed
        print(f"🚨 ALL ATTEMPTS FAILED - kubectl-ai not responding")
        
        # Check if we can get any partial response from the output handler
        print(f"🔍 CHECKING FOR PARTIAL RESPONSES...")
        partial_responses = []
        while not self.output_queue.empty():
            try:
                partial = self.output_queue.get_nowait()
                partial_responses.append(partial)
            except queue.Empty:
                break
        
        if partial_responses:
            combined = '\n'.join(partial_responses)
            print(f"📝 FOUND PARTIAL RESPONSE: {repr(combined[:100])}")
            return combined
        
        return "kubectl-ai session is not responding. This usually means the GEMINI_API_KEY is not properly configured or kubectl-ai process has issues. Please restart AI mode."
    
    def stop_persistent_session(self):
        """Stop the persistent kubectl-ai session."""
        self.running = False
        
        try:
            self.input_queue.put(None)
        except:
            pass
        
        time.sleep(0.5)
        
        try:
            if hasattr(self, 'master_fd'):
                os.close(self.master_fd)
        except:
            pass
        
        if self.process:
            try:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
            except:
                pass
        
        if self.kubeconfig_path and os.path.exists(self.kubeconfig_path):
            try:
                os.unlink(self.kubeconfig_path)
            except:
                pass


class InteractiveKubectlAI:
    def __init__(self, cluster, session_id):
        self.cluster = cluster
        self.session_id = session_id
        self.process = None
        self.input_queue = queue.Queue()
        self.output_queue = queue.Queue()
        self.running = False
        self.kubeconfig_path = None
    
    def _check_environment(self):
        """Check if the environment is properly set up for kubectl-ai."""
        issues = []
        
        # Check for API key
        if 'GEMINI_API_KEY' not in os.environ:
            issues.append("❌ GEMINI_API_KEY not found in Django environment")
            issues.append("💡 Fix: Stop Django, run 'export GEMINI_API_KEY=your-key', then restart Django")
        
        # Check if kubectl-ai is accessible
        kubectl_ai_path = self._find_kubectl_ai()
        if not kubectl_ai_path:
            issues.append("❌ kubectl-ai not found in PATH")
            issues.append("💡 Fix: Install kubectl-ai or add it to PATH")
        
        return issues
        
    def start_session(self):
        """Start the interactive kubectl-ai process."""
        try:
            # Check environment first
            env_issues = self._check_environment()
            if env_issues:
                print("🚨 Environment issues detected:")
                for issue in env_issues:
                    print(f"  {issue}")
                print()
                # Continue anyway, but warn user
            
            # Create temporary kubeconfig file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                f.write(self.cluster.kubeconfig)
                self.kubeconfig_path = f.name
            
            # Find kubectl-ai executable path
            kubectl_ai_path = self._find_kubectl_ai()
            if not kubectl_ai_path:
                print("kubectl-ai not found in PATH")
                return False
            
            print(f"Using kubectl-ai at: {kubectl_ai_path}")
            
            # Import os at the top since we need it for environment and PTY
            import os
            import pty
            
            # Set up full terminal environment - exactly like Mac/Linux terminal
            env = os.environ.copy()
            env['KUBECONFIG'] = self.kubeconfig_path
            
            # Ensure kubectl is available
            kubectl_paths = [
                '/usr/local/bin/kubectl',
                '/opt/homebrew/bin/kubectl', 
                '/usr/bin/kubectl'
            ]
            
            kubectl_found = False
            for kubectl_path in kubectl_paths:
                if os.path.exists(kubectl_path):
                    kubectl_found = True
                    break
            
            if not kubectl_found:
                # Try to find kubectl in PATH
                try:
                    result = subprocess.run(['which', 'kubectl'], capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        kubectl_found = True
                except:
                    pass
            
            if not kubectl_found:
                print("❌ WARNING: kubectl not found - kubectl-ai won't work properly")
            
            # Add comprehensive PATH for Mac/Linux compatibility
            additional_paths = [
                '/usr/local/bin',
                '/opt/homebrew/bin',
                '/usr/bin',
                '/bin',
                '/usr/sbin',
                '/sbin',
                os.path.expanduser('~/.local/bin'),
                os.path.expanduser('~/go/bin'),
                '/opt/homebrew/sbin'
            ]
            
            current_path = env.get('PATH', '')
            for path in additional_paths:
                if path not in current_path:
                    env['PATH'] = f"{path}:{env['PATH']}"
            
            # Set up terminal environment variables
            env['TERM'] = 'xterm-256color'  # Full color terminal
            env['COLUMNS'] = '120'
            env['LINES'] = '30'
            env['PS1'] = '$ '  # Simple prompt
            
            # Test kubectl access first
            print("🔍 Testing kubectl access...")
            try:
                kubectl_test = subprocess.run(['kubectl', 'cluster-info'], 
                                            env=env, capture_output=True, text=True, timeout=10)
                if kubectl_test.returncode == 0:
                    print("✅ kubectl cluster access working")
                else:
                    print(f"⚠️ kubectl test failed: {kubectl_test.stderr}")
            except Exception as e:
                print(f"⚠️ kubectl test error: {e}")
            
            # DOZEN GPU RESCUE: Try interactive shell approach
            cmd = f'bash -c "export TERM=xterm-256color; {kubectl_ai_path} --model gemini-2.5-flash-preview-04-17"'
            print(f"🚀 DOZEN GPU RESCUE: Running kubectl-ai command: {cmd}")
            print("🚀 DOZEN GPU RESCUE: Using bash wrapper for better compatibility")
            
            # Debug: Check current environment first
            print(f"🔍 DEBUGGING ENVIRONMENT:")
            print(f"  Django process has GEMINI_API_KEY: {'GEMINI_API_KEY' in os.environ}")
            if 'GEMINI_API_KEY' in os.environ:
                api_key = os.environ['GEMINI_API_KEY']
                print(f"  GEMINI_API_KEY value: {api_key[:10]}...{api_key[-4:]} (length: {len(api_key)})")
            else:
                print(f"  Available environment variables containing 'GEMINI' or 'API': {[k for k in os.environ.keys() if 'GEMINI' in k.upper() or 'API' in k.upper()]}")
            
            # Make sure GEMINI_API_KEY is in environment
            if 'GEMINI_API_KEY' not in env:
                # Check if it's in the current environment
                if 'GEMINI_API_KEY' in os.environ:
                    env['GEMINI_API_KEY'] = os.environ['GEMINI_API_KEY']
                    print(f"✅ Added GEMINI_API_KEY to environment (key starts with: {os.environ['GEMINI_API_KEY'][:10]}...)")
                else:
                    print("❌ CRITICAL: GEMINI_API_KEY not found in Django environment")
                    print("💡 SOLUTION: Restart Django server with API key:")
                    print("   export GEMINI_API_KEY='your-api-key'")
                    print("   python manage.py runserver")
                    print(f"Available env vars: {[k for k in os.environ.keys() if 'GEMINI' in k or 'API' in k]}")
                    # Don't fail here, but warn user
            else:
                print(f"✅ GEMINI_API_KEY already in environment (key starts with: {env['GEMINI_API_KEY'][:10]}...)")
            
            # Show all environment variables that will be passed to kubectl-ai
            print(f"Environment variables for kubectl-ai process:")
            for key in ['GEMINI_API_KEY', 'PATH', 'HOME']:
                if key in env:
                    if key == 'GEMINI_API_KEY':
                        print(f"  {key}: {env[key][:10]}... (length: {len(env[key])})")
                    else:
                        print(f"  {key}: {env[key][:100]}...")
                else:
                    print(f"  {key}: NOT SET")
            
            # Create full terminal environment like Mac/Linux
            print("🔧 Creating full interactive terminal for kubectl-ai")
            
            # Create a pseudo-terminal pair
            master_fd, slave_fd = pty.openpty()
            
            # Set terminal size (important for kubectl-ai)
            try:
                import termios
                import struct
                # Set terminal window size
                winsize = struct.pack('HHHH', 30, 120, 0, 0)  # rows, cols, xpixel, ypixel
                try:
                    import fcntl
                    fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)
                except:
                    pass
            except ImportError:
                # termios not available on all systems
                pass
            
            # Start kubectl-ai process with full terminal environment
            self.process = subprocess.Popen(
                cmd,
                shell=True,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,  # Send stderr to same PTY for full terminal experience
                env=env,
                cwd=os.path.expanduser('~'),
                preexec_fn=os.setsid  # Create new session
            )
            
            # Close slave fd in parent
            os.close(slave_fd)
            
            # Store master fd for communication
            self.master_fd = master_fd
            
            # Wait a moment to see if process starts successfully
            time.sleep(2)  # Give more time for Gemini API connection
            if self.process.poll() is not None:
                # Process has already terminated
                try:
                    # Read stderr for error details
                    stderr_output = self.process.stderr.read()
                    print(f"kubectl-ai process failed to start. Exit code: {self.process.returncode}")
                    if stderr_output:
                        print(f"stderr: {stderr_output.decode('utf-8', errors='ignore')}")
                    else:
                        print("No stderr output available")
                except Exception as e:
                    print(f"Error getting process output: {e}")
                return False
            
            print(f"kubectl-ai process started successfully. PID: {self.process.pid}")
            
            # Skip direct test since we're using PTY now
            print("🧪 SKIPPING direct test - using PTY for proper terminal emulation")
            
            # Quick check if kubectl-ai is working with our model
            try:
                # Check if process is responsive
                print("Checking if kubectl-ai process is responsive...")
                for i in range(5):  # Check for 5 seconds
                    time.sleep(1)
                    if self.process.poll() is not None:
                        print(f"Process died during startup. Exit code: {self.process.poll()}")
                        # Try to get any error output
                        try:
                            remaining_stdout = self.process.stdout.read()
                            if remaining_stdout:
                                print(f"Remaining stdout: {remaining_stdout}")
                        except:
                            pass
                        return False
                    print(f"Process still alive after {i+1} seconds")
                print("✅ kubectl-ai process appears to be running stable")
            except Exception as e:
                print(f"Error checking process responsiveness: {e}")
                return False
            
            # Don't send test message - kubectl-ai is interactive and will start naturally
            
            self.running = True
            
            # Start threads for terminal communication
            self.input_thread = threading.Thread(target=self._input_handler, daemon=True)
            self.output_thread = threading.Thread(target=self._output_handler, daemon=True)
            self.monitor_thread = threading.Thread(target=self._terminal_monitor, daemon=True)
            
            print("Starting terminal communication threads...")
            self.input_thread.start()
            self.output_thread.start()
            self.monitor_thread.start()
            
            # Give threads a moment to start
            time.sleep(0.5)
            
            print(f"Terminal threads started. Input: {self.input_thread.is_alive()}, Output: {self.output_thread.is_alive()}, Monitor: {self.monitor_thread.is_alive()}")
            
            # Wait for initial kubectl-ai greeting (like "Hey there, what can I help you with today?")
            print("Waiting for initial kubectl-ai greeting...")
            try:
                initial_greeting = self.output_queue.get(timeout=15)  # Longer wait for API connection
                print(f"Got initial greeting: {repr(initial_greeting[:100])}")
                # Put it back for the frontend to receive
                self.output_queue.put(initial_greeting)
                print("✅ kubectl-ai with Gemini is working!")
            except queue.Empty:
                print("❌ No initial greeting received - kubectl-ai may not be working with Gemini")
                print("This could mean:")
                print("1. Invalid GEMINI_API_KEY or not available to Django process")
                print("2. Model 'gemini-2.5-flash-preview-04-17' not working or API issues")
                print("3. Network/API connection issues") 
                print("4. Django server needs to be restarted with environment variables")
                print("5. Try manually: echo 'hello' | kubectl-ai --model gemini-2.5-flash-preview-04-17")
                print("💡 SOLUTION: Stop Django, export GEMINI_API_KEY='your-key', then restart Django")
                # Don't fail here, let the user try anyway
                pass
            
            print("kubectl-ai session started successfully")
            return True
            
        except Exception as e:
            print(f"Failed to start kubectl-ai session: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _find_kubectl_ai(self):
        """Find the kubectl-ai executable path."""
        # Try common locations where kubectl-ai might be installed
        possible_paths = [
            'kubectl-ai',  # In PATH
            '/usr/local/bin/kubectl-ai',
            '/opt/homebrew/bin/kubectl-ai',
            os.path.expanduser('~/.local/bin/kubectl-ai'),
            os.path.expanduser('~/go/bin/kubectl-ai'),
            '/usr/bin/kubectl-ai'
        ]
        
        for path in possible_paths:
            try:
                # Test if the command exists and is executable
                result = subprocess.run(['which', path], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    return result.stdout.strip()
                    
                # Also try direct path check
                if os.path.isfile(path) and os.access(path, os.X_OK):
                    return path
                    
            except Exception:
                continue
        
        # Last resort: use shell to find it
        try:
            result = subprocess.run('which kubectl-ai', shell=True, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
            
        return None
    
    def _input_handler(self):
        """DOZEN GPU RESCUE MODE: Force kubectl-ai to respond! 🚀💪"""
        import os
        import fcntl
        import time
        
        while self.running and self.process and self.process.poll() is None:
            try:
                message = self.input_queue.get(timeout=1)
                if message is None:  # Shutdown signal
                    break
                
                # Check if process is still alive
                if self.process.poll() is not None:
                    break
                
                print(f"🚀 DOZEN GPU RESCUE: Sending message: {repr(message)}")
                
                # DOZEN GPU RESCUE: Send message with multiple strategies
                try:
                    # Strategy 1: Clear terminal and send clean command
                    clear_and_send = f"\x03\x15{message.strip()}\r"  # Ctrl+C, Ctrl+U, message, Enter
                    os.write(self.master_fd, clear_and_send.encode('utf-8'))
                    time.sleep(0.5)
                    
                    print(f"🚀 DOZEN GPU RESCUE: Sent with clear strategy")
                    
                except OSError as e:
                    print(f"🚀 DOZEN GPU RESCUE: OSError in input: {e}")
                    if self.process.poll() is not None:
                        break
                    continue
                
            except queue.Empty:
                if self.process.poll() is not None:
                    break
                continue
            except Exception as e:
                print(f"🚀 DOZEN GPU RESCUE: Input handler error: {e}")
                break
    
    def _terminal_monitor(self):
        """Monitor terminal health and kubectl-ai process."""
        while self.running and self.process and self.process.poll() is None:
            try:
                # Check process health every 5 seconds
                time.sleep(5)
                
                # If process died, stop the session
                if self.process.poll() is not None:
                    print(f"kubectl-ai process ended: {self.process.poll()}")
                    self.running = False
                    break
                    
            except Exception:
                break
    
    def _output_handler(self):
        """Handle receiving responses from kubectl-ai process via PTY - full terminal mode."""
        import select
        import os
        import re
        import fcntl
        
        # Set non-blocking mode
        try:
            fcntl.fcntl(self.master_fd, fcntl.F_SETFL, os.O_NONBLOCK)
        except:
            pass
        
        response_buffer = ""
        last_activity = time.time()
        
        while self.running and self.process and self.process.poll() is None:
            try:
                # Use select with shorter timeout for more responsive terminal
                ready, _, _ = select.select([self.master_fd], [], [], 0.5)
                
                if ready:
                    try:
                        # Read available data
                        data = os.read(self.master_fd, 4096).decode('utf-8', errors='ignore')
                        if data:
                            response_buffer += data
                            last_activity = time.time()
                            
                            # Check if response is complete (DOZEN GPU MODE - more aggressive!)
                            if self._is_response_complete(response_buffer):
                                cleaned = self._clean_response(response_buffer)
                                print(f"🚀 DOZEN GPU MODE: Complete response detected!")
                                print(f"🚀 DOZEN GPU MODE: Raw: {repr(response_buffer[:200])}")
                                print(f"🚀 DOZEN GPU MODE: Cleaned: {repr(cleaned[:200])}")
                                if cleaned.strip():
                                    print(f"🚀 DOZEN GPU MODE: Sending complete response!")
                                    self.output_queue.put(cleaned)
                                    response_buffer = ""
                                else:
                                    print(f"🚀 DOZEN GPU MODE: Complete but cleaned empty! Sending raw...")
                                    if response_buffer.strip():
                                        self.output_queue.put(response_buffer.strip())
                                        response_buffer = ""
                    
                    except OSError as e:
                        if e.errno in [5, 11]:  # I/O error or would block
                            break
                        continue
                
                # DOZEN GPU RESCUE: Much more aggressive timeout - 1 second!
                elif response_buffer.strip() and (time.time() - last_activity) > 1.0:
                    cleaned = self._clean_response(response_buffer)
                    print(f"🚀 DOZEN GPU RESCUE: 1s timeout - Raw buffer: {repr(response_buffer[:200])}")
                    print(f"🚀 DOZEN GPU RESCUE: Cleaned result: {repr(cleaned[:200])}")
                    
                    # DOZEN GPU RESCUE: Send ANYTHING we have!
                    if cleaned.strip():
                        print(f"🚀 DOZEN GPU RESCUE: Sending cleaned response!")
                        self.output_queue.put(cleaned)
                        response_buffer = ""
                    elif len(response_buffer.strip()) > 5:  # Very low threshold
                        print(f"🚀 DOZEN GPU RESCUE: Sending raw response (desperate mode)!")
                        raw_cleaned = response_buffer.replace('\x1b[J', '').replace('\x1b[2K', '').replace('\r', '').replace('\x08', '').strip()
                        if raw_cleaned:
                            self.output_queue.put(f"Raw response: {raw_cleaned}")
                        else:
                            self.output_queue.put("kubectl-ai seems to be responding but output is unclear. Try a different question.")
                        response_buffer = ""
                    else:
                        print(f"🚀 DOZEN GPU RESCUE: Buffer too small ({len(response_buffer)} chars), waiting more...")
                
            except Exception:
                break
    
    def _is_response_complete(self, buffer):
        """DOZEN GPU MODE: Super aggressive response completion detection! 🚀"""
        import re
        
        # Basic cleanup
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        clean_buffer = ansi_escape.sub('', buffer)
        control_sequences = re.compile(r'\d+;[\d?]*;?\??')
        clean_buffer = control_sequences.sub('', clean_buffer)
        
        # DOZEN GPU MODE: Much lower threshold!
        if len(clean_buffer.strip()) < 8:
            return False
        
        # Get cleaned content
        cleaned_content = self._clean_response(buffer)
        
        # DOZEN GPU MODE: Even accept empty cleaned content if raw buffer has substance
        if not cleaned_content.strip() and len(clean_buffer.strip()) < 30:
            return False
        
        # Super aggressive completion patterns
        completion_patterns = [
            r"How can I help you\??",
            r"What would you like to know\??", 
            r"What can I help you with\??",
            r"Is there anything else\??",
            r"Feel free to ask",
            r"Let me know if you need",
            r"Any other questions\??",
            r"Would you like me to",
            r"Do you need help with",
            r"Hope this helps",
            r"Let me help you",
            r"anything else I can help",
            r"need any help with",
            r"help you with today",  # From greeting
            r"pods? in",             # Pod-related responses
            r"currently running",    # Status responses
            r"namespace",            # K8s responses
            r"deployment",           # K8s responses
        ]
        
        # Check for any completion indicator
        for pattern in completion_patterns:
            if re.search(pattern, clean_buffer, re.IGNORECASE):
                print(f"🚀 DOZEN GPU MODE: Found completion pattern: {pattern}")
                return True
        
        # kubectl command output patterns (be very liberal)
        kubectl_patterns = [
            r"NAME\s+.*STATUS", r"No resources found", r"\d+ pods?",
            r"(created|configured|deleted|scaled)", r"Error from server",
            r"error:", r"failed to", r"Kubernetes control plane",
            r"cluster-info", r"running", r"pending", r"succeeded",
            r"deployment", r"service", r"namespace", r"node"
        ]
        
        for pattern in kubectl_patterns:
            if re.search(pattern, clean_buffer, re.IGNORECASE):
                print(f"🚀 DOZEN GPU MODE: Found kubectl pattern: {pattern}")
                return True
        
        # DOZEN GPU MODE: Very liberal completion detection
        lines = [line.strip() for line in clean_buffer.split('\n') if line.strip()]
        if len(lines) >= 1:  # Even single line responses!
            last_line = lines[-1]
            # Accept most punctuation endings
            if (len(last_line) > 5 and 
                (last_line.endswith(('?', '.', '!', ':', ';', ')')) or
                 any(word in last_line.lower() for word in ['pod', 'node', 'service', 'help', 'cluster', 'running']))):
                print(f"🚀 DOZEN GPU MODE: Found natural ending: {last_line}")
                return True
        
        # DOZEN GPU MODE: Accept anything substantial after short wait
        if len(cleaned_content.strip()) > 20 or len(clean_buffer.strip()) > 40:
            print(f"🚀 DOZEN GPU MODE: Substantial content detected, considering complete")
            time.sleep(0.1)  # Very short wait
            return True
        
        return False

    def _fallback_kubectl_response(self, user_message):
        """🚀 FULL TERMINAL FALLBACK: When kubectl-ai fails, use intelligent kubectl interpretation!"""
        # Use the same intelligent interpreter as the main terminal
        from chat.views import intelligent_kubectl_interpreter
        
        # Create a minimal cluster object with kubeconfig
        class MinimalCluster:
            def __init__(self, kubeconfig):
                self.kubeconfig = kubeconfig
        
        cluster = MinimalCluster(self.cluster.kubeconfig)
        result = intelligent_kubectl_interpreter(cluster, user_message)
        
        # Add fallback notice to the output
        if not result['output'].startswith('🚀'):
            result['output'] = f"🚀 FULL TERMINAL FALLBACK: kubectl-ai didn't respond, using direct kubectl:\n\n{result['output']}"
        
        return result['output']
    
    def _clean_response(self, response):
        """Aggressively clean kubectl-ai response - DOZEN GPU MODE! 🚀"""
        import re
        
        # STEP 1: Remove ALL terminal escape sequences and control codes
        # Remove standard ANSI escape sequences
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        cleaned = ansi_escape.sub('', response)
        
        # Remove terminal control sequences like '11;?11;?', '11;711;?'
        control_sequences = re.compile(r'\d+;[\d?]*;?\??')
        cleaned = control_sequences.sub('', cleaned)
        
        # Remove control characters but preserve newlines and spaces
        control_chars = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]+')
        cleaned = control_chars.sub('', cleaned)
        
        # STEP 2: Extract meaningful content
        lines = cleaned.split('\n')
        good_lines = []
        
        for line in lines:
            line = line.strip()
            
            # Skip completely empty lines
            if not line:
                continue
            
            # AGGRESSIVE FILTERING - Skip obvious junk
            skip_patterns = [
                r'^>>>',              # Shell prompts
                r'^user@',            # User prompts  
                r'^kubectl-ai:',      # App prompts
                r'^\$',               # Shell prompts
                r'^#',                # Comments
                r'^how many pods\??$', # Echo of user input
                r'^\w{1,4}$',         # Very short strings (typing artifacts)
                r'^\d+;\d+',          # Remaining control sequences
                r'^J>>>',             # Terminal artifacts
                r'^Loading',          # Loading messages
                r'^Waiting',          # Wait messages
                r'^Starting',         # Startup messages
                r'^Checking',         # Check messages
            ]
            
            # Check if line should be skipped
            should_skip = False
            for pattern in skip_patterns:
                if re.match(pattern, line, re.IGNORECASE):
                    should_skip = True
                    break
            
            if should_skip:
                continue
            
            # KEEP ANYTHING SUBSTANTIAL - be more liberal
            if len(line) > 8:  # Lowered threshold
                good_lines.append(line)
            elif any(keyword in line.lower() for keyword in ['pod', 'node', 'service', 'deployment', 'namespace', 'cluster', 'running', 'pending', 'error', 'help']):
                # Keep kubectl/k8s related content even if short
                good_lines.append(line)
        
        # STEP 3: If we have ANY good content, return it
        if good_lines:
            result = '\n'.join(good_lines)
            # Clean up spacing
            result = re.sub(r' +', ' ', result)
            result = re.sub(r'\n\s*\n\s*\n+', '\n\n', result)
            return result.strip()
        
        # STEP 4: Last resort - return raw cleaned content if it looks meaningful
        if len(cleaned.strip()) > 10:
            # Just remove extra whitespace
            raw_result = re.sub(r' +', ' ', cleaned)
            raw_result = re.sub(r'\n\s*\n\s*\n+', '\n\n', raw_result)
            return raw_result.strip()
        
        return ""
    
    def send_message(self, message):
        """DOZEN GPU RESCUE: Send message and get response by any means necessary! 💪"""
        import time
        original_message = message  # Store for fallback
        
        if not self.running:
            return "Session not running"
            
        if not self.process:
            print(f"🚀 DOZEN GPU RESCUE: No process, using direct kubectl!")
            return self._fallback_kubectl_response(original_message)
            
        if self.process.poll() is not None:
            print(f"🚀 DOZEN GPU RESCUE: Process ended (code: {self.process.poll()}), using direct kubectl!")
            return self._fallback_kubectl_response(original_message)
            
        # Clear any old responses
        while not self.output_queue.empty():
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                break
        
        print(f"🚀 DOZEN GPU RESCUE: Sending message to kubectl-ai: {repr(message)}")
        
        # Send the message
        self.input_queue.put(message)
        
        # DOZEN GPU RESCUE: Check if process dies immediately after sending
        time.sleep(1)  # Give it a moment
        if self.process.poll() is not None:
            print(f"🚀 DOZEN GPU RESCUE: kubectl-ai died immediately after message! Using direct kubectl!")
            return self._fallback_kubectl_response(original_message)
        
        try:
            # Wait for a complete response - DOZEN GPU RESCUE timeout!
            response = self.output_queue.get(timeout=10)  # Even shorter timeout!
            
            if response and response.strip():
                print(f"🚀 DOZEN GPU RESCUE: Got response from kubectl-ai!")
                return response
            else:
                print(f"🚀 DOZEN GPU RESCUE: Empty response from kubectl-ai, trying fallback")
                return self._fallback_kubectl_response(original_message)
                
        except queue.Empty:
            print(f"🚀 DOZEN GPU RESCUE: Timeout waiting for kubectl-ai, checking partial responses...")
            
            # Check if there's any partial content in the queue
            partial_responses = []
            while not self.output_queue.empty():
                try:
                    partial = self.output_queue.get_nowait()
                    partial_responses.append(partial)
                except queue.Empty:
                    break
            
            if partial_responses:
                combined = '\n'.join(partial_responses)
                cleaned = self._clean_response(combined)
                if cleaned.strip():
                    print(f"🚀 DOZEN GPU RESCUE: Found partial response, using it!")
                    return cleaned
                    
            # DOZEN GPU RESCUE: If kubectl-ai doesn't respond, try direct kubectl!
            print(f"🚀 DOZEN GPU RESCUE: kubectl-ai completely failed, activating direct kubectl for: {repr(original_message)}")
            return self._fallback_kubectl_response(original_message)
            # Check if process is still alive
            if self.process.poll() is not None:
                return f"kubectl-ai process has ended (exit code: {self.process.poll()}). Try restarting AI mode."
            else:
                return "No response received from kubectl-ai. This usually means:\n1. GEMINI_API_KEY is not available to Django process\n2. Try: Press Esc, restart Django with 'export GEMINI_API_KEY=your-key', then press / again"
    
    def stop_session(self):
        """Stop the interactive AI session and clean up terminal resources."""
        self.running = False
        
        # Send shutdown signal to input handler
        try:
            self.input_queue.put(None)
        except:
            pass
        
        # Give threads a moment to stop
        time.sleep(0.5)
        
        # Close PTY master file descriptor
        try:
            if hasattr(self, 'master_fd'):
                os.close(self.master_fd)
        except:
            pass
        
        # Terminate the process gracefully
        if self.process:
            try:
                # Send SIGTERM first
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    # If it doesn't exit, force kill
                    self.process.kill()
                    self.process.wait(timeout=2)
            except:
                pass
        
        # Clean up temporary kubeconfig file
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
    """🚀 PERSISTENT KUBECTL-AI SESSION: Start exactly like terminal kubectl-ai!"""
    try:
        chat_session = get_object_or_404(ChatSession, session_id=session_id)
        
        # Check if session already exists and is healthy
        if session_id in active_ai_sessions:
            ai_session = active_ai_sessions[session_id]
            if ai_session.running and ai_session.process and ai_session.process.poll() is None:
                # Get any pending welcome message
                try:
                    initial_response = ai_session.output_queue.get(timeout=1)
                    return JsonResponse({
                        'success': True,
                        'message': 'Interactive kubectl-ai session already active',
                        'initial_response': initial_response
                    })
                except queue.Empty:
                    return JsonResponse({
                        'success': True,
                        'message': 'Interactive kubectl-ai session already active'
                    })
            else:
                # Clean up dead session
                del active_ai_sessions[session_id]
        
        print(f"🚀 PERSISTENT SESSION: Starting kubectl-ai for session {session_id}")
        
        # Create and start new persistent interactive session
        ai_session = PersistentKubectlAI(chat_session.cluster, session_id)
        
        if ai_session.start_persistent_session():
            active_ai_sessions[session_id] = ai_session
            
            # Wait for initial kubectl-ai greeting (like in terminal)
            try:
                initial_response = ai_session.output_queue.get(timeout=10)
                print(f"🚀 PERSISTENT SESSION: Got initial response: {repr(initial_response[:100])}")
                
                return JsonResponse({
                    'success': True,
                    'message': 'Persistent kubectl-ai session started!',
                    'initial_response': initial_response
                })
            except queue.Empty:
                print(f"🚀 PERSISTENT SESSION: No initial response, but session started")
                return JsonResponse({
                    'success': True,
                    'message': 'Persistent kubectl-ai session started!',
                    'initial_response': 'kubectl-ai session is ready. How can I help you with your Kubernetes cluster?'
                })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Failed to start persistent kubectl-ai session. Check that kubectl-ai is installed and GEMINI_API_KEY is set.'
            })
            
    except ChatSession.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Chat session not found'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error starting persistent session: {str(e)}'
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
    """🚀 PURE kubectl-ai SESSION: Exactly like running kubectl-ai in terminal!"""
    try:
        chat_session = get_object_or_404(ChatSession, session_id=session_id)
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()
        
        if not user_message:
            return JsonResponse({
                'success': False,
                'error': 'Message is required'
            })
        
        print(f"🚀 KUBECTL-AI SESSION: Processing: {repr(user_message)}")
        
        # Check if persistent kubectl-ai session exists
        if session_id not in active_ai_sessions:
            print(f"🚨 NO SESSION: kubectl-ai session not found for {session_id}")
            return JsonResponse({
                'success': False,
                'error': 'kubectl-ai session not active. Please restart AI mode (press Esc, then /).'
            })
        
        ai_session = active_ai_sessions[session_id]
        
        # Ensure it's a persistent session
        if not hasattr(ai_session, 'send_persistent_message'):
            print(f"🚨 WRONG SESSION TYPE: Found {type(ai_session).__name__}, need PersistentKubectlAI")
            return JsonResponse({
                'success': False,
                'error': 'Wrong session type. Please restart AI mode for persistent kubectl-ai session.'
            })
        
        # Check if session is alive
        if not (ai_session.running and ai_session.process and ai_session.process.poll() is None):
            print(f"🚨 DEAD SESSION: kubectl-ai process is not running")
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
        
        # Send message to persistent kubectl-ai (exactly like terminal)
        print(f"🚀 SENDING TO kubectl-ai: {repr(user_message)}")
        try:
            response = ai_session.send_persistent_message(user_message)
            print(f"🚀 kubectl-ai RESPONSE: {repr(response[:200] if response else 'None')}")
            
            if not response or response.startswith("Session not running") or response.startswith("No response received"):
                raise Exception("kubectl-ai failed to respond")
            
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
            print(f"🚨 kubectl-ai ERROR: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': f'kubectl-ai communication error: {str(e)}. Try restarting AI mode.'
            })
            
    except ChatSession.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Chat session not found'
        })
    except Exception as e:
        print(f"🚨 UNEXPECTED ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
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