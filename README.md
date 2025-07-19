# K8S-AI Cloud Terminal

A modern web-based terminal interface for Kubernetes cluster management with full shell access.

## Setup

1. Create and activate a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run Django migrations:
```bash
python manage.py migrate
```

4. Start the development server:
```bash
python manage.py runserver 0.0.0.0:8000
```

5. Open your browser and navigate to `http://localhost:8000`

## Features

- **Full Terminal Access**: Execute any shell command, not just kubectl
- **Kubernetes Integration**: Automatic kubeconfig management for kubectl commands
- **Multiple Clusters**: Connect and manage multiple Kubernetes clusters
- **Command History**: Persistent command history for each cluster session
- **Interactive Command Handling**: Smart detection and guidance for unsupported interactive commands
- **Modern UI**: Dark theme with terminal-like styling
- **Real-time Execution**: Live command output with exit codes
- **Security Features**: Interactive command blocking, timeout protection
- **Mobile-friendly**: Responsive design that works on all devices

## Project Structure

```
K8S-AI/
├── k8s_ai/              # Django project settings
├── chat/                # Chat app
├── templates/           # HTML templates
├── static/              # CSS, JS, and other static files
├── manage.py            # Django management script
└── requirements.txt     # Python dependencies
```

## Example Commands

### Kubernetes Commands
```bash
kubectl get pods
kubectl get nodes
kubectl describe pod <pod-name>
kubectl logs <pod-name>
kubectl apply -f deployment.yaml
```

### General Shell Commands
```bash
ls -la
pwd
whoami
ps aux
df -h
curl -I https://google.com
wget https://example.com/file.txt
cat /etc/os-release
```

### File Operations
```bash
echo "Hello World" > test.txt
cat test.txt
mkdir my-directory
cd my-directory
find . -name "*.yaml"
```

## Security Considerations

⚠️ **Important Security Notes:**
- This terminal provides full shell access to the server
- Only use with trusted clusters and in secure environments
- Interactive commands (vim, ssh, etc.) are blocked for security
- Commands have a 60-second timeout limit
- Only connect kubeconfig files from trusted sources

## Limitations

- Interactive commands (vim, nano, ssh, etc.) are not supported
- No persistent sessions - each command runs independently
- File editing must be done with non-interactive tools
- Some commands may behave differently in web environment

## How to Use

1. **Add a Cluster:**
   - Click the "+" button in the sidebar
   - Enter cluster name and paste your kubeconfig
   - System validates connection and creates terminal session

2. **Execute Commands:**
   - Select a cluster from sidebar
   - Type any shell command (e.g., `ls -la`, `kubectl get pods`)
   - View real-time output with exit codes

3. **Manage Sessions:**
   - Multiple clusters supported
   - Switch between clusters instantly
   - Command history preserved per session

## Built With

- **Backend**: Django 4.2.7 with Kubernetes Python client
- **Frontend**: Vanilla JavaScript with modern UI
- **Security**: Command validation, timeout protection, kubeconfig isolation
- **Storage**: SQLite database with proper indexing
