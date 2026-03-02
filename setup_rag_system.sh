#!/bin/bash
# setup_rag_system.sh - Complete RAG System Setup Script

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1${NC}"
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
    error "This script should not be run as root (except for package installation steps)"
    exit 1
fi

echo "================================================================"
echo " RAG System Complete Setup Script"
echo "================================================================"
echo ""

# Step 1: System Requirements Check
log "Step 1: Checking system requirements..."

# Check OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
    info "Detected macOS"
elif [[ -f /etc/os-release ]]; then
    . /etc/os-release
    OS=$ID
    info "Detected Linux: $OS"
else
    error "Unsupported operating system"
    exit 1
fi

# Check available memory
MEMORY_GB=$(free -g 2>/dev/null | grep '^Mem:' | awk '{print $2}' || sysctl -n hw.memsize 2>/dev/null | awk '{print int($1/1024/1024/1024)}' || echo "unknown")
if [[ "$MEMORY_GB" != "unknown" && "$MEMORY_GB" -lt 8 ]]; then
    warn "System has ${MEMORY_GB}GB RAM. Recommended: 16GB+ for optimal performance"
else
    info "Memory check passed: ${MEMORY_GB}GB RAM"
fi

# Check available disk space
DISK_GB=$(df -BG . | tail -1 | awk '{print $4}' | sed 's/G//' || echo "unknown")
if [[ "$DISK_GB" != "unknown" && "$DISK_GB" -lt 50 ]]; then
    warn "Available disk space: ${DISK_GB}GB. Recommended: 50GB+ free space"
else
    info "Disk space check passed: ${DISK_GB}GB available"
fi

# Step 2: Install Dependencies
log "Step 2: Installing system dependencies..."

# Install Git if not present
if ! command -v git &> /dev/null; then
    info "Installing Git..."
    case $OS in
        "macos")
            if command -v brew &> /dev/null; then
                brew install git
            else
                error "Git not found. Please install Git first or install Homebrew"
                exit 1
            fi
            ;;
        "ubuntu"|"debian")
            sudo apt-get update
            sudo apt-get install -y git
            ;;
        "centos"|"rhel"|"fedora")
            if command -v dnf &> /dev/null; then
                sudo dnf install -y git
            else
                sudo yum install -y git
            fi
            ;;
    esac
else
    info "Git is already installed: $(git --version)"
fi

# Install curl if not present
if ! command -v curl &> /dev/null; then
    info "Installing curl..."
    case $OS in
        "macos")
            # curl is usually pre-installed on macOS
            ;;
        "ubuntu"|"debian")
            sudo apt-get install -y curl
            ;;
        "centos"|"rhel"|"fedora")
            if command -v dnf &> /dev/null; then
                sudo dnf install -y curl
            else
                sudo yum install -y curl
            fi
            ;;
    esac
else
    info "curl is already installed"
fi

log "Step 3: Installing Python, Node.js, and Ollama..."

# Install Python if not present
if ! command -v python3 &> /dev/null; then
    info "Installing Python..."
    case $OS in
        "macos")
            if command -v brew &> /dev/null; then
                brew install python@3.11
            else
                error "Python not found. Please install Python or Homebrew manually."
                exit 1
            fi
            ;;
        "ubuntu"|"debian")
            sudo apt-get update
            sudo apt-get install -y python3 python3-pip
            ;;
        "centos"|"rhel"|"fedora")
            if command -v dnf &> /dev/null; then
                sudo dnf install -y python3 python3-pip
            else
                sudo yum install -y python3 python3-pip
            fi
            ;;
    esac
else
    info "Python is already installed: $(python3 --version)"
fi

# Install Node.js if not present
if ! command -v node &> /dev/null; then
    info "Installing Node.js..."
    case $OS in
        "macos")
            if command -v brew &> /dev/null; then
                brew install node
            else
                error "Node.js not found. Please install Node.js or Homebrew manually."
                exit 1
            fi
            ;;
        "ubuntu"|"debian")
            sudo apt-get install -y nodejs npm
            ;;
        "centos"|"rhel"|"fedora")
            if command -v dnf &> /dev/null; then
                sudo dnf install -y nodejs npm
            else
                sudo yum install -y nodejs npm
            fi
            ;;
    esac
else
    info "Node.js is already installed: $(node --version)"
fi

# Install Ollama if not present
if ! command -v ollama &> /dev/null; then
    info "Installing Ollama..."
    curl -fsSL https://ollama.ai/install.sh | bash
else
    info "Ollama is already installed: $(ollama --version)"
fi

# Step 4: Setup RAG System
log "Step 4: Setting up RAG System..."

# Create project directory structure
info "Creating directory structure..."
mkdir -p {lancedb,shared_uploads,logs,ollama_data}
mkdir -p index_store/{overviews,bm25,graph}
mkdir -p backups

# Set proper permissions
chmod 755 {lancedb,shared_uploads,logs,ollama_data}
chmod 755 index_store/{overviews,bm25,graph}
chmod 755 backups

# Create environment file
if [[ ! -f ".env" ]]; then
    info "Creating environment configuration..."
    cat > .env << 'EOF'
# System Configuration
NODE_ENV=production
LOG_LEVEL=info
DEBUG=false

# Service URLs
FRONTEND_URL=http://localhost:3000
BACKEND_URL=http://localhost:8000
RAG_API_URL=http://localhost:8001
OLLAMA_URL=http://localhost:11434

# Database Configuration
DATABASE_PATH=./backend/chat_data.db
LANCEDB_PATH=./lancedb
UPLOADS_PATH=./shared_uploads
INDEX_STORE_PATH=./index_store

# Model Configuration
DEFAULT_EMBEDDING_MODEL=sentence-transformers/all-mpnet-base-v2
# Default model names - updated to current versions
DEFAULT_GENERATION_MODEL=gemma3:12b-cloud
DEFAULT_RERANKER_MODEL=answerdotai/answerai-colbert-small-v1
DEFAULT_ENRICHMENT_MODEL=gemma3:4b-cloud

# Performance Configuration
MAX_CONCURRENT_REQUESTS=5
REQUEST_TIMEOUT=300
EMBEDDING_BATCH_SIZE=32
MAX_CONTEXT_LENGTH=4096

# Security Configuration
CORS_ORIGINS=http://localhost:3000
API_KEY_REQUIRED=false
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=60

# Storage Configuration
MAX_FILE_SIZE=50MB
MAX_UPLOAD_FILES=10
CLEANUP_INTERVAL=3600
BACKUP_RETENTION_DAYS=30
EOF
    info "Environment file created: .env"
else
    info "Environment file already exists: .env"
fi

# Step 5: Install Python and Node.js dependencies
log "Step 5: Installing Python and Node.js dependencies..."

info "Installing Python dependencies..."
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

info "Installing Node.js dependencies..."
npm install
npm run build

# Step 6: Start Services
log "Step 6: Starting services..."

info "Starting backend API server..."
nohup python3 -m rag_system.api_server > logs/backend_api.log 2>&1 &

info "Starting backend server..."
nohup python3 backend/server.py > logs/backend_server.log 2>&1 &

info "Starting frontend..."
nohup npm start > logs/frontend.log 2>&1 &

# Step 7: Install AI Models
log "Step 7: Installing AI models..."

info "Pulling required Ollama models..."
ollama pull gemma3:12b-cloud
ollama pull gemma3:4b-cloud

info "Verifying model installation..."
ollama list

# Step 8: System Verification
log "Step 8: Verifying system installation..."

info "Checking service health..."
services=("frontend:3000" "backend:8000" "rag-api:8001" "ollama:11434")
for service in "${services[@]}"; do
    name="${service%:*}"
    port="${service#*:}"
    if curl -s -f "http://localhost:$port" &> /dev/null || curl -s -f "http://localhost:$port/health" &> /dev/null || curl -s -f "http://localhost:$port/api/tags" &> /dev/null || curl -s -f "http://localhost:$port/models" &> /dev/null; then
        info " $name service is healthy"
    else
        warn " $name service may not be ready yet"
    fi
done

echo ""
echo "================================================================"
echo " RAG System Setup Complete!"
echo "================================================================"
echo ""
echo " System Status:"
echo "   - Frontend: http://localhost:3000"
echo "   - Backend API: http://localhost:8000"
echo "   - RAG API: http://localhost:8001"
echo "   - Ollama: http://localhost:11434"
echo ""
echo " Documentation:"
echo "   - System Overview: Documentation/system_overview.md"
echo "   - Deployment Guide: Documentation/deployment_guide.md"
echo "   - Installation Guide: Documentation/installation_guide.md"
echo ""
echo " Next Steps:"
echo "   1. Open http://localhost:3000 in your browser"
echo "   2. Create a new chat session"
echo "   3. Upload some PDF documents"
echo "   4. Start asking questions about your documents!"
echo ""
echo " System Information:"
echo "   - OS: $OS"
echo "   - Memory: ${MEMORY_GB}GB"
echo "   - Disk Space: ${DISK_GB}GB available"
echo ""
echo "For support and troubleshooting, check the documentation in the"
echo "Documentation/ folder."
echo ""