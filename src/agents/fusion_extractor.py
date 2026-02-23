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

from typing import List, Dict, Optional
from ..core.utils import logger
from ..core.models import UnifiedEvidenceState

class UniversalFusionExtractor:
    """
    SOTA component that aggregates multi-source file evidence.
    Creates a 'Unified Evidence State' for the Planner.
    """
    
    def __init__(self, db):
        self.db = db
        logger.info("UniversalMultimodalFusionExtractor initialized")

    async def extract_and_fuse(self, conversation_id: str, mentioned_files: list = None) -> UnifiedEvidenceState:
        """
        Gathers evidence from all assets associated with a conversation.
        Categorizes them into Text, Visual, and Audio buckets.
        Supports strict filtering by @mentioned files.
        """
        logger.info(f"Fusing multimodal evidence for conversation: {conversation_id} (Mentions: {mentioned_files})")
        state = UnifiedEvidenceState()
        
        # 1. Fetch Unified Enriched Content (New Architecture)
        enriched_items = self.db.get_enriched_content_by_chat(conversation_id)
        
        # Tracks for filename-based deduplication and legacy fallback
        fused_file_ids = set()
        seen_filenames = set()
        
        for item in enriched_items:
            f_id = item.get('file_id')
            f_name = item.get('file_name', 'Unknown')
            content = item.get('enriched_content', '')
            c_type = item.get('content_type', 'document').lower()
            
            if not content: continue
            if not self._name_matches(f_name, mentioned_files): continue
            
            fused_file_ids.add(f_id)
            
            # SOTA Deduplication: One card per file name
            if f_name in seen_filenames:
                continue
            seen_filenames.add(f_name)
            
            # Bucketize based on content type
            if c_type in ['image', 'photo', 'screenshot', 'video']:
                state.visual_evidence.append({
                    "file_name": f_name,
                    "content": content,
                    "type": c_type
                })
            elif c_type == 'audio':
                state.audio_evidence.append({
                    "file_name": f_name,
                    "content": content,
                    "type": c_type
                })
            else:
                state.text_evidence.append({
                    "file_name": f_name,
                    "text": content,
                    "source": f_name
                })
                
        # 2. Fallback to Legacy Scraped Content (Backward Compatibility)
        scraped_items = self.db.get_scraped_content_by_chat(conversation_id)
        legacy_seen_files = set()
        
        for item in scraped_items:
            f_id = item.get('file_id')
            if f_id in fused_file_ids: continue 
            
            f_name = item.get('file_name', 'Unknown')
            if not self._name_matches(f_name, mentioned_files): continue
            
            content = item.get('content', '')
            if not content: continue
            
            metadata = item.get('metadata', {})
            m_type = metadata.get('type', item.get('sub_type', 'text'))
            
            if f_id in legacy_seen_files: continue
            legacy_seen_files.add(f_id)

            if m_type in ['vision', 'ocr', 'processed_narrative', 'processed_description', 'image', 'video_visual']:
                state.visual_evidence.append(item)
            elif m_type in ['audio_transcript', 'audio_summary', 'audio', 'video_audio']:
                state.audio_evidence.append(item)
            else:
                state.text_evidence.append(item)

        # 3. Supplemental: Ensure all registered assets are acknowledged
        all_assets = self.db.get_documents_by_chat(conversation_id)
        for asset in all_assets:
            f_id = asset.get('id')
            f_name = asset.get('file_name', 'Unknown')
            f_type = asset.get('file_type', 'document').lower()
            
            if not self._name_matches(f_name, mentioned_files): continue
            if f_name in seen_filenames or f_id in fused_file_ids or f_id in legacy_seen_files:
                continue
            
            if f_type in ['image', 'photo', 'screenshot', 'video']:
                state.visual_evidence.append({
                    "file_name": f_name,
                    "content": f"[Registry Match] {f_name} (Metadata only)",
                    "type": f_type
                })
            elif f_type == 'audio':
                state.audio_evidence.append({
                    "file_name": f_name,
                    "content": f"[Registry Match] {f_name} (Metadata only)",
                    "type": f_type
                })
            else:
                state.text_evidence.append({
                    "file_name": f_name,
                    "text": f"[Registry Match] {f_name} is available in the knowledge base.",
                    "source": f_name
                })
            
            seen_filenames.add(f_name)

        logger.info(f"Fusion Complete: {len(state.text_evidence)} text, {len(state.visual_evidence)} visual, {len(state.audio_evidence)} audio pieces.")
        return state

    def _name_matches(self, fname: str, targets: list) -> bool:
        """Helper to check if a file name matches any of the targets (strict or base match)."""
        if not targets: return True # No filter
        fname_lower = fname.lower()
        for t in targets:
            t_lower = t.lower()
            # Match strict filename or base name (e.g. @cats matching cats.pdf)
            if fname_lower == t_lower or fname_lower.split('.')[0] == t_lower:
                return True
        return False
