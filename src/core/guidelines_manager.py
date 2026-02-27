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
GuidelinesManager — Continuous Learning Rules Read Authority
============================================================
SINGLE READ AUTHORITY: Only this class reads system_guidelines.json.
All other modules call app_state.guidelines_manager — never read the file directly.

Responsibilities:
  - Load and cache active rules from system_guidelines.json
  - mtime-based cache invalidation (default: 60s TTL)
  - Hardware-aware rule filtering (5 rules for 4B models, 7 for 8B)
  - Token budget enforcement (150 tokens hard limit)
  - Async-safe with asyncio.Lock for concurrent callers
  - Force-reload (bypasses TTL) called by ReflectionAgent after writes
  - Schema migration v1→v2 (atomic, backup-first, embedding-generating)

Also contains: run_schema_migration() — called once at startup.
"""

import os
import json
import time
import uuid
import asyncio
import threading
import shutil
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any

from .utils import logger
from .embedding_manager import detect_model_size


# =============================================================================
# SCHEMA MIGRATION (Phase 2)
# =============================================================================

def run_schema_migration(guidelines_path: str, embedding_manager=None) -> None:
    """
    Atomic, backup-first migration from v1 (flat string list) → v2 (rich objects).
    Called ONCE at startup before GuidelinesManager initializes.
    App MUST NOT crash due to migration failure.

    Migration steps (exact order):
      1. Check if already v2 → skip
      2. Read current file (or create empty if missing/corrupt)
      3. Write backup → .backup.[YYYYMMDD_HHMMSS].json
      4. Migrate each rule to v2 schema
      5. Write to .temp file
      6. Validate temp
      7. os.replace(temp → final) ← atomic on all platforms
    """
    try:
        path = guidelines_path
        temp_path = path + ".temp"

        # STEP 1: Check if already v2
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if existing.get("schema_version") == "2.0":
                    logger.info("GuidelinesManager: Schema already v2.0 — no migration needed.")
                    return
            except json.JSONDecodeError:
                logger.error("GuidelinesManager: Corrupt JSON detected — will recreate.")
                existing = None
        else:
            existing = None

        # STEP 2: Read current file
        if existing is None:
            if not os.path.exists(path):
                # File doesn't exist — create empty v2
                empty_v2 = {
                    "schema_version": "2.0",
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                    "rules": []
                }
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(empty_v2, f, ensure_ascii=False, indent=2)
                logger.info("GuidelinesManager: Created new empty v2.0 guidelines file.")
                return
            else:
                # Corrupt file — start fresh
                existing = {"guidelines": []}

        # STEP 3: Write backup
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = path + f".backup.{ts}.json"
        try:
            shutil.copy2(path, backup_path)
            backup_size = os.path.getsize(backup_path)
            logger.info(f"GuidelinesManager: Backup written: {backup_path} — {backup_size} bytes")
        except Exception as be:
            logger.warning(f"GuidelinesManager: Backup failed (continuing anyway): {be}")

        # STEP 4: Migrate each rule to v2 schema
        # Handle both old formats:
        #   v1a: {"guidelines": ["rule text 1", "rule text 2"]}  ← flat string list
        #   v1b: {"rules": [{...}, ...]}                          ← partial v2 objects
        old_rules_raw = existing.get("guidelines", existing.get("rules", []))
        migrated_rules = []

        for raw in old_rules_raw:
            rule_id = str(uuid.uuid4())
            now_iso = datetime.now(timezone.utc).isoformat()

            # Extract rule text regardless of format
            if isinstance(raw, str):
                rule_text = raw.strip()
            elif isinstance(raw, dict):
                rule_text = (raw.get("rule") or raw.get("guideline") or "").strip()
            else:
                continue

            if not rule_text:
                continue

            # Generate embedding if EmbeddingManager is available
            embedding = []
            if embedding_manager is not None and hasattr(embedding_manager, "is_ready") and embedding_manager.is_ready:
                try:
                    result = embedding_manager.encode(rule_text)
                    if result is not None:
                        embedding = result
                        logger.info(f"GuidelinesManager: Embedding generated for rule {rule_id}")
                    else:
                        logger.info(f"GuidelinesManager: Embedding unavailable for rule {rule_id} — using []")
                except Exception:
                    logger.info(f"GuidelinesManager: Embedding unavailable for rule {rule_id} — using []")
            else:
                logger.info(f"GuidelinesManager: Embedding unavailable for rule {rule_id} — using []")

            migrated_rule = {
                "id": rule_id,
                "user_id": "default",
                "rule": rule_text,
                "embedding": embedding,
                "confidence": raw.get("confidence", 0.5) if isinstance(raw, dict) else 0.5,
                "trigger_count": raw.get("trigger_count", 1) if isinstance(raw, dict) else 1,
                "query_types": raw.get("query_types", ["general"]) if isinstance(raw, dict) else ["general"],
                "language_hint": raw.get("language_hint", "auto") if isinstance(raw, dict) else "auto",
                "created_at": raw.get("created_at", now_iso) if isinstance(raw, dict) else now_iso,
                "last_triggered": raw.get("last_triggered", now_iso) if isinstance(raw, dict) else now_iso,
                "status": raw.get("status", "active") if isinstance(raw, dict) else "active",
                "source_summary": raw.get("source_summary", "Migrated from previous version") if isinstance(raw, dict) else "Migrated from previous version",
                "model_generated_by": raw.get("model_generated_by", "unknown") if isinstance(raw, dict) else "unknown",
            }
            migrated_rules.append(migrated_rule)

        # STEP 5: Build final v2 structure
        new_data = {
            "schema_version": "2.0",
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "rules": migrated_rules
        }

        # STEP 6: Write to temp
        json_str = json.dumps(new_data, ensure_ascii=False, indent=2)
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(json_str)

        # Validate temp
        with open(temp_path, "r", encoding="utf-8") as f:
            test = json.load(f)
        assert test.get("schema_version") == "2.0", "schema_version mismatch"
        assert isinstance(test.get("rules"), list), "'rules' not a list"
        for r in test["rules"]:
            for key in ("id", "user_id", "rule", "confidence", "status"):
                assert key in r, f"Rule missing required key: {key}"

        # STEP 7: Atomic rename
        os.replace(temp_path, path)
        logger.info(f"GuidelinesManager: Migration complete. {len(migrated_rules)} rules migrated to schema v2.0.")

    except Exception as e:
        import traceback
        logger.error(f"GuidelinesManager: Migration FAILED: {e}\n{traceback.format_exc()}")
        # Try to restore from backup
        try:
            if "backup_path" in dir() and os.path.exists(backup_path):
                shutil.copy2(backup_path, guidelines_path)
                logger.info("GuidelinesManager: Restored from backup.")
        except Exception as re:
            logger.error(f"GuidelinesManager: Backup restoration also failed: {re}")
        # Clean up temp if it exists
        try:
            if os.path.exists(guidelines_path + ".temp"):
                os.remove(guidelines_path + ".temp")
        except Exception:
            pass
        # Create empty v2 as last-resort fallback
        try:
            fallback = {
                "schema_version": "2.0",
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "rules": []
            }
            os.makedirs(os.path.dirname(guidelines_path), exist_ok=True)
            with open(guidelines_path, "w", encoding="utf-8") as f:
                json.dump(fallback, f, ensure_ascii=False, indent=2)
            logger.info("GuidelinesManager: Created empty v2 fallback after migration failure.")
        except Exception as fe:
            logger.error(f"GuidelinesManager: Fallback creation also failed: {fe}")


# =============================================================================
# GUIDELINES MANAGER
# =============================================================================

class GuidelinesManager:
    """
    Singleton reading authority for system_guidelines.json.

    Provides get_relevant_rules() for the Brain and force_reload() for ReflectionAgent.
    Uses mtime-based cache invalidation to avoid file I/O on every request.
    Hardware-aware (4B vs 8B model) rule count and token budget limits.

    Thread safety:
      - asyncio.Lock for coroutine callers (get_relevant_rules, force_reload)
      - threading.Lock reserved for future sync callers
    """

    def __init__(
        self,
        guidelines_path: str,
        model_name: str,
        cache_ttl_seconds: int = 60
    ):
        self._path = guidelines_path
        self._model_size = detect_model_size(model_name)
        self._cache_ttl = cache_ttl_seconds
        self._rules: List[Dict] = []
        self._active_rules: List[Dict] = []
        self._last_mtime: float = 0.0
        self._last_check_time: float = 0.0
        self._lock = asyncio.Lock()
        self._sync_lock = threading.Lock()
        self._loaded = False
        self._load()  # synchronous load at init (before event loop starts)
        logger.info(
            f"GuidelinesManager: Loaded. Active: {len(self._active_rules)} | "
            f"Model size: {self._model_size} | "
            f"Max inject: {'5' if self._model_size == '4B' else '7'} rules"
        )

    # ── SYNC FILE LOAD (called from __init__ before event loop) ──────

    def _load(self) -> None:
        """Synchronous file load. Safe to call from __init__."""
        try:
            if not os.path.exists(self._path):
                logger.warning(
                    f"GuidelinesManager: {self._path} not found. Starting with 0 rules."
                )
                self._rules = []
                self._active_rules = []
                self._loaded = True
                return

            mtime = os.path.getmtime(self._path)
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._rules = data.get("rules", [])
            self._active_rules = [r for r in self._rules if r.get("status") == "active"]
            self._last_mtime = mtime
            self._loaded = True

        except json.JSONDecodeError as e:
            logger.error(f"GuidelinesManager: Corrupt JSON — {e}. Keeping previous cache.")
            if not self._loaded:
                self._rules = []
                self._active_rules = []
        except Exception as e:
            logger.error(f"GuidelinesManager: Load error — {e}")
            if not self._loaded:
                self._rules = []
                self._active_rules = []

    # ── ASYNC RELOAD (runs inside event loop without blocking it) ─────

    async def _async_reload(self) -> None:
        """Reloads file from disk without blocking the event loop."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._load)

    # ── PUBLIC: GET RELEVANT RULES (called by Brain per request) ─────

    async def get_relevant_rules(
        self,
        query_type: str = "general",
        token_budget: int = 150
    ) -> List[Dict]:
        """
        Returns filtered, scored, hardware-capped list of active rules.
        Fast path: no file I/O unless cache TTL has expired.

        Args:
            query_type: Intent type from IntentClassifier
                        ("factual", "reasoning", "multilingual", "technical",
                         "creative", "general")
            token_budget: Max tokens to allocate for guidelines (hard limit: 150)

        Returns:
            list of rule dicts, best matching rules first, within budget
        """
        async with self._lock:
            # Cache invalidation check (max once per TTL seconds)
            now = time.monotonic()
            if (now - self._last_check_time) >= self._cache_ttl:
                try:
                    current_mtime = os.path.getmtime(self._path)
                    if current_mtime != self._last_mtime:
                        await self._async_reload()
                except FileNotFoundError:
                    pass  # file deleted — keep existing cache
                self._last_check_time = now

            if not self._active_rules:
                return []

            # Score rules by relevance to query_type
            def score(rule: Dict) -> float:
                conf = rule.get("confidence", 0.5)
                qtypes = rule.get("query_types", ["general"])
                if query_type in qtypes:
                    return conf * 1.0
                elif "general" in qtypes:
                    return conf * 0.6
                else:
                    return conf * 0.3

            scored = sorted(self._active_rules, key=score, reverse=True)

            # Hardware-aware rule count limit
            max_rules = 5 if self._model_size == "4B" else 7
            scored = scored[:max_rules]

            # Token budget enforcement (~4 chars per token heuristic)
            selected = []
            token_count = 0.0
            for rule in scored:
                rule_tokens = len(rule.get("rule", "")) / 4.0
                if token_count + rule_tokens <= token_budget:
                    selected.append(rule)
                    token_count += rule_tokens
                else:
                    break

            return selected

    # ── PUBLIC: FORCE RELOAD (called by ReflectionAgent after writes) ─

    async def force_reload(self) -> None:
        """
        Bypasses TTL. Reloads immediately from disk.
        Called by ReflectionAgent after a successful atomic write.
        """
        async with self._lock:
            await self._async_reload()
            self._last_check_time = time.monotonic()  # reset TTL timer
            logger.info(
                f"GuidelinesManager: force_reload complete. "
                f"Active: {len(self._active_rules)} | "
                f"Total: {len(self._rules)}"
            )

    # ── PUBLIC: GET STATS (admin endpoint & startup diagnostics) ──────

    def get_stats(self) -> Dict[str, Any]:
        """Returns summary statistics. Safe to call synchronously."""
        active = len([r for r in self._rules if r.get("status") == "active"])
        retired = len([r for r in self._rules if r.get("status") == "retired"])
        pending = len([r for r in self._rules if r.get("status") == "pending_review"])
        return {
            "active_rules": active,
            "retired_rules": retired,
            "pending_review": pending,
            "total_rules": len(self._rules),
            "model_size": self._model_size,
            "guidelines_path": self._path,
            "schema_version": "2.0"
        }
