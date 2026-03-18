#  API Reference (Backend & RAG API)
---

## Backend HTTP API (Python `backend/server.py`)
**Base URL**: `http://localhost:8000`

| Endpoint | Method | Description | Request Body | Success Response |
|----------|--------|-------------|--------------|------------------|
| `/health` | GET | Health probe incl. Ollama status & DB stats |  | 200 JSON `{ status, ollama_running, available_models, database_stats }` |
| `/metrics` | GET | Lightweight in-memory service metrics |  | 200 JSON `{ uptime_s, requests:{...}, indexing:{...} }` |
| `/chat` | POST | Stateless chat (no session) | `{ message:str, model?:str, conversation_history?:[{role,content}]}` | 200 `{ response:str, model:str, message_count:int }` |
| `/sessions` | GET | List all sessions |  | `{ sessions:ChatSession[], total:int }` |
| `/sessions` | POST | Create session | `{ title?:str, model?:str }` | 201 `{ session:ChatSession, session_id }` |
| `/sessions/<id>` | GET | Get session + msgs |  | `{ session, messages }` |
| `/sessions/<id>` | DELETE | Delete session |  | `{ message, deleted_session_id }` |
| `/sessions/<id>/rename` | POST | Rename session | `{ title:str }` | `{ message, session }` |
| `/sessions/<id>/messages` | POST | Session chat (builds history) | See ChatRequest + retrieval opts  | `{ response, session, user_message_id, ai_message_id }` |
| `/sessions/<id>/documents` | GET | List uploaded docs |  | `{ files:string[], file_count:int, session }` |
| `/sessions/<id>/upload` | POST multipart | Upload docs to session | field `files[]` | `{ message, uploaded_files, processing_results?, session_documents?, total_session_documents? }` |
| `/sessions/<id>/index` | POST | Trigger RAG indexing for session | `{ latechunk?, doclingChunk?, chunkSize?, ... }` | `{ message }` |
| `/sessions/<id>/indexes` | GET | List indexes linked to session |  | `{ indexes, total }` |
| `/sessions/<sid>/indexes/<idxid>` | POST | Link index to session |  | `{ message }` |
| `/sessions/cleanup` | GET | Remove empty sessions |  | `{ message, cleanup_count }` |
| `/models` | GET | List generation / embedding models |  | `{ generation_models:str[], embedding_models:str[] }` |
| `/indexes` | GET | List all indexes |  | `{ indexes, total }` |
| `/indexes` | POST | Create index | `{ name:str, description?:str, metadata?:dict }` | `{ index_id }` |
| `/indexes/<id>` | GET | Get single index |  | `{ index }` |
| `/indexes/<id>` | DELETE | Delete index |  | `{ message, index_id }` |
| `/indexes/<id>/upload` | POST multipart | Upload docs to index | field `files[]` | `{ message, uploaded_files }` |
| `/indexes/<id>/build` | POST | Build / rebuild index (RAG) | `{ latechunk?, doclingChunk?, ...}` | 200 `{ response?, message?}` (idempotent) |

---

## RAG API (Python `rag_system/api_server.py`)
**Base URL**: `http://localhost:8001`

| Endpoint | Method | Description | Request Body | Success Response |
|----------|--------|-------------|--------------|------------------|
| `/chat` | POST | Run RAG query with full pipeline | See RAG ChatRequest  | `{ answer:str, source_documents:[], reasoning?:str, confidence?:float }` |
| `/chat/stream` | POST | Run RAG query with SSE streaming | Same as /chat | Server-Sent Events stream |
| `/metrics` | GET | Lightweight in-memory service metrics + semantic cache stats |  | 200 JSON `{ uptime_s, requests:{...}, indexing:{...}, semantic_cache:{...} }` |
| `/retrieval/diagnostics` | POST | Inspect retrieval ranking before/after rerank | See Retrieval Diagnostics Request | `{ query, table_name, retrieval:{ pre_rerank:[], post_rerank:[], ... } }` |
| `/index` | POST | Index documents with full configuration | See Index Request  | `{ message:str, indexed_files:[], table_name:str }` |
| `/models` | GET | List available models |  | `{ generation_models:str[], embedding_models:str[] }` |

### Lightweight Metrics Response (summary)
```jsonc
{
  "uptime_s": 123.45,
  "requests": {
    "total": 42,
    "by_status": { "2xx": 40, "4xx": 1, "5xx": 1 },
    "by_endpoint": {
      "GET /health": { "count": 10, "avg_ms": 3.2, "max_ms": 7.1, "4xx": 0, "5xx": 0 }
    }
  },
  "indexing": {
    "count": 3,
    "success": 2,
    "failed": 1,
    "avg_duration_ms": 15234.9,
    "max_duration_ms": 20311.4,
    "last_duration_ms": 9811.0
  },
  "semantic_cache": {
    "lookups": 27,
    "hits": 9,
    "misses": 18,
    "hit_rate": 0.3333,
    "scope": "global",
    "threshold": 0.98
  }
}
```

### RAG ChatRequest (Advanced Options)
```jsonc
{
  "query": "string",                    // Required  user question
  "session_id": "string",               // Optional  for session context
  "table_name": "string",               // Optional  specific index table
  "compose_sub_answers": true,          // Optional  compose sub-answers 
  "query_decompose": true,              // Optional  decompose complex queries
  "ai_rerank": false,                   // Optional  AI-powered reranking
  "context_expand": false,              // Optional  context expansion
  "verify": true,                       // Optional  answer verification
  "retrieval_k": 20,                    // Optional  number of chunks to retrieve
  "context_window_size": 1,             // Optional  context window size
  "reranker_top_k": 10,                 // Optional  top-k after reranking
  "search_type": "hybrid",              // Optional  "hybrid|dense|fts"
  "dense_weight": 0.7,                  // Optional  dense search weight (0-1)
  "force_rag": false,                   // Optional  bypass triage, force RAG
  "provence_prune": false,              // Optional  sentence-level pruning
  "provence_threshold": 0.8,            // Optional  pruning threshold
  "model": "gemma3:12b-cloud"                   // Optional  generation model override
}
```

### Index Request (Document Indexing)
```jsonc
{
  "file_paths": ["path1.pdf", "path2.pdf"],  // Required  files to index
  "session_id": "string",                     // Required  session identifier
  "chunk_size": 512,                          // Optional  chunk size (default: 512)
  "chunk_overlap": 64,                        // Optional  chunk overlap (default: 64)
  "enable_latechunk": true,                   // Optional  enable late chunking
  "enable_docling_chunk": false,              // Optional  enable DocLing chunking
  "retrieval_mode": "hybrid",                 // Optional  "hybrid|dense|fts"
  "window_size": 2,                           // Optional  context window
  "enable_enrich": true,                      // Optional  enable enrichment
  "embedding_model": "Qwen/Qwen3-Embedding-0.6B",  // Optional  embedding model
  "enrich_model": "gemma3:12b-cloud",               // Optional  enrichment model
  "overview_model_name": "gemma3:12b-cloud",        // Optional  overview model
  "batch_size_embed": 50,                     // Optional  embedding batch size
  "batch_size_enrich": 25                     // Optional  enrichment batch size
}
```

### Retrieval Diagnostics Request
```jsonc
{
  "query": "string",              // Required
  "session_id": "string",         // Optional (resolves linked table)
  "table_name": "string",         // Optional explicit table override
  "retrieval_k": 20,               // Optional total chunks retrieved pre-rerank
  "pre_rerank_k": 10,              // Optional top-k included in pre_rerank output
  "post_rerank_k": 10,             // Optional top-k included in post_rerank output
  "search_type": "hybrid",        // Optional retrieval mode override
  "dense_weight": 0.7,             // Optional dense-vs-lexical fusion weight
  "ai_rerank": true                // Optional force enable/disable AI reranking
}
```

> **Note on CORS**  All endpoints include `Access-Control-Allow-Origin: *` header.

---

## Frontend Wrapper (`src/lib/api.ts`)
The React/Next.js frontend calls the backend via a typed wrapper. Important methods & payloads:

| Method | Backend Endpoint | Payload Shape |
|--------|------------------|---------------|
| `checkHealth()` | `/health` |  |
| `sendMessage({ message, model?, conversation_history? })` | `/chat` | ChatRequest |
| `getSessions()` | `/sessions` |  |
| `createSession(title?, model?)` | `/sessions` |  |
| `getSession(sessionId)` | `/sessions/<id>` |  |
| `sendSessionMessage(sessionId, message, opts)` | `/sessions/<id>/messages` | `ChatRequest + retrieval opts` |
| `uploadFiles(sessionId, files[])` | `/sessions/<id>/upload` | multipart |
| `indexDocuments(sessionId)` | `/sessions/<id>/index` | opts similar to buildIndex |
| `buildIndex(indexId, opts)` | `/indexes/<id>/build` | Index build options |
| `linkIndexToSession` | `/sessions/<sid>/indexes/<idx>` |  |

---

## Payload Definitions (Canonical)

### ChatRequest (frontend  backend)
```jsonc
{
  "message": "string",              // Required  raw user text
  "model": "string",                // Optional  generation model id
  "conversation_history": [         // Optional  prior turn list
    { "role": "user|assistant", "content": "string" }
  ]
}
```

### Session Chat Extended Options
```jsonc
{
  "composeSubAnswers": true,
  "decompose": true,
  "aiRerank": false,
  "contextExpand": false,
  "verify": true,
  "retrievalK": 10,
  "contextWindowSize": 5,
  "rerankerTopK": 20,
  "searchType": "fts|hybrid|dense",
  "denseWeight": 0.75,
  "force_rag": false
}
```

### Index Build Options
```jsonc
{
  "latechunk": true,
  "doclingChunk": false,
  "chunkSize": 512,
  "chunkOverlap": 64,
  "retrievalMode": "hybrid|dense|fts",
  "windowSize": 2,
  "enableEnrich": true,
  "embeddingModel": "Qwen/Qwen3-Embedding-0.6B",
  "enrichModel": "gemma3:12b-cloud",
  "overviewModel": "gemma3:12b-cloud",
  "batchSizeEmbed": 64,
  "batchSizeEnrich": 32
}
```

---

_This reference is derived from static code analysis of `backend/server.py`, `rag_system/api_server.py`, and `src/lib/api.ts`. Keep it in sync with route or type changes._ 