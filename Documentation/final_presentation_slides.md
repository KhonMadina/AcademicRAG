# Final Project Presentation Slides

## Slide 1 - Title Slide
**AcademicRAG: A Privacy-Preserving Local Document Intelligence Platform for Academic Knowledge Retrieval and Question Answering**

- Master of Information Technology in Education
- Candidate: [Your Name]
- Supervisor: [Supervisor Name]
- Royal University of Phnom Penh
- March 2026

**Speaker note:**
Introduce the project as a local AI-powered document intelligence platform designed for academic and institutional use.

---

## Slide 2 - Background
**Why this project matters**

- Educational institutions manage large collections of reports, policies, manuals, and research papers
- Important knowledge is often locked inside PDFs and difficult to search efficiently
- Cloud AI tools raise privacy and data-governance concerns
- Institutions need secure, evidence-based access to internal knowledge

**Speaker note:**
Emphasize the practical problem: information exists, but finding and synthesizing it is slow and difficult, especially when documents are sensitive.

---

## Slide 3 - Problem Statement
**Core problem**

- Traditional keyword search is limited for complex questions
- Generic AI chatbots may hallucinate or lack document grounding
- Many solutions require uploading sensitive documents to external servers
- There is a need for a local, privacy-preserving system that can answer questions from institutional documents reliably

**Speaker note:**
State the project problem clearly and link it to privacy, usability, and answer quality.

---

## Slide 4 - Aim and Objectives
**Aim**

To design and implement a local document intelligence platform for secure question answering over academic documents.

**Objectives**

- Analyse requirements for privacy-preserving academic document QA
- Design a modular local architecture
- Implement document upload, indexing, retrieval, and chat
- Improve baseline RAG with routing, hybrid retrieval, reranking, and verification
- Evaluate the prototype using functional and technical evidence

**Speaker note:**
Keep this slide concise. Show that the work is a systems-development project with clear technical objectives.

---

## Slide 5 - Proposed Solution
**AcademicRAG**

- A fully local Retrieval-Augmented Generation platform
- Supports document upload, indexing, and natural-language querying
- Keeps document processing and model inference on local infrastructure
- Designed for academic, administrative, and research document collections

**Key idea:**
Combine privacy, evidence-based retrieval, and modern AI interaction in one platform.

**Speaker note:**
Present AcademicRAG as the direct response to the problem identified earlier.

---

## Slide 6 - System Architecture
**Four-service architecture**

- **Frontend:** Next.js, React, TypeScript
- **Backend:** Python HTTP server for sessions, uploads, and routing
- **RAG API:** Python retrieval and indexing service
- **Model Server:** Ollama for local LLM inference

**Storage**

- SQLite for sessions and metadata
- LanceDB for vector embeddings
- Local filesystem for uploaded files and index artifacts

**Suggested visual:**
Browser -> Frontend -> Backend -> RAG API -> Ollama  
with SQLite and LanceDB shown below

**Speaker note:**
Explain that the architecture separates interaction, orchestration, retrieval, and inference for maintainability and scalability.

---

## Slide 7 - Document Indexing Pipeline
**How documents become searchable**

1. Upload documents
2. Extract text from files
3. Chunk documents into smaller sections
4. Optionally generate contextual enrichment
5. Create embeddings
6. Store vectors in LanceDB
7. Save metadata in SQLite

**Additional robustness**

- Large-PDF memory guard
- PyMuPDF fallback when Docling fails

**Speaker note:**
Highlight that indexing is not just file upload; it is a structured pipeline designed for reliability and retrieval quality.

---

## Slide 8 - Retrieval and Answer Generation
**Query processing workflow**

- User submits a question
- System decides whether to use direct LLM or RAG
- If RAG is selected:
  - retrieve relevant chunks
  - combine dense and BM25 results
  - rerank evidence
  - expand chunk context when needed
  - generate final answer
  - optionally verify grounding

**Speaker note:**
This is the core technical contribution slide. Show that the platform uses multiple quality-control layers.

---

## Slide 9 - Main Technical Innovations
**Beyond basic RAG**

- Dual-layer routing between direct LLM and RAG
- Hybrid retrieval: semantic + lexical search
- Contextual enrichment during indexing
- Late chunk expansion for local context preservation
- AI reranking using ColBERT-style reranker
- Optional answer verification with confidence scoring
- Session-aware history and semantic caching

**Speaker note:**
This slide helps demonstrate originality and technical depth.

---

## Slide 10 - Technologies Used
**Frontend**

- Next.js 15
- React 19
- TypeScript
- Tailwind CSS

**Backend / AI stack**

- Python
- Ollama
- Transformers
- Sentence Transformers
- Docling
- LanceDB
- SQLite

**Models**

- `gemma3:12b-cloud` for generation
- `gemma3:4b-cloud` for routing and enrichment
- `Qwen/Qwen3-Embedding-0.6B` for embeddings
- `answerdotai/answerai-colbert-small-v1` for reranking

**Speaker note:**
Mention that the project relies on open-source components and is designed for local deployment.

---

## Slide 11 - Results
**Functional results**

- Completed multi-service working prototype
- Supports sessions, indexing, uploads, and document-grounded chat
- Includes health checks and backend test scripts
- Frontend supports typed API integration and streaming interaction

**Reported engineering performance**

- Simple chat: 1-3 seconds
- Document query: 5-15 seconds
- Complex analysis: 15-30 seconds
- Indexing: 2-5 minutes per 100 MB

**Speaker note:**
Clarify that these are engineering benchmarks from the project documentation, not formal experimental metrics.

---

## Slide 12 - Educational Relevance
**Why this matters for education**

- Supports secure access to institutional knowledge
- Useful for administration, curriculum work, research support, and policy lookup
- Reduces dependence on external AI services
- Demonstrates responsible AI deployment in education

**Possible use cases**

- Querying academic regulations
- Summarizing project reports
- Searching research papers
- Accessing internal administrative guidance

**Speaker note:**
Connect the technical system back to the degree field: Information Technology in Education.

---

## Slide 13 - Limitations
**Current limitations**

- No formal user study yet
- No labelled benchmark dataset for retrieval metrics
- Some advanced features remain experimental
- Performance depends on local hardware and model configuration
- Production maturity is strongest for PDF-based workflows

**Speaker note:**
Be transparent. Examiners usually appreciate a realistic assessment of what is complete and what remains future work.

---

## Slide 14 - Future Work
**Recommended next steps**

- Conduct formal evaluation with labelled academic queries
- Add user testing with staff and students
- Improve multimodal support for images and tables
- Expand document-format support
- Add graph-based retrieval features
- Improve citation display and answer provenance
- Package for easier institutional deployment

**Speaker note:**
Show that the project has a clear continuation path and research value beyond the prototype.

---

## Slide 15 - Conclusion
**Conclusion**

- AcademicRAG addresses the need for private, local, document-grounded AI in education
- The system successfully integrates indexing, retrieval, routing, reranking, and verification
- It demonstrates that secure local AI deployment is feasible and useful for academic institutions
- The project provides a strong foundation for future research and institutional adoption

**Speaker note:**
End with a confident summary: the project is a meaningful systems contribution with clear educational relevance.

---

## Slide 16 - Thank You / Q&A
**Thank You**

Questions and Discussion

- Email: [Your Email]
- Project: AcademicRAG

**Speaker note:**
Pause here and prepare to answer likely questions on privacy, evaluation, architecture, and future work.

---

## Suggested Viva Questions to Prepare

1. Why did you choose a local deployment instead of cloud AI?
2. What makes your system better than a simple chatbot over PDFs?
3. Why did you use hybrid retrieval instead of only embeddings?
4. How does the routing mechanism improve performance?
5. What are the limitations of your current evaluation?
6. How is this project relevant to Information Technology in Education?
7. What would you improve if you had more time?

---

## Suggested Design Tips for PowerPoint

- Use a clean academic theme with dark blue, white, and gray
- Keep 4-6 bullet points per slide
- Add one architecture diagram and one pipeline diagram
- Use screenshots of the UI on the results slide if available
- Keep total presentation length around 10-15 minutes
- Prepare a shorter 2-minute summary in case time is limited
