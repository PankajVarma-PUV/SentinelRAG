# UltimaRAG: The Complete Deep-Dive Guide to AI Agents
> **Version:** Post-Audit (2026-02-27) — Fully corrected against live source code.
> **Status:** ✅ Trustworthy source of truth. All "listens to / reports to" fields verified in code.

Welcome to the **UltimaRAG Multi-Agent Architecture Guide**. This document describes all 27 specialized AI agents exactly as they exist in the current codebase — not as originally designed.

We have organized them into two sections:
* **Section 1 (The Senses & Foundation):** Background agents that process files on upload. They use Hugging Face, PyTorch, and local inference to give UltimaRAG "eyes and ears."
* **Section 2 (The Thinking Mind):** Query-time agents orchestrated by the LangGraph `MetacognitiveBrain`. Most operate as **nodes in the LangGraph StateGraph**, not as standalone programs.

---

> ⚠️ **Architecture Note — How Agents Actually Communicate**
>
> In the documented design, agents were described as a "linear assembly line."
> The actual implementation uses a **LangGraph StateGraph** (in `metacognitive_brain.py`).
> Most thinking agents are **graph nodes** that receive and return a shared `UltimaRAGState` dict.
> Communication happens through state mutation, not direct function calls between agent objects.
>
> Two agents run **outside the graph** as API-layer middleware: `PromptFirewall` and `IdentityAgent`.
> One agent runs via **post-processing** after the graph completes: `TranslatorAgent`.

---

# Section 1: The Senses (Perception & Foundation Agents)

These 5 agents run entirely in the background when files are uploaded. They are data-extractors that build the knowledge base.

## 1. Vision Perception Agent (The Eyes)
* **Engine Used:** `Qwen2-VL-2B-Instruct` (4-bit quantized for ~6GB GPU VRAM; falls back to CPU)
* **File:** `src/vision/qwen_agent.py` — Class: `QwenVisionAgent`
* **Purpose:** Interprets visual data from images, PDFs, and video frames into high-fidelity text descriptions.
* **How it Works:** Uses Qwen2-VL in Vision-HD tiled processing mode. Divides high-resolution images into sub-tiles, processes each tile to manage VRAM constraints, then merges the semantic output into a unified narrative.
* **📥 Listens To (Inputs):** `ImageProcessor` (which calls it directly via `image_processor.py`)
* **📤 Reports To (Outputs):** `ContentEnricher` (the OCR result + vision narrative are both passed to enrichment)
* **⚠️ Note:** Documentation previously stated `Qwen2-VL-7B`. The actual loaded model is `2B` (hardware constraint, not a bug).

---

## 2. Multilingual OCR Agent (The Reader)
* **Engine Used:** `EasyOCR` (PyTorch backend, GPU-accelerated if `Ultima_FORCE_GPU` env var is set)
* **File:** `src/vision/image_processor.py` — internal to `ImageProcessor`, not a separate class
* **Purpose:** Extracts text from images and embedded PDF pages using bounding-box detection.
* **How it Works:** `ImageProcessor.extract_text()` runs EasyOCR internally using a tiled-scanning approach for large images. Supports 6 core languages (`en`, `hi`, `fr`, `de`, `es`, `zh`).
* **📥 Listens To (Inputs):** Called by `MultimodalManager` during file upload processing
* **📤 Reports To (Outputs):** Its text output is combined with `QwenVisionAgent`'s description and passed to `ContentEnricher`
* **⚠️ Note:** OCR is embedded inside `ImageProcessor`, not a standalone agent class. EasyOCR supports 80+ languages in theory; only 6 are configured here by default.

---

## 3. Advanced Video & Audio Agent (The Listener)
* **Engine Used:** `faster-whisper` (audio) + Intelligent Keyframe Sampling (video)
* **Files:** `src/vision/video_processor.py`, `src/vision/audio_processor.py`
* **Purpose:** Processes temporal media by extracting audio transcripts and key visual snapshots.
* **How it Works:** `faster-whisper` transcribes audio locally. For video, keyframe sampling picks semantically meaningful frames, which are then processed by `QwenVisionAgent`. An LLM fuses the transcript and visual descriptions into a coherent "Media Chronicle."
* **📥 Listens To (Inputs):** `MultimodalManager` during upload of `.mp4`, `.mp3`, `.wav` files
* **📤 Reports To (Outputs):** `ContentEnricher`

---

## 4. Semantic Embedder Agent (The Librarian)
* **Engine Used:** `sentence-transformers/all-MiniLM-L6-v2` (384-dimensional vectors)
* **File:** `src/data/embedder.py` — Class: `DeterministicEmbedder`
* **Purpose:** Converts text chunks into mathematical embedding vectors for semantic search.
* **How it Works:** Uses `sentence-transformers` with a hashing-based deterministic cache — identical text always produces identical vectors, preventing duplicate embeddings and ensuring reproducible search results.
* **📥 Listens To (Inputs):** `DocumentChunker` output (called from the `/index` API endpoint after chunking)
* **📤 Reports To (Outputs):** LanceDB vector database via `UltimaRAGDatabase.add_knowledge()`

---

## 5. Neural Reranker Agent (The Ranker)
* **Engine Used:** `cross-encoder/ms-marco-MiniLM-L-6-v2`
* **Files:** `src/agents/retriever.py` — Class: `RetrieverAgent` (inline CrossEncoder reranking)
* **Purpose:** Refines raw vector search results by deeply scoring each chunk's relevance to the specific query.
* **How it Works:** `RetrieverAgent.retrieve()` loads and runs a CrossEncoder inline to score each retrieved chunk from 0 to 1. Multimodal evidence chunks are protected from being discarded.
* **📥 Listens To (Inputs):** LanceDB hybrid search results (vector + BM25)
* **📤 Reports To (Outputs):** The `retrieval` LangGraph node in `MetacognitiveBrain`, which places the ranked evidence into `UltimaRAGState["evidence"]`
* **⚠️ Note:** A separate `src/agents/reranker.py` (`RerankerModule`) was implemented but is **not wired into the production path** (archived). The actual reranking happens inline inside `RetrieverAgent`.

---

# Section 2: The Thinking Mind (Local LLM Agents via Ollama)

### Phase 1: Gateway & Security (API Middleware — Runs BEFORE LangGraph)

## 6. Prompt Firewall Agent (The Guard)
* **File:** `src/agents/intent_classifier.py` — Class: `PromptFirewall`
* **Singleton:** Initialized once at startup and stored in `app_state.firewall` (NOT instantiated per request)
* **Purpose:** Detects and blocks malicious prompts, prompt injections, and jailbreak attempts before they reach the Brain.
* **How it Works:** Multi-layer scan using Regex-based blacklisting and LLM-based intent scrutiny. Checks for common jailbreak patterns and enforces character limits.
* **📥 Listens To (Inputs):** Every incoming query in `stream_query` and the upload+query endpoint. Runs AFTER identity check, BEFORE the Brain.
* **📤 Reports To (Outputs):** If blocked → returns `FIREWALL_BLOCKED` response directly to user. If safe → allows query to proceed to `MetacognitiveBrain.run()`.
* **⚠️ Note:** Class lives inside `intent_classifier.py` (not its own file). Was previously instantiated on every request — now fixed to a singleton.

---

## 7. Identity Agent (The Receptionist)
* **File:** `src/api/utils.py` — Functions: `is_identity_query()` + `IDENTITY_RESPONSE`
* **Purpose:** Provides immediate, zero-latency branded responses to identity questions without invoking the LLM or Brain.
* **How it Works:** A keyword dictionary checks the query against 15 identity phrases ("who made you", "what are you", etc.). On match, returns a hardcoded branded response instantly.
* **📥 Listens To (Inputs):** First check in `stream_query` — runs BEFORE Firewall and Brain.
* **📤 Reports To (Outputs):** Directly to the user SSE stream. Response is also persisted to conversation history.
* **⚠️ Note:** Not a class — implemented as a utility function. Previously documented as missing from codebase but was always present in `api/utils.py`.

---

## 8. Intent Classifier (The Wise Router)
* **LLM Model Used:** `qwen3:4b`
* **File:** `src/agents/intent_classifier.py` — Class: `IntentClassifier`
* **LangGraph Node:** `route_intent` (the `router` node)
* **Purpose:** Classifies the query intent and decides the routing path through the LangGraph workflow.
* **How it Works:** Uses an Ollama LLM to classify queries into: `RAG`, `PERCEPTION`, `GENERAL`, `MULTI_TASK`, or `HISTORY_RECALL`. Also performs `@mention` file parsing and target language detection.
* **📥 Listens To (Inputs):** `UltimaRAGState` after the `extractor` node runs
* **📤 Reports To (Outputs):** The `decide_path()` conditional edge in LangGraph, which routes to `planner`, `chronicler`, or other nodes based on intent

---

### Phase 2: Evidence Gathering (LangGraph Nodes)

## 9. Content Enrichment Agent (The Narrator)
* **LLM Model Used:** `gemma3:4b`
* **File:** `src/agents/content_enricher.py` — Class: `ContentEnricher`
* **Purpose:** Transforms raw, fragmented extracted data (OCR text, audio transcripts, vision descriptions) into high-fidelity, cohesive knowledge entries for the vector DB.
* **How it Works:** Uses type-specific LLM prompts to enrich each modality. For images: narrative description. For audio: structured transcript. For documents: semantic summary.
* **📥 Listens To (Inputs):** Called during upload ingestion pipeline by `MultimodalManager`
* **📤 Reports To (Outputs):** `DeterministicEmbedder` → LanceDB

---

## 10. Evidence Fusion Agent (The Multimodal Aggregator)
* **File:** `src/agents/fusion_extractor.py` — Class: `UniversalFusionExtractor`
* **LangGraph Node:** `extractor` (first node in the graph)
* **Purpose:** Aggregates and organizes all available evidence (document chunks, visual perceptions, audio transcripts) from the conversation and file context into a unified state object.
* **How it Works:** Collects raw document chunks, enriched media narratives, and prior retrieval results. Organizes them into `text_evidence`, `visual_evidence`, and `audio_evidence` buckets within `UltimaRAGState["unified_evidence"]`.
* **📥 Listens To (Inputs):** Initial `UltimaRAGState` (first node to run)
* **📤 Reports To (Outputs):** `IntentClassifier` (via `router` node after `extractor`)

---

## 11. Multi-Stage Planner (The Task Manager)
* **LLM Model Used:** `qwen3:4b` (light)
* **File:** `src/agents/planner.py` — Class: `MultiStagePlanner`
* **LangGraph Node:** `planner`
* **Purpose:** Decomposes complex, multi-intent queries into an ordered Directed Acyclic Graph (DAG) of sub-tasks.
* **How it Works:** For complex queries, uses an LLM to identify which specialized paths are needed (`perception`, `rag`, `direct`) and in what order. Falls back to heuristic logic for simple queries.
* **📥 Listens To (Inputs):** `router` node output (runs if intent is NOT `HISTORY_RECALL`)
* **📤 Reports To (Outputs):** LangGraph conditional edge routes to `perception`, `retrieval`, or `direct_initiator` nodes based on the plan

---

## 12. Retriever Agent (The Librarian)
* **File:** `src/agents/retriever.py` — Class: `RetrieverAgent`
* **LangGraph Node:** `retrieval`
* **Purpose:** Performs hybrid semantic + keyword search over LanceDB and returns the most relevant evidence chunks.
* **How it Works:** Combines dense vector search (FAISS-style via LanceDB) with BM25 sparse search. Applies inline CrossEncoder reranking (see Agent 5). Supports `@mention`-scoped file isolation.
* **📥 Listens To (Inputs):** `planner` node (for RAG-path queries)
* **📤 Reports To (Outputs):** `evaluator` node

---

### Phase 3: Auditing & Healing (LangGraph Nodes)

## 13. NLI Fact Checker Agent (The Auditor)
* **LLM Model Used:** `qwen3:4b`; NLI model: `cross-encoder/ms-marco-MiniLM-L-6-v2`
* **File:** `src/agents/fact_checker.py` — Class: `FactChecker`
* **LangGraph Node:** `critic`
* **Purpose:** Validates the synthesized answer against original evidence using Natural Language Inference.
* **How it Works:** Extracts atomic claims from the answer, cross-references each against source chunks using the NLI CrossEncoder, generates a factuality score, and flags unsupported claims. If below threshold, routes to `healer`.
* **📥 Listens To (Inputs):** `synthesis` or `general_synthesis` node output (the draft answer in state)
* **📤 Reports To (Outputs):** `verify_grounding` conditional node → either `healer` (if score too low) or `ui_orchestrator` (if score passes)

---

## 14. Hallucination Healer (The Surgeon)
* **LLM Model Used:** `deepseek-r1:8b`
* **File:** `src/agents/healer.py` — Class: `HallucinationHealer`
* **LangGraph Node:** `healer`
* **Purpose:** Surgically rewrites flawed responses to eliminate hallucinations and bridge factual gaps.
* **How it Works:** Receives the flagged claims and full evidence (including visual evidence from `unified_evidence`). Uses a corrective prompt with step-by-step `<thinking>` block reasoning to rewrite the answer without adding new errors.
* **📥 Listens To (Inputs):** `critic` node (only triggered when factuality score is below threshold)
* **📤 Reports To (Outputs):** `ui_orchestrator` node

---

## 15. Quality Indicator Agent (The Transparency Gate)
* **File:** `src/agents/refusal_gate.py` — Class: `QualityIndicator` (alias: `RefusalGate`)
* **LangGraph Node:** Invoked within the `ui_orchestrator` (`apply_ui_hints`) node
* **Purpose:** Classifies response confidence and attaches quality metadata for the frontend Fidelity badge.
* **How it Works:** Calculates a composite confidence score from the fact-checker output. Classifies into HIGH/MEDIUM/LOW/VERY_LOW and generates quality warnings. **Never blocks responses** — always shows the answer with transparency indicators.
* **📥 Listens To (Inputs):** Final state after `healer` or `critic` (whichever was last)
* **📤 Reports To (Outputs):** `UltimaRAGState["ui_hints"]` → frontend Fidelity badge and glow intensity
* **⚠️ Note:** File is named `refusal_gate.py` for historical reasons. The class was renamed to `QualityIndicator` during the 2026-02-27 audit. `RefusalGate` remains as a backward-compatible alias.

---

### Phase 4: Specialized Action Agents (Bypass LangGraph — Direct API)

These agents are triggered by clicking action buttons in the UI. They bypass the main LangGraph workflow entirely via `run_agentic_action()`.

## 16. Executive Summary Agent (The C-Suite Reporter)
* **LLM Model Used:** `qwen3:8b` (Heavy)
* **Location:** Inline inside `MetacognitiveBrain.run_agentic_action()` — `EXECUTIVE_SUMMARY` intent branch
* **Purpose:** Generates concise, structured business reports with Core Findings, Key Metrics, Strategic Implications, and Recommended Actions.
* **How it Works:** Pulls vector evidence for the selected documents, then uses Context-Aware XML Few-Shot Prompting with strict length and structure mandates.
* **📥 Listens To (Inputs):** User button click → `/query/agentic_action` endpoint with `intent="EXECUTIVE_SUMMARY"`
* **📤 Reports To (Outputs):** Streamed tokens to UI, then `Action Planner Agent` for Next Best Actions

---

## 17. Deep Insight Agent (The Debate Team)
* **File:** `src/agents/deep_insight_agent.py` — Class: `DeepInsightAgent`
* **Purpose:** Uncovers latent contradictions and deeper patterns through a 3-stage multi-agent reflection loop.
* **How it Works:** Three sub-agents run sequentially: **Analyst** (drafts the insight), **Skeptic** (challenges and stress-tests it), **Synthesizer** (produces the final peer-reviewed analysis). Each stage streams live "Cognitive Trace" events to the UI.
* **📥 Listens To (Inputs):** User button click → `/query/agentic_action` endpoint with `intent="DEEP_INSIGHT"`
* **📤 Reports To (Outputs):** Streamed tokens and thought events to UI, then `Action Planner Agent`

---

## 18. Risk Assessment Agent (The Vulnerability Scanner)
* **LLM Model Used:** `qwen3:8b` (Heavy, JSON mode)
* **Location:** Inline inside `MetacognitiveBrain.run_agentic_action()` — `RISK_ASSESSMENT` intent branch
* **Purpose:** Scans document evidence for risks, biases, and vulnerabilities, structured for Generative UI rendering.
* **How it Works:** Operates in strict JSON mode using `OllamaClient` with `format="json"`. Returns a structured schema with `overall_score`, `risk_level`, `risks[]`, `bias_flags[]`, and `confidence`. The JSON is passed directly to frontend graph widgets.
* **📥 Listens To (Inputs):** User button click → `/query/agentic_action` endpoint with `intent="RISK_ASSESSMENT"`
* **📤 Reports To (Outputs):** `json_chunk` SSE event → frontend Risk Matrix widget, then `Action Planner Agent`

---

## 19. Action Planner Agent (The NBA Engine)
* **LLM Model Used:** `qwen3:4b` (Light)
* **Location:** Inline inside `MetacognitiveBrain.run_agentic_action()` — runs after ALL intents
* **Purpose:** Generates 3 "Next Best Action" (NBA) follow-up suggestions as clickable UI buttons.
* **How it Works:** Analyzes the just-completed agentic output and generates 3 specific 4–7-word imperative phrases contextual to the analysis. Returns a JSON array parsed by the frontend into suggestion pills.
* **📥 Listens To (Inputs):** Final output of whichever agentic intent just ran (Executive Summary, Deep Insight, or Risk Assessment)
* **📤 Reports To (Outputs):** `next_actions` SSE event → frontend suggestion buttons

---

### Phase 5: Memory & History Agents (LangGraph Nodes)

## 20. Semantic Memory Agent (The Recall Engine)
* **File:** `src/core/memory.py` — Class: `MemoryManager`
* **LangGraph Node:** `retrieve_full_history`
* **Purpose:** Retrieves semantically relevant context from past conversations using vector search over interaction history.
* **How it Works:** For topic-specific recall queries, vector-searches the conversation history to pull "memories" from previous turns. For full-context queries, returns recent turns with MemGPT overflow guard (pages out oldest turn when context budget exceeded).
* **📥 Listens To (Inputs):** `router` node (only on `HISTORY_RECALL` intent)
* **📤 Reports To (Outputs):** `chronicler` node with `UltimaRAGState["full_history"]` populated

---

## 21. History Chronicler Agent (The Archivist)
* **LLM Model Used:** `gemma3:4b`
* **File:** `src/agents/metacognitive_brain.py` — Class: `HistoryChroniclerAgent` (inline class)
* **LangGraph Node:** `chronicler`
* **Purpose:** Synthesizes retrieved conversation history into a coherent humanized summary that answers history-based questions.
* **How it Works:** Compresses older chat logs into a dense semantic narrative. Supports `target_language` for multilingual history summaries. Only triggered when intent is `HISTORY_RECALL`.
* **📥 Listens To (Inputs):** `retrieve_full_history` node (receives `UltimaRAGState["full_history"]`)
* **📤 Reports To (Outputs):** `UltimaRAGState["answer"]` directly → final response (bypasses synthesis/critic)

---

## 22. Query Reformulator Agent (The Context Deducer)
* **LLM Model Used:** `qwen3:4b` (Light)
* **File:** `src/agents/metacognitive_brain.py` — Class: `QueryReformulatorAgent` (inline class)
* **LangGraph Node:** `reformulate_query`
* **Purpose:** Rewrites ambiguous or pronoun-heavy queries (e.g., "What about it?") into self-contained search queries using conversation history.
* **How it Works:** Analyzes the last 5 conversation turns to resolve coreferences and expand the query for better retrieval hits.
* **📥 Listens To (Inputs):** `router` node (for short/ambiguous queries on `HISTORY_RECALL` path)
* **📤 Reports To (Outputs):** `retrieve_full_history` node with a disambiguated `search_query` in state

---

## 23. Multi-hop Reasoning (The Logic Bridge)
* **LLM Model Used:** `qwen3:8b` (Heavy, via inline multi-query expansion in `execute_rag`)
* **Location:** Inline inside `MetacognitiveBrain.execute_rag()` node
* **Purpose:** Expands a single query into multiple retrieval variants to bridge logical gaps across documents.
* **How it Works:** Uses Chain-of-Thought (CoT) prompting to generate 3 query variations that cover different aspects of the question (definitions, comparisons, practical implications). All variants are retrieved and their evidence merged.
* **📥 Listens To (Inputs):** `planner` node (for RAG-path queries with complex intent)
* **📤 Reports To (Outputs):** `RetrieverAgent` (called for each query variant), results merged into `UltimaRAGState["evidence"]`
* **⚠️ Note:** The separate `QueryAnalyzer` class (`query_analyzer.py`) implemented this feature but was never wired in — archived. This functionality is implemented inline in the Brain.

---

### Phase 6: Synthesis & Post-Processing

## 24. Cognitive Synthesis (The Storyteller)
* **LLM Model Used:** `qwen3:8b` (Heavy)
* **Location:** Inline inside `MetacognitiveBrain.generate_answer()` — LangGraph `synthesis` node
* **Purpose:** Weaves retrieved evidence into a unified, cinematic final answer with precise citations.
* **How it Works:** Builds a structured context from all evidence sources (visual cards, document chunks, web results). Applies token budget guards (≈4 chars/token heuristic) to prevent VRAM overflow. Uses CoT reasoning in a `<thinking>` block (stripped from final output). Always generates in English; `TranslatorAgent` handles language conversion post-synthesis.
* **📥 Listens To (Inputs):** `evaluator` node output (grounded evidence in state)
* **📤 Reports To (Outputs):** `critic` node (FactChecker reviews the draft)
* **⚠️ Note:** A standalone `SynthesizerAgent` class (`synthesizer.py`) with Parent-Child Context Strategy was implemented but **never wired in** — archived. All synthesis happens inline here.

---

## 25. Translator Agent (The Localization Expert)
* **LLM Model Used:** Configured Ollama model (via `translator_agent.py`)
* **File:** `src/agents/translator_agent.py` — Class: `TranslatorAgent`; singleton: `get_translator()`
* **Purpose:** Provides high-fidelity final-pass translation of the English synthesis result into the user's requested language.
* **How it Works:** Called as a **post-processing step** in `stream_results()` after the LangGraph workflow completes. Only fires when `target_language` is set in state. Uses strict linguistic rules to maintain accuracy and natural phrasing.
* **📥 Listens To (Inputs):** `stream_results()` in `MetacognitiveBrain.run()` — fires after the full graph finishes
* **📤 Reports To (Outputs):** `final_answer` (persisted to conversation history and returned to user)
* **⚠️ Note:** Previously had a **double-translation bug** — the LLM prompt also contained a `lang_directive` forcing the LLM to write in the target language. This caused double translation. Fixed in 2026-02-27 audit: `lang_directive` removed; `TranslatorAgent` is now the single translation authority.

---

## 26. Self-Correction Agent (The Reflector)
* **LLM Model Used:** `qwen3:4b` (Light)
* **File:** `src/agents/reflector.py` — Class: `ReflectionAgent`
* **Purpose:** Enables continuous learning by distilling behavioral rules from failed interactions.
* **How it Works:** Analyzes the negative-feedback query-response pair, deduces an imperative corrective rule (e.g., "Always cite document name when referencing a statistic"), and appends it to `system_guidelines.json`. These guidelines are injected into future system prompts.
* **📥 Listens To (Inputs):** `/query/feedback` endpoint — triggered automatically when `score < 0` (thumbs down)
* **📤 Reports To (Outputs):** `system_guidelines.json` file (on disk) → injected into future LLM prompts
* **⚠️ Note:** This agent IS active and wired into `main.py:765`. It runs as a `BackgroundTask` so it never blocks the response.

---

## 27. Metacognitive Brain (The Master Orchestrator)
* **LLM Models Used:** `qwen3:4b` (Light — routing) & `qwen3:8b` (Heavy — synthesis)
* **File:** `src/agents/metacognitive_brain.py` — Class: `MetacognitiveBrain`
* **Purpose:** The absolute supervisor. Manages the entire LangGraph StateGraph orchestration and all agent coordination.
* **How it Works:** Builds and runs a LangGraph `StateGraph` with conditional edges. Streams results via `astream_events`. Manages MemGPT overflow, knowledge distillation (via `memory.extract_facts`), conversation persistence, and abort-safe streaming. Also handles the `run_agentic_action()` path for button-clicked deep analysis.
* **📥 Listens To (Inputs):** `app_state.brain.run()` called from `/query/stream` and `/query` endpoints (after Identity + Firewall checks pass)
* **📤 Reports To (Outputs):** The End User via SSE stream

---

## Dead Code Registry (Archived — Not Active in Production)

| File | What It Was | Why Archived |
|---|---|---|
| `Garbage/synthesizer.py` | `SynthesizerAgent` with Parent-Child Context Strategy | Synthesis done inline in `MetacognitiveBrain.generate_answer()` |
| `Garbage/query_analyzer.py` | `QueryAnalyzer` with multi-query expansion & intent detection | Multi-query expansion done inline in `execute_rag()`; intent detection inline in `routes.py` |
| `Garbage/humanizer_agent.py` | `HumanizerAgent` with burstiness/active-voice protocols | No call sites anywhere in codebase; cinematic tone comes from LLM prompts |
| `Garbage/reranker.py` | `RerankerModule` standalone CrossEncoder wrapper | Reranking implemented inline in `RetrieverAgent.retrieve()` |
| `Garbage/orchestrator.py` | `AgentOrchestrator` (legacy v1 pipeline) | Replaced by `MetacognitiveBrain` + LangGraph |

---

*End of Architecture Guide — Verified against live source code, 2026-02-27.*
