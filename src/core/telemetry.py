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
UltimaRAG Telemetry Utility
Captures agentic activity and performance metrics for real-time UI updates.
"""
from typing import Dict, Any, Optional
import time
import json
from .utils import logger

class AgentTelemetry:
    """Captured state of an agentic step"""
    def __init__(self, agent_name: str, stage: str):
        self.agent_name = agent_name
        self.stage = stage
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.metadata: Dict[str, Any] = {}

    def finish(self, metadata: Optional[Dict[str, Any]] = None):
        self.end_time = time.time()
        if metadata:
            self.metadata.update(metadata)

    def to_dict(self) -> Dict[str, Any]:
        duration = (self.end_time - self.start_time) if self.end_time else (time.time() - self.start_time)
        return {
            "agent": self.agent_name,
            "stage": self.stage,
            "duration": round(duration, 3),
            "status": "completed" if self.end_time else "running",
            "metadata": self.metadata
        }

class TelemetryManager:
    """Manages recording and broadcasting of agent activities"""
    def __init__(self):
        self.activities: Dict[str, AgentTelemetry] = {}

    def start_activity(self, agent_name: str, stage: str) -> str:
        # Auto-prune old running activities to prevent HUD ghosting
        dead_threshold = time.time() - 60 # 60 seconds max longevity
        self.activities = {k: v for k, v in self.activities.items() if v.end_time or (time.time() - v.start_time) < 60}
        
        activity_id = f"{agent_name}_{int(time.time() * 1000)}"
        self.activities[activity_id] = AgentTelemetry(agent_name, stage)
        logger.info(f"📊 Telemetry Start: {agent_name} -> {stage}")
        
        import asyncio
        # Broadcast the startup event
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                data = self.activities[activity_id].to_dict()
                data["type"] = "telemetry_start"
                loop.create_task(ws_manager.broadcast(data))
        except Exception:
            pass
            
        return activity_id

    def clear_all(self):
        """Emergency reset for telemetry state"""
        self.activities = {}
        logger.info("📊 Telemetry: State cleared")

    def end_activity(self, activity_id: str, metadata: Optional[Dict[str, Any]] = None):
        if activity_id in self.activities:
            self.activities[activity_id].finish(metadata)
            logger.info(f"📊 Telemetry End: {self.activities[activity_id].agent_name}")
            import asyncio
            # Broadcast the completion event
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    data = self.activities[activity_id].to_dict()
                    data["type"] = "telemetry_end"
                    loop.create_task(ws_manager.broadcast(data))
            except Exception:
                pass

        running = [a.to_dict() for a in self.activities.values() if a.end_time is None]
        return running[-1] if running else {"status": "idle"}

    def get_active_status(self) -> Dict[str, Any]:
        """Get the current running activity for telemetry"""
        running = [a.to_dict() for a in self.activities.values() if a.end_time is None]
        return running[-1] if running else {"status": "idle"}

# =============================================================================
# SOTA Phase 5: WebSocket UI Telemetry Manager
# =============================================================================
class WebSocketTelemetryManager:
    """Manages active WebSocket connections for real-time UI telemetry streaming."""
    def __init__(self):
        self.active_connections: list = []

    async def connect(self, websocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"🔌 WebSocket Connected: {websocket.client.host}. Total: {len(self.active_connections)}")

    def disconnect(self, websocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"🔌 WebSocket Disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast an event to all connected clients."""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"🔌 WebSocket broadcast failed to a client: {e}")
                
# Global instances
ws_manager = WebSocketTelemetryManager()
telemetry = TelemetryManager()

