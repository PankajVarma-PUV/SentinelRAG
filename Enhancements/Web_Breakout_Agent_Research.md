# Web-Breakout Agent (Self-Routing Fallback) - Research & Feasibility Report

## 1. Executive Summary & Feasibility
**Verdict: YES, it is highly feasible—even on your constrained 6GB VRAM system.**

Unlike GraphRAG (which demands massive continuous LLM inference and RAM during ingestion), the "Web-Breakout Agent" is a **Runtime/Query-Phase** feature. It requires almost zero extra VRAM because the actual heavy lifting (searching the internet and scraping text) is done by standard Python libraries using your CPU and System RAM, not your GPU. 

The LLM (`gemma-3-12b` or similar) is only used serially:
1. To decide if a search is needed.
2. To synthesize the final answer.
Because these steps don't run simultaneously, your 6GB VRAM will handle it perfectly without bottlenecking.

---

## 2. Completely Free Tooling (No Paid APIs)

You absolutely do *not* need to pay for Tavily, Google, Bing, or Serper. The Python open-source ecosystem provides everything you need to build a production-grade web searcher for free.

Here is your Free Tech Stack:
*   **Search Engine**: `duckduckgo-search` (Python library). It bypasses the need for an API key by scraping DuckDuckGo's HTML results directly.
*   **Web Scraper**: `trafilatura` or `BeautifulSoup4`. When DuckDuckGo returns a URL, you cannot just feed the LLM the short 2-sentence search snippet (this is what causes garbage/hallucinated responses). You must actively visit the URL and scrape the full article text. `trafilatura` is exceptionally fast, lightweight (uses CPU/RAM), and automatically strips out ads, navbars, and garbage HTML, leaving only clean read-friendly text.

---

## 3. How to Prevent "Garbage Responses"

The biggest risk of Web Search Agents is that they pull in SEO spam or irrelevant articles, leading the Synthesizer LLM to generate garbage. 

**To solve this, implement a strict "Metacognitive Brain" flow:**

1. **The Evaluation (Fact Checker Agent)**:
   * The user asks a question. LanceDB pulls the local context.
   * The Fact Checker LLM reads the context and the prompt. It is instructed: *"If the provided context fully answers the question, output `LOCAL`. If the question involves breaking news or information definitively missing from the context, output a JSON object: `{"action": "SEARCH", "query": "Optimized search terms here"}`."*
2. **The Execution (Web Search Agent - Python Native)**:
   * If the LLM outputted JSON, intercept it in Python.
   * Do **NOT** use the LLM to search. Use the `duckduckgo-search` library to run the `query`.
   * Grab the **top 2 URLs** only.
3. **The Extraction (The Scraper)**:
   * Use `trafilatura` to download and extract the raw text from those 2 URLs. 
   * *Constraint Limit*: Truncate the scraped text to ~1,500 tokens total so it doesn't blow up your KV Cache limit.
4. **The Synthesis**:
   * Inject the clean web text into your final prompt: *"Here is context from the live web: [WEB TEXT]. Answer the user's question, citing your sources."*

---

## 4. Hardware Impact on 6GB VRAM / 16GB RAM

This upgrade is perfectly suited for your machine because it is **Sequential**.

*   **VRAM Impact**: 0GB extra. The LLM is just doing standard text generation. When the Python script halts the LLM to go search the web (which takes ~2-3 seconds), the LLM is just idling in VRAM. 
*   **System RAM Impact**: Minimal. `duckduckgo-search` and `trafilatura` will briefly consume around 50MB to 150MB of System RAM while downloading the web pages, leaving plenty of room for your OS and LanceDB.
*   **Disk I/O Impact**: None. Web searches happen entirely in volatile memory and over the network; your Gen 4 NVMe SSD won't even break a sweat.

---

## 5. The Routing Flow Debate: Toggle Button vs. Autonomous Fallback

Your intuition to add an explicit UI toggle button (e.g., a "Web" icon next to the query input) is **excellent from a UX and safety perspective, but your flow logic contains a flaw in Step 5.**

Let's dissect your proposed flow and debate the optimal implementation within SentinelRAG.

### The Correct Intuitions (Where your logic is perfect)
Your Flow Steps 1 and 2 are perfectly designed.
*   **User Uploads/Mentions File + Web Toggle OFF**: Standard RAG. If the file doesn't have the answer, the system politely says "No Evidence Found." This preserves strict grounding.
*   **User Uploads/Mentions File + Web Toggle ON**: The system tries the file first. If the file fails (e.g., asking about dogs in a cat document), the system automatically triggers `duckduckgo_search`, scrapes the web, and answers the question. 

This explicit user-control design ensures that users *know* when their data might be supplemented by outside sources, preventing hallucinations and preserving trust.

### The Flaw: Flow Step 5 (Ignoring the Knowledge Base)
> *"5. If user has asked a query without mentioning file and Web Search Toggle Button is on then the system will ignore the existing knowledge base related to file and do a online research based on that research a proper response will get generated."*

**Why this is dangerous/unoptimized:**
If the user turns the Web Toggle ON and asks, "Summarize the key points of the contract," but forgets to explicitly `@mention` the contract file they uploaded yesterday:
*   Under your proposed Step 5, the system *ignores* the local database entirely and searches the internet for "key points of the contract," returning garbage results. 
*   This breaks the core "Conversation Memory" feature of RAG. 

### The Optimized Routing Flow (The SentinelRAG Way)

Instead of the Web Toggle *overriding* the local database, the Web Toggle should act as a **Fallback Permission Switch**.

Here is the exact, optimized logic flow the `OrchestratorAgent` should follow:

```mermaid
graph TD
    A[User Submits Query] --> B{Did User Upload/Mention File?}
    B -- Yes --> C[Query LanceDB for specific File]
    B -- No --> D{Are there files in current Conversation?}
    D -- Yes --> E[Query LanceDB for Conversation Files]
    D -- No (General Chat) --> F{Is Web Toggle ON?}
    
    C --> G{Evidence Found?}
    E --> G
    
    G -- Yes --> H[Synthesizer: Generate Grounded Answer]
    
    G -- No Evidence --> I{Is Web Toggle ON?}
    
    I -- OFF --> J[Fact Checker: Return "No Evidence Found"]
    
    I -- ON --> K[Web Agent: Search DuckDuckGo & Scrape]
    K --> L[Synthesizer: Generate Answer from Web Data]
    
    F -- OFF --> M[LLM: Generate Answer from Internal Memory]
    F -- ON --> K
```

### Why this Optimized Flow is Better:
1.  **Local Data ALWAYS wins:** Even if the Web toggle is ON, the system *always* checks LanceDB first (unless there are zero files in the conversation). This saves API time, protects privacy, and ensures the user's documents are prioritized.
2.  **Graceful Degradation:** If the Web Toggle is ON, but the user asks a general question ("Write a poem"), the `duckduckgo_search` will return poor results. The Synthesizer LLM must be smart enough to read the web results, realize they are useless for poem writing, and fall back to its internal weights. 

---

## 6. Comprehensive Implementation Plan (File-by-File)

To implement this God-Level Upgrade smoothly without breaking your existing flows, you will need to update the Frontend (to add the toggle), the Backend API (to receive the toggle state), and the `AgentOrchestrator` (to execute the new routing logic).

### Phase 1: Frontend UI (The Web Toggle)
*Files to modify: `ui/index.html`, `ui/style.css`, `ui/app.js`*

1.  **`index.html`**: Add a toggle button (e.g., a "Globe" icon or a simple switch) next to the chat input area.
    ```html
    <div class="input-actions">
        <!-- Existing attachment buttons -->
        ...
        <!-- New Web Search Toggle -->
        <label class="web-toggle-container" title="Enable Web Search Fallback">
            <input type="checkbox" id="web-search-toggle">
            <span class="slider round"><i class="fas fa-globe"></i> Web Search</span>
        </label>
    </div>
    ```
2.  **`style.css`**: Style the toggle so it visually indicates when "Web Search" is active (e.g., turning from gray to blue).
3.  **`app.js`**: 
    *   Read the state of `document.getElementById('web-search-toggle').checked` when the user submits a message.
    *   Append this boolean value to the message payload payload sent to the backend.

### Phase 2: Backend API Updates
*Files to modify: `src/main.py`*

1.  Update the `ChatRequest` Pydantic schema to accept the new boolean flag from the frontend.
    ```python
    class ChatRequest(BaseModel):
        conversation_id: str
        message: str
        mentioned_file: Optional[str] = None
        use_web_search: bool = False  # NEW FIELD (Default to Off)
    ```
2.  Pass this `use_web_search` flag down into the `AgentOrchestrator.process_query()` method when the endpoint is called.

### Phase 3: The Web Search Tool
*Files to create: `src/tools/web_search.py`*

Create the standalone Python tool that actually performs the DuckDuckGo lookup and Trafilatura scraping.

1.  **Dependencies**: Run `pip install duckduckgo-search trafilatura` and add them to `requirements.txt`.
2.  **Implementation**:
    ```python
    from duckduckgo_search import DDGS
    import trafilatura
    import logging

    logger = logging.getLogger(__name__)

    def fallback_web_search(query: str, max_results: int = 2) -> str:
        """Searches the live web and extracts clean text."""
        logger.info(f"[Web Agent] Initiating web breakout for query: '{query}'")
        try:
            results = DDGS().text(query, max_results=max_results)
            if not results:
                return "No real-time web results found."

            combined_web_context = []
            for res in results:
                url = res.get("href")
                title = res.get("title")
                # Download raw HTML
                downloaded = trafilatura.fetch_url(url)
                if downloaded:
                    # Extract clean article text
                    clean_text = trafilatura.extract(downloaded)
                    if clean_text:
                        # CRITICAL: Truncate to ~1000 chars per site to save 6GB VRAM
                        combined_web_context.append(f"Source: {title} ({url})\n{clean_text[:1000]}...")
            
            return "\n\n---\n\n".join(combined_web_context)
        except Exception as e:
            logger.error(f"[Web Agent] Web search failed: {e}")
            return f"Web search failed: {str(e)}"
    ```

### Phase 4: Agent Orchestrator Routing Logic (Metacognitive Brain)
*Files to modify: `src/agents/metacognitive_brain.py`*

This is where the magic happens. You must update the core LangGraph state and routing logic to respect the Web Toggle.

1.  **Update `SentinelRAGState` Definition**:
    Add the `use_web_search` flag to the state dictionary schema at the top of the file:
    ```python
    class SentinelRAGState(TypedDict):
        # ... existing fields ...
        use_web_search: bool  # NEW FALLBACK FLAG
    ```

2.  **Initialize the Flag in `run()`**:
    Inside the `run()` method (around line 1140), initialize the new state flag from the API request:
    ```python
    async def run(self, query: str, conversation_id: str, ..., use_web_search: bool = False):
        # ...
        initial_state: SentinelRAGState = {
            # ... existing initial state ...
            "use_web_search": use_web_search,
        }
    ```

3.  **Inject the Web Fallback in `evaluate_knowledge()`**:
    This node determines if the local context is sufficient. Modify it to trigger the web search tool if local context fails AND the toggle is on.

    ```python
    async def evaluate_knowledge(self, state: SentinelRAGState) -> Dict:
        # ... existing logic ...
        
        # SOTA Web Breakout Fork (Inject before returning 'internal_llm_weights')
        if not confidence_yes and state.get("use_web_search"):
            logger.info("[MetacognitiveBrain] Local grounding failed. Web Toggle ON. Initiating Web Breakout.")
            
            from ..tools.web_search import fallback_web_search
            # Execute the web search
            web_context = fallback_web_search(query)
            
            if "failed" not in web_context.lower() and "no real-time web results" not in web_context.lower():
                # OVERRIDE the LLM's 'NO' because we found web evidence!
                logger.info("[MetacognitiveBrain] Web Breakout successful. Forcing grounded mode.")
                
                # Append web context to the evidence stream so the Synthesizer uses it
                new_evidence = state.get("evidence", [])
                new_evidence.append({
                    "file_name": "Live Web Search",
                    "text": web_context,
                    "sub_type": "text",
                    "source": "WebBreakoutAgent"
                })
                
                # Return updated state pushing to standard RAG synthesis
                return {"response_mode": "grounded_in_docs", "evidence": new_evidence}
            else:
                logger.info("[MetacognitiveBrain] Web Breakout yielded no results. Proceeding to internal knowledge.")
                
        # ... resume existing logic ...
        mode = "grounded_in_docs" if confidence_yes else "internal_llm_weights"
        # ...
    ```

---

## 7. Migration Checklist for the User
Before you make these changes to your codebase, review this checklist:
1.  [ ] **Backup `app.js` and `metacognitive_brain.py`**: These are the critical routing and frontend files.
2.  [ ] **Install new libraries**: Ensure `trafilatura` and `duckduckgo-search` install cleanly. Run `pip install duckduckgo-search trafilatura`.
3.  [ ] **Test the API**: Use Postman or curl to hit your `/query/stream` endpoint with `{"use_web_search": true}` and ensure it doesn't 500-error.
4.  [ ] **Verify VRAM Limits**: When the `Synthesizer` generates the final web response, monitor your VRAM. If it chokes, reduce `clean_text[:1000]` down to `clean_text[:500]` in the `web_search.py` tool.

By explicitly gating the web search behind the frontend toggle flag (`use_web_search`) and injecting it into the LangGraph `evaluate_knowledge` node, you completely protect your system's core Conversation Memory capabilities while adding God-Level live data retrieval!
