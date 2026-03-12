#  RAG System Deployment Guide

This guide provides comprehensive instructions for deploying the RAG system using direct development approaches.

---

##  Deployment Options


### Direct Development (Recommended)
- **Best for**: Development, debugging, customization
- **Pros**: Direct access to code, faster iteration, easier debugging
- **Cons**: More dependencies to manage

---

## 1. Prerequisites

### 1.1 System Requirements

#### **Minimum Requirements**
- **CPU**: 4 cores, 2.5GHz+
- **RAM**: 8GB (16GB recommended)
- **Storage**: 50GB free space
- **OS**: Linux, macOS, or Windows with WSL2

#### **Recommended Requirements**
- **CPU**: 8+ cores, 3.0GHz+
- **RAM**: 32GB+ (for large models)
- **Storage**: 200GB+ SSD
- **GPU**: NVIDIA GPU with 8GB+ VRAM (optional, for acceleration)

### 1.2 Common Dependencies

**Both deployment methods require:**
```bash
# Ollama (required for both approaches)
curl -fsSL https://ollama.ai/install.sh | sh

### 5.2 Model Configuration

#### **Default Models**
```python
# Embedding Models
EMBEDDING_MODELS = [
    "Qwen/Qwen3-Embedding-0.6B",  # Fast, 1024 dimensions
    "Qwen/Qwen3-Embedding-4B",    # High quality, 2048 dimensions
]

# Generation Models  
GENERATION_MODELS = [
    "gemma3:12b-cloud",  # Fast responses
    "gemma3:27b-cloud",    # High quality
]
```

### 5.3 Performance Tuning

#### **Memory Settings**
```bash

# For Direct Development: Monitor with
htop  # or top on macOS
```

#### **Model Settings**
```python
# Batch sizes (adjust based on available RAM)
EMBEDDING_BATCH_SIZE = 50   # Reduce if OOM
ENRICHMENT_BATCH_SIZE = 25  # Reduce if OOM

# Chunk settings
CHUNK_SIZE = 512           # Text chunk size
CHUNK_OVERLAP = 64         # Overlap between chunks
```

---

## 6. Operational Procedures

### 6.0 Canonical Startup Path

Use the unified launcher as the primary startup path:

```bash
python run_system.py
```

Useful launcher options:

```bash
python run_system.py --health
python run_system.py --no-frontend
python run_system.py --stop
```

### 6.1 System Monitoring

#### **Health Checks**
```bash
# Comprehensive system check
curl -f http://localhost:3000 && echo " Frontend OK"
curl -f http://localhost:8000/health && echo " Backend OK"
curl -f http://localhost:8001/health && echo " RAG API OK"
curl -f http://localhost:11434/api/tags && echo " Ollama OK"
curl -f http://localhost:8000/metrics && echo " Backend Metrics OK"
curl -f http://localhost:8001/metrics && echo " RAG Metrics OK"
```

#### **Performance Monitoring**
```bash

# Direct development monitoring
htop           # Overall system
nvidia-smi     # GPU usage (if available)
```

### 6.2 Log Management

#### **Direct Development Logs**
```bash
# Logs are printed to terminal
# Redirect to file if needed:
python run_system.py > system.log 2>&1
```

### 6.3 Backup and Restore

#### **Data Backup**
```bash
# Create backup directory
mkdir -p backups/$(date +%Y%m%d)

# Backup databases and indexes
cp -r backend/chat_data.db backups/$(date +%Y%m%d)/
cp -r lancedb backups/$(date +%Y%m%d)/
cp -r index_store backups/$(date +%Y%m%d)/

---

## 7. Troubleshooting

### 7.1 Common Issues

#### **Port Conflicts**
```bash
# Check what's using ports
lsof -i :3000 -i :8000 -i :8001 -i :11434

# For Direct: Kill processes
pkill -f "npm run dev"
pkill -f "server.py"
pkill -f "api_server"
```

#### **Ollama Issues**
```bash
# Check Ollama status
curl http://localhost:11434/api/tags

# Restart Ollama
pkill ollama
ollama serve

# Reinstall models
ollama pull gemma3:12b-cloud
ollama pull gemma3:27b-cloud
```

### 7.2 Performance Issues

#### **Memory Problems**
```bash
# Check memory usage
free -h           # Linux
vm_stat           # macOS

# Solutions:
# 1. Increase system RAM
# 2. Reduce batch sizes in configuration
# 3. Use smaller models (gemma3:12b-cloud instead of gemma3:12b-cloud)
```

#### **Slow Response Times**
```bash
# Check model loading
curl http://localhost:11434/api/tags

# Monitor component response times
time curl http://localhost:8001/models

# Solutions:
# 1. Use SSD storage
# 2. Increase CPU cores
# 3. Use GPU acceleration (if available)
```

---

## 8. Production Considerations

### 8.1 Security

#### **Network Security**
```bash
# Use reverse proxy (nginx/traefik) for production
# Enable HTTPS/TLS
# Restrict port access with firewall
```

#### **Data Security**
```bash
# Enable authentication in production
# Encrypt sensitive data
# Regular security updates
```

### 8.2 Scaling

#### **Horizontal Scaling**
```bash
# Load balance frontend and backend
# Scale RAG API instances based on load
```

#### **Resource Optimization**
```bash
# Use dedicated GPU nodes for AI workloads
# Implement model caching
# Optimize batch processing
```

---

## 9. Success Criteria

### 9.1 Deployment Verification

Your deployment is successful when:

-  All health checks pass
-  Frontend loads at http://localhost:3000
-  You can create document indexes
-  You can chat with uploaded documents
-  No error messages in logs

### 9.2 Performance Benchmarks

**Acceptable Performance:**
- Index creation: < 2 minutes per 100MB document
- Query response: < 30 seconds for complex questions
- Memory usage: < 8GB total system memory

**Optimal Performance:**
- Index creation: < 1 minute per 100MB document  
- Query response: < 10 seconds for complex questions
- Memory usage: < 16GB total system memory

---

## 10. Operations Runbook

For day-2 operations (startup/shutdown, backup/restore, and incident response), use:

- `Documentation/production_runbook.md`

## 11. Limits and Capacity

For practical limits and tuning guardrails (file sizes, memory, latency, and retrieval knobs), use:

- `Documentation/known_limits_capacity_guide.md`

## 12. Release Checklist and Dry Run

For release gating and smoke-validation evidence, use:

- `Documentation/release_checklist_dry_run.md`