const API_BASE_URL = 'http://localhost:8000';

//  Simple UUID generator for client-side message IDs
export const generateUUID = () => {
  if (typeof window !== 'undefined' && window.crypto && window.crypto.randomUUID) {
    return window.crypto.randomUUID();
  }
  // Fallback for older browsers or non-secure contexts
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
};

export interface Step {
  key: string;
  label: string;
  status: 'pending' | 'active' | 'done';
  details: unknown;
}

export interface ChatMessage {
  id: string;
  content: string | Array<Record<string, unknown>> | { steps: Step[] };
  sender: 'user' | 'assistant';
  timestamp: string;
  isLoading?: boolean;
  metadata?: Record<string, unknown>;
}

export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  model_used: string;
  message_count: number;
}

export interface ChatRequest {
  message: string;
  model?: string;
  conversation_history?: Array<{
    role: 'user' | 'assistant';
    content: string;
  }>;
}

export interface ChatResponse {
  response: string;
  model: string;
  message_count: number;
}

export interface HealthResponse {
  status: string;
  ollama_running: boolean;
  available_models: string[];
  database_stats?: {
    total_sessions: number;
    total_messages: number;
    most_used_model: string | null;
  };
}

export interface ModelsResponse {
  generation_models: string[];
  embedding_models: string[];
}

export interface SessionResponse {
  sessions: ChatSession[];
  total: number;
}

export interface SessionChatResponse {
  response: string;
  session: ChatSession;
  user_message_id: string;
  ai_message_id: string;
}

export interface IndexDocument {
  filename?: string;
  [key: string]: unknown;
}

export interface IndexSummary {
  id?: string;
  index_id?: string;
  name: string;
  title?: string;
  status?: string;
  created_at?: string;
  updated_at?: string;
  documents?: IndexDocument[];
  metadata?: Record<string, unknown>;
  session?: ChatSession;
  model_used?: string;
  [key: string]: unknown;
}

export interface IndexBuildResponse {
  message: string;
  index_id?: string;
  status?: string;
}

export interface IndexListResponse {
  indexes: IndexSummary[];
  total: number;
}

type StreamEvent = {
  type: string;
  data: Record<string, unknown>;
};

type ErrorContext = 'chat' | 'upload' | 'index' | 'stream' | 'generic';

export class ApiServiceError extends Error {
  status?: number;
  errorCode?: string;
  context: ErrorContext;
  userMessage: string;

  constructor(params: {
    message: string;
    context: ErrorContext;
    status?: number;
    errorCode?: string;
    userMessage: string;
  }) {
    super(params.message);
    this.name = 'ApiServiceError';
    this.status = params.status;
    this.errorCode = params.errorCode;
    this.context = params.context;
    this.userMessage = params.userMessage;
  }
}

class ChatAPI {
  private inFlightGetRequests = new Map<string, Promise<unknown>>();
  private getResponseCache = new Map<string, { expiresAt: number; value: unknown }>();

  private buildActionableMessage(context: ErrorContext, status?: number, errorCode?: string, serverMessage?: string): string {
    const normalizedMessage = String(serverMessage || '').toLowerCase();
    const normalizedCode = String(errorCode || '').toLowerCase();

    if (
      normalizedMessage.includes('failed to fetch') ||
      normalizedMessage.includes('networkerror') ||
      normalizedMessage.includes('network error') ||
      normalizedMessage.includes('econnreset') ||
      normalizedMessage.includes('connection reset') ||
      normalizedMessage.includes('forcibly closed')
    ) {
      return 'Connection issue detected. Verify the backend is running (`python run_system.py`), then retry.';
    }

    if (normalizedMessage.includes('ollama is not running') || normalizedCode === 'service_unavailable') {
      return 'Model service is unavailable. Start Ollama, wait for readiness, then retry your request.';
    }

    if (status === 413 || normalizedMessage.includes('exceeds 50mb')) {
      return 'Upload is too large. Reduce total file size below 50MB and upload again.';
    }

    if (normalizedMessage.includes('no files were uploaded') || normalizedMessage.includes('no files uploaded')) {
      return 'No files were detected. Attach one or more supported files and retry upload.';
    }

    if (normalizedMessage.includes('no documents to index')) {
      return 'No uploaded documents found. Upload files first, then run indexing.';
    }

    if (normalizedMessage.includes('session not found')) {
      return 'This chat session is no longer available. Refresh and create or select another session.';
    }

    if (normalizedCode === 'invalid_json' || normalizedCode === 'invalid_request' || normalizedCode === 'validation_error' || status === 400) {
      if (context === 'upload') {
        return 'Upload request was invalid. Check selected files and try again.';
      }
      if (context === 'chat' || context === 'stream') {
        return 'Message request was invalid. Edit your prompt/settings and try again.';
      }
      return 'Request was invalid. Review inputs and retry.';
    }

    if (status === 404) {
      return 'Requested resource was not found. Refresh the page and retry.';
    }

    if (status === 503) {
      return 'Service is temporarily unavailable. Wait a moment and retry.';
    }

    if (context === 'upload') {
      return 'Upload failed. Check file format/size and retry.';
    }
    if (context === 'chat' || context === 'stream') {
      return 'Message failed. Retry, and if this persists, verify backend and model services are healthy.';
    }
    if (context === 'index') {
      return 'Indexing failed. Verify uploaded documents and service health, then retry.';
    }
    return 'Request failed. Please retry.';
  }

  private async createApiError(response: Response, context: ErrorContext, fallbackPrefix: string): Promise<ApiServiceError> {
    const payload = await response.json().catch(() => ({} as Record<string, unknown>));
    const serverError = typeof payload.error === 'string' ? payload.error : response.statusText || 'Unknown error';
    const errorCode = typeof payload.error_code === 'string' ? payload.error_code : undefined;
    const message = `${fallbackPrefix}: ${serverError}`;
    const userMessage = this.buildActionableMessage(context, response.status, errorCode, serverError);

    return new ApiServiceError({
      message,
      context,
      status: response.status,
      errorCode,
      userMessage,
    });
  }

  private toApiError(error: unknown, context: ErrorContext, fallbackPrefix: string): ApiServiceError {
    if (error instanceof ApiServiceError) {
      return error;
    }

    const rawMessage = error instanceof Error ? error.message : String(error);
    return new ApiServiceError({
      message: `${fallbackPrefix}: ${rawMessage}`,
      context,
      userMessage: this.buildActionableMessage(context, undefined, undefined, rawMessage),
    });
  }

  public getActionableErrorMessage(error: unknown, context: ErrorContext = 'generic'): string {
    if (error instanceof ApiServiceError && error.userMessage) {
      return error.userMessage;
    }
    return this.toApiError(error, context, 'Request failed').userMessage;
  }

  private async getJson<T>(
    url: string,
    options: {
      cacheTtlMs?: number;
      cacheKey?: string;
      errorMessage?: string;
    } = {},
  ): Promise<T> {
    const { cacheTtlMs = 0, cacheKey = url, errorMessage = 'Request failed' } = options;
    const now = Date.now();

    if (cacheTtlMs > 0) {
      const cached = this.getResponseCache.get(cacheKey);
      if (cached && cached.expiresAt > now) {
        return cached.value as T;
      }
    }

    const inFlight = this.inFlightGetRequests.get(cacheKey);
    if (inFlight) {
      return inFlight as Promise<T>;
    }

    const requestPromise = (async () => {
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`${errorMessage}: ${response.status}`);
      }

      const payload = await response.json();

      if (cacheTtlMs > 0) {
        this.getResponseCache.set(cacheKey, {
          expiresAt: Date.now() + cacheTtlMs,
          value: payload,
        });
      }

      return payload as T;
    })();

    this.inFlightGetRequests.set(cacheKey, requestPromise as Promise<unknown>);

    try {
      return await requestPromise;
    } finally {
      if (this.inFlightGetRequests.get(cacheKey) === requestPromise) {
        this.inFlightGetRequests.delete(cacheKey);
      }
    }
  }

  private invalidateGetCache(match: string | RegExp): void {
    for (const key of this.getResponseCache.keys()) {
      const matched = typeof match === 'string' ? key.includes(match) : match.test(key);
      if (matched) {
        this.getResponseCache.delete(key);
      }
    }
  }

  private normalizeIndexListResponse(payload: unknown): IndexListResponse {
    const rawIndexes = Array.isArray(payload)
      ? payload
      : Array.isArray((payload as { indexes?: unknown[] })?.indexes)
        ? (payload as { indexes: unknown[] }).indexes
        : [];

    const indexes: IndexSummary[] = rawIndexes
      .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
      .map((item) => {
        const rawId = item.id ?? item.index_id;
        const rawName = item.name ?? item.title;
        const normalizedId = typeof rawId === 'string' ? rawId : undefined;
        const normalizedName =
          typeof rawName === 'string' && rawName.trim().length > 0
            ? rawName
            : normalizedId ?? 'Untitled index';

        return {
          ...item,
          ...(normalizedId ? { id: normalizedId, index_id: normalizedId } : {}),
          name: normalizedName,
        } as IndexSummary;
      });

    const rawTotal = !Array.isArray(payload) && typeof payload === 'object'
      ? (payload as { total?: unknown }).total
      : undefined;
    const total = typeof rawTotal === 'number' ? rawTotal : indexes.length;

    return { indexes, total };
  }

  async checkHealth(): Promise<HealthResponse> {
    try {
      return await this.getJson<HealthResponse>(`${API_BASE_URL}/health`, {
        cacheTtlMs: 3000,
        errorMessage: 'Health check failed',
      });
    } catch (error) {
      console.error('Health check failed:', error);
      throw error;
    }
  }

  async sendMessage(request: ChatRequest): Promise<ChatResponse> {
    try {
      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: request.message,
          model: request.model || 'gemma3:12b-cloud',
          conversation_history: request.conversation_history || [],
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
        throw new Error(`Chat API error: ${errorData.error || response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.error('Chat API failed:', error);
      throw error;
    }
  }

  // Convert ChatMessage array to conversation history format
  messagesToHistory(messages: ChatMessage[]): Array<{ role: 'user' | 'assistant'; content: string }> {
    return messages
      .filter(msg => typeof msg.content === 'string' && msg.content.trim())
      .map(msg => ({
        role: msg.sender,
        content: msg.content as string,
      }));
  }

  // Session Management
  async getSessions(): Promise<SessionResponse> {
    try {
      return await this.getJson<SessionResponse>(`${API_BASE_URL}/sessions`, {
        cacheTtlMs: 1500,
        errorMessage: 'Failed to get sessions',
      });
    } catch (error) {
      console.error('Get sessions failed:', error);
      throw error;
    }
  }

  async createSession(title: string = 'New Chat', model: string = 'gemma3:12b-cloud'): Promise<ChatSession> {
    try {
      const response = await fetch(`${API_BASE_URL}/sessions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ title, model }),
      });

      if (!response.ok) {
        throw new Error(`Failed to create session: ${response.status}`);
      }

      const data = await response.json();
      this.invalidateGetCache('/sessions');
      return data.session;
    } catch (error) {
      console.error('Create session failed:', error);
      throw error;
    }
  }

  async getSession(sessionId: string): Promise<{ session: ChatSession; messages: ChatMessage[] }> {
    try {
      return await this.getJson<{ session: ChatSession; messages: ChatMessage[] }>(`${API_BASE_URL}/sessions/${sessionId}`, {
        cacheTtlMs: 700,
        errorMessage: 'Failed to get session',
      });
    } catch (error) {
      console.error('Get session failed:', error);
      throw error;
    }
  }

  async sendSessionMessage(
    sessionId: string,
    message: string,
    opts: { 
      model?: string; 
      composeSubAnswers?: boolean; 
      decompose?: boolean; 
      aiRerank?: boolean; 
      contextExpand?: boolean; 
      verify?: boolean;
      //  NEW RETRIEVAL PARAMETERS
      retrievalK?: number;
      contextWindowSize?: number;
      rerankerTopK?: number;
      searchType?: string;
      denseWeight?: number;
      forceRag?: boolean;
      provencePrune?: boolean;
    } = {}
  ): Promise<SessionChatResponse & { source_documents: unknown[] }> {
    try {
      const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}/messages`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message,
          ...(opts.model && { model: opts.model }),
          ...(typeof opts.composeSubAnswers === 'boolean' && { compose_sub_answers: opts.composeSubAnswers }),
          ...(typeof opts.decompose === 'boolean' && { query_decompose: opts.decompose }),
          ...(typeof opts.aiRerank === 'boolean' && { ai_rerank: opts.aiRerank }),
          ...(typeof opts.contextExpand === 'boolean' && { context_expand: opts.contextExpand }),
          ...(typeof opts.verify === 'boolean' && { verify: opts.verify }),
          //  ADD NEW RETRIEVAL PARAMETERS
          ...(typeof opts.retrievalK === 'number' && { retrieval_k: opts.retrievalK }),
          ...(typeof opts.contextWindowSize === 'number' && { context_window_size: opts.contextWindowSize }),
          ...(typeof opts.rerankerTopK === 'number' && { reranker_top_k: opts.rerankerTopK }),
          ...(typeof opts.searchType === 'string' && { search_type: opts.searchType }),
          ...(typeof opts.denseWeight === 'number' && { dense_weight: opts.denseWeight }),
          ...(typeof opts.forceRag === 'boolean' && { force_rag: opts.forceRag }),
          ...(typeof opts.provencePrune === 'boolean' && { provence_prune: opts.provencePrune }),
        }),
      });

      if (!response.ok) {
        throw await this.createApiError(response, 'chat', 'Session chat error');
      }
      const payload = await response.json();
      this.invalidateGetCache('/sessions');
      this.invalidateGetCache(`/sessions/${sessionId}`);
      return payload;
    } catch (error) {
      console.error('Session chat failed:', error);
      throw this.toApiError(error, 'chat', 'Session chat error');
    }
  }

  async deleteSession(sessionId: string): Promise<{ message: string; deleted_session_id: string }> {
    try {
      const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
        throw new Error(`Delete session error: ${errorData.error || response.statusText}`);
      }
      const payload = await response.json();
      this.invalidateGetCache('/sessions');
      this.invalidateGetCache(`/sessions/${sessionId}`);
      return payload;
    } catch (error) {
      console.error('Delete session failed:', error);
      throw error;
    }
  }

  async renameSession(sessionId: string, newTitle: string): Promise<{ message: string; session: ChatSession }> {
    try {
      const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}/rename`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ title: newTitle }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
        throw new Error(`Rename session error: ${errorData.error || response.statusText}`);
      }
      const payload = await response.json();
      this.invalidateGetCache('/sessions');
      this.invalidateGetCache(`/sessions/${sessionId}`);
      return payload;
    } catch (error) {
      console.error('Rename session failed:', error);
      throw error;
    }
  }

  async cleanupEmptySessions(): Promise<{ message: string; cleanup_count: number }> {
    try {
      const response = await fetch(`${API_BASE_URL}/sessions/cleanup`);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
        throw new Error(`Cleanup sessions error: ${errorData.error || response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.error('Cleanup sessions failed:', error);
      throw error;
    }
  }

  async uploadFiles(sessionId: string, files: File[]): Promise<{ 
    message: string; 
    uploaded_files: {filename: string, stored_path: string}[]; 
  }> {
    try {
      const formData = new FormData();
      files.forEach((file) => {
        formData.append('files', file, file.name);
      });

      const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}/upload`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw await this.createApiError(response, 'upload', 'Upload error');
      }
      return await response.json();
    } catch (error) {
      console.error('File upload failed:', error);
      throw this.toApiError(error, 'upload', 'Upload error');
    }
  }

  async indexDocuments(sessionId: string): Promise<{ message: string }> {
    try {
      const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}/index`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw await this.createApiError(response, 'index', 'Indexing error');
      }
      return await response.json();
    } catch (error) {
      console.error('Indexing failed:', error);
      throw this.toApiError(error, 'index', 'Indexing error');
    }
  }

  // Legacy upload function - can be removed if no longer needed
  async uploadPDFs(sessionId: string, files: File[]): Promise<{ 
    message: string; 
    uploaded_files: unknown[]; 
    processing_results: unknown[];
    session_documents: unknown[];
    total_session_documents: number;
  }> {
    try {
      // Test if files have content and show size info
      let totalSize = 0;
      for (const file of files) {
        if (file.size === 0) {
          throw new Error(`File ${file.name} is empty (0 bytes)`);
        }
        totalSize += file.size;
        const sizeMB = (file.size / (1024 * 1024)).toFixed(2);
        console.log(` File ${file.name}: ${sizeMB}MB (${file.size} bytes), type: ${file.type}`);
      }
      
      const totalSizeMB = (totalSize / (1024 * 1024)).toFixed(2);
      console.log(` Total upload size: ${totalSizeMB}MB`);
      
      if (totalSize > 50 * 1024 * 1024) { // 50MB limit
        throw new Error(`Total file size ${totalSizeMB}MB exceeds 50MB limit`);
      }
      
      const formData = new FormData();
      
      // Use a generic field name 'file' that the backend expects
      let i = 0;
      for (const file of files) {
        formData.append(`file_${i}`, file, file.name);
        i++;
      }
      
      const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}/upload`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
        throw new Error(`Upload error: ${errorData.error || response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.error('PDF upload failed:', error);
      throw error;
    }
  }

  // Convert database message format to ChatMessage format
  convertDbMessage(dbMessage: Record<string, unknown>): ChatMessage {
    return {
      id: dbMessage.id as string,
      content: dbMessage.content as string,
      sender: dbMessage.sender as 'user' | 'assistant',
      timestamp: dbMessage.timestamp as string,
      metadata: dbMessage.metadata as Record<string, unknown> | undefined,
    };
  }

  // Create a new ChatMessage with UUID (for loading states)
  createMessage(
    content: string, 
    sender: 'user' | 'assistant', 
    isLoading = false
  ): ChatMessage {
    return {
      id: generateUUID(),
      content,
      sender,
      timestamp: new Date().toISOString(),
      isLoading,
    };
  }

  // ---------------- Models ----------------
  async getModels(): Promise<ModelsResponse> {
    return this.getJson<ModelsResponse>(`${API_BASE_URL}/models`, {
      cacheTtlMs: 30000,
      errorMessage: 'Failed to fetch models list',
    });
  }

  async getSessionDocuments(sessionId: string): Promise<{ files: string[]; file_count: number; session: ChatSession }> {
    return this.getJson<{ files: string[]; file_count: number; session: ChatSession }>(`${API_BASE_URL}/sessions/${sessionId}/documents`, {
      cacheTtlMs: 1500,
      errorMessage: 'Failed to fetch session documents',
    });
  }

  // ---------- Index endpoints ----------

  async createIndex(name: string, description?: string, metadata: Record<string, unknown> = {}): Promise<{ index_id: string; reused?: boolean }> {
    const resp = await fetch(`${API_BASE_URL}/indexes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, description, metadata }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(`Create index error: ${err.error || resp.statusText}`);
    }
    const payload = await resp.json();
    this.invalidateGetCache('/indexes');
    return payload;
  }

  async uploadFilesToIndex(indexId: string, files: File[]): Promise<{ message: string; uploaded_files: unknown[] }> {
    const fd = new FormData();
    files.forEach((f) => fd.append('files', f, f.name));
    const resp = await fetch(`${API_BASE_URL}/indexes/${indexId}/upload`, { method: 'POST', body: fd });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(`Upload to index error: ${err.error || resp.statusText}`);
    }
    const payload = await resp.json();
    this.invalidateGetCache(`/indexes/${indexId}`);
    this.invalidateGetCache('/indexes');
    return payload;
  }

  async getIndex(indexId: string): Promise<IndexSummary> {
    return this.getJson<IndexSummary>(`${API_BASE_URL}/indexes/${indexId}`, {
      cacheTtlMs: 1200,
      errorMessage: 'Get index error',
    });
  }

  async buildIndex(indexId: string, opts: { 
    latechunk?: boolean; 
    doclingChunk?: boolean;
    chunkSize?: number;
    chunkOverlap?: number;
    retrievalMode?: string;
    windowSize?: number;
    enableEnrich?: boolean;
    embeddingModel?: string;
    enrichModel?: string;
    overviewModel?: string;
    batchSizeEmbed?: number;
    batchSizeEnrich?: number;
  } = {}): Promise<IndexBuildResponse> {
    try {
      const requestBody = JSON.stringify({ 
        latechunk: opts.latechunk ?? false,
        doclingChunk: opts.doclingChunk ?? false,
        chunkSize: opts.chunkSize ?? 512,
        chunkOverlap: opts.chunkOverlap ?? 64,
        retrievalMode: opts.retrievalMode ?? 'hybrid',
        windowSize: opts.windowSize ?? 2,
        enableEnrich: opts.enableEnrich ?? true,
        embeddingModel: opts.embeddingModel,
        enrichModel: opts.enrichModel,
        overviewModel: opts.overviewModel,
        batchSizeEmbed: opts.batchSizeEmbed ?? 50,
        batchSizeEnrich: opts.batchSizeEnrich ?? 25,
      });

      const isTransientError = (msg: string) =>
        /Connection aborted|ConnectionResetError|forcibly closed by the remote host|ECONNRESET|Failed to fetch|NetworkError/i.test(msg);

      const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

      const pollBuildStatus = async (): Promise<IndexBuildResponse> => {
        const startedAt = Date.now();
        const timeoutMs = 45 * 60 * 1000;

        while (Date.now() - startedAt < timeoutMs) {
          const index = await this.getIndex(indexId);
          const metadata = (index.metadata ?? {}) as Record<string, unknown>;
          const status = String(metadata.status ?? 'unknown');

          if (status === 'functional' || status === 'ready' || status === 'completed') {
            return { message: 'Index build completed.', index_id: indexId, status };
          }

          if (status === 'failed') {
            const errorText = String(metadata.build_error ?? 'Unknown indexing failure');
            throw new Error(`Build index error: ${errorText}`);
          }

          await wait(status === 'building' ? 2500 : 1200);
        }

        throw new Error('Build index error: polling timed out');
      };

      for (let attempt = 1; attempt <= 2; attempt += 1) {
        let response: Response;
        try {
          response = await fetch(`${API_BASE_URL}/indexes/${indexId}/build`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: requestBody,
          });
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          if (attempt < 2 && isTransientError(message)) {
            await wait(1200);
            continue;
          }
          throw error;
        }

        if (response.ok) {
          const payload = await response.json().catch(() => ({} as IndexBuildResponse));
          if (response.status === 202 || payload.status === 'building') {
            return await pollBuildStatus();
          }
          return payload;
        }

        const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
        const message = String(errorData.error || response.statusText || 'Unknown error');
        if (attempt < 2 && isTransientError(message)) {
          await new Promise((resolve) => setTimeout(resolve, 1200));
          continue;
        }

        throw new Error(`Build index error: ${message}`);
      }

      throw new Error('Build index error: transient retry attempts exhausted');
    } catch (error) {
      console.error('Build index failed:', error);
      throw error;
    } finally {
      this.invalidateGetCache(`/indexes/${indexId}`);
      this.invalidateGetCache('/indexes');
    }
  }

  async linkIndexToSession(sessionId: string, indexId: string): Promise<{ message: string }> {
    const resp = await fetch(`${API_BASE_URL}/sessions/${sessionId}/indexes/${indexId}`, { method: 'POST' });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(`Link index error: ${err.error || resp.statusText}`);
    }
    const payload = await resp.json();
    this.invalidateGetCache(`/sessions/${sessionId}`);
    this.invalidateGetCache(`/sessions/${sessionId}/indexes`);
    this.invalidateGetCache('/sessions');
    return payload;
  }

  async listIndexes(): Promise<IndexListResponse> {
    const payload = await this.getJson<unknown>(`${API_BASE_URL}/indexes`, {
      cacheTtlMs: 2500,
      errorMessage: 'Failed to list indexes',
    });
    return this.normalizeIndexListResponse(payload);
  }

  async getSessionIndexes(sessionId: string): Promise<IndexListResponse> {
    const payload = await this.getJson<unknown>(`${API_BASE_URL}/sessions/${sessionId}/indexes`, {
      cacheTtlMs: 1200,
      errorMessage: 'Failed to get session indexes',
    });
    return this.normalizeIndexListResponse(payload);
  }

  async deleteIndex(indexId: string): Promise<{ message: string }> {
    const resp = await fetch(`${API_BASE_URL}/indexes/${indexId}`, {
      method: 'DELETE',
    });
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({ error: 'Unknown error'}));
      throw new Error(data.error || `Failed to delete index: ${resp.status}`);
    }
    const payload = await resp.json();
    this.invalidateGetCache(`/indexes/${indexId}`);
    this.invalidateGetCache('/indexes');
    this.invalidateGetCache('/sessions');
    return payload;
  }

  // -------------------- Streaming (SSE-over-fetch) --------------------
  async streamSessionMessage(
    params: {
      query: string;
      model?: string;
      session_id?: string;
      table_name?: string;
      composeSubAnswers?: boolean;
      decompose?: boolean;
      aiRerank?: boolean;
      contextExpand?: boolean;
      verify?: boolean;
      //  NEW RETRIEVAL PARAMETERS
      retrievalK?: number;
      contextWindowSize?: number;
      rerankerTopK?: number;
      searchType?: string;
      denseWeight?: number;
      forceRag?: boolean;
      provencePrune?: boolean;
    },
    onEvent: (event: StreamEvent) => void,
  ): Promise<void> {
    const { query, model, session_id, table_name, composeSubAnswers, decompose, aiRerank, contextExpand, verify, retrievalK, contextWindowSize, rerankerTopK, searchType, denseWeight, forceRag, provencePrune } = params;

    const payload: Record<string, unknown> = { query };
    if (model) payload.model = model;
    if (session_id) payload.session_id = session_id;
    if (table_name) payload.table_name = table_name;
    if (typeof composeSubAnswers === 'boolean') payload.compose_sub_answers = composeSubAnswers;
    if (typeof decompose === 'boolean') payload.query_decompose = decompose;
    if (typeof aiRerank === 'boolean') payload.ai_rerank = aiRerank;
    if (typeof contextExpand === 'boolean') payload.context_expand = contextExpand;
    if (typeof verify === 'boolean') payload.verify = verify;
    //  ADD NEW RETRIEVAL PARAMETERS TO PAYLOAD
    if (typeof retrievalK === 'number') payload.retrieval_k = retrievalK;
    if (typeof contextWindowSize === 'number') payload.context_window_size = contextWindowSize;
    if (typeof rerankerTopK === 'number') payload.reranker_top_k = rerankerTopK;
    if (typeof searchType === 'string') payload.search_type = searchType;
    if (typeof denseWeight === 'number') payload.dense_weight = denseWeight;
    if (typeof forceRag === 'boolean') payload.force_rag = forceRag;
    if (typeof provencePrune === 'boolean') payload.provence_prune = provencePrune;

    try {
      const resp = await fetch('http://localhost:8001/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!resp.ok || !resp.body) {
        if (!resp.ok) {
          throw await this.createApiError(resp, 'stream', 'Stream request failed');
        }
        throw this.toApiError(new Error(`Missing stream body: ${resp.status}`), 'stream', 'Stream request failed');
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      let streamClosed = false;
      let receivedComplete = false;
      while (!streamClosed) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';

        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith('data:')) continue;
          const jsonStr = line.replace(/^data:\s*/, '');
          try {
            const evt = JSON.parse(jsonStr) as StreamEvent;
            onEvent(evt);

            if (evt.type === 'error') {
              const rawError = typeof evt.data?.error === 'string' ? evt.data.error : 'Streaming failed';
              throw this.toApiError(new Error(rawError), 'stream', 'Stream request failed');
            }

            if (evt.type === 'complete') {
              receivedComplete = true;
              // Gracefully close the stream so the caller unblocks
              try { await reader.cancel(); } catch {}
              streamClosed = true;
              break;
            }
          } catch (error) {
            throw this.toApiError(error, 'stream', 'Stream request failed');
          }
        }
      }

      if (!receivedComplete) {
        throw this.toApiError(new Error('Stream ended before completion event'), 'stream', 'Stream request failed');
      }
    } catch (error) {
      throw this.toApiError(error, 'stream', 'Stream request failed');
    }
  }
}

export const chatAPI = new ChatAPI(); 