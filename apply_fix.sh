#!/bin/bash

echo "🔧 Applying fixes to K8S-AI Terminal..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found. Creating one..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🐍 Activating virtual environment..."
source venv/bin/activate

# Install requirements
echo "📦 Installing requirements..."
pip install -r requirements.txt

# Stop any existing containers
echo "🐳 Cleaning up existing containers..."
docker ps -q --filter "name=k8s-terminal-" | xargs -r docker stop
docker ps -aq --filter "name=k8s-terminal-" | xargs -r docker rm

# Apply migrations if needed
echo "🗄️ Applying database migrations..."
python manage.py makemigrations
python manage.py migrate

echo "✅ Setup complete!"
echo ""
echo "🚀 To start the server, run:"
echo "   source venv/bin/activate"
echo "   python manage.py runserver"
echo ""
echo "🔍 To test the fix:"
echo "   1. Start the server"
echo "   2. Create a new cluster or use existing one"
echo "   3. Try: kubectl-ai \"how many pods\""
echo "   4. The command should now work with fallback logic"
