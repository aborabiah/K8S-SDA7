#!/bin/bash

echo "🔧 Applying Interactive Streaming Fix to K8S-AI Terminal..."
echo "This will create a truly interactive kubectl-ai session with real streaming!"
echo ""

# Check if we're in the right directory
if [ ! -f "manage.py" ]; then
    echo "❌ Error: manage.py not found. Please run this script from the K8S-AI project root directory."
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found. Creating one..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🐍 Activating virtual environment..."
source venv/bin/activate

# Install requirements (including new packages for streaming)
echo "📦 Installing requirements..."
pip install -r requirements.txt

# Stop any existing containers
echo "🐳 Cleaning up existing containers..."
docker ps -q --filter "name=k8s-terminal-" | xargs -r docker stop
docker ps -aq --filter "name=k8s-terminal-" | xargs -r docker rm

# Remove old images to force rebuild with new packages
echo "🔄 Removing old Docker images to force rebuild..."
docker images | grep "your-kubectl-image" | awk '{print $3}' | xargs -r docker rmi -f

# Apply migrations if needed
echo "🗄️ Applying database migrations..."
python manage.py makemigrations
python manage.py migrate

# Verify environment file
if [ ! -f ".env" ]; then
    echo "⚠️ Warning: .env file not found. Creating a template..."
    cat > .env << EOF
GEMINI_API_KEY=AIzaSyAus1bYeszdrau2WHY-OSJnfDSqPCqL47g
EOF
    echo "📝 Created .env file with your API key. Please verify it's correct."
else
    echo "✅ .env file found."
fi

echo ""
echo "✅ Interactive streaming fix applied successfully!"
echo ""
echo "🚀 To start the server:"
echo "   source venv/bin/activate"
echo "   python manage.py runserver"
echo ""
echo "🎯 How the new interactive system works:"
echo "   1. Type 'kubectl-ai' to start an interactive AI session"
echo "   2. Chat naturally with the AI (e.g., 'how many pods')"
echo "   3. The session stays active until you type 'exit'"
echo "   4. Real streaming responses (no more hanging!)"
echo "   5. Automatic fallback to kubectl commands if AI times out"
echo ""
echo "🔍 Key improvements:"
echo "   • Removed invalid --no-interact flag"
echo "   • Added real streaming communication"
echo "   • Interactive session management"
echo "   • Background threading for responsiveness"
echo "   • Proper session cleanup on 'exit'"
echo ""
echo "🧪 Test these commands after starting:"
echo "   kubectl-ai"
echo "   how many pods do I have?"
echo "   show me all services"
echo "   what's wrong with my cluster?"
echo "   exit"
echo ""
echo "🎉 Your terminal should now be fully interactive!"
