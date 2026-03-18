import json
import http.server
import socketserver
import cgi
import os
import uuid
from urllib.parse import urlparse, parse_qs
import requests  #  Import requests for making HTTP calls
import sys
from datetime import datetime
import time
import threading
import traceback
import logging
from logging.handlers import RotatingFileHandler
from collections import defaultdict

# Add parent directory to path so we can import rag_system modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import RAG system modules for complete metadata
try:
    from rag_system.main import PIPELINE_CONFIGS
    RAG_SYSTEM_AVAILABLE = True
    print(" RAG system modules accessible from backend")
except ImportError as e:
    PIPELINE_CONFIGS = {}
    RAG_SYSTEM_AVAILABLE = False
    print(f" RAG system modules not available: {e}")

from ollama_client import OllamaClient
from database import db, generate_session_title
import simple_pdf_processor as pdf_module
from simple_pdf_processor import initialize_simple_pdf_processor
from typing import List, Dict, Any
import re


_INDEX_BUILD_LOCK = threading.Lock()
_ACTIVE_INDEX_BUILDS: set[str] = set()
_MAX_HISTORY_MESSAGES = max(2, int(os.getenv("OLLAMA_MAX_HISTORY_MESSAGES", "12")))
_RAG_CHAT_TIMEOUT_SEC = max(30, int(os.getenv("RAG_CHAT_TIMEOUT_SEC", "180")))
_OVERVIEW_CACHE_TTL_SEC = max(5, int(os.getenv("OVERVIEW_CACHE_TTL_SEC", "120")))
_OVERVIEW_CACHE_LOCK = threading.Lock()
_OVERVIEW_CACHE: dict[tuple[str, ...], tuple[float, list[str]]] = {}
_CASUAL_DIRECT_PATTERNS = [
    'hello', 'hi', 'hey', 'greetings', 'good morning', 'good afternoon', 'good evening',
    'how are you', 'how do you do', 'nice to meet', 'pleasure to meet',
    'thanks', 'thank you', 'bye', 'goodbye', 'see you', 'talk to you later',
    'test', 'testing', 'check', 'ping', 'just saying', 'nevermind',
    'ok', 'okay', 'alright', 'got it', 'understood', 'i see'
]
_RAG_INDICATORS = [
    'document', 'doc', 'file', 'pdf', 'text', 'content', 'page',
    'according to', 'based on', 'mentioned', 'states', 'says',
    'what does', 'summarize', 'summary', 'analyze', 'analysis',
    'quote', 'citation', 'reference', 'source', 'evidence',
    'explain from', 'extract', 'find in', 'search for'
]
_QUESTION_WORDS = ['what', 'how', 'when', 'where', 'why', 'who', 'which']


def _is_plain_conversational_message(message: str) -> bool:
    normalized = " ".join(str(message or "").strip().lower().split())
    if not normalized:
        return True

    return any(pattern in normalized for pattern in _CASUAL_DIRECT_PATTERNS)


def _prepare_conversation_history(
    conversation_history: List[Dict[str, Any]] | None,
    latest_user_message: str,
    max_messages: int = _MAX_HISTORY_MESSAGES,
) -> List[Dict[str, str]]:
    """Trim persisted history for faster follow-up turns and remove duplicated latest user prompts."""
    latest_normalized = str(latest_user_message or "").strip()
    prepared: List[Dict[str, str]] = []

    for item in conversation_history or []:
        role = str(item.get("role", "")).strip().lower()
        content = str(item.get("content", "")).strip()
        if role not in {"user", "assistant"} or not content:
            continue
        prepared.append({"role": role, "content": content})

    if prepared and latest_normalized:
        last_message = prepared[-1]
        if last_message.get("role") == "user" and last_message.get("content", "").strip() == latest_normalized:
            prepared.pop()

    if max_messages > 0 and len(prepared) > max_messages:
        prepared = prepared[-max_messages:]

    return prepared


class ServiceMetrics:
    def __init__(self):
        self._started_at = time.time()
        self._lock = threading.Lock()
        self._requests_total = 0
        self._requests_by_status: dict[str, int] = defaultdict(int)
        self._requests_by_endpoint: dict[str, dict[str, float]] = defaultdict(
            lambda: {
                "count": 0,
                "total_ms": 0.0,
                "max_ms": 0.0,
                "4xx": 0,
                "5xx": 0,
            }
        )
        self._index_builds = {
            "count": 0,
            "success": 0,
            "failed": 0,
            "total_duration_ms": 0.0,
            "max_duration_ms": 0.0,
            "last_duration_ms": None,
        }

    def record_request(self, method: str, path: str, status_code: int, duration_ms: float):
        endpoint_key = f"{method.upper()} {path}"
        status_bucket = f"{int(status_code) // 100}xx"
        with self._lock:
            self._requests_total += 1
            self._requests_by_status[status_bucket] += 1
            bucket = self._requests_by_endpoint[endpoint_key]
            bucket["count"] += 1
            bucket["total_ms"] += float(duration_ms)
            bucket["max_ms"] = max(bucket["max_ms"], float(duration_ms))
            if 400 <= int(status_code) < 500:
                bucket["4xx"] += 1
            if int(status_code) >= 500:
                bucket["5xx"] += 1

    def record_index_build(self, duration_ms: float, success: bool):
        with self._lock:
            self._index_builds["count"] += 1
            if success:
                self._index_builds["success"] += 1
            else:
                self._index_builds["failed"] += 1
            self._index_builds["total_duration_ms"] += float(duration_ms)
            self._index_builds["max_duration_ms"] = max(self._index_builds["max_duration_ms"], float(duration_ms))
            self._index_builds["last_duration_ms"] = float(duration_ms)

    def snapshot(self) -> dict:
        with self._lock:
            endpoints = {}
            for key, stats in self._requests_by_endpoint.items():
                count = int(stats["count"])
                avg_ms = (stats["total_ms"] / count) if count else 0.0
                endpoints[key] = {
                    "count": count,
                    "avg_ms": round(avg_ms, 2),
                    "max_ms": round(float(stats["max_ms"]), 2),
                    "4xx": int(stats["4xx"]),
                    "5xx": int(stats["5xx"]),
                }

            index_count = int(self._index_builds["count"])
            index_avg_ms = (self._index_builds["total_duration_ms"] / index_count) if index_count else 0.0

            return {
                "uptime_s": round(time.time() - self._started_at, 2),
                "requests": {
                    "total": self._requests_total,
                    "by_status": dict(self._requests_by_status),
                    "by_endpoint": endpoints,
                },
                "indexing": {
                    "count": index_count,
                    "success": int(self._index_builds["success"]),
                    "failed": int(self._index_builds["failed"]),
                    "avg_duration_ms": round(index_avg_ms, 2),
                    "max_duration_ms": round(float(self._index_builds["max_duration_ms"]), 2),
                    "last_duration_ms": self._index_builds["last_duration_ms"],
                },
            }


def _setup_service_logger(service_name: str, log_filename: str) -> logging.Logger:
    logger = logging.getLogger(service_name)
    if logger.handlers:
        return logger

    os.makedirs("logs", exist_ok=True)
    max_bytes = int(os.getenv("LOG_MAX_BYTES", str(5 * 1024 * 1024)))
    backup_count = int(os.getenv("LOG_BACKUP_COUNT", "5"))

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    file_handler = RotatingFileHandler(
        os.path.join("logs", log_filename),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    if os.getenv("LOG_TO_STDOUT", "0") == "1":
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
    logger.propagate = False
    return logger


LOGGER = _setup_service_logger("academicrag.backend", "backend_server.log")
BACKEND_METRICS = ServiceMetrics()


def _resolve_request_id(headers) -> str:
    if not headers:
        return uuid.uuid4().hex

    incoming = headers.get("X-Request-ID") or headers.get("X-Correlation-ID")
    if isinstance(incoming, str):
        normalized = incoming.strip()
        if normalized:
            return normalized[:128]

    return uuid.uuid4().hex


def _get_pending_file_paths(all_file_paths: List[str], completed_files=None) -> List[str]:
    completed = set(completed_files or [])
    return [path for path in all_file_paths if path not in completed]


def _run_index_build_job(index_id: str, file_paths: List[str], table_name: str, options: Dict[str, Any]):
    """Run a potentially long index build out-of-band and persist progress in index metadata."""
    build_started_at = time.time()
    build_success = False
    rag_api_url = "http://localhost:8001/index"
    correlation_id = options.get("request_id") or f"build-{uuid.uuid4().hex[:16]}"
    latechunk = bool(options.get("latechunk", False))
    docling_chunk = bool(options.get("docling_chunk", False))
    chunk_size = int(options.get("chunk_size", 512))
    chunk_overlap = int(options.get("chunk_overlap", 64))
    retrieval_mode = str(options.get("retrieval_mode", "hybrid"))
    window_size = int(options.get("window_size", 2))
    enable_enrich = bool(options.get("enable_enrich", True))
    embedding_model = options.get("embedding_model")
    enrich_model = options.get("enrich_model")
    overview_model = options.get("overview_model")
    batch_size_embed = int(options.get("batch_size_embed", 50))
    batch_size_enrich = int(options.get("batch_size_enrich", 25))
    completed_files = list(options.get("completed_files") or [])
    failed_files: List[str] = list(options.get("failed_files") or [])

    pending_paths = _get_pending_file_paths(file_paths, completed_files)
    total_files = len(file_paths)

    if not pending_paths:
        db.update_index_metadata(index_id, {
            "status": "functional",
            "indexing_stage": "done",
            "indexing_progress": 100.0,
            "completed_files": completed_files,
            "failed_files": failed_files,
            "pending_files": 0,
            "build_error": None,
            "build_completed_at": datetime.now().isoformat(),
        })
        with _INDEX_BUILD_LOCK:
            _ACTIVE_INDEX_BUILDS.discard(index_id)
        return

    db.update_index_metadata(index_id, {
        "status": "building",
        "indexing_stage": "parsing",
        "indexing_progress": 10.0,
        "indexing_details": {
            "files_total": total_files,
            "files_completed": len(completed_files),
            "files_remaining": len(pending_paths),
        },
        "completed_files": completed_files,
        "failed_files": failed_files,
        "pending_files": len(pending_paths),
    })

    try:
        current_file_path = None
        for offset, file_path in enumerate(pending_paths, start=1):
            current_file_path = file_path
            payload = {
                "file_paths": [file_path],
                "session_id": index_id,
                "table_name": table_name,
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
                "retrieval_mode": retrieval_mode,
                "window_size": window_size,
                "enable_enrich": enable_enrich,
                "batch_size_embed": batch_size_embed,
                "batch_size_enrich": batch_size_enrich,
            }
            if latechunk:
                payload["enable_latechunk"] = True
            if docling_chunk:
                payload["enable_docling_chunk"] = True
            if embedding_model:
                payload["embeddingModel"] = embedding_model
                payload["embedding_model"] = embedding_model
            if enrich_model:
                payload["enrichModel"] = enrich_model
                payload["enrich_model"] = enrich_model
            if overview_model:
                payload["overviewModel"] = overview_model
                payload["overview_model_name"] = overview_model

            parsed_progress = min(95.0, 10.0 + (((len(completed_files) + 1) / max(1, total_files)) * 85.0))
            db.update_index_metadata(index_id, {
                "status": "building",
                "indexing_stage": "parsing",
                "indexing_progress": parsed_progress,
                "indexing_details": {
                    "current_file": os.path.basename(file_path),
                    "files_total": total_files,
                    "files_completed": len(completed_files),
                    "files_remaining": len(_get_pending_file_paths(file_paths, completed_files)),
                },
            })

            rag_resp = None
            last_error = None
            for attempt in range(1, 4):
                try:
                    rag_resp = requests.post(
                        rag_api_url,
                        json=payload,
                        timeout=(10, 1800),
                        headers={"X-Request-ID": str(correlation_id)},
                    )
                    if rag_resp.status_code in (502, 503, 504) and attempt < 3:
                        wait_s = 1.5 * attempt
                        print(f"Transient RAG API status {rag_resp.status_code}; retrying build in {wait_s:.1f}s (attempt {attempt}/3)")
                        time.sleep(wait_s)
                        continue
                    break
                except requests.exceptions.RequestException as e:
                    last_error = e
                    if isinstance(e, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)) and attempt < 3:
                        wait_s = 1.5 * attempt
                        print(f"Transient RAG API connection error: {e}; retrying in {wait_s:.1f}s (attempt {attempt}/3)")
                        time.sleep(wait_s)
                        continue
                    raise

            if rag_resp is None and last_error is not None:
                raise last_error

            if rag_resp.status_code == 200:
                if file_path not in completed_files:
                    completed_files.append(file_path)
                db.update_index_metadata(index_id, {
                    "status": "building",
                    "completed_files": completed_files,
                    "failed_files": failed_files,
                    "pending_files": len(_get_pending_file_paths(file_paths, completed_files)),
                    "indexing_progress": min(99.0, 10.0 + ((len(completed_files) / max(1, total_files)) * 88.0)),
                    "indexing_details": {
                        "last_completed_file": os.path.basename(file_path),
                        "files_total": total_files,
                        "files_completed": len(completed_files),
                        "files_remaining": len(_get_pending_file_paths(file_paths, completed_files)),
                    },
                    "last_build_response": rag_resp.json(),
                })
            else:
                try:
                    err_json = rag_resp.json()
                except Exception:
                    err_json = {}
                err_text = err_json.get("error") if isinstance(err_json, dict) else rag_resp.text
                if err_text and "already exists" in str(err_text):
                    if file_path not in completed_files:
                        completed_files.append(file_path)
                    db.update_index_metadata(index_id, {
                        "status": "building",
                        "completed_files": completed_files,
                        "failed_files": failed_files,
                        "pending_files": len(_get_pending_file_paths(file_paths, completed_files)),
                        "indexing_details": {
                            "last_completed_file": os.path.basename(file_path),
                            "note": str(err_text),
                        },
                    })
                else:
                    raise RuntimeError(f"RAG indexing failed for {os.path.basename(file_path)}: {err_text or rag_resp.text}")

        meta_updates = {
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "retrieval_mode": retrieval_mode,
            "window_size": window_size,
            "enable_enrich": enable_enrich,
            "latechunk": latechunk,
            "docling_chunk": docling_chunk,
            "batch_size_embed": batch_size_embed,
            "batch_size_enrich": batch_size_enrich,
            "build_completed_at": datetime.now().isoformat(),
            "status": "functional",
            "indexing_stage": "done",
            "indexing_progress": 100.0,
            "build_error": None,
            "completed_files": completed_files,
            "failed_files": failed_files,
            "pending_files": 0,
        }
        if embedding_model:
            meta_updates["embedding_model"] = embedding_model
        if enrich_model:
            meta_updates["enrich_model"] = enrich_model
        if overview_model:
            meta_updates["overview_model"] = overview_model
        db.update_index_metadata(index_id, meta_updates)
        build_success = True
    except Exception as e:
        if current_file_path and current_file_path not in failed_files:
            failed_files.append(current_file_path)
        db.update_index_metadata(index_id, {
            "status": "failed",
            "indexing_stage": "failed",
            "indexing_progress": 100.0,
            "build_error": str(e),
            "build_completed_at": datetime.now().isoformat(),
            "build_traceback": traceback.format_exc(limit=20),
            "completed_files": completed_files,
            "failed_files": failed_files,
            "pending_files": len(_get_pending_file_paths(file_paths, completed_files)),
        })
        LOGGER.error("Background build failed for index %s: %s", index_id[:8], e)
    finally:
        BACKEND_METRICS.record_index_build(
            duration_ms=(time.time() - build_started_at) * 1000.0,
            success=build_success,
        )
        with _INDEX_BUILD_LOCK:
            _ACTIVE_INDEX_BUILDS.discard(index_id)

#  Reusable threaded TCPServer with address reuse enabled
class ReusableTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True
    block_on_close = False

class ChatHandler(http.server.BaseHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.ollama_client = OllamaClient()
        super().__init__(*args, **kwargs)
    
    def do_OPTIONS(self):
        """Handle CORS preflight requests"""
        self.request_id = _resolve_request_id(self.headers)
        self.request_started_at = time.time()
        LOGGER.info(
            "request_started request_id=%s method=%s path=%s client=%s",
            self.request_id,
            "OPTIONS",
            self.path,
            getattr(self, "client_address", ("unknown",))[0],
        )
        self.send_response(200)
        self.send_header('X-Request-ID', str(self.request_id))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_GET(self):
        """Handle GET requests"""
        self.request_id = _resolve_request_id(self.headers)
        self.request_started_at = time.time()
        LOGGER.info(
            "request_started request_id=%s method=%s path=%s client=%s",
            self.request_id,
            "GET",
            self.path,
            getattr(self, "client_address", ("unknown",))[0],
        )
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == '/health':
            self.send_json_response({
                "status": "ok",
                "service": "backend",
                "check": "liveness"
            })
        elif parsed_path.path == '/metrics':
            self.send_json_response(BACKEND_METRICS.snapshot())
        elif parsed_path.path == '/health/ready':
            self.send_json_response({
                "status": "ready" if self._backend_ready() else "not_ready",
                "service": "backend",
                "check": "readiness",
                "ollama_running": self.ollama_client.is_ollama_running(),
                "available_models": self.ollama_client.list_models(),
                "database_stats": db.get_stats()
            }, status_code=200 if self._backend_ready() else 503)
        elif parsed_path.path == '/sessions':
            self.handle_get_sessions()
        elif parsed_path.path == '/sessions/cleanup':
            self.handle_cleanup_sessions()
        elif parsed_path.path == '/models':
            self.handle_get_models()
        elif parsed_path.path == '/indexes':
            self.handle_get_indexes()
        elif parsed_path.path.startswith('/indexes/') and parsed_path.path.count('/') == 2:
            index_id = parsed_path.path.split('/')[-1]
            self.handle_get_index(index_id)
        elif parsed_path.path.startswith('/sessions/') and parsed_path.path.endswith('/documents'):
            session_id = parsed_path.path.split('/')[-2]
            self.handle_get_session_documents(session_id)
        elif parsed_path.path.startswith('/sessions/') and parsed_path.path.endswith('/indexes'):
            session_id = parsed_path.path.split('/')[-2]
            self.handle_get_session_indexes(session_id)
        elif parsed_path.path.startswith('/sessions/') and parsed_path.path.count('/') == 2:
            session_id = parsed_path.path.split('/')[-1]
            self.handle_get_session(session_id)
        else:
            self.send_error_response("Not Found", status_code=404, error_code="not_found")
    
    def do_POST(self):
        """Handle POST requests"""
        self.request_id = _resolve_request_id(self.headers)
        self.request_started_at = time.time()
        LOGGER.info(
            "request_started request_id=%s method=%s path=%s client=%s",
            self.request_id,
            "POST",
            self.path,
            getattr(self, "client_address", ("unknown",))[0],
        )
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == '/chat':
            self.handle_chat()
        elif parsed_path.path == '/sessions':
            self.handle_create_session()
        elif parsed_path.path == '/indexes':
            self.handle_create_index()
        elif parsed_path.path.startswith('/indexes/') and parsed_path.path.endswith('/upload'):
            index_id = parsed_path.path.split('/')[-2]
            self.handle_index_file_upload(index_id)
        elif parsed_path.path.startswith('/indexes/') and parsed_path.path.endswith('/build'):
            index_id = parsed_path.path.split('/')[-2]
            self.handle_build_index(index_id)
        elif parsed_path.path.startswith('/sessions/') and '/indexes/' in parsed_path.path:
            parts = parsed_path.path.split('/')
            session_id = parts[2]
            index_id = parts[4]
            self.handle_link_index_to_session(session_id, index_id)
        elif parsed_path.path.startswith('/sessions/') and parsed_path.path.endswith('/messages'):
            session_id = parsed_path.path.split('/')[-2]
            self.handle_session_chat(session_id)
        elif parsed_path.path.startswith('/sessions/') and parsed_path.path.endswith('/upload'):
            session_id = parsed_path.path.split('/')[-2]
            self.handle_file_upload(session_id)
        elif parsed_path.path.startswith('/sessions/') and parsed_path.path.endswith('/index'):
            session_id = parsed_path.path.split('/')[-2]
            self.handle_index_documents(session_id)
        elif parsed_path.path.startswith('/sessions/') and parsed_path.path.endswith('/rename'):
            session_id = parsed_path.path.split('/')[-2]
            self.handle_rename_session(session_id)
        else:
            self.send_error_response("Not Found", status_code=404, error_code="not_found")

    def do_DELETE(self):
        """Handle DELETE requests"""
        parsed_path = urlparse(self.path)
        
        if parsed_path.path.startswith('/sessions/') and parsed_path.path.count('/') == 2:
            session_id = parsed_path.path.split('/')[-1]
            self.handle_delete_session(session_id)
        elif parsed_path.path.startswith('/indexes/') and parsed_path.path.count('/') == 2:
            index_id = parsed_path.path.split('/')[-1]
            self.handle_delete_index(index_id)
        else:
            self.send_error_response("Not Found", status_code=404, error_code="not_found")
    
    def handle_chat(self):
        """Handle legacy chat requests (without sessions)"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            message = data.get('message', '')
            model = data.get('model', 'gemma3:12b-cloud')
            conversation_history = data.get('conversation_history', [])
            
            if not message:
                self.send_json_response({
                    "error": "Message is required"
                }, status_code=400)
                return
            
            # Check if Ollama is running
            if not self.ollama_client.is_ollama_running():
                self.send_json_response({
                    "error": "Ollama is not running. Please start Ollama first."
                }, status_code=503)
                return
            
            # Get response from Ollama
            response = self.ollama_client.chat(message, model, conversation_history)
            
            self.send_json_response({
                "response": response,
                "model": model,
                "message_count": len(conversation_history) + 1
            })
            
        except json.JSONDecodeError:
            self.send_json_response({
                "error": "Invalid JSON"
            }, status_code=400)
        except Exception as e:
            self.send_json_response({
                "error": f"Server error: {str(e)}"
            }, status_code=500)
    
    def handle_get_sessions(self):
        """Get all chat sessions"""
        try:
            sessions = db.get_sessions()
            self.send_json_response({
                "sessions": sessions,
                "total": len(sessions)
            })
        except Exception as e:
            self.send_json_response({
                "error": f"Failed to get sessions: {str(e)}"
            }, status_code=500)
    
    def handle_cleanup_sessions(self):
        """Clean up empty sessions"""
        try:
            cleanup_count = db.cleanup_empty_sessions()
            self.send_json_response({
                "message": f"Cleaned up {cleanup_count} empty sessions",
                "cleanup_count": cleanup_count
            })
        except Exception as e:
            self.send_json_response({
                "error": f"Failed to cleanup sessions: {str(e)}"
            }, status_code=500)
    
    def handle_get_session(self, session_id: str):
        """Get a specific session with its messages"""
        try:
            session = db.get_session(session_id)
            if not session:
                self.send_json_response({
                    "error": "Session not found"
                }, status_code=404)
                return
            
            messages = db.get_messages(session_id)
            
            self.send_json_response({
                "session": session,
                "messages": messages
            })
        except Exception as e:
            self.send_json_response({
                "error": f"Failed to get session: {str(e)}"
            }, status_code=500)
    
    def handle_get_session_documents(self, session_id: str):
        """Return documents and basic info for a session."""
        try:
            session = db.get_session(session_id)
            if not session:
                self.send_json_response({"error": "Session not found"}, status_code=404)
                return

            docs = db.get_documents_for_session(session_id)

            # Extract original filenames from stored paths
            filenames = [os.path.basename(p).split('_', 1)[-1] if '_' in os.path.basename(p) else os.path.basename(p) for p in docs]

            self.send_json_response({
                "session": session,
                "files": filenames,
                "file_count": len(docs)
            })
        except Exception as e:
            self.send_json_response({"error": f"Failed to get documents: {str(e)}"}, status_code=500)
    
    def handle_create_session(self):
        """Create a new chat session"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            title = data.get('title', 'New Chat')
            model = data.get('model', 'gemma3:12b-cloud')
            
            session_id = db.create_session(title, model)
            session = db.get_session(session_id)
            
            self.send_json_response({
                "session": session,
                "session_id": session_id
            }, status_code=201)
            
        except json.JSONDecodeError:
            self.send_json_response({
                "error": "Invalid JSON"
            }, status_code=400)
        except Exception as e:
            self.send_json_response({
                "error": f"Failed to create session: {str(e)}"
            }, status_code=500)
    
    def handle_session_chat(self, session_id: str):
        """
        Handle chat within a specific session.
        Intelligently routes between direct LLM (fast) and RAG pipeline (document-aware).
        """
        try:
            session = db.get_session(session_id)
            if not session:
                self.send_json_response({"error": "Session not found"}, status_code=404)
                return
            
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            message = data.get('message', '')

            if not message:
                self.send_json_response({"error": "Message is required"}, status_code=400)
                return

            if session['message_count'] == 0:
                title = generate_session_title(message)
                db.update_session_title(session_id, title)

            # Add user message to database first
            user_message_id = db.add_message(session_id, message, "user")
            
            #  SMART ROUTING: Decide between direct LLM vs RAG
            idx_ids = db.get_indexes_for_session(session_id)
            force_rag = bool(data.get("force_rag", False))
            use_rag = True if force_rag else self._should_use_rag(message, idx_ids)
            
            if use_rag:
                #  --- Use RAG Pipeline for Document-Related Queries ---
                print(f" Using RAG pipeline for document query: '{message[:50]}...'")
                response_text, source_docs = self._handle_rag_query(session_id, message, data, idx_ids)
            else:
                #  --- Use Direct LLM for General Queries (FAST) ---
                print(f" Using direct LLM for general query: '{message[:50]}...'")
                response_text, source_docs = self._handle_direct_llm_query(session_id, message, session, data)

            # Add AI response to database
            ai_message_id = db.add_message(session_id, response_text, "assistant")
            
            updated_session = db.get_session(session_id)
            
            # Send response with proper error handling
            self.send_json_response({
                "response": response_text,
                "session": updated_session,
                "source_documents": source_docs,
                "used_rag": use_rag
            })
            
        except BrokenPipeError:
            # Client disconnected - this is normal for long queries, just log it
            print(f"  Client disconnected during RAG processing for query: '{message[:30]}...'")
        except json.JSONDecodeError:
            self.send_json_response({
                "error": "Invalid JSON"
            }, status_code=400)
        except Exception as e:
            print(f" Server error in session chat: {str(e)}")
            try:
                self.send_json_response({
                    "error": f"Server error: {str(e)}"
                }, status_code=500)
            except BrokenPipeError:
                print(f"  Client disconnected during error response")
    
    def _should_use_rag(self, message: str, idx_ids: List[str]) -> bool:
        """
         ENHANCED: Determine if a query should use RAG pipeline using document overviews.
        
        Args:
            message: The user's query
            idx_ids: List of index IDs associated with the session
            
        Returns:
            bool: True if should use RAG, False for direct LLM
        """
        # No indexes = definitely no RAG needed
        if not idx_ids:
            return False

        # Skip expensive overview routing for clearly conversational prompts.
        if _is_plain_conversational_message(message):
            return False

        # Load document overviews for intelligent routing
        try:
            doc_overviews = self._load_document_overviews(idx_ids)
            if doc_overviews:
                return self._route_using_overviews(message, doc_overviews)
        except Exception as e:
            print(f" Overview-based routing failed, falling back to simple routing: {e}")
        
        # Fallback to simple pattern matching if overviews unavailable
        return self._simple_pattern_routing(message, idx_ids)

    def _load_document_overviews(self, idx_ids: List[str]) -> List[str]:
        """Load and aggregate overviews for the given index IDs.
        
        Strategy:
        1. Attempt to load each index's dedicated overview file.
        2. Aggregate all overviews found across available files (deduplicated).
        3. If none of the index files exist, fall back to the legacy global overview file.
        """
        import os, json

        cache_key = tuple(sorted(str(idx) for idx in idx_ids if idx))
        now = time.time()
        with _OVERVIEW_CACHE_LOCK:
            cached = _OVERVIEW_CACHE.get(cache_key)
            if cached and now < cached[0]:
                return list(cached[1])

        aggregated: list[str] = []

        # 1  Collect overviews from per-index files
        for idx in idx_ids:
            candidate_paths = [
                f"../index_store/overviews/{idx}.jsonl",
                f"index_store/overviews/{idx}.jsonl",
                f"./index_store/overviews/{idx}.jsonl",
            ]
            for p in candidate_paths:
                if os.path.exists(p):
                    print(f" Loading overviews from: {p}")
                    try:
                        with open(p, "r", encoding="utf-8") as f:
                            for line in f:
                                if not line.strip():
                                    continue
                                try:
                                    record = json.loads(line)
                                    overview = record.get("overview", "").strip()
                                    if overview:
                                        aggregated.append(overview)
                                except json.JSONDecodeError:
                                    continue  # skip malformed lines
                        break  # Stop after the first existing path for this idx
                    except Exception as e:
                        print(f" Error reading {p}: {e}")
                        break  # Don't keep trying other paths for this idx if read failed

        # 2  Fall back to legacy global file if no per-index overviews found
        if not aggregated:
            legacy_paths = [
                "../index_store/overviews/overviews.jsonl",
                "index_store/overviews/overviews.jsonl",
                "./index_store/overviews/overviews.jsonl",
            ]
            for p in legacy_paths:
                if os.path.exists(p):
                    print(f" Falling back to legacy overviews file: {p}")
                    try:
                        with open(p, "r", encoding="utf-8") as f:
                            for line in f:
                                if not line.strip():
                                    continue
                                try:
                                    record = json.loads(line)
                                    overview = record.get("overview", "").strip()
                                    if overview:
                                        aggregated.append(overview)
                                except json.JSONDecodeError:
                                    continue
                    except Exception as e:
                        print(f" Error reading legacy overviews file {p}: {e}")
                    break

        # Limit for performance
        if aggregated:
            print(f" Loaded {len(aggregated)} document overviews from {len(idx_ids)} index(es)")
        else:
            print(f" No overviews found for indices {idx_ids}")
        limited = aggregated[:40]
        with _OVERVIEW_CACHE_LOCK:
            _OVERVIEW_CACHE[cache_key] = (time.time() + _OVERVIEW_CACHE_TTL_SEC, list(limited))
        return limited

    def _route_using_overviews(self, query: str, overviews: List[str]) -> bool:
        """
         Use document overviews and LLM to make intelligent routing decisions.
        Returns True if RAG should be used, False for direct LLM.
        """
        if not overviews:
            return False
        
        # Format overviews for the routing prompt
        overviews_block = "\n".join(f"[{i+1}] {ov}" for i, ov in enumerate(overviews))
        
        router_prompt = f"""You are an AI router deciding whether a user question should be answered via:
 "USE_RAG"  search the user's private documents (described below)  
 "DIRECT_LLM"  reply from general knowledge (greetings, public facts, unrelated topics)

CRITICAL PRINCIPLE: When documents exist in the KB, strongly prefer USE_RAG unless the query is purely conversational or completely unrelated to any possible document content.

RULES:
1. If ANY overview clearly relates to the question (entities, numbers, addresses, dates, amounts, companies, technical terms)  USE_RAG
2. For document operations (summarize, analyze, explain, extract, find)  USE_RAG  
3. For greetings only ("Hi", "Hello", "Thanks")  DIRECT_LLM
4. For pure math/world knowledge clearly unrelated to documents  DIRECT_LLM
5. When in doubt  USE_RAG

DOCUMENT OVERVIEWS:
{overviews_block}

DECISION EXAMPLES:
 "What invoice amounts are mentioned?"  USE_RAG (document-specific)
 "Who is PromptX AI LLC?"  USE_RAG (entity in documents)  
 "What is the DeepSeek model?"  USE_RAG (mentioned in documents)
 "Summarize the research paper"  USE_RAG (document operation)
 "What is 2+2?"  DIRECT_LLM (pure math)
 "Hi there"  DIRECT_LLM (greeting only)

USER QUERY: "{query}"

Respond with exactly one word: USE_RAG or DIRECT_LLM"""

        try:
            # Use Ollama to make the routing decision
            response = self.ollama_client.chat(
                message=router_prompt,
                model="gemma3:12b-cloud",  # Fast model for routing
                enable_thinking=False  # Fast routing
            )
            
            # The response is directly the text, not a dict
            decision = response.strip().upper()
            
            # Parse decision
            if "USE_RAG" in decision:
                print(f" Overview-based routing: USE_RAG for query: '{query[:50]}...'")
                return True
            elif "DIRECT_LLM" in decision:
                print(f" Overview-based routing: DIRECT_LLM for query: '{query[:50]}...'")
                return False
            else:
                print(f" Unclear routing decision '{decision}', defaulting to RAG")
                return True  # Default to RAG when uncertain
                
        except Exception as e:
            print(f" LLM routing failed: {e}, falling back to pattern matching")
            return self._simple_pattern_routing(query, [])

    def _simple_pattern_routing(self, message: str, idx_ids: List[str]) -> bool:
        """
         FALLBACK: Simple pattern-based routing (original logic).
        """
        message_lower = message.lower()

        if _is_plain_conversational_message(message_lower):
            return False

        # Check for strong RAG indicators
        for indicator in _RAG_INDICATORS:
            if indicator in message_lower:
                return True

        # Question words + substantial length might benefit from RAG
        starts_with_question = any(message_lower.startswith(word) for word in _QUESTION_WORDS)

        if starts_with_question and len(message) > 40:
            return True

        # Very short messages - use direct LLM
        if len(message.strip()) < 20:
            return False

        # Default to Direct LLM unless there's clear indication of document query
        return False
    
    def _handle_direct_llm_query(self, session_id: str, message: str, session: dict, data: dict):
        """
        Handle query using direct Ollama client with thinking disabled for speed.
        
        Returns:
            tuple: (response_text, empty_source_docs)
        """
        try:
            # Get conversation history for context
            conversation_history = _prepare_conversation_history(
                db.get_conversation_history(session_id),
                latest_user_message=message,
            )

            # Use the session's model or default
            model = data.get('model') or session.get('model_used') or session.get('model') or 'gemma3:27b-cloud'

            # Direct Ollama call with thinking disabled for speed
            response_text = self.ollama_client.chat(
                message=message,
                model=model,
                conversation_history=conversation_history,
                enable_thinking=False  #  DISABLE THINKING FOR SPEED
            )
            
            return response_text, []  # No source docs for direct LLM
            
        except Exception as e:
            print(f" Direct LLM error: {e}")
            return f"Error processing query: {str(e)}", []
    
    def _handle_rag_query(self, session_id: str, message: str, data: dict, idx_ids: List[str]):
        """
        Handle query using the full RAG pipeline (delegates to the advanced RAG API running on port 8001).

        Returns:
            tuple[str, List[dict]]: (response_text, source_documents)
        """
        # Defaults
        response_text = ""
        source_docs: List[dict] = []

        # Build payload for RAG API
        rag_api_url = "http://localhost:8001/chat"
        table_name = f"text_pages_{idx_ids[-1]}" if idx_ids else None
        payload: Dict[str, Any] = {
            "query": message,
            "session_id": session_id,
        }
        if table_name:
            payload["table_name"] = table_name

        # Copy optional parameters from the incoming request
        optional_params: Dict[str, tuple[type, str]] = {
            "compose_sub_answers": (bool, "compose_sub_answers"),
            "query_decompose": (bool, "query_decompose"),
            "ai_rerank": (bool, "ai_rerank"),
            "context_expand": (bool, "context_expand"),
            "verify": (bool, "verify"),
            "retrieval_k": (int, "retrieval_k"),
            "context_window_size": (int, "context_window_size"),
            "reranker_top_k": (int, "reranker_top_k"),
            "search_type": (str, "search_type"),
            "dense_weight": (float, "dense_weight"),
            "provence_prune": (bool, "provence_prune"),
            "provence_threshold": (float, "provence_threshold"),
        }
        for key, (caster, payload_key) in optional_params.items():
            val = data.get(key)
            if val is not None:
                try:
                    payload[payload_key] = caster(val)  # type: ignore[arg-type]
                except Exception:
                    payload[payload_key] = val

        try:
            rag_response = requests.post(
                rag_api_url,
                json=payload,
                headers={"X-Request-ID": str(getattr(self, "request_id", _resolve_request_id(None)))},
                timeout=(10, _RAG_CHAT_TIMEOUT_SEC),
            )
            if rag_response.status_code == 200:
                rag_data = rag_response.json()
                response_text = rag_data.get("answer", "No answer found.")
                source_docs = rag_data.get("source_documents", [])
            else:
                response_text = f"Error from RAG API ({rag_response.status_code}): {rag_response.text}"
                print(f" RAG API error: {response_text}")
        except requests.exceptions.ConnectionError:
            response_text = "Could not connect to the RAG API server. Please ensure it is running."
            print(" Connection to RAG API failed (port 8001).")
        except requests.exceptions.Timeout:
            response_text = "The RAG API took too long to respond. Please retry your question."
            print(f" RAG API timed out after {_RAG_CHAT_TIMEOUT_SEC}s.")
        except Exception as e:
            response_text = f"Error processing RAG query: {str(e)}"
            print(f" RAG processing error: {e}")

        # Strip any <think>/<thinking> tags that might slip through
        response_text = re.sub(r'<(think|thinking)>.*?</\\1>', '', response_text, flags=re.DOTALL | re.IGNORECASE).strip()

        return response_text, source_docs

    def handle_delete_session(self, session_id: str):
        """Delete a session and its messages"""
        try:
            deleted = db.delete_session(session_id)
            if deleted:
                self.send_json_response({'deleted': deleted})
            else:
                self.send_json_response({'error': 'Session not found'}, status_code=404)
        except Exception as e:
            self.send_json_response({'error': str(e)}, status_code=500)
    
    def handle_file_upload(self, session_id: str):
        """Handle file uploads, save them, and associate with the session."""
        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={'REQUEST_METHOD': 'POST', 'CONTENT_TYPE': self.headers['Content-Type']}
        )

        uploaded_files = []
        if 'files' in form:
            files = form['files']
            if not isinstance(files, list):
                files = [files]
            
            upload_dir = "shared_uploads"
            os.makedirs(upload_dir, exist_ok=True)

            for file_item in files:
                if file_item.filename:
                    # Create a unique filename to avoid overwrites
                    unique_filename = f"{uuid.uuid4()}_{file_item.filename}"
                    file_path = os.path.join(upload_dir, unique_filename)
                    
                    with open(file_path, 'wb') as f:
                        f.write(file_item.file.read())
                    
                    # Store the absolute path for the indexing service
                    absolute_file_path = os.path.abspath(file_path)
                    db.add_document_to_session(session_id, absolute_file_path)
                    uploaded_files.append({"filename": file_item.filename, "stored_path": absolute_file_path})

        if not uploaded_files:
            self.send_json_response({"error": "No files were uploaded"}, status_code=400)
            return
            
        self.send_json_response({
            "message": f"Successfully uploaded {len(uploaded_files)} files.",
            "uploaded_files": uploaded_files
        })

    def handle_index_documents(self, session_id: str):
        """Triggers indexing for all documents in a session."""
        print(f" Received request to index documents for session {session_id[:8]}...")
        try:
            file_paths = db.get_documents_for_session(session_id)
            if not file_paths:
                self.send_json_response({"message": "No documents to index for this session."}, status_code=200)
                return

            print(f"Found {len(file_paths)} documents to index. Sending to RAG API...")
            
            rag_api_url = "http://localhost:8001/index"
            rag_response = requests.post(
                rag_api_url,
                json={"file_paths": file_paths, "session_id": session_id},
                headers={"X-Request-ID": str(getattr(self, "request_id", _resolve_request_id(None)))},
            )

            if rag_response.status_code == 200:
                print(" RAG API successfully indexed documents.")
                # Merge key config values into index metadata
                idx_meta = {
                    "session_linked": True,
                    "retrieval_mode": "hybrid",
                }
                try:
                    db.update_index_metadata(session_id, idx_meta)  # session_id used as index_id in text table naming
                except Exception as e:
                    print(f" Failed to update index metadata for session index: {e}")
                self.send_json_response(rag_response.json())
            else:
                error_info = rag_response.text
                print(f" RAG API indexing failed ({rag_response.status_code}): {error_info}")
                self.send_json_response({"error": f"Indexing failed: {error_info}"}, status_code=500)

        except Exception as e:
            print(f" Exception during indexing: {str(e)}")
            self.send_json_response({"error": f"An unexpected error occurred: {str(e)}"}, status_code=500)
            
    def handle_pdf_upload(self, session_id: str):
        """
        Processes PDF files: extracts text and stores it in the database.
        DEPRECATED: This is the old method. Use handle_file_upload instead.
        """
        # This function is now deprecated in favor of the new indexing workflow
        # but is kept for potential legacy/compatibility reasons.
        # For new functionality, it should not be used.
        self.send_json_response({
            "warning": "This upload method is deprecated. Use the new file upload and indexing flow.",
            "message": "No action taken."
        }, status_code=410) # 410 Gone

    def handle_get_models(self):
        """Get available models from both Ollama and HuggingFace, grouped by capability"""
        try:
            generation_models = []
            embedding_models = []
            
            # Get Ollama models if available
            if self.ollama_client.is_ollama_running():
                all_ollama_models = [m for m in self.ollama_client.list_models() if isinstance(m, str) and m.strip()]
                
                # Very naive classification - same logic as RAG API server
                ollama_embedding_models = [m for m in all_ollama_models if any(k in m for k in ['embed','bge','embedding','text'])]
                ollama_generation_models = [m for m in all_ollama_models if m not in ollama_embedding_models]
                
                generation_models.extend(ollama_generation_models)
                embedding_models.extend(ollama_embedding_models)
            
            # Add supported HuggingFace embedding models
            huggingface_embedding_models = [
                "Qwen/Qwen3-Embedding-0.6B", 
                "Qwen/Qwen3-Embedding-4B"
            ]
            embedding_models.extend(huggingface_embedding_models)
            
            # De-duplicate and sort models for consistent ordering
            generation_models = sorted(set(generation_models))
            embedding_models = sorted(set(embedding_models))
            
            self.send_json_response({
                "generation_models": generation_models,
                "embedding_models": embedding_models
            })
        except Exception as e:
            self.send_json_response({
                "error": f"Could not list models: {str(e)}"
            }, status_code=500)

    def handle_get_indexes(self):
        try:
            data = db.list_indexes()
            self.send_json_response({'indexes': data, 'total': len(data)})
        except Exception as e:
            self.send_json_response({'error': str(e)}, status_code=500)
    
    def handle_get_index(self, index_id: str):
        try:
            data = db.get_index(index_id)
            if not data:
                self.send_json_response({'error': 'Index not found'}, status_code=404)
                return
            self.send_json_response(data)
        except Exception as e:
            self.send_json_response({'error': str(e)}, status_code=500)
    
    def handle_create_index(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            name = data.get('name')
            description = data.get('description')
            metadata = data.get('metadata', {})
            
            if not name:
                self.send_json_response({'error': 'Name required'}, status_code=400)
                return
            
            # Add complete metadata from RAG system configuration if available
            if RAG_SYSTEM_AVAILABLE and PIPELINE_CONFIGS.get('default'):
                default_config = PIPELINE_CONFIGS['default']
                complete_metadata = {
                    'status': 'created',
                    'metadata_source': 'rag_system_config',
                    'created_at': json.loads(json.dumps(datetime.now().isoformat())),
                    'chunk_size': 512,  # From default config
                    'chunk_overlap': 64,  # From default config
                    'retrieval_mode': 'hybrid',  # From default config
                    'window_size': 5,  # From default config
                    'embedding_model': 'nomic-embed-text:v1.5',  # From default config
                    'enrich_model': 'gemma3:12b-cloud',  # From default config
                    'overview_model': 'gemma3:12b-cloud',  # From default config
                    'enable_enrich': True,  # From default config
                    'latechunk': True,  # From default config
                    'docling_chunk': True,  # From default config
                    'note': 'Default configuration from RAG system'
                }
                # Merge with any provided metadata
                complete_metadata.update(metadata)
                metadata = complete_metadata

            existing = db.get_index_by_name(name)
            idx_id = db.create_index(name, description, metadata)
            self.send_json_response({'index_id': idx_id, 'reused': bool(existing)}, status_code=201)
        except Exception as e:
            self.send_json_response({'error': str(e)}, status_code=500)
    
    def handle_index_file_upload(self, index_id: str):
        """Reuse file upload logic but store docs under index."""
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={'REQUEST_METHOD':'POST', 'CONTENT_TYPE': self.headers['Content-Type']})
        uploaded_files=[]
        if 'files' in form:
            files=form['files']
            if not isinstance(files, list):
                files=[files]
            upload_dir='shared_uploads'
            os.makedirs(upload_dir, exist_ok=True)
            for f in files:
                if f.filename:
                    unique=f"{uuid.uuid4()}_{f.filename}"
                    path=os.path.join(upload_dir, unique)
                    with open(path,'wb') as out: out.write(f.file.read())
                    db.add_document_to_index(index_id, f.filename, os.path.abspath(path))
                    uploaded_files.append({'filename':f.filename,'stored_path':os.path.abspath(path)})
        if not uploaded_files:
            self.send_json_response({'error':'No files uploaded'}, status_code=400); return
        self.send_json_response({'message':f"Uploaded {len(uploaded_files)} files","uploaded_files":uploaded_files})
    
    def handle_build_index(self, index_id: str):
        try:
            index=db.get_index(index_id)
            if not index:
                self.send_json_response({'error':'Index not found'}, status_code=404); return
            file_paths=[d['stored_path'] for d in index.get('documents',[])]
            if not file_paths:
                self.send_json_response({'error':'No documents to index'}, status_code=400); return

            # Parse request body for optional flags and configuration
            latechunk = False
            docling_chunk = False
            chunk_size = 512
            chunk_overlap = 64
            retrieval_mode = 'hybrid'
            window_size = 2
            enable_enrich = True
            embedding_model = None
            enrich_model = None
            batch_size_embed = 50
            batch_size_enrich = 25
            overview_model = None
            resume_build = True
            force_rebuild = False
            
            if 'Content-Length' in self.headers and int(self.headers['Content-Length']) > 0:
                try:
                    length = int(self.headers['Content-Length'])
                    body = self.rfile.read(length)
                    opts = json.loads(body.decode('utf-8'))
                    latechunk = bool(opts.get('latechunk', False))
                    docling_chunk = bool(opts.get('doclingChunk', False))
                    chunk_size = int(opts.get('chunkSize', 512))
                    chunk_overlap = int(opts.get('chunkOverlap', 64))
                    retrieval_mode = str(opts.get('retrievalMode', 'hybrid'))
                    window_size = int(opts.get('windowSize', 2))
                    enable_enrich = bool(opts.get('enableEnrich', True))
                    embedding_model = opts.get('embeddingModel')
                    enrich_model = opts.get('enrichModel')
                    batch_size_embed = int(opts.get('batchSizeEmbed', 50))
                    batch_size_enrich = int(opts.get('batchSizeEnrich', 25))
                    overview_model = opts.get('overviewModel')
                    resume_build = bool(opts.get('resume', True))
                    force_rebuild = bool(opts.get('forceRebuild', False))
                except Exception:
                    # Keep defaults on parse error
                    pass

            existing_metadata = index.get("metadata") or {}
            completed_files = list(existing_metadata.get("completed_files") or [])
            failed_files = list(existing_metadata.get("failed_files") or [])

            if force_rebuild or not resume_build:
                completed_files = []
                failed_files = []

            pending_paths = _get_pending_file_paths(file_paths, completed_files)

            if not pending_paths:
                db.update_index_metadata(index_id, {
                    "status": "functional",
                    "indexing_stage": "done",
                    "indexing_progress": 100.0,
                    "pending_files": 0,
                    "completed_files": file_paths,
                    "failed_files": failed_files,
                    "build_error": None,
                })
                self.send_json_response({
                    "message": "Index already up to date.",
                    "index_id": index_id,
                    "status": "functional",
                    "pending_files": 0,
                }, status_code=200)
                return

            table_name = index.get("vector_table_name")
            with _INDEX_BUILD_LOCK:
                if index_id in _ACTIVE_INDEX_BUILDS or (index.get("metadata") or {}).get("status") == "building":
                    self.send_json_response({
                        "message": "Index build already in progress.",
                        "index_id": index_id,
                        "status": "building",
                    }, status_code=202)
                    return
                _ACTIVE_INDEX_BUILDS.add(index_id)

            db.update_index_metadata(index_id, {
                "status": "building",
                "indexing_stage": "queued",
                "indexing_progress": 0.0,
                "indexing_details": {
                    "files_total": len(file_paths),
                    "files_completed": len(completed_files),
                    "files_remaining": len(pending_paths),
                    "table_name": table_name,
                },
                "completed_files": completed_files,
                "failed_files": failed_files,
                "pending_files": len(pending_paths),
                "build_error": None,
                "build_traceback": None,
                "build_started_at": datetime.now().isoformat(),
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
                "retrieval_mode": retrieval_mode,
                "window_size": window_size,
                "enable_enrich": enable_enrich,
                "latechunk": latechunk,
                "docling_chunk": docling_chunk,
                "batch_size_embed": batch_size_embed,
                "batch_size_enrich": batch_size_enrich,
                **({"embedding_model": embedding_model} if embedding_model else {}),
                **({"enrich_model": enrich_model} if enrich_model else {}),
                **({"overview_model": overview_model} if overview_model else {}),
            })

            worker = threading.Thread(
                target=_run_index_build_job,
                args=(
                    index_id,
                    file_paths,
                    table_name,
                    {
                        "latechunk": latechunk,
                        "docling_chunk": docling_chunk,
                        "chunk_size": chunk_size,
                        "chunk_overlap": chunk_overlap,
                        "retrieval_mode": retrieval_mode,
                        "window_size": window_size,
                        "enable_enrich": enable_enrich,
                        "embedding_model": embedding_model,
                        "enrich_model": enrich_model,
                        "overview_model": overview_model,
                        "batch_size_embed": batch_size_embed,
                        "batch_size_enrich": batch_size_enrich,
                        "request_id": getattr(self, "request_id", _resolve_request_id(None)),
                        "completed_files": completed_files,
                        "failed_files": failed_files,
                    },
                ),
                daemon=True,
                name=f"index-build-{index_id[:8]}",
            )
            worker.start()

            self.send_json_response({
                "message": "Index build started.",
                "index_id": index_id,
                "status": "building",
                "pending_files": len(pending_paths),
                "completed_files": len(completed_files),
            }, status_code=202)
        except Exception as e:
            with _INDEX_BUILD_LOCK:
                _ACTIVE_INDEX_BUILDS.discard(index_id)
            self.send_json_response({'error':str(e)}, status_code=500)
    
    def handle_link_index_to_session(self, session_id: str, index_id: str):
        try:
            db.link_index_to_session(session_id, index_id)
            self.send_json_response({'message':'Index linked to session'})
        except Exception as e:
            self.send_json_response({'error':str(e)}, status_code=500)

    def handle_get_session_indexes(self, session_id: str):
        try:
            idx_ids = db.get_indexes_for_session(session_id)
            indexes = []
            for idx_id in idx_ids:
                idx = db.get_index(idx_id)
                if idx:
                    # Try to populate metadata for older indexes that have empty metadata
                    if not idx.get('metadata') or len(idx['metadata']) == 0:
                        print(f" Attempting to infer metadata for index {idx_id[:8]}...")
                        inferred_metadata = db.inspect_and_populate_index_metadata(idx_id)
                        if inferred_metadata:
                            # Refresh the index data with the new metadata
                            idx = db.get_index(idx_id)
                    indexes.append(idx)
            self.send_json_response({'indexes': indexes, 'total': len(indexes)})
        except Exception as e:
            self.send_json_response({'error': str(e)}, status_code=500)

    def handle_delete_index(self, index_id: str):
        """Remove an index, its documents, links, and the underlying LanceDB table."""
        try:
            deleted = db.delete_index(index_id)
            if deleted:
                self.send_json_response({'message': 'Index deleted successfully', 'index_id': index_id})
            else:
                self.send_json_response({'error': 'Index not found'}, status_code=404)
        except Exception as e:
            self.send_json_response({'error': str(e)}, status_code=500)

    def handle_rename_session(self, session_id: str):
        """Rename an existing session title"""
        try:
            session = db.get_session(session_id)
            if not session:
                self.send_json_response({"error": "Session not found"}, status_code=404)
                return

            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_json_response({"error": "Request body required"}, status_code=400)
                return

            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            new_title: str = data.get('title', '').strip()

            if not new_title:
                self.send_json_response({"error": "Title cannot be empty"}, status_code=400)
                return

            db.update_session_title(session_id, new_title)
            updated_session = db.get_session(session_id)

            self.send_json_response({
                "message": "Session renamed successfully",
                "session": updated_session
            })

        except json.JSONDecodeError:
            self.send_json_response({"error": "Invalid JSON"}, status_code=400)
        except Exception as e:
            self.send_json_response({"error": f"Failed to rename session: {str(e)}"}, status_code=500)

    def send_json_response(self, data, status_code: int = 200):
        """Send a JSON (UTF-8) response with CORS headers. Safe against client disconnects."""
        try:
            response_data = data
            if status_code >= 400:
                if isinstance(data, dict):
                    error_message = data.get("error")
                    if isinstance(error_message, dict):
                        error_message = error_message.get("message", "Request failed")
                    elif error_message is None:
                        error_message = data.get("message", "Request failed")

                    response_data = {
                        "success": False,
                        "error": str(error_message),
                        "error_code": data.get("error_code") or self._default_error_code(status_code),
                    }
                    if "details" in data:
                        response_data["details"] = data["details"]
                else:
                    response_data = {
                        "success": False,
                        "error": "Request failed",
                        "error_code": self._default_error_code(status_code),
                    }

            self.send_response(status_code)
            self.send_header('X-Request-ID', str(getattr(self, "request_id", _resolve_request_id(None))))
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
            self.send_header('Access-Control-Allow-Credentials', 'true')
            self.end_headers()
        
            response_bytes = json.dumps(response_data, indent=2).encode('utf-8')
            self.wfile.write(response_bytes)
            duration_ms = int((time.time() - getattr(self, "request_started_at", time.time())) * 1000)
            LOGGER.info(
                "request_finished request_id=%s method=%s path=%s status=%s duration_ms=%s",
                getattr(self, "request_id", "n/a"),
                getattr(self, "command", "unknown"),
                self.path,
                status_code,
                duration_ms,
            )
            path = urlparse(self.path).path
            BACKEND_METRICS.record_request(
                method=getattr(self, "command", "UNKNOWN"),
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
            )
        except BrokenPipeError:
            # Client disconnected before we could finish sending
            LOGGER.warning("Client disconnected during response request_id=%s", getattr(self, "request_id", "n/a"))
        except Exception as e:
            LOGGER.error("Error sending response request_id=%s error=%s", getattr(self, "request_id", "n/a"), e)

    def _backend_ready(self) -> bool:
        try:
            stats = db.get_stats()
            if not isinstance(stats, dict):
                return False
            return self.ollama_client.is_ollama_running()
        except Exception:
            return False

    def send_error_response(self, message: str, status_code: int = 400, error_code=None, details=None):
        payload = {
            "error": message,
            "error_code": error_code or self._default_error_code(status_code),
        }
        if details is not None:
            payload["details"] = details
        self.send_json_response(payload, status_code=status_code)

    def _default_error_code(self, status_code: int) -> str:
        if status_code == 400:
            return "bad_request"
        if status_code == 401:
            return "unauthorized"
        if status_code == 403:
            return "forbidden"
        if status_code == 404:
            return "not_found"
        if status_code == 409:
            return "conflict"
        if status_code >= 500:
            return "internal_error"
        return "request_error"
    
    def log_message(self, format, *args):
        """Custom log format"""
        LOGGER.info(
            "http_access request_id=%s client=%s message=%s",
            getattr(self, "request_id", "n/a"),
            getattr(self, "client_address", ("unknown",))[0],
            format % args,
        )

def main():
    """Main function to initialize and start the server"""
    try:
        PORT = int(os.getenv("BACKEND_PORT", "8000"))
    except ValueError:
        print(" Invalid BACKEND_PORT value, falling back to 8000")
        PORT = 8000
    try:
        # Initialize the database
        print(" Database initialized successfully")

        # Initialize the PDF processor
        try:
            pdf_module.initialize_simple_pdf_processor()
            print(" Initializing simple PDF processing...")
            if pdf_module.simple_pdf_processor:
                print(" Simple PDF processor initialized")
            else:
                print(" PDF processing could not be initialized.")
        except Exception as e:
            print(f" Error initializing PDF processor: {e}")
            print(" PDF processing disabled - server will run without RAG functionality")

        # Set a global reference to the initialized processor if needed elsewhere
        global pdf_processor
        pdf_processor = pdf_module.simple_pdf_processor
        if pdf_processor:
            print(" Global PDF processor initialized")
        else:
            print(" PDF processing disabled - server will run without RAG functionality")
        
        # Cleanup empty sessions on startup
        print(" Cleaning up empty sessions...")
        cleanup_count = db.cleanup_empty_sessions()
        if cleanup_count > 0:
            print(f" Cleaned up {cleanup_count} empty sessions")
        else:
            print(" No empty sessions to clean up")

        # Start the server
        with ReusableTCPServer(("", PORT), ChatHandler) as httpd:
            print(f" Starting backend server on port {PORT}")
            print(f" Chat endpoint: http://localhost:{PORT}/chat")
            print(f" Health check: http://localhost:{PORT}/health")
            
            # Test Ollama connection
            client = OllamaClient()
            if client.is_ollama_running():
                models = client.list_models()
                print(f" Ollama is running with {len(models)} models")
                print(f" Available models: {', '.join(models[:3])}{'...' if len(models) > 3 else ''}")
            else:
                print("  Ollama is not running. Please start Ollama:")
                print("   Install: https://ollama.ai")
                print("   Run: ollama serve")
            
            print(f"\n Frontend should connect to: http://localhost:{PORT}")
            print(" Ready to chat!\n")
            
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n Server stopped")

if __name__ == "__main__":
    main() 