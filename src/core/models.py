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

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum

class ResponseMode(str, Enum):
    GROUNDED = "grounded_in_docs"
    KNOWLEDGE = "internal_llm_weights"
    HYBRID = "multiple_sources_fused"

class Intent(str, Enum):
    GENERAL = "general_intelligence" # Chat, Translation, Knowledge
    RAG = "document_search" # File-grounded queries
    PERCEPTION = "multimodal_analysis" # Image/Video analysis
    MULTI_TASK = "chained_agents" # Multi-step logic
    HISTORY = "history_recall" # Conversation history reasoning
    WEB_SEARCH = "web_search" # Adaptive web breakout

class VirtualContext(BaseModel):
    active_memory: str = Field(..., description="Currently loaded context in LLM RAM")
    archived_memory_ref: List[str] = Field(..., description="Vector IDs for context paged to DB")
    attached_assets: List[Dict[str, str]] = Field(..., description="List of [{file_id: path}] for current chat")

class QualityMetrics(BaseModel):
    groundedness: float = Field(..., description="Claims supported by context (0-1)")
    answer_relevancy: float = Field(..., description="Alignment with user query (0-1)")
    context_utility: float = Field(..., description="Retrieved chunks usefulness (0-1)")

class UIHints(BaseModel):
    theme_accent: str = Field(..., description="HEX code for intent-based glow")
    layout_pattern: str = Field(..., description="vision_hybrid, evidence_grid, or text_standard")
    animation_trigger: str = "fade_slide_up"

class UserPersona(BaseModel):
    tone: str = "professional" # concise, creative, academic
    expertise_domains: List[str] = Field(default_factory=list, description="User's known strong areas")
    formatting_pref: str = "markdown"

class UnifiedResponse(BaseModel):
    final_text: str
    mode: ResponseMode
    citations: List[Dict[str, Any]]
    quality: QualityMetrics
    ui_hints: UIHints
    branch_id: str = Field(..., description="ID for forked conversation tracks")
    confidence_score: float = Field(..., description="Weighted: (0.5*Grounded) + (0.3*Relevancy) + (0.2*Utility)")
    steps_taken: List[str] = Field(..., description="Audit trail: 'Visual Analysis', 'Hindi Translation', 'Summarization'")
    status: str # ANSWERED, PARTIAL, ERROR

class PagingTrigger(BaseModel):
    token_count: int
    threshold: int = 102400 # 80% of 128k
    action: str = "archive_oldest_turn"

class UnifiedEvidenceState(BaseModel):
    """Container for fused multimodal evidence"""
    text_evidence: List[Dict] = []
    visual_evidence: List[Dict] = []
    audio_evidence: List[Dict] = []
    summary_of_evidence: Optional[str] = None
