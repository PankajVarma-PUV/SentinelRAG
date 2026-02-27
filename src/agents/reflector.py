# UltimaRAG — Multi-Agent RAG System
# Copyright (C) 2026 Pankaj Varma
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
ReflectionAgent — Continuous Learning Loop (Write Path)
========================================================
Triggered by negative feedback (thumbs-down). Analyzes failed interactions,
generates behavioural rules via Ollama structured output, deduplicates using
HuggingFace embeddings, and writes atomically to system_guidelines.json.

Key design decisions:
  - schedule_reflection() returns IMMEDIATELY (fire-and-forget)
  - asyncio.Semaphore(1) prevents concurrent JSON writes
  - Task registry (_background_tasks set) prevents GC of in-flight tasks
  - done-callback surfaces exceptions to logs (no silent swallowing)
  - os.replace() for atomic write (identical to GuidelinesManager's write path)
  - force_reload() called on GuidelinesManager after every successful write

LLM calls go via Ollama REST (format="json") — NEVER HuggingFace.
Embedding calls go via EmbeddingManager (HuggingFace, CPU) — NEVER Ollama.
"""

import os
import re
import json
import uuid
import asyncio
import httpx
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field, field_validator

from ..core.utils import logger
from ..core.config import Config
from ..core.embedding_manager import detect_model_size


# =============================================================================
# PYDANTIC SCHEMA FOR STRUCTURED OLLAMA OUTPUT
# =============================================================================

class GeneratedRule(BaseModel):
    """Pydantic schema for structured LLM rule extraction via Ollama format=json."""

    rule: str = Field(
        description=(
            "A specific, actionable behavioral instruction for the AI. "
            "Must START with a verb (Always, When, Avoid, Ensure, Never). "
            "Between 15 and 150 words. "
            "Describes exactly what to do differently next time. "
            "NOT a complaint, NOT vague. "
            "Good: 'When the user asks in Hindi, ensure the entire response "
            "including technical terms is in Hindi. Do not mix English phrases.' "
            "Bad: 'Answer better in Hindi.'"
        )
    )
    query_type: str = Field(
        description=(
            "One of: factual | reasoning | multilingual | technical | creative | general"
        )
    )
    language_hint: str = Field(
        description=(
            "Primary language code of the failed query: 'en', 'hi', 'te', 'auto', etc."
        )
    )
    source_summary: str = Field(
        description=(
            "10-20 words describing what went wrong. "
            "Example: 'Response was in English when user asked in Hindi'"
        )
    )
    confidence_in_rule: float = Field(
        ge=0.1, le=1.0,
        description="Confidence this rule is useful and actionable, 0.1–1.0"
    )

    @field_validator("rule")
    @classmethod
    def validate_rule_length(cls, v: str) -> str:
        words = v.split()
        if len(words) < 15:
            raise ValueError(f"Rule too short: {len(words)} words (minimum 15)")
        if len(words) > 150:
            raise ValueError(f"Rule too long: {len(words)} words (maximum 150)")
        return v

    @field_validator("query_type")
    @classmethod
    def validate_query_type(cls, v: str) -> str:
        valid = {"factual", "reasoning", "multilingual", "technical", "creative", "general"}
        return v.lower() if v.lower() in valid else "general"


# =============================================================================
# REFLECTION AGENT
# =============================================================================

class ReflectionAgent:
    """
    Agent 26 (updated): Continuous Learning — Write Path

    Triggered on thumbs-down feedback. Writes new rules to system_guidelines.json.
    GuidelinesManager (read path) picks up changes via force_reload().

    NEVER await this from an HTTP handler. Use schedule_reflection() only.
    """

    # Class-level task registry — prevents GC of fire-and-forget tasks (CPython pattern)
    _background_tasks: set = set()

    # Semaphore: only one reflection writes at a time (single-user, prevents JSON races)
    _semaphore: asyncio.Semaphore = asyncio.Semaphore(1)

    def __init__(self, app_state: Any):
        """
        Args:
            app_state: The FastAPI app_state object.
                       Must have: .guidelines_manager, .embedding_manager
        """
        self._app_state = app_state
        logger.info(
            f"ReflectionAgent initialized | "
            f"Model: {Config.learning.PRIMARY_OLLAMA_MODEL} | "
            f"Guidelines: {Config.learning.GUIDELINES_PATH}"
        )

    # ── PUBLIC API ────────────────────────────────────────────────────

    def schedule_reflection(self, feedback_data: dict) -> None:
        """
        Creates a background task for reflection learning.
        NEVER awaited by the caller — returns immediately.
        The HTTP handler calls this and returns HTTP 200 instantly.

        Args:
            feedback_data: dict with keys:
              query (str), response (str), feedback_type (str),
              feedback_id (str, optional), user_id (str, optional)
        """
        feedback_id = feedback_data.get("feedback_id") or str(uuid.uuid4())
        feedback_data["feedback_id"] = feedback_id

        task = asyncio.create_task(
            self._run_with_semaphore(feedback_data),
            name=f"reflection_{feedback_id}"
        )

        # Store reference to prevent GC (CPython recommended pattern for fire-and-forget)
        ReflectionAgent._background_tasks.add(task)

        # Done callback: removes from registry + surfaces exceptions to logs
        task.add_done_callback(ReflectionAgent._task_done_callback)

        logger.info(f"ReflectionAgent TASK_CREATED | feedback_id={feedback_id}")

    @staticmethod
    def _task_done_callback(task: asyncio.Task) -> None:
        """Removes completed task from registry and surfaces any exception."""
        ReflectionAgent._background_tasks.discard(task)
        try:
            task.result()  # re-raises exception if one occurred
        except asyncio.CancelledError:
            logger.info(f"ReflectionAgent task cancelled: {task.get_name()}")
        except Exception as e:
            logger.error(
                f"ReflectionAgent task FAILED: {task.get_name()} | "
                f"Error: {type(e).__name__}: {e}",
                exc_info=True
            )

    # ── SEMAPHORE WRAPPER ─────────────────────────────────────────────

    async def _run_with_semaphore(self, feedback_data: dict) -> None:
        """Ensures only one reflection write runs at a time."""
        async with ReflectionAgent._semaphore:
            await self._process(feedback_data)

    # ── CORE PROCESSING ───────────────────────────────────────────────

    async def _process(self, feedback_data: dict) -> None:
        """
        Full reflection pipeline. Never call directly — use schedule_reflection().

        Steps:
          1. Quality gate        — reject low-quality or non-negative feedback
          2. Generate rule       — Ollama structured output, temperature=0
          3. Post-gen validation — length, confidence checks
          4. Load current rules  — sync read while holding semaphore
          5. Dedup               — embedding sim ≥ 0.82, or keyword fallback
          6. Create/reinforce    — new rule or increment trigger_count
          7. Lifecycle           — retire stale rules, enforce cap
          8. Atomic write        — write-to-temp → os.replace → force_reload
        """
        # ── STEP 1: Quality Gate ──────────────────────────────────────
        query = (feedback_data.get("query") or "").strip()
        response = (feedback_data.get("response") or "").strip()
        feedback_type = str(feedback_data.get("feedback_type", "")).lower()
        feedback_id = feedback_data.get("feedback_id", "n/a")

        if len(query) < Config.learning.REFLECTION_MIN_QUERY_LEN:
            logger.info(
                f"ReflectionAgent SKIP [{feedback_id}]: "
                f"query too short ({len(query)} chars)"
            )
            return
        if len(response) < Config.learning.REFLECTION_MIN_RESPONSE_LEN:
            logger.info(
                f"ReflectionAgent SKIP [{feedback_id}]: "
                f"response too short ({len(response)} chars)"
            )
            return
        if feedback_type not in {"thumbs_down", "negative", "dislike", "bad", "0", "false"}:
            logger.info(
                f"ReflectionAgent SKIP [{feedback_id}]: "
                f"not a negative feedback signal (type={feedback_type})"
            )
            return

        logger.info(f"ReflectionAgent START [{feedback_id}] | query={query[:60]}...")

        # ── STEP 2: Generate Rule via Ollama ──────────────────────────
        generated_rule = await self._generate_rule(query, response)
        if generated_rule is None:
            return

        # ── STEP 3: Post-Generation Validation ───────────────────────
        if generated_rule.confidence_in_rule < Config.learning.REFLECTION_MIN_CONFIDENCE:
            logger.info(
                f"ReflectionAgent SKIP [{feedback_id}]: "
                f"low confidence ({generated_rule.confidence_in_rule:.2f} < "
                f"{Config.learning.REFLECTION_MIN_CONFIDENCE})"
            )
            return

        words = generated_rule.rule.split()
        if not (15 <= len(words) <= 150):
            logger.info(
                f"ReflectionAgent SKIP [{feedback_id}]: "
                f"rule length invalid ({len(words)} words)"
            )
            return

        if len(generated_rule.source_summary.split()) < 5:
            logger.info(
                f"ReflectionAgent SKIP [{feedback_id}]: source_summary too short"
            )
            return

        # ── STEP 4: Load current guidelines ──────────────────────────
        current_data = self._read_guidelines_raw()
        rules = current_data.get("rules", [])

        # ── STEP 5: Semantic Deduplication ────────────────────────────
        duplicate_id = await self._find_duplicate(generated_rule.rule, rules)

        if duplicate_id:
            rules = self._reinforce_rule(rules, duplicate_id)
        else:
            new_rule = await self._create_rule_entry(generated_rule)
            rules.append(new_rule)
            logger.info(
                f"ReflectionAgent NEW_RULE [{feedback_id}] "
                f"id={new_rule['id']} | "
                f"type={new_rule['query_types']} | "
                f"conf={new_rule['confidence']:.2f} | "
                f"summary={new_rule['source_summary']}"
            )

        # ── STEP 6: Lifecycle Management ─────────────────────────────
        rules = self._run_lifecycle(rules)

        # ── STEP 7: Atomic Write ──────────────────────────────────────
        success = await self._atomic_write(current_data, rules)

        if success:
            # Notify GuidelinesManager to reload immediately (bypasses TTL)
            if hasattr(self._app_state, "guidelines_manager"):
                await self._app_state.guidelines_manager.force_reload()

    # ── RULE GENERATION VIA OLLAMA ────────────────────────────────────

    async def _generate_rule(self, query: str, response: str) -> Optional[GeneratedRule]:
        """
        Calls Ollama with format='json' at temperature=0.
        Uses the PRIMARY model (same as Brain).
        Retries once on failure.
        Parses and validates via Pydantic — rejects malformed/vague rules.
        """
        # Truncate to stay within token budget for local models
        truncated_response = response[:600]  # ~150 tokens — conservative for 4B/8B

        system_prompt = (
            "You are a behavioral learning agent for an AI assistant. "
            "Analyze the failed interaction and extract ONE specific, actionable "
            "behavioral rule to prevent this failure in the future. "
            "Output ONLY valid JSON matching this schema:\n"
            '{"rule": "...", "query_type": "...", "language_hint": "...", '
            '"source_summary": "...", "confidence_in_rule": 0.0}\n'
            "No explanations, no markdown. Just the JSON object."
        )

        user_prompt = (
            f"Failed query: {query}\n\n"
            f"Failed response (truncated): {truncated_response}\n\n"
            f"User feedback: Negative (thumbs down)\n\n"
            f"Extract one behavioral rule to improve future responses."
        )

        full_prompt = f"SYSTEM: {system_prompt}\n\nUSER: {user_prompt}\n\nASSISTANT:"

        model = Config.learning.PRIMARY_OLLAMA_MODEL
        base_url = Config.ollama.BASE_URL

        for attempt in range(2):
            try:
                payload = {
                    "model": model,
                    "prompt": full_prompt,
                    "stream": False,
                    "format": "json",
                    "options": {
                        "temperature": 0.0,
                        "num_predict": 512,
                    }
                }

                async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=5.0)) as client:
                    http_response = await client.post(
                        f"{base_url}/api/generate",
                        json=payload
                    )
                    if http_response.status_code != 200:
                        raise RuntimeError(
                            f"Ollama API error: {http_response.status_code} — "
                            f"{http_response.text[:200]}"
                        )
                    result = http_response.json()

                raw_text = result.get("response", "")

                # Strip thinking tags if model leaks them
                raw_text = re.sub(
                    r"<think>[\s\S]*?</think>", "", raw_text, flags=re.IGNORECASE
                ).strip()

                # Extract JSON object
                json_match = re.search(r"\{[\s\S]*\}", raw_text)
                if json_match:
                    data = json.loads(json_match.group())
                else:
                    data = json.loads(raw_text)

                rule = GeneratedRule.model_validate(data)
                logger.info(
                    f"ReflectionAgent: Rule generated | "
                    f"type={rule.query_type} | "
                    f"conf={rule.confidence_in_rule:.2f} | "
                    f"words={len(rule.rule.split())}"
                )
                return rule

            except Exception as e:
                if attempt == 0:
                    logger.warning(
                        f"ReflectionAgent: Rule generation failed (attempt 1): {e}. Retrying..."
                    )
                else:
                    logger.error(
                        f"ReflectionAgent: Rule generation failed after retry: {e}"
                    )
                    return None

        return None

    # ── DEDUPLICATION ─────────────────────────────────────────────────

    async def _find_duplicate(
        self, new_rule_text: str, existing_rules: List[Dict]
    ) -> Optional[str]:
        """
        Returns id of duplicate rule if found, None otherwise.
        Embedding dedup preferred (HuggingFace via run_in_executor).
        Keyword overlap fallback if EmbeddingManager unavailable.
        """
        active_rules = [r for r in existing_rules if r.get("status") == "active"]
        if not active_rules:
            return None

        embedding_manager = getattr(self._app_state, "embedding_manager", None)

        if embedding_manager and embedding_manager.is_ready:
            # Run in executor — SentenceTransformer.encode is synchronous
            loop = asyncio.get_running_loop()
            new_embedding = await loop.run_in_executor(
                None, embedding_manager.encode, new_rule_text
            )

            if new_embedding is not None:
                threshold = Config.learning.EMBEDDING_SIMILARITY_THRESHOLD
                for rule in active_rules:
                    stored_emb = rule.get("embedding", [])
                    if len(stored_emb) == 384:
                        sim = embedding_manager.cosine_similarity(new_embedding, stored_emb)
                        if sim >= threshold:
                            logger.info(
                                f"ReflectionAgent DEDUP: embedding match "
                                f"id={rule['id']} sim={sim:.3f}"
                            )
                            return rule["id"]
                return None

        # Keyword overlap fallback
        logger.debug("ReflectionAgent: Using keyword fallback for dedup")
        return self._keyword_dedup(new_rule_text, active_rules)

    def _keyword_dedup(
        self, new_text: str, active_rules: List[Dict]
    ) -> Optional[str]:
        """Jaccard overlap deduplication using stopword-filtered token sets."""
        STOPWORDS = {
            "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "could",
            "should", "may", "might", "must", "can", "to", "of", "in", "for",
            "on", "with", "at", "by", "from", "as", "it", "its", "that", "this",
            "and", "or", "but", "not", "no", "so", "if", "when", "then", "than"
        }
        new_tokens = set(new_text.lower().split()) - STOPWORDS

        for rule in active_rules:
            existing_tokens = set(rule.get("rule", "").lower().split()) - STOPWORDS
            if not new_tokens or not existing_tokens:
                continue
            intersection = new_tokens & existing_tokens
            union = new_tokens | existing_tokens
            overlap = len(intersection) / len(union) if union else 0
            if overlap >= 0.55:
                logger.info(
                    f"ReflectionAgent DEDUP (keyword): match "
                    f"id={rule['id']} overlap={overlap:.3f}"
                )
                return rule["id"]
        return None

    # ── RULE REINFORCEMENT ────────────────────────────────────────────

    def _reinforce_rule(self, rules: List[Dict], rule_id: str) -> List[Dict]:
        """Increments trigger_count and boosts confidence for an existing rule."""
        for rule in rules:
            if rule.get("id") == rule_id:
                old_conf = rule.get("confidence", 0.5)
                rule["trigger_count"] = rule.get("trigger_count", 1) + 1
                rule["confidence"] = round(min(1.0, old_conf + 0.08), 3)
                rule["last_triggered"] = datetime.now(timezone.utc).isoformat()
                logger.info(
                    f"ReflectionAgent REINFORCE id={rule_id} | "
                    f"conf={old_conf:.3f}→{rule['confidence']:.3f} | "
                    f"count={rule['trigger_count']}"
                )
                break
        return rules

    # ── NEW RULE CREATION ─────────────────────────────────────────────

    async def _create_rule_entry(self, generated: GeneratedRule) -> Dict:
        """Build the full rule dict from a GeneratedRule."""
        embedding_manager = getattr(self._app_state, "embedding_manager", None)
        embedding = []

        if embedding_manager and embedding_manager.is_ready:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, embedding_manager.encode, generated.rule
            )
            if result is not None:
                embedding = result

        now = datetime.now(timezone.utc).isoformat()

        return {
            "id": str(uuid.uuid4()),
            "user_id": "default",          # multi-user hook — future: real user_id
            "rule": generated.rule,
            "embedding": embedding,
            # Scale down initial confidence — trust grows through reinforcement
            "confidence": round(generated.confidence_in_rule * 0.6, 3),
            "trigger_count": 1,
            "query_types": [generated.query_type],
            "language_hint": generated.language_hint,
            "created_at": now,
            "last_triggered": now,
            "status": "active",
            "source_summary": generated.source_summary,
            "model_generated_by": Config.learning.PRIMARY_OLLAMA_MODEL,
        }

    # ── LIFECYCLE MANAGEMENT ──────────────────────────────────────────

    def _run_lifecycle(self, rules: List[Dict]) -> List[Dict]:
        """
        Retirement check: stale + low-reinforcement rules → retired.
        Rule cap: hardware-aware maximum active count.
        """
        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)

        # Retirement check: stale AND low-reinforcement
        for rule in rules:
            if rule.get("status") != "active":
                continue
            last_triggered_str = rule.get("last_triggered", rule.get("created_at", ""))
            try:
                last_triggered = datetime.fromisoformat(last_triggered_str)
                if last_triggered.tzinfo is None:
                    last_triggered = last_triggered.replace(tzinfo=timezone.utc)
                if (last_triggered < thirty_days_ago
                        and rule.get("trigger_count", 1) < 3):
                    rule["status"] = "retired"
                    logger.info(
                        f"ReflectionAgent RETIRE id={rule['id']} | "
                        f"reason=stale_low_reinforcement | "
                        f"count={rule.get('trigger_count', 0)}"
                    )
            except (ValueError, TypeError):
                pass

        # Rule cap
        model_size = detect_model_size(Config.learning.PRIMARY_OLLAMA_MODEL)
        cap = 30 if model_size == "4B" else 50

        active_rules = [r for r in rules if r.get("status") == "active"]
        if len(active_rules) > cap:
            active_rules.sort(key=lambda r: r.get("confidence", 0))
            to_retire = len(active_rules) - cap
            retired_count = 0
            for rule in active_rules:
                if retired_count >= to_retire:
                    break
                rule["status"] = "retired"
                logger.info(
                    f"ReflectionAgent RETIRE id={rule['id']} | "
                    f"reason=cap_exceeded | conf={rule.get('confidence', 0):.3f}"
                )
                retired_count += 1
            logger.info(
                f"ReflectionAgent: Rule cap hit. Retired {retired_count} rules. "
                f"Active count now at cap ({cap})."
            )

        return rules

    # ── ATOMIC WRITE ──────────────────────────────────────────────────

    async def _atomic_write(
        self, original_data: dict, updated_rules: List[Dict]
    ) -> bool:
        """
        Write-to-temp → os.replace() → atomic.
        All file I/O runs in executor to avoid blocking the event loop.
        """
        path = Config.learning.GUIDELINES_PATH
        temp_path = path + ".temp"

        try:
            updated_data = {
                **original_data,
                "schema_version": "2.0",
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "rules": updated_rules,
            }

            # Serialize in memory
            json_str = json.dumps(updated_data, ensure_ascii=False, indent=2)

            # Round-trip validation
            test_parse = json.loads(json_str)
            if "rules" not in test_parse:
                raise ValueError("Round-trip validation failed: 'rules' key missing")

            loop = asyncio.get_running_loop()

            # Write to temp (blocking I/O → executor)
            def _write():
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(temp_path, "w", encoding="utf-8") as f:
                    f.write(json_str)

            await loop.run_in_executor(None, _write)

            # Atomic rename
            await loop.run_in_executor(None, os.replace, temp_path, path)

            active_count = len([r for r in updated_rules if r.get("status") == "active"])
            retired_count = len([r for r in updated_rules if r.get("status") == "retired"])
            logger.info(
                f"Guidelines saved. Active: {active_count} | "
                f"Retired: {retired_count} | Total: {len(updated_rules)}"
            )
            return True

        except Exception as e:
            logger.error(f"ReflectionAgent: Atomic write FAILED: {e}", exc_info=True)
            # Clean up temp file
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass
            return False

    # ── RAW READ (sync — only called while holding semaphore) ─────────

    def _read_guidelines_raw(self) -> dict:
        """Sync read of raw guidelines dict. Safe because we hold the semaphore."""
        try:
            with open(Config.learning.GUIDELINES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {"schema_version": "2.0", "rules": []}
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"ReflectionAgent: Raw read error: {e}")
            return {"schema_version": "2.0", "rules": []}

    # ── GRACEFUL SHUTDOWN ─────────────────────────────────────────────

    @classmethod
    async def await_pending_tasks(cls) -> None:
        """
        Called during app shutdown to complete any in-progress reflection tasks.
        Prevents mid-write corruption on server restart.
        Waits up to 15 seconds, then cancels remaining tasks.
        """
        pending = list(cls._background_tasks)
        if not pending:
            return
        logger.info(
            f"ReflectionAgent: Waiting for {len(pending)} pending tasks on shutdown..."
        )
        try:
            await asyncio.wait_for(
                asyncio.gather(*pending, return_exceptions=True),
                timeout=15.0
            )
            logger.info("ReflectionAgent: All pending tasks completed.")
        except asyncio.TimeoutError:
            logger.warning("ReflectionAgent: Shutdown timeout. Cancelling remaining tasks.")
            for task in pending:
                task.cancel()
