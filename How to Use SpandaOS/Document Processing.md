# SpandaOS Document Processing Workflow

This document provides a detailed, professional overview of the document processing capabilities within SpandaOS. It outlines the intelligent lifecycle of a text-based format or PDF, exploring how the system extracts, classifies, and makes both native text and embedded imagery fully searchable.

## Step 1: Document Selection, File Hashing, and Query
To initiate the document processing workflow, **we must select and upload a text, document, markdown, or PDF file and ask a query alongside the media upload.** This gives the AI the specific direction it needs to evaluate the text. Immediately upon ingestion, SpandaOS calculates a strict SHA-256 hash. This **Intelligent Caching** layer ensures that if you re-upload a previously processed document within the same session, the system instantly bypasses redundant extraction and retrieves the cached contextual data.

![Step 1: Upload Document](Media/Document/txt1.png)

## Step 2: Intelligent Dual-Extraction (Native Text & Perception Fusion)
**The system will detect whether the file is pure text or OCR based, and based on that it will perform necessary steps to extract all the textual data available in the file and store them in chunks.**
SpandaOS actively analyzes each page dynamically:
1. **Native Text:** It securely pulls all embedded characters directly from the file formatting.
2. **Scanned Page Detection (SOTA):** If a page appears empty but contains visual data (i.e., a scanned book), the system dynamically routes that page to the **Qwen2-VL** multi-modal agent to perform a high-fidelity visual extraction, grabbing both text and layout descriptions.
3. **Embedded Image Parsing:** SpandaOS isolates pictures embedded within PDFs and independently analyzes each one using Vision perception so that infographics and charts inside reports are fully captured.

![Step 2: Dual-Extraction Pipeline](Media/Document/txt2.png)

## Step 3: Knowledge Base Storage & RAG Context Retrieval
**Once text extraction gets done and the related textual data gets stored in the knowledge base, the application starts processing the user query with the RAG (Retrieval-Augmented Generation) flow.** By securely clustering and indexing the extracted chapters and descriptions into the vector database, lengthy documents transform into rapidly searchable knowledge. 
**Based on the user query, the RAG flow scrapes the related context and delivers it to the Synthesizer model to generate a proper response.** The RAG engine scans the hundreds or thousands of pages and retrieves only the exact paragraphs semantically related to the prompt, injecting them as grounded evidence.

![Step 3: Storage and Retrieval](Media/Document/txt3.png)

## Step 4: Verification by Critic & Healing Agent
**Once the synthesizer finishes producing the response, the Critic and Healing agent checks and verifies whether the response is proper or not, and fills any missing gaps.** This is our highest level of accuracy assurance. Before the user ever sees the answer, the metacognitive critic evaluates the drafted response against the retrieved document text to strictly ensure the synthesizer did not hallucinate figures, dates, or logic.

![Step 4: Verification Phase](Media/Document/txt4.png)

## Step 5: Final Response & Grounded Sources UI
**Once a detailed response gets generated, we will get the document name listed below "Grounded Sources". If we click on the file name, the text will get loaded into the source explorer.** This enforces conversational traceability.
**Only the chunks responsible for response generation will be visible, and a maximum of TOP K chunks will get loaded.** This keeps the UI highly performant and user-focused, pointing the reader directly to the exact paragraphs that provided the answer, rather than forcing them to scroll a 300-page file.

![Step 5: Grounded Sources](Media/Document/txt5.png)

## Step 6: Internal Meta-Data Review & Media Download
**At the end of the file, internal meta-data related to the file will be written.** This provides administrators with extreme transparency, surfacing system parameters such as chunk sizes, vector indexing hashes, semantic cluster counts, and file-parsing logic.
**The user can download this file as well.** The interface maintains secure access to the originally uploaded document, allowing researchers to quickly download the native asset to their local environment. 

![Step 6: Meta-Data and Download](Media/Document/txt6.png)

---

## Detailed Document Processing Architecture Flow

The following Mermaid.js diagram provides an extremely detailed visualization of the physical SpandaOS document processing infrastructure, illustrating the intelligent routing between native text extraction and SOTA Vision perception.

```mermaid
graph TD
    classDef user fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef process fill:#f3e5f5,stroke:#4a148c,stroke-width:2px;
    classDef model fill:#fff3e0,stroke:#e65100,stroke-width:2px;
    classDef storage fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef ui fill:#fce4ec,stroke:#c2185b,stroke-width:2px;

    %% Ingestion Phase
    A[User Uploads Document/PDF & Submits Query]:::user --> B{System Hash / Caching Layer}:::process
    B -->|Hash Exists in Session| C[Return Cached Indexed Document]:::storage
    B -->|New Document| D{File Parsing Engine}:::process
    
    %% Intelligent Dual-Extraction Pipeline
    D -->|Standard Text / MD| E[Straight Knowledge Chunking]:::process
    D -->|PDF File Detected| F{Page-by-Page Evaluator}:::process
    
    %% Dynamic PDF Handling (Native vs Scanned)
    F --> |Analyze Page Matrix| G{Native Text Detected?}:::process
    
    %% Scanned Logic
    G --> |No: Likely Scanned Page| H[Render SOTA Image Matrix]:::process
    H --> I[Qwen2-VL: Extract Scene + Text]:::model
    
    %% Native Logic + Embedded Image Handle
    G --> |Yes: Native Text| J[Extract Pure Text Characters]:::storage
    G --> |Detect Embedded Image| K{Image Matrix > 150px?}:::process
    K --> |Valid Chart/Graph| L[Qwen2-VL: Describe Infographic]:::model
    
    %% Aggregation
    I --> M[Document Aggregation Engine]:::storage
    J --> M
    L --> M
    E --> M
    
    %% Storage & Chunking Phase
    M --> N[Intelligent Text Chunking Node]:::process
    N --> O[(Vector Database Indexed)]:::storage
    
    %% Retrieval & Generation (RAG) Phase
    O --> |Activated by User Query| P[RAG Semantic Matcher]:::process
    P --> |Inject Top K Chunks as Context| Q[Synthesizer Model]:::model
    
    %% Metacognitive Validation Phase
    Q --> |Draft Formulation| R[Critic Node: Fact Check]:::model
    R -->|Hallucination Detected?| S[Healing Agent: Correct Draft]:::model
    S --> T
    R -->|Output Validated| T[Final Response Formulation]:::process
    
    %% UI Presentation Phase
    T --> U[Chat UI: Render Final Response]:::ui
    T --> V[Chat UI: Render Grounded Sources]:::ui
    
    V -.-> |User clicks Document Pill| W[Source Explorer Side-Panel]:::ui
    W --> X[Load Specific TOP K Retrieved Chunks]:::ui
    W --> Y[Highlight Text Fragments Informing Response]:::ui
    W --> Z[Expose Technical Meta-Data & Parsing Schema]:::ui
    W --> AA[Provide Native File Download Capability]:::ui
```
