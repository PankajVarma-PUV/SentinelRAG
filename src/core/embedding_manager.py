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
EmbeddingManager — HuggingFace Sentence Transformer Singleton
==============================================================
ARCHITECTURE LAW: This module loads an embedding model from the HuggingFace
venv ONLY. It must NEVER use Ollama and MUST run on CPU to avoid competing
with the primary LLM for VRAM.

Responsibilities:
  - Load all-MiniLM-L6-v2 once at startup (~90MB, 384-dim output)
  - Expose encode() and cosine_similarity() for the learning loop
  - Degrade gracefully to a keyword-overlap fallback if unavailable
  - Cache warm: run one encode() on init to force weight loading into RAM

Registered as app_state.embedding_manager in main.py lifespan.
"""

from ..core.utils import logger


def detect_model_size(model_name: str) -> str:
    """
    Derives model size tier from the Ollama model name string.
    This is the SINGLE source of truth for hardware-aware decisions.
    Never hardcode a MODEL_SIZE config string — always call this function.

    Returns "4B" or "8B" (8B is the safe default for unknown models).

    Examples:
      detect_model_size("gemma3:4b")    → "4B"
      detect_model_size("qwen3:8b")     → "8B"
      detect_model_size("llama3:70b")   → "8B"  (safe default)
    """
    lower = model_name.lower()
    small_markers = ["4b", "3b", "2b", "1b", "0.5b", "0.5", "_4b", "_3b", "_2b"]
    large_markers = ["8b", "7b", "6b", "9b", "_8b", "_7b", "_6b"]

    for m in small_markers:
        if m in lower:
            return "4B"
    for m in large_markers:
        if m in lower:
            return "8B"
    return "8B"  # safe default: conservative limits


class EmbeddingManager:
    """
    HuggingFace Sentence Transformer singleton for the continuous learning loop.

    NEVER runs on GPU — device='cpu' is mandatory to avoid VRAM competition
    with the primary Ollama LLM (which owns all GPU memory on a 6GB card).

    Usage:
        emb = EmbeddingManager()
        success = emb.initialize()      # call once at startup
        vec = emb.encode("some text")   # returns list[float] or None
        sim = emb.cosine_similarity(a, b)  # float in [-1.0, 1.0]
    """

    def __init__(self):
        self._model = None
        self._model_ready = False
        self._load_error: Exception | None = None

    def initialize(self) -> bool:
        """
        Load the embedding model. Called ONCE at startup.
        Returns True if successful, False if fallback mode is needed.
        """
        try:
            logger.info("EmbeddingManager: Loading all-MiniLM-L6-v2 from HuggingFace...")
            logger.info("  → First run: model download may take 30-90 seconds (~90MB)")
            logger.info("  → Subsequent runs: loads from local HuggingFace cache instantly")

            from sentence_transformers import SentenceTransformer  # type: ignore

            # device='cpu' is MANDATORY — must never compete with primary LLM for VRAM
            self._model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
            self._model_ready = True

            # Warm up: encode one sentence to force weight loading into CPU memory
            _ = self._model.encode(["warmup"], show_progress_bar=False)

            logger.info("EmbeddingManager: ✅ Ready. 384-dim embeddings on CPU.")
            return True

        except Exception as e:
            self._load_error = e
            self._model_ready = False
            logger.error(f"EmbeddingManager: ❌ Failed to load: {e}")
            logger.warning("EmbeddingManager: Falling back to keyword-overlap deduplication.")
            return False

    def encode(self, text: str) -> list | None:
        """
        Returns a 384-dim embedding as list[float], or None if unavailable.
        Never raises — callers must handle None return.
        normalize_embeddings=True means vectors have unit length,
        so cosine similarity reduces to a simple dot product.
        """
        if not self._model_ready or self._model is None:
            return None
        try:
            embedding = self._model.encode(
                [text],
                show_progress_bar=False,
                normalize_embeddings=True
            )
            return embedding[0].tolist()
        except Exception as e:
            logger.error(f"EmbeddingManager: encode() failed: {e}")
            return None

    def cosine_similarity(self, vec_a: list, vec_b: list) -> float:
        """
        Pure numpy cosine similarity for two pre-normalized vectors.
        For normalized vectors (normalize_embeddings=True): cosine_sim = dot product.
        Fast — no model call needed.

        Returns float in [-1.0, 1.0]. Values ≥ 0.82 are considered near-duplicate.
        """
        try:
            import numpy as np
            a = np.array(vec_a, dtype=np.float32)
            b = np.array(vec_b, dtype=np.float32)
            dot = float(np.dot(a, b))
            return max(-1.0, min(1.0, dot))  # clamp for float precision
        except Exception as e:
            logger.error(f"EmbeddingManager: cosine_similarity() failed: {e}")
            return 0.0

    @property
    def is_ready(self) -> bool:
        """True if model loaded successfully and is ready to encode."""
        return self._model_ready
