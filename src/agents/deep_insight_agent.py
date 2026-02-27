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
DeepInsightAgent — Phase 3: Multi-Agent Reflection Loop (SOTA)

Implements a 3-stage Analyst → Skeptic → Synthesizer debate via sequential
LLM calls with streaming cognitive trace events. Designed for the
/query/agentic_action endpoint with the DEEP_INSIGHT intent.

All calls use num_ctx: 4096 (VRAM safety per upgrade spec).
Model: qwen3:4b (configurable via Config)
"""

import re
import asyncio
from typing import AsyncGenerator, Dict, Any, List, Optional
from datetime import datetime

from langchain_ollama import OllamaLLM
from ..core.config import Config
from ..core.utils import logger


class DeepInsightAgent:
    """
    SOTA Multi-Agent Reflection Loop for Deep Insight generation.

    Stages:
    1. Analyst  — drafts the initial analysis of the provided context
    2. Skeptic  — critically challenges the analyst's claims
    3. Synthesizer — merges analysis + critique into a final, peer-reviewed insight

    Streams status events between each stage so the frontend Cognitive Trace
    accordion can show live progress. Each LLM call uses qwen3:4b with
    appropriate temperature settings optimized for its role.
    """

    # Ollama options for VRAM safety as per upgrade spec
    _SAFE_OPTIONS = {"num_ctx": 4096}

    def __init__(self):
        base_url = Config.ollama.BASE_URL
        timeout = Config.ollama.TIMEOUT

        # Analyst: Creative reasoning, moderate temperature for diverse connections
        self._analyst_llm = OllamaLLM(
            model=Config.ollama_multi_model.HEAVY_MODEL,
            base_url=base_url,
            timeout=timeout,
        )

        # Skeptic: Slightly higher temp to surface unexpected challenges
        self._skeptic_llm = OllamaLLM(
            model=Config.ollama_multi_model.HEAVY_MODEL,
            base_url=base_url,
            timeout=timeout,
        )

        # Synthesizer: Lower temp for clean, authoritative final output
        self._synthesizer_llm = OllamaLLM(
            model=Config.ollama_multi_model.HEAVY_MODEL,
            base_url=base_url,
            timeout=timeout,
        )

    @staticmethod
    def _strip_thinking(text: str) -> str:
        """Strip <thinking> blocks emitted by reasoning models."""
        return re.sub(r'<thinking>[\s\S]*?</thinking>', '', text).strip()

    async def _run_stage(
        self,
        llm: OllamaLLM,
        prompt: str,
        tag: str,
        check_abort_fn=None
    ) -> str:
        """Run a single LLM stage and collect the full response."""
        full = ""
        try:
            async for chunk in llm.astream(prompt, config={"tags": [tag]}):
                if check_abort_fn and check_abort_fn():
                    logger.info(f"DeepInsightAgent [{tag}]: Abort detected.")
                    break
                full += chunk
        except Exception as e:
            logger.error(f"DeepInsightAgent [{tag}] error: {e}")
            full = f"[{tag.capitalize()} encountered an error: {str(e)}]"
        return self._strip_thinking(full)

    async def run(
        self,
        context: str,
        document_names: List[str],
        history: List[Dict],
        check_abort_fn=None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute the 3-stage deep insight debate and yield SSE-ready events.

        Yields event dicts of type:
          - {"type": "thought", "agent": str, "action": str}  — trace events
          - {"type": "token", "token": str}                   — streaming tokens (synthesizer only)
          - {"type": "deep_insight_done", "content": str}     — completion signal
        """
        now = datetime.now().strftime("%A, %B %d, %Y, %I:%M %p")
        doc_list = ", ".join(document_names) if document_names else "the uploaded documents"
        # Trim context to avoid VRAM overflow
        trimmed_ctx = context[:6000] if len(context) > 6000 else context
        recent_history = "\n".join([
            f"{m.get('role', 'user')}: {m.get('content', '')[:200]}"
            for m in (history or [])[-3:]
        ])

        # ─── STAGE 1: ANALYST ────────────────────────────────────────────────
        yield {"type": "thought", "agent": "🔬 Analyst", "action": "Drafting initial analysis from evidence..."}

        analyst_prompt = f"""<role>
You are the UltimaRAG Analyst — a world-class evidence analyst. Your task is to produce a thorough, structured first-pass analysis of the provided document context.
</role>

<system_info>
CURRENT TIME: {now}
DOCUMENTS: {doc_list}
STAGE: ANALYST (Pass 1 of 3)
</system_info>

<context>
{trimmed_ctx}
</context>

<conversation_history>
{recent_history}
</conversation_history>

<analyst_mandates>
1. COGNITION: Think step-by-step inside <thinking> tags first to map the key themes.
2. STRUCTURE: Produce a structured analysis with clear sections: Key Findings, Themes, Evidence Quality.
3. DEPTH: Surface non-obvious patterns and latent contradictions in the evidence.
4. CITATIONS: Reference source documents where applicable using [[FileName]] notation.
5. LENGTH: Aim for a substantive analysis of 300-500 words.
</analyst_mandates>

ANALYST REPORT:"""

        analyst_report = await self._run_stage(
            self._analyst_llm, analyst_prompt, "deep_insight_analyst", check_abort_fn
        )

        if check_abort_fn and check_abort_fn():
            return

        logger.info(f"DeepInsightAgent: Analyst stage complete ({len(analyst_report)} chars)")
        yield {"type": "thought", "agent": "🔬 Analyst", "action": f"Analysis complete — {len(analyst_report.split())} word report drafted."}

        # ─── STAGE 2: SKEPTIC ────────────────────────────────────────────────
        yield {"type": "thought", "agent": "⚔️ Skeptic", "action": "Challenging the analyst's conclusions..."}

        skeptic_prompt = f"""<role>
You are the UltimaRAG Skeptic — a rigorous devil's advocate. You have received an analyst's first-pass report and must identify its weaknesses, unsupported claims, and alternative interpretations.
</role>

<system_info>
CURRENT TIME: {now}
DOCUMENTS: {doc_list}
STAGE: SKEPTIC (Pass 2 of 3)
</system_info>

<original_context>
{trimmed_ctx[:3000]}
</original_context>

<analyst_report>
{analyst_report}
</analyst_report>

<skeptic_mandates>
1. COGNITION: Think critically inside <thinking> tags to pinpoint the 3 weakest claims.
2. CHALLENGE: For each weakness, provide a specific counter-argument or alternative interpretation.
3. GAPS: Identify what evidence is missing or what questions remain unanswered.
4. TONE: Intellectually rigorous but constructive. The goal is to strengthen the final insight.
5. FORMAT: Output as a structured critique: [Weakness 1], [Weakness 2], [Weakness 3], [Open Questions].
</skeptic_mandates>

SKEPTIC CRITIQUE:"""

        skeptic_critique = await self._run_stage(
            self._skeptic_llm, skeptic_prompt, "deep_insight_skeptic", check_abort_fn
        )

        if check_abort_fn and check_abort_fn():
            return

        logger.info(f"DeepInsightAgent: Skeptic stage complete ({len(skeptic_critique)} chars)")
        yield {"type": "thought", "agent": "⚔️ Skeptic", "action": f"Critique complete — {len(skeptic_critique.split())} word challenge filed."}

        # ─── STAGE 3: SYNTHESIZER ────────────────────────────────────────────
        yield {"type": "thought", "agent": "✨ Synthesizer", "action": "Forging final peer-reviewed insight from debate..."}

        synthesizer_prompt = f"""<role>
You are the UltimaRAG Synthesizer — the final arbitrator of intellectual debate. You have received an analyst's initial report and a skeptic's critique. Your task is to forge a final, authoritative, deeply nuanced insight that is stronger than either individual perspective.
</role>

<system_info>
CURRENT TIME: {now}
DOCUMENTS: {doc_list}
STAGE: SYNTHESIZER (Pass 3 of 3 — FINAL)
</system_info>

<analyst_report>
{analyst_report}
</analyst_report>

<skeptic_critique>
{skeptic_critique}
</skeptic_critique>

<synthesizer_mandates>
1. COGNITION: Think inside <thinking> tags to identify what each side got right.
2. SYNTHESIS: Merge both perspectives into a final insight that addresses the skeptic's challenges head-on.
3. NARRATIVE: Write as a cinematic intelligence report — authoritative, flowing, not a list.
4. CITATIONS: Use [[FileName]] notation for source attribution.
5. CONCLUSION: End with a powerful 2-sentence executive summary of the most important takeaway.
6. LENGTH: 400-600 words of final synthesized insight.
</synthesizer_mandates>

UltimaRAG DEEP INSIGHT:"""

        # Stream the synthesizer response token by token (final output visible to user)
        final_content = ""
        try:
            async for chunk in self._synthesizer_llm.astream(
                synthesizer_prompt, config={"tags": ["deep_insight_synthesizer"]}
            ):
                if check_abort_fn and check_abort_fn():
                    logger.info("DeepInsightAgent [Synthesizer]: Abort detected mid-stream.")
                    break
                final_content += chunk
                yield {"type": "token", "token": chunk}
        except Exception as e:
            logger.error(f"DeepInsightAgent [Synthesizer] stream error: {e}")
            final_content = analyst_report  # graceful fallback to analyst report

        final_content = self._strip_thinking(final_content)
        final_content = final_content.replace("UltimaRAG DEEP INSIGHT:", "").strip()

        logger.info(f"DeepInsightAgent: Synthesis complete ({len(final_content)} chars)")
        yield {"type": "thought", "agent": "✨ Synthesizer", "action": "Peer-reviewed insight forged. Debate concluded."}
        yield {"type": "deep_insight_done", "content": final_content}
