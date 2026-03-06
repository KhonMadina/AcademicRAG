#  Quick Start Guide - RAG System

_Get up and running in 5 minutes!_

---

##  Choose Your Deployment Method


### Direct Development (Developer Friendly) 

Best for: Development, customization, debugging, faster iteration

---



---

##  Direct Development

### Prerequisites
- Python 3.8+
- Node.js 16+ and npm
- 8GB+ RAM available

### Step 1: Clone and Install Dependencies

```bash
# Clone repository
git clone <your-repository-url>
cd AcademicRAG

# Install Python dependencies
pip install -r requirements.txt

# Install Node.js dependencies  
npm install

# Create local environment config
cp .env.example .env
```

### Step 2: Install and Configure Ollama

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama (in one terminal)
ollama serve

# Install models (in another terminal)
ollama pull gemma3:4b-cloud
ollama pull gemma3:12b-cloud
```

### Step 3: Start the System (Primary Path)

```bash
# Start all components with one command
python run_system.py
```

**Manual startup (advanced troubleshooting):**

```bash
# Terminal 1: Ollama
ollama serve

# Terminal 1: RAG API
python -m rag_system.api_server

# Terminal 2: Backend
cd backend && python server.py

# Terminal 3: Frontend
npm run dev
```

### Step 4: Verify Installation

```bash
# Check system health
python system_health_check.py

# Test endpoints
curl http://localhost:3000      # Frontend
curl http://localhost:8000/health  # Backend
curl http://localhost:8001/health  # RAG API
curl http://localhost:8000/metrics # Backend metrics
curl http://localhost:8001/metrics # RAG metrics
```

### Step 5: Access Application

Open your browser to: **http://localhost:3000**

---

##  First Use Guide

### 1. Create a Chat Session
- Click "New Chat" in the interface
- Give your session a descriptive name

### 2. Upload Documents
- Click "Create New Index" button
- Upload PDF files from your computer
- Configure processing options:
  - **Chunk Size**: 512 (recommended)
  - **Embedding Model**: Qwen/Qwen3-Embedding-0.6B
  - **Enable Enrichment**: Yes
- Click "Build Index" and wait for processing

### 3. Start Chatting
- Select your built index
- Ask questions about your documents:
  - "What is this document about?"
  - "Summarize the key points"
  - "What are the main findings?"
  - "Compare the arguments in section 3 and 5"

---

##  Management Commands



### Direct Development Commands

```bash
# System management
python run_system.py               # Start all services
python run_system.py --health      # Liveness/readiness summary
python run_system.py --no-frontend # Start backend + RAG only
python run_system.py --stop        # Stop managed services
python system_health_check.py      # Check system health

# Individual components
python -m rag_system.api_server    # RAG API only
cd backend && python server.py     # Backend only
npm run dev                         # Frontend only

# Stop: Press Ctrl+C in terminal running services
```

---

##  Quick Troubleshooting



### Direct Development Issues

**Import errors?**
```bash
# Check Python installation
python --version  # Should be 3.8+

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

**Node.js errors?**
```bash
# Check Node version
node --version    # Should be 16+

# Reinstall dependencies
rm -rf node_modules package-lock.json
npm install
```

### Common Issues

**Ollama not responding?**
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Restart Ollama
pkill ollama
ollama serve
```

**Out of memory?**
```bash
# Check memory usage
htop          # For direct development

# Recommended: 16GB+ RAM for optimal performance
```

---

##  System Verification

Run this comprehensive check:

```bash
# Check all endpoints
curl -f http://localhost:3000 && echo " Frontend OK"
curl -f http://localhost:8000/health && echo " Backend OK"  
curl -f http://localhost:8001/health && echo " RAG API OK"
curl -f http://localhost:11434/api/tags && echo " Ollama OK"
curl -f http://localhost:8000/metrics && echo " Backend Metrics OK"
curl -f http://localhost:8001/metrics && echo " RAG Metrics OK"

```

---

##  Success!

If you see:
-  All services responding
-  Frontend accessible at http://localhost:3000  
-  No error messages

You're ready to start using AcademicRAG!

### What's Next?

1. ** Upload Documents**: Add your PDF files to create indexes
2. ** Start Chatting**: Ask questions about your documents
3. ** Customize**: Explore different models and settings
4. ** Learn More**: Check the full documentation below

###  Key Files

```
rag-system/
  run_system.py             # Direct development launcher
  system_health_check.py    # System verification
  requirements.txt          # Python dependencies
  package.json              # Node.js dependencies
  Documentation/            # Complete documentation
  rag_system/              # Core system code
```

###  Additional Resources

- ** Architecture**: See `Documentation/architecture_overview.md`
- ** Configuration**: See `Documentation/system_overview.md`   

---

##  Indexing Scripts

The repository includes several convenient scripts for document indexing:

### Simple Index Creation Script

For quick document indexing without the UI:

```bash
# Basic usage
./simple_create_index.sh "Index Name" "document.pdf"

# Multiple documents
./simple_create_index.sh "Research Papers" "paper1.pdf" "paper2.pdf" "notes.txt"

# Using wildcards
./simple_create_index.sh "Invoice Collection" ./invoices/*.pdf
```

**Supported file types**: PDF, TXT, DOCX, MD

### Batch Indexing Script

For processing large document collections:

```bash
# Using the Python batch indexing script
python demo_batch_indexing.py

# Or using the direct indexing script
python create_index_script.py
```

These scripts automatically:
-  Check prerequisites (Ollama running, Python dependencies)
-  Validate document formats
-  Create database entries
-  Process documents with the RAG pipeline
-  Generate searchable indexes

--- 