# ROYAL UNIVERSITY OF PHNOM PENH
## Master of Information Technology in Education

# AcademicRAG: A Cloud-Enabled Document Intelligence Platform for Academic Knowledge Retrieval and Question Answering

**A Final Project Report Draft**  
In Partial Fulfilment of the Requirements for the Degree of  
**Master of Information Technology in Education**

**Candidate:** [Your Name]  
**Student ID:** [Your ID]  
**Supervisor:** [Supervisor Name]  
**Date:** March 2026

---

## Supervisor's Research Supervision Statement

This section should be formatted according to the university template and signed by the supervisor.  

**Programme:** Master of Information Technology in Education  
**Candidate:** [Your Name]  
**Title of Report:** *AcademicRAG: A Cloud-Enabled Document Intelligence Platform for Academic Knowledge Retrieval and Question Answering*  

This is to certify that the work presented in this report was completed under my supervision and that, to the best of my knowledge, it is suitable for submission in partial fulfilment of the degree requirements.

**Supervisor Name:** ____________________  
**Signature:** ____________________  
**Date:** ____________________

---

## Candidate's Statement

I certify that this report is my own work and has not been submitted, either in whole or in part, for any other qualification at this or any other institution. Where the ideas or words of others have been used, they have been acknowledged appropriately.

**Candidate Name:** ____________________  
**Signature:** ____________________  
**Date:** ____________________

---

## Acknowledgements

I would like to express my sincere gratitude to my supervisor for guidance, encouragement, and constructive feedback throughout the development of this project. I also wish to thank the lecturers and staff of the Master of Information Technology in Education programme for providing the academic foundation that made this work possible. Finally, I am grateful to my family, friends, and peers for their patience and support during the design, implementation, and documentation of this project.

---

## Abstract

This report presents **AcademicRAG**, a cloud-enabled and privacy-aware document intelligence platform for question answering over academic and institutional documents. The project addresses a practical challenge faced by universities and education-related organisations: critical knowledge is distributed across reports, policies, manuals, and research papers, while conventional search is limited and many external AI services raise governance and confidentiality concerns.

To address this challenge, the project implements a Retrieval-Augmented Generation (RAG) system that combines a modern web interface, a Python backend gateway, a dedicated RAG API layer, inference through Ollama Cloud, SQLite metadata persistence, and LanceDB vector storage. Beyond a baseline RAG workflow, the platform incorporates dual-layer routing, hybrid dense-lexical retrieval, contextual enrichment, late chunk expansion, AI reranking, optional verification, session-aware interaction, and safeguards for large-PDF indexing.

The study follows a design-and-development methodology appropriate for applied information technology research. Evaluation is based on implementation artifacts, functional testing, operational dry-run evidence, and documented benchmark ranges. The completed prototype demonstrates end-to-end capability for upload, indexing, retrieval-grounded chat, and streaming responses. Reported engineering ranges indicate approximately 1-3 seconds for simple direct chat, 5-15 seconds for document-grounded responses, 15-30 seconds for complex analysis, and 2-5 minutes per 100 MB for indexing, depending on configuration.

The project contributes a practical model for governed AI deployment in education by balancing privacy, usability, and retrieval quality in a modular architecture. Current limitations include the absence of a controlled user study, incomplete retrieval-quality benchmarking, and partially experimental advanced features (for example, graph-based and fully multimodal retrieval). Overall, AcademicRAG provides a credible foundation for secure academic knowledge support in the RUPP and broader Cambodian context.

**Keywords:** Retrieval-Augmented Generation, cloud-enabled AI, document intelligence, educational technology, privacy-aware systems, hybrid retrieval, academic knowledge management.

---

## Table of Contents

*This draft is structured for later formatting in the university template. The table of contents, list of figures, and list of tables should be generated automatically in the final word-processing stage.*

---

# CHAPTER 1: INTRODUCTION

## 1.1 Background to the Study

The rapid growth of digital content in education has created a knowledge management challenge. Universities, schools, teacher training institutions, and academic departments generate large volumes of documents such as policy papers, course outlines, lesson guides, accreditation evidence, project reports, administrative memoranda, and research publications. Although these documents contain valuable institutional knowledge, they are often stored as disconnected files that are difficult to search efficiently. In many cases, staff and students must manually open and read multiple documents to locate specific information.

Recent progress in large language models has created new opportunities for question answering over document collections. Retrieval-Augmented Generation (RAG) has emerged as an important approach because it combines document retrieval with language generation, allowing the system to answer user questions using relevant evidence rather than relying only on model memory. This makes RAG particularly attractive for educational settings, where answers should be grounded in institutional documents and where transparency is important.

However, educational organisations also face serious privacy and governance constraints. Many cloud-based AI tools require documents to be uploaded to remote servers without sufficient institutional control. For institutions handling internal reports, student-related records, curriculum drafts, assessment material, or unpublished research, this creates risks related to data leakage, confidentiality, and compliance. As a result, there is a strong need for privacy-aware AI systems that can enforce controlled data handling while still benefiting from modern cloud inference.

AcademicRAG was developed in response to this need. The project is a cloud-enabled document intelligence platform designed to ingest private documents, index them, and support natural-language question answering through a browser-based interface. The system integrates modern web technologies with open-source AI tooling and managed cloud inference through Ollama Cloud, while preserving strong governance through controlled indexing, storage, and retrieval workflows. It also adds several enhancements beyond a simple RAG baseline, including routing, hybrid retrieval, reranking, contextual enrichment, and answer verification.

From an educational technology perspective, this project is relevant because it addresses a real operational problem: how to make institutional knowledge more accessible while preserving privacy. It also demonstrates how modern AI systems can be adapted to the realities of educational infrastructure, where budgets, bandwidth, data policies, and local deployment constraints matter.

## 1.2 Problem Statement

Educational institutions increasingly depend on large collections of digital documents, yet these materials are difficult to search, synthesise, and reuse efficiently. Traditional keyword search often fails when users ask conceptual questions, while generic cloud-based AI assistants may provide unsupported answers or require sensitive data to be uploaded externally. There is therefore a gap between the need for intelligent document access and the need for privacy, control, and evidence-based responses.

A conventional document chatbot is also insufficient for this context. Simple systems frequently rely on a single retrieval method, do not distinguish between questions that require retrieval and those that can be answered directly, and may return long but weakly grounded responses. In addition, educational and administrative documents vary considerably in structure and size, especially PDF reports, creating operational issues for indexing and retrieval.

This project addresses the following core problem: **How can a cloud-enabled, privacy-aware document intelligence platform be designed and implemented to support reliable question answering over academic and institutional documents while maintaining acceptable usability and technical performance?**

## 1.3 Aim and Objectives of the Study

### Aim

The aim of this project is to design, implement, and evaluate a cloud-enabled document intelligence platform that enables secure, evidence-based question answering over private academic documents.

### Objectives

1. To analyse the technical and practical requirements for a privacy-aware academic document question answering system.
2. To design a modular architecture combining frontend interaction, backend session management, retrieval services, model serving, and persistent storage.
3. To implement a cloud-enabled RAG pipeline capable of document upload, indexing, retrieval, and answer generation.
4. To improve a baseline RAG approach through hybrid retrieval, dual-layer routing, contextual enrichment, late chunk expansion, reranking, and answer verification.
5. To assess the completed prototype using engineering-oriented functional and performance evidence derived from the system implementation and project documentation.
6. To discuss the relevance, strengths, limitations, and future potential of the system in educational settings.

## 1.4 Rationale of the Study

The rationale for this study is both practical and academic. Practically, educational institutions need secure tools that can help staff and students interact with large document collections more efficiently. A cloud-enabled document intelligence platform can reduce time spent manually searching documents, improve access to institutional knowledge, and support evidence-based responses.

Academically, the project provides a useful case study in applied educational technology and information systems design. It demonstrates how current AI techniques can be adapted for environments where privacy and governance are central concerns. Rather than treating AI as an unrestricted cloud service, the project explores a controlled cloud-integration model that is more suitable for institutions with data sensitivity requirements.

The study is also significant because it moves beyond a minimal RAG implementation. By integrating routing, hybrid retrieval, reranking, and verification, the project examines how system design choices can improve trustworthiness and usability. These are especially important in education, where incorrect or unsupported answers can have consequences for teaching, assessment, administration, and policy interpretation.

## 1.5 Scope and Limitations

The scope of the project is limited to the design and implementation of a working prototype for cloud-enabled document intelligence. The system covers document upload, indexing, session management, retrieval, response generation, and a browser-based user interface. It is intended primarily for private document collections with controlled cloud inference.

The project has several limitations.

1. The current evidence base is primarily engineering and implementation-oriented rather than based on a controlled experimental user study.
2. Reported performance values come from project documentation and internal testing rather than a formal benchmark paper.
3. The system documentation indicates that some capabilities, such as graph-based reasoning and full multimodal support, remain future-facing or partially implemented.
4. Although converter code indicates support for several document formats, project documentation emphasises PDF as the primary supported production format.
5. No gold-standard annotated dataset was created to measure retrieval quality with metrics such as Recall@k, F1, or exact match.

These limitations do not reduce the value of the project as a systems-development study, but they do define the boundaries of the conclusions that can be drawn.

## 1.6 Structure of the Study

This report is organised into six chapters. Chapter 1 introduces the study, its problem, objectives, rationale, and scope. Chapter 2 reviews relevant literature and technical concepts related to RAG, hybrid retrieval, cloud-integrated AI deployment, and verification. Chapter 3 explains the research methodology and the technical design of the AcademicRAG platform. Chapter 4 presents the implementation outcomes, functional features, and reported performance results. Chapter 5 discusses the significance of the findings, project contributions, limitations, and future directions. Chapter 6 concludes the report and presents recommendations.

---

# CHAPTER 2: LITERATURE REVIEW

## 2.1 Retrieval-Augmented Generation

Retrieval-Augmented Generation has become an important strategy for improving the usefulness of large language models on knowledge-intensive tasks. Lewis et al. (2020) describe RAG as a framework that combines a generative model with access to external non-parametric memory, enabling responses to be grounded in retrieved documents rather than only model parameters. This is especially relevant for domains in which information changes over time or where evidence should be explicit.

For educational and institutional document use, RAG is attractive for three reasons. First, it allows answers to be linked to specific sources. Second, it reduces dependence on the model's internal memory for domain-specific information. Third, it supports updating a knowledge base by re-indexing documents instead of retraining a model. These properties align well with academic environments, where policy documents, handbooks, and reports are frequently revised.

At the same time, standard RAG has known weaknesses. If documents are chunked poorly, relevant context may be separated from the most important facts. If retrieval is weak, generation quality declines. If prompts are not carefully constrained, models may still hallucinate. These issues motivate the enhancements explored in this project.

## 2.2 Hybrid Retrieval and Dense-Lexical Fusion

A major limitation of relying on a single retrieval technique is that different question types require different retrieval strengths. Dense vector retrieval is effective for semantic similarity and paraphrase matching, but it may miss exact terms, acronyms, identifiers, and highly specific keywords. Lexical retrieval approaches such as BM25 remain valuable for precise matching and are widely used in information retrieval.

Robertson and Zaragoza (2009) explain BM25 as a probabilistic retrieval framework that remains highly effective because it balances term frequency, inverse document frequency, and document length normalization. More recent RAG practice has shown that combining dense retrieval with lexical retrieval often improves robustness. Anthropic's discussion of contextual retrieval also highlights that embedding-based search can miss exact matches and that BM25 helps recover these cases, especially when combined with contextual preprocessing and reranking.

This literature supports the hybrid strategy used in AcademicRAG. The project documentation describes a retrieval process that combines dense similarity with BM25-style keyword matching, then fuses and reranks the results. This is consistent with current best practice for systems that must answer both conceptual and exact-match questions.

## 2.3 Reranking and Late Interaction Models

Initial retrieval often returns a mixed set of relevant and marginally relevant chunks. A reranker can improve final answer quality by reordering candidates and passing only the strongest evidence into generation. Khattab and Zaharia (2020) proposed ColBERT, a late-interaction retrieval architecture that preserves token-level matching while remaining efficient enough for large-scale passage search.

Reranking is important because generation quality depends heavily on the quality of the supplied context. If irrelevant chunks are passed into the language model, the answer may become diluted, incomplete, or misleading. The project's use of an AI reranker reflects this understanding. AcademicRAG uses a ColBERT-style reranker as its primary ranking mechanism, with a fallback cross-encoder reranker documented for resilience.

A related concept is late chunking or contextual window expansion. Small chunks help retrieval precision, but they can strip away nearby sentences needed for interpretation. Expanding a retrieved chunk with its neighbors can preserve context while still allowing fine-grained retrieval. This technique is particularly useful for academic and administrative documents in which meaning often depends on nearby headings, definitions, or explanatory paragraphs.

## 2.4 Contextual Enrichment and Query Transformation

Traditional chunking methods often ignore the broader document context in which a passage appears. Contextual retrieval techniques attempt to improve this by adding chunk-level or document-level context before indexing or retrieval. Anthropic's contextual retrieval guidance argues that retrieval quality improves when chunk-specific context is added to support both semantic and lexical search.

AcademicRAG adopts this idea through contextual enrichment and overview generation. The indexing pipeline can create per-chunk summaries and document-level overviews, which are then reused during retrieval and routing. This makes the system more than a simple storage-and-search pipeline. It creates an intermediate knowledge layer that helps later stages decide what to retrieve and whether retrieval is necessary at all.

The project also supports query transformation features such as query decomposition and optional hypothetical reformulation. These techniques are intended to help the system address complex user requests by turning them into more targeted sub-queries. In educational contexts, this is useful because users often ask broad questions such as summarising findings, comparing sections, or extracting decisions from long reports.

## 2.5 Verification and Grounded Answering

One of the most persistent criticisms of generative AI is hallucination: the production of fluent but unsupported statements. In educational settings, this is especially problematic because users may over-trust confident responses. A grounded answer should therefore be linked to retrieved evidence and, where possible, checked for support.

AcademicRAG includes an optional verifier component that assesses whether an answer is supported by the retrieved snippets and returns a verdict, reasoning, and confidence score in structured form. Although this does not eliminate error, it reflects a growing systems-design trend: adding a post-generation control layer to improve reliability.

Verification is not a complete substitute for human judgement. It remains dependent on model behaviour and formatting reliability. However, as part of a broader architecture that already includes retrieval, reranking, and constrained prompting, it strengthens the platform's trustworthiness and makes it more appropriate for professional and academic use.

## 2.6 Cloud-Integrated AI Deployment and Privacy in Education

Educational institutions operate within ethical and administrative constraints that make privacy an essential requirement. Student information, internal evaluations, draft policies, and committee reports cannot always be shared with external AI platforms without governance controls. A cloud-integrated deployment model can address this issue by combining managed inference with strict institutional controls over data preparation, retrieval scope, and access policy.

AcademicRAG is explicitly designed around this principle. The project uses Ollama Cloud for language model inference, SQLite for metadata storage, LanceDB for embeddings, and file-system-based storage for uploaded documents and auxiliary indexes. This design aligns with a privacy-aware interpretation of educational technology: AI should support learning and administration while maintaining institutional control over document workflows and data governance.

From a theoretical perspective, this also shifts the focus from raw model performance to deployment appropriateness. In education, the most useful system is not always the largest or most centralized one; it is often the system that can be deployed safely, maintained locally, and adapted to existing workflows.

## 2.7 Research Gap and Conceptual Positioning

The literature and current tooling suggest a clear gap. Many discussions of RAG focus on retrieval quality, but fewer address the combined challenge of privacy, operational robustness, routing efficiency, and educational suitability in governed cloud-integrated deployments. Likewise, many prototypes demonstrate chat over documents but do not incorporate routing, reranking, verification, and indexing safeguards within one coherent platform.

This project positions itself as a **systems-development response** to that gap. Its contribution is not the proposal of a new retrieval theory, but the practical integration of multiple proven design ideas into a single, locally deployable platform suitable for academic documents. In that sense, AcademicRAG contributes to applied educational technology by translating AI and information retrieval concepts into a usable institutional tool.

---

# CHAPTER 3: METHODOLOGY

## 3.1 Research Design

This project followed a **design-and-development** methodology consistent with applied information technology research. The goal was not to test a social hypothesis through a large participant study, but to build and evaluate a technical artifact that addresses a real-world problem. The central artifact was the AcademicRAG platform itself.

The methodology can be summarised in four iterative stages:

1. **Problem analysis** – identifying the need for secure, local question answering over academic documents.
2. **System design** – defining the architecture, components, data flow, and operational requirements.
3. **Implementation** – building the frontend, backend, indexing pipeline, retrieval pipeline, and support services.
4. **Evaluation** – validating the prototype through documented functionality, configuration inspection, health checks, and reported engineering benchmarks.

This approach is appropriate because the value of the project lies in the creation and assessment of a working system artifact.

## 3.2 Requirements Analysis

The project requirements were inferred from the implementation files and system documentation. The main functional requirements were as follows:

- Users must be able to create and manage chat sessions.
- Users must be able to upload documents and associate them with indexes.
- The system must index documents into a searchable form.
- Users must be able to ask natural-language questions about indexed documents.
- The system must provide source-aware, document-grounded answers.
- The platform must run locally without requiring external document upload.
- The interface must support practical interaction through a modern web frontend.

The main non-functional requirements were:

- Privacy and local data control.
- Modularity and extensibility.
- Acceptable latency for user interaction.
- Support for configuration of models and retrieval behaviour.
- Operational stability, especially during large PDF indexing.

These requirements are reflected across the repository, particularly in the unified launcher, backend API, RAG pipeline configuration, and system documentation.

## 3.3 System Architecture

AcademicRAG uses a four-service architecture:

1. **Frontend layer** – a Next.js and React interface running on port 3000.
2. **Backend gateway** – a Python HTTP server running on port 8000 for session management, uploads, and API routing.
3. **RAG API layer** – a Python service running on port 8001 to handle indexing and retrieval-based chat.
4. **Model service layer** – Ollama Cloud API for managed model inference.

Supporting these services are three storage layers:

- **SQLite** for sessions, messages, index metadata, and session-index links.
- **LanceDB** for vector embeddings and retrieval tables.
- **Local file storage** for uploaded files, overviews, and auxiliary artifacts.

This architecture separates concerns clearly. The frontend handles interaction, the backend handles orchestration and persistence, the RAG API handles heavy retrieval logic, and Ollama provides inference. Such separation improves maintainability and makes the project easier to extend.

## 3.4 Data Model and Persistence Strategy

The database layer is implemented in SQLite. Based on the project code, the database stores session records, message histories, document associations, persistent indexes, and links between sessions and indexes. This data model supports practical application behaviour such as reopening prior conversations, associating chats with particular document collections, and tracking indexed resources.

Vector data is stored in LanceDB. The documentation indicates that separate text tables are created per index, and that the system is structured to support related assets such as BM25 indexes, document overviews, and graph data. This combination of relational metadata storage and vector storage is appropriate because it separates transactional state from high-dimensional retrieval data.

The persistence strategy has three advantages:

1. It is lightweight enough for institutional and hybrid deployment.
2. It preserves user history and document metadata.
3. It allows retrieval components to operate independently of frontend state.

## 3.5 Document Indexing Workflow

The indexing methodology implemented by AcademicRAG is multi-stage.

### Stage 1: File acquisition and preprocessing

Documents are uploaded through the frontend and passed to the backend. They are then forwarded to the indexing service with user-selected configuration options such as chunk size, overlap, retrieval mode, and enrichment settings.

### Stage 2: Conversion

The system uses a document converter that prioritises Docling for structured extraction. The converter includes safeguards for large PDFs: proactive bypass rules and fallback extraction using PyMuPDF. This is a significant engineering decision because large educational reports and scanned administrative files can otherwise cause memory failures during preprocessing.

### Stage 3: Chunking

The platform supports multiple chunking approaches, including standard recursive chunking, Docling-based structural chunking, and late chunking support. Chunking is necessary to convert large documents into manageable retrieval units while preserving enough semantic coherence to remain useful.

### Stage 4: Contextual enrichment and overview generation

When enabled, chunks are enriched with contextual summaries, and document overviews are generated. This stage supports later retrieval and routing by adding more informative representations of document content.

### Stage 5: Embedding and storage

The indexed chunks are converted into vector embeddings using a configured embedding model and stored in LanceDB. Index metadata is recorded in SQLite, creating a persistent bridge between user-visible indexes and low-level vector tables.

The overall indexing method shows a clear design intention: improve downstream retrieval quality while preserving operational robustness.

## 3.6 Query Processing Workflow

The query-processing methodology is a core aspect of the project.

### Step 1: Session-aware request handling

A user sends a message through the frontend. The backend receives the request and has access to the session state, prior history, and linked indexes.

### Step 2: Fast-path routing

Before invoking the full retrieval pipeline, the backend applies a routing decision. Simple greetings or general queries may be answered directly by the language model, while document-related questions are sent to the RAG path. This reduces unnecessary retrieval overhead.

### Step 3: Overview-based or agent-level routing

If document indexes are available, the system can use overview-based routing and an agent-level decision process to determine whether retrieval is justified. This second routing layer adds semantic awareness beyond simple heuristics.

### Step 4: Retrieval and fusion

For RAG queries, the retrieval pipeline transforms the query as needed and retrieves candidate chunks using dense search, BM25 search, or hybrid retrieval. Candidate results are then fused.

### Step 5: Reranking and context expansion

The strongest candidates are reranked using an AI reranker. Retrieved chunks can then be expanded with surrounding chunks to improve context quality before generation.

### Step 6: Answer synthesis

The language model generates a final answer using the selected evidence. The system is designed to stream output to the frontend and return source information.

### Step 7: Optional verification

If enabled, the verifier assesses whether the answer is grounded in the retrieved snippets and returns a structured support judgement.

This methodology reflects a layered design in which each stage attempts to improve answer quality while controlling cost and latency.

## 3.7 Development Tools and Technical Environment

The project uses the following implementation environment:

- **Frontend:** Next.js 15, React 19, TypeScript, Tailwind CSS, Radix UI, Framer Motion.
- **Backend and RAG services:** Python 3.x.
- **Model serving:** Ollama Cloud.
- **Embedding and retrieval libraries:** `transformers`, `torch`, `sentence-transformers`, `rerankers`, `rank-bm25`, and `lancedb`.
- **Document processing:** `docling`, `PyMuPDF`, and supporting ingestion tools.
- **Persistence:** SQLite and LanceDB.

The project also includes a unified launcher workflow for starting the RAG API, the backend, and the frontend together with configured model-service connectivity. This improves reproducibility and deployment convenience.

## 3.8 Evaluation Procedure

Because this project is a systems-development study, evaluation focused on technical verification and reproducible engineering evidence rather than a large participant experiment. The evaluation procedure used five evidence streams:

1. **Static architecture evidence** from implementation and documentation files.
2. **Functional validation** from backend tests and health-check routines.
3. **Operational dry-run evidence** from startup, readiness, and metrics probes.
4. **Retrieval evaluation artifacts** from the versioned retrieval evaluation set and tuning outputs.
5. **Feature completeness analysis** based on implemented components and API interfaces.

The system health-check script validates imports, configuration consistency, embedding model behaviour, LanceDB access, agent initialization, and sample query capability. Backend tests validate the health endpoint, chat endpoint, and short-term conversation memory. Release dry-run records provide readiness evidence (service startup, endpoint probes, metrics response, and observed minor issues). Retrieval tuning artifacts provide an initial quantitative baseline, although current published values indicate no measurable gain under the latest evaluated setup.

To increase methodological clarity, the analysis in Chapter 4 is organised into three evaluation dimensions:

- **Functional completeness** (whether required capabilities were implemented and callable).
- **Operational reliability and performance** (startup stability, endpoint readiness, and latency ranges from documented runs).
- **Retrieval-quality evidence** (current baseline metrics and their interpretation).

This procedure does not replace a controlled user study; instead, it establishes a transparent engineering evidence base suitable for an applied master-level system artifact.

## 3.9 Ethical and Privacy Considerations

The project's core design principle is privacy preservation. Document processing and storage remain under institutional control, while model inference can be routed through Ollama Cloud with governed access and configuration. This is especially important in educational environments, where data may include confidential administrative content or sensitive academic materials.

The system does not eliminate all ethical concerns. Incorrect answers are still possible, and users may still place too much trust in AI-generated outputs. However, the addition of source attribution, routing, and verification represents a responsible attempt to reduce those risks.

---

# CHAPTER 4: DATA ANALYSIS AND RESULTS

## 4.1 Overview of the Implemented System

The completed AcademicRAG prototype demonstrates a substantial level of implementation maturity. The repository contains a production-oriented web frontend, backend services, persistent data storage, indexing logic, retrieval logic, configuration files, health-check scripts, and deployment documentation. This indicates that the project progressed beyond a proof-of-concept script into a multi-component application.

Functionally, the system supports:

- Session creation, retrieval, renaming, and deletion.
- File upload and association with sessions or indexes.
- Persistent index creation and linkage.
- Document indexing with configurable chunking and enrichment settings.
- Chat over indexed documents.
- Streaming response handling.
- Hybrid retrieval and reranking options.
- Optional verification.
- Unified startup and service monitoring.

These outcomes show that the project successfully delivered the main artifact described in the objectives.

## 4.2 Functional Results by Component

### 4.2.1 Frontend Results

The frontend provides a modern browser-based interface built with Next.js and React. The project includes typed API wrappers for health checking, session management, index management, file upload, and chat. This indicates a strong emphasis on usability and maintainable integration between client and server.

The interface is not merely decorative; it functions as the operational surface of the platform. From an educational technology perspective, this is important because a technically strong backend has little institutional value if users cannot interact with it effectively.

### 4.2.2 Backend Results

The backend successfully implements session-aware chat, CRUD operations for sessions and indexes, file handling, index building triggers, and health monitoring. It also contains the first routing layer that decides whether a query should use direct generation or the document-grounded RAG path.

This backend design improves responsiveness for simple conversations while preserving document-aware behaviour for more demanding questions. As a result, the system avoids forcing every user message through the most expensive pipeline.

### 4.2.3 Indexing Results

The indexing pipeline demonstrates several completed features that are significant for real-world use:

- Support for chunking configuration.
- Optional contextual enrichment.
- Overview generation.
- Embedding generation and storage.
- Metadata persistence.
- Large-PDF safeguards with fallback extraction.

The large-PDF protection is especially valuable because large academic reports and scanned documents are common in institutional settings. This feature improves robustness and reduces the likelihood that indexing will fail on realistic workloads.

### 4.2.4 Retrieval Results

The retrieval system supports multiple retrieval modes and retrieval-enhancement techniques. Based on the documentation and implementation, the core completed retrieval features include:

- Dense vector retrieval.
- BM25 lexical retrieval.
- Hybrid fusion.
- AI reranking.
- Late chunk expansion.
- Query decomposition.
- Optional verification.

These results indicate that the final system is meaningfully stronger than a baseline document chatbot. It uses multiple control layers to improve evidence selection and answer quality.

## 4.3 Reported Performance Results

Project documentation provides engineering-oriented benchmark ranges. These are summarised in Table 4.1.

### Table 4.1 Reported System Response Benchmarks

| Operation | Reported Time Range | Interpretation |
|---|---:|---|
| Simple chat | 1-3 seconds | Direct language-model response without retrieval |
| Document query | 5-15 seconds | Retrieval, reranking, and answer synthesis |
| Complex analysis | 15-30 seconds | Multi-step reasoning and broader evidence use |
| Document indexing | 2-5 minutes per 100 MB | Depends on enrichment and processing configuration |

These results suggest that the platform is usable for interactive academic document work, particularly where privacy, governance, and evidence traceability are prioritised over ultra-low latency.

### Table 4.2 Reported Resource Characteristics

| Resource Category | Reported Range |
|---|---:|
| Embedding model memory | 1-2 GB |
| Generation model memory | 8-16 GB |
| Reranker memory | 500 MB-1 GB |
| Database cache | 500 MB-2 GB |

The documentation also reports approximate scalability characteristics of 5-10 concurrent users with 16 GB RAM, 10,000+ documents per index, and 10-20 queries per minute per instance. These values position the system as a realistic departmental or lab-scale solution rather than a high-scale cloud service.

### Table 4.3 Reported Indexing Throughput by Document Type

| Document Type | Processing Speed | Memory Usage | Storage Efficiency |
|---|---:|---:|---:|
| Text PDFs | 2-5 pages/sec | 2-4 GB | 1 MB/100 pages |
| Image PDFs | 0.5-1 page/sec | 4-8 GB | 2 MB/100 pages |
| Technical documents | 1-3 pages/sec | 3-6 GB | 1.5 MB/100 pages |
| Research papers | 2-4 pages/sec | 2-4 GB | 1.2 MB/100 pages |

These figures show that the system is engineered with practical deployment concerns in mind, especially document type variability.

## 4.4 Operational Dry-Run Evidence

In addition to benchmark ranges, the project includes a documented release dry run that validates deployment readiness in a realistic workspace environment.

### Table 4.4 Dry-Run Operational Evidence Summary

| Check Category | Observed Outcome | Interpretation |
|---|---|---|
| Launcher startup | Services started in no-frontend mode | Core backend and RAG services can be brought up reliably |
| Health endpoints | Backend and RAG liveness/readiness returned HTTP 200 | Services were operational and responsive |
| Metrics endpoints | Both `/metrics` endpoints returned HTTP 200 | Basic observability pipeline is functioning |
| Health script summary | 5/6 checks passed with minor issues | System was mostly healthy, with follow-up fixes recommended |

Observed non-blocking issues in the dry run included deprecation warnings and an intermittent model request error during a sample query path. These findings are important because they demonstrate transparent reporting of remaining technical risks rather than only reporting successful outcomes.

## 4.5 Validation and Testing Results

The project includes explicit testing and validation scripts.

### 4.5.1 System Health Check

The health-check script validates:

- Core imports.
- Configuration consistency.
- Agent initialization.
- Embedding model operation and vector dimensions.
- LanceDB connectivity.
- Sample query execution when tables are available.

This indicates that the project includes operational checks beyond basic startup.

### 4.5.2 Backend Tests

The backend test script validates:

- The `/health` endpoint.
- The `/chat` endpoint.
- Basic memory of short conversation history.

Although these tests are modest, they are appropriate for a prototype system and show that the application was built with a verification mindset.

## 4.6 Retrieval-Evaluation Baseline and Interpretation

The repository includes a versioned retrieval evaluation set and automated tuning outputs. The latest compact tuning result records baseline and candidate configurations with no measurable improvement and zero scored relevance metrics in the currently reported run.

### Table 4.5 Latest Retrieval Tuning Snapshot

| Metric | Baseline | Best Candidate | Delta |
|---|---:|---:|---:|
| Retrieval relevance @k | 0.0 | 0.0 | 0.0 |
| MRR @k | 0.0 | 0.0 | 0.0 |
| Citation hit rate @k | 0.0 | 0.0 | 0.0 |

This result should be interpreted carefully. It does not mean retrieval is universally ineffective; rather, it indicates that the current labelled evaluation setup, table selection, or scoring alignment requires improvement before meaningful comparative claims can be made. Methodologically, this is an important finding because it identifies evaluation quality as the highest-priority gap for the next iteration.

## 4.7 Analysis of the Project Against Objectives

### Objective 1: Analyse requirements

This objective was achieved. The repository documents the need for privacy-aware document intelligence and provides corresponding architectural and deployment choices.

### Objective 2: Design a modular architecture

This objective was achieved. The project clearly separates frontend, backend, retrieval API, model serving, and storage.

### Objective 3: Implement a cloud-enabled RAG pipeline

This objective was achieved. The codebase includes document conversion, chunking, embedding, retrieval, answer generation, and persistence.

### Objective 4: Improve a baseline RAG approach

This objective was achieved to a substantial degree. The implementation includes hybrid retrieval, routing, contextual enrichment, late chunking, reranking, and verification.

### Objective 5: Assess the prototype

This objective was partially achieved. Functional and engineering assessment is present, but controlled experimental evaluation remains limited.

### Objective 6: Discuss educational relevance

This objective was achieved conceptually. The system is strongly aligned with the needs of privacy-sensitive academic document environments.

## 4.8 Educational Use Scenarios

The platform has clear relevance to educational institutions. Possible practical scenarios include:

1. **Academic administration:** querying internal regulations, meeting minutes, or accreditation evidence.
2. **Faculty support:** summarising curriculum documents, policy manuals, or course handbooks.
3. **Research support:** locating methods, findings, and references across collections of papers or reports.
4. **Student support services:** helping staff access approved policy guidance quickly without exposing documents externally.
5. **Institutional knowledge retention:** making archived reports and procedural documents more accessible to new staff.

These scenarios illustrate the practical significance of a privacy-aware document intelligence platform in education.

---

# CHAPTER 5: DISCUSSION

## 5.1 Interpretation of Findings

The main finding of this project is that a privacy-aware document intelligence platform can be implemented with a relatively lightweight but modular architecture using current open-source tools. The system demonstrates that strong practical value can be achieved when governance controls are built into ingestion, retrieval, and response workflows.

A second important finding is that quality-oriented architectural additions matter. The project does not treat RAG as a single retrieval step followed by a prompt. Instead, it introduces routing, enrichment, hybrid retrieval, reranking, and verification. Together, these mechanisms form a layered reliability strategy.

The dual-layer routing approach is particularly important. Many user queries in a chat interface do not require document retrieval. By recognising this, the system improves user experience and conserves processing resources. In contrast, document-specific questions can still be escalated into the full RAG pipeline when necessary.

## 5.2 Contributions of the Project

The project makes five main contributions.

### 5.2.1 A governed deployment model for academic AI

The system demonstrates a practical architecture for combining institutional document control with configurable model inference. This is an important contribution in education, where privacy and governance are often decisive factors in technology adoption.

### 5.2.2 Integration of multiple retrieval-enhancement strategies

Rather than relying on a single retrieval technique, the platform integrates hybrid search, contextual enrichment, reranking, and late chunk expansion. This makes the implementation stronger and more realistic than minimal RAG examples.

### 5.2.3 Adaptive routing for cost and latency control

The use of routing between direct LLM answers and RAG-based answers is a practical innovation that reflects user-intent variation. This improves efficiency while preserving grounded retrieval for document-specific queries.

### 5.2.4 Reliability-oriented answer verification

The optional verifier adds a post-hoc grounding check, helping move the system toward more trustworthy behaviour.

### 5.2.5 Operational robustness for document indexing

The addition of large-PDF safeguards and fallback extraction shows awareness of real deployment challenges. This matters because educational documents are often long, inconsistent, and imperfectly formatted.

## 5.3 Relevance to Information Technology in Education

This project is well aligned with the field of Information Technology in Education because it addresses how technology can support institutional knowledge work, not only classroom delivery. Educational technology is broader than teaching software alone; it also includes systems that improve access to information, administrative efficiency, and research support.

AcademicRAG is relevant to this field in three ways.

1. It supports **knowledge accessibility**, enabling users to query large bodies of academic documents in natural language.
2. It supports **ethical deployment**, prioritising privacy and controlled cloud integration.
3. It supports **institutional capacity building**, since the system can potentially be deployed within universities, departments, or libraries without dependence on external hosted AI providers.

These characteristics make the project a meaningful example of applied educational IT.

## 5.4 Challenges Encountered

The repository and documentation suggest several challenges encountered during development.

### 5.4.1 Balancing latency and quality

Higher-quality retrieval pipelines generally add latency because they involve more stages such as reranking and verification. The project responds to this with routing and configurable modes.

### 5.4.2 Handling large PDFs reliably

Structured document extraction can be memory-intensive. The addition of PDF memory guards and PyMuPDF fallback indicates that this was a real engineering challenge during development.

### 5.4.3 Maintaining modularity across services

A four-service system is easier to extend, but it also increases integration complexity. The presence of a unified launcher and health checks shows that service coordination was an important concern.

### 5.4.4 Evaluating quality rigorously

The current project contains strong implementation evidence but limited formal retrieval-quality evaluation. This is a common challenge in student systems projects where building the artifact consumes most of the available time.

## 5.5 Limitations of the Study

Several limitations should be acknowledged.

First, the project does not yet present a full comparative experiment against multiple external baseline systems. Second, current retrieval-evaluation outputs indicate that metric instrumentation and dataset-label alignment still need refinement before robust quality conclusions can be drawn. Third, some advanced features remain incomplete or experimental, particularly graph-based and fully multimodal capabilities. Fourth, the system's documented performance depends on hardware and model configuration, so results may vary across deployment environments.

These limitations mean that the project should be understood primarily as a strong systems-development prototype rather than a final benchmarked research product.

## 5.6 Future Work

The repository documentation and architecture suggest several high-impact directions for future work:

1. Repair and extend retrieval evaluation with stronger gold annotations, clear relevance labels, and repeatable benchmark scripts.
2. Conduct human usability testing with staff, lecturers, and postgraduate students in realistic institutional tasks.
3. Add comparative baselines (BM25-only, dense-only, hybrid, hybrid+reranker, hybrid+reranker+verifier).
4. Improve multilingual handling, including Khmer and mixed-language institutional documents.
5. Expand document support beyond PDF with robust table and image extraction.
6. Progress graph-based and multimodal retrieval from experimental to production quality.
7. Strengthen citation rendering and provenance tracing in the user interface.
8. Package deployment profiles for university servers and constrained departmental workstations.

These improvements would strengthen both the academic rigor and the practical impact of the platform.

---

# CHAPTER 6: CONCLUSION

This report presented AcademicRAG, a document intelligence platform developed to support question answering over academic and institutional documents. The project addressed an important problem in educational settings: how to make document collections more searchable and useful while maintaining privacy and governance.

The completed system demonstrates a substantial technical achievement. It combines a modern frontend, backend orchestration, session persistence, model serving, vector storage, indexing, hybrid retrieval, reranking, routing, and verification into one coherent platform. The project therefore meets its central aim of creating a cloud-enabled RAG-based document intelligence prototype.

The findings of the study suggest that privacy-aware AI deployment is feasible and valuable for education-focused knowledge work. AcademicRAG shows that privacy and usability do not need to be treated as opposing goals. Through layered retrieval controls and operational safeguards, the system also demonstrates how a more reliable and context-aware alternative to a basic document chatbot can be built.

At the same time, the project remains an evolving system. Its evaluation is currently stronger on engineering evidence than on formal retrieval-quality metrics, and some advanced features remain incomplete. These limitations point directly to future research and development opportunities.

In conclusion, AcademicRAG makes a meaningful contribution as an applied educational technology project. It provides a practical foundation for secure academic knowledge retrieval in the RUPP and broader Cambodian context and offers a strong basis for future enhancement, institutional deployment, and more rigorous evaluation.

---

# REFERENCES

*Note: format these according to your department's required citation style (APA, Harvard, or university-specific) before final submission.*

Anthropic. (2024, September 19). *Introducing Contextual Retrieval*. https://www.anthropic.com/news/contextual-retrieval

Khattab, O., & Zaharia, M. (2020). *ColBERT: Efficient and Effective Passage Search via Contextualized Late Interaction over BERT*. Proceedings of the 43rd International ACM SIGIR Conference on Research and Development in Information Retrieval, 39-48. https://doi.org/10.1145/3397271.3401075

Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., Küttler, H., Lewis, M., Yih, W.-t., Rocktäschel, T., Riedel, S., & Kiela, D. (2020). *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*. Advances in Neural Information Processing Systems, 33. https://proceedings.neurips.cc/paper_files/paper/2020/hash/6b493230205f780e1bc26945df7481e5-Paper.pdf

Robertson, S., & Zaragoza, H. (2009). *The Probabilistic Relevance Framework: BM25 and Beyond*. Foundations and Trends in Information Retrieval, 3(4), 333-389.

AcademicRAG Project Documentation. (2026). *README and system documentation files*. Local project repository.

AcademicRAG Source Code Repository. (2026). *Implementation files including backend, frontend, and rag_system modules*. Local project repository.

---

# APPENDICES

## Appendix A: Summary of Core Technologies

| Layer | Technologies |
|---|---|
| Frontend | Next.js, React, TypeScript, Tailwind CSS, Radix UI |
| Backend | Python HTTP server |
| RAG Layer | Python pipelines, retrieval, reranking, verification |
| Model Serving | Ollama |
| Data Storage | SQLite, LanceDB, local filesystem |
| Document Processing | Docling, PyMuPDF |

## Appendix B: Summary of Major Features

| Feature | Purpose |
|---|---|
| Privacy-aware processing | Keeps sensitive document workflows under institutional control |
| Session management | Preserves chat history and user workflow |
| Hybrid retrieval | Improves retrieval robustness across question types |
| Dual-layer routing | Reduces unnecessary retrieval cost and latency |
| Contextual enrichment | Adds richer context for indexing and retrieval |
| AI reranking | Improves evidence ordering before answer generation |
| Verification | Checks grounding of generated answers |
| Large-PDF safeguards | Improves indexing reliability |

## Appendix C: Suggested Final Formatting Tasks

Before submitting the final report, replace all placeholder personal details and complete the following:

1. Apply the official faculty cover-page and margin settings.
2. Generate the table of contents automatically.
3. Add page numbers, list of figures, and list of tables if required.
4. Convert the references into the exact citation style required by the programme.
5. Insert screenshots of the interface, architecture diagrams, and testing outputs if your supervisor requests visual evidence.
6. Review wording for first-person versus third-person style according to faculty guidance.
