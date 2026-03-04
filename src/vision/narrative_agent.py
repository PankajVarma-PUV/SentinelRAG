# SpandaOS — The Living Pulse of Agentic Intelligence
# A self-pulsing intelligence that lives at the core of the system — perpetually vibrating, continuously learning from every interaction, self-correcting its own errors, and driving all reasoning from a single living center — not because it was told to, but because that is its fundamental nature.
# Copyright (C) 2026 Pankaj Umesh Varma
# Contact: 9372123700
# Email: pv43770@gmail.com
"""
Narrative Agent for SpandaOS.
Provides high-level LLM enrichment for structured multimodal extractions.
"""

from ..core.ollama_client import get_ollama_client
from ..core.utils import logger

class NarrativeAgent:
    """Agent specialized in turning structured extraction context into humanized narratives."""
    
    def __init__(self):
        self.client = get_ollama_client()

    async def generate(self, prompt: str, max_tokens: int = 1024, temperature: float = 0.7) -> str:
        """Generates a narrative based on the provided prompt."""
        try:
            result = await self.client.generate(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature
            )
            # OllamaClient.generate returns {'response': str, ...} or a string
            if isinstance(result, dict):
                return result.get("response", "")
            return str(result)
        except Exception as e:
            logger.error(f"NarrativeAgent generation failed: {e}")
            return f"Error: {str(e)}"

def get_narrative_agent():
    """Factory function for NarrativeAgent."""
    return NarrativeAgent()
