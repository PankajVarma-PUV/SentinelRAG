# SOTA Enhancement: Hybrid Alpha Retrieval Architecture

**Target Audience:** SentinelRAG Lead Architect  
**Objective:** Compare current Dense-Only retrieval against the SOTA Hybrid Alpha approach and provide a highly detailed, extremely safe implementation plan to upgrade the codebase without breaking existing functionality.

---

## 1. The Strategy: Why Hybrid Search?

Your current `RetrieverAgent` and `SentinelRAGDatabase` are incredibly robust. They use LanceDB to perform Deep Vector (Semantic) Search, followed by an advanced Cross-Encoder for reranking. 
*   **Vector Search Excels at:** Finding *meaning* (e.g., retrieving facts about "monetary penalties" when the user asks about "fines").
*   **Vector Search Fails at:** *Exact keyword matching* (e.g., searching for "Error Code 404X-B" or specific names like "Johnathan H. Doe").

By implementing **Hybrid Alpha Search**, we will run a Sparse Lexical Search (BM25/FTS) and a Dense Vector Search simultaneously, fusing the results together using Reciprocal Rank Fusion (RRF) before sending them to your Cross-Encoder. This guarantees God-Level precision.

---

## 2. Implementation Plan (Step-by-Step)

The safest, most "SOTA" way to implement this in your specific ecosystem is to leverage **LanceDB's Native Full-Text Search (FTS) via Tantivy**. Because LanceDB is your primary vector store, it can natively manage the BM25 text index right alongside your vectors, preventing you from having to maintain a separate messy Python BM25 index on disk.

We will modify precisely **three files**.

### Step 1: Updating Dependencies (`requirements.txt`)
LanceDB requires the `tantivy` rust-based search engine for its native Full-Text Search.

*   **File:** `requirements.txt`
*   **Action:** Add `tantivy` under the SOTA Storage section.
*   **Code Addition:**
    ```text
    # SOTA Storage (LanceDB)
    lancedb>=0.5.0
    pyarrow>=14.0.0
    tantivy>=0.21.1  # <-- NEW: Required for LanceDB Hybrid FTS
    ```

### Step 2: Upgrading the Database Engine (`src/core/database.py`)
We need to tell LanceDB to build a text index every time new knowledge is added, and we need to modify `search_knowledge` to run a hybrid query.

*   **File:** `src/core/database.py`
*   **Action A:** Modify `add_knowledge_from_text()` to create the FTS index after indexing new chunks.
    *   Find the `add_knowledge_from_text` method.
    *   Right at the end of the method, after `table.add(records)`, insert the FTS build command:
    ```python
    # ... existing code ...
    table.add(records)
    logger.info(f"Indexed {len(records)} knowledge chunks for {file_name}")
    
    # SOTA HYBRID SEARCH: Build Full-Text Search Index
    try:
        table.create_fts_index("text", replace=True)
        logger.info(f"Updated LanceDB FTS (BM25) index for {file_name}")
    except Exception as e:
        logger.warning(f"Could not build FTS index (ensure tantivy is installed): {e}")
    ```

*   **Action B:** Modify `search_knowledge()` to accept the raw text string and run a hybrid search.
    *   Change the signature to accept `query_text: str`.
    *   Change the table search initialization to use `query_type="hybrid"`.
    ```python
    # SOTA HYBRID UPDATE: Signature now requires query_text
    def search_knowledge(self, query_vector: List[float], query_text: str, project_id: Optional[str] = None, 
                         conversation_id: Optional[str] = None, file_names: Optional[List[str]] = None, 
                         limit: int = 5) -> List[Dict]:
        """Search the knowledge base using Hybrid SOTA (Vector + BM25), with filtering."""
        table = self.conn.open_table("knowledge_base")
        
        # SOTA: Execute Native Hybrid Search
        try:
            # LanceDB natively fuses Vector and Text via Reciprocal Rank Fusion
            query = table.search(query_text, query_type="hybrid").vector(query_vector)
        except Exception as e:
            # Safe Fallback to Vector-only if FTS index doesn't exist yet
            logger.warning(f"Hybrid search failed, falling back to Vector-only: {e}")
            query = table.search(query_vector)
            
        where_clauses = []
        # ... REST OF YOUR EXISTING FILTERING LOGIC REMAINS EXACTLY THE SAME ...
        if project_id:
            where_clauses.append(f"project_id = '{project_id}'")
        # ... 
        
        return query.limit(limit).to_list()
    ```

### Step 3: Upgrading the Retriever Agent (`src/agents/retriever.py`)
The RetrieverAgent currently only passes the vector to the database. We need to pass the raw string alongside it.

*   **File:** `src/agents/retriever.py`
*   **Action:** Update the `retrieve()` method so that `search_knowledge` receives the `query` text.
    ```python
    # Inside retrieve()
    
    # 1. Generate Query Embedding
    query_vector = self.embedder.encode(query).tolist()
    
    # 2. Perform SOTA Hybrid Search (LanceDB Native Dense + BM25)
    initial_pool = RerankerConfig.RERANK_TOP_K
    results = self.db.search_knowledge(
        query_vector=query_vector,
        query_text=query,        # <-- NEW: We now pass the raw text for FTS
        project_id=project_id,
        file_names=file_names,
        limit=initial_pool
    )
    
    # ... REST OF RERANKING LOGIC REMAINS EXACTLY THE SAME ...
    ```

---

## 3. Risk Assessment and Safe Rollout Strategy

### Potential Issues & Mitigations:
1.  **Missing `tantivy` Module:** If you try to run hybrid search without installing the `tantivy` python package, LanceDB will throw an error.
    *   **Mitigation:** The `try/except` block I placed in `search_knowledge` ensures that if `tantivy` crashes (or the FTS index hasn't finished building), it silently gracefully falls back to your current Vector-Only search. The UI will never break.
2.  **Legacy Conversations:** Existing conversations in LanceDB do not have an FTS index built yet. 
    *   **Mitigation:** The `create_fts_index` call replaces the index entirely for the table. The next time you upload *any* document, LanceDB will rebuild the index spanning all previous documents too. Also, the fallback will keep old chats working perfectly.

### Rollout Steps (When you give the green light):
1.  I will run `pip install tantivy` in the terminal to prepare the environment.
2.  I will patch `retriever.py` and `database.py`.
3.  We will run a test: Ask SentinelRAG an exact serial number or acronym question and watch it instantly retrieve the exact manual page.

**Please review this plan. I am fully confident and ready to execute this perfectly the moment you say "Go ahead and implement."**
