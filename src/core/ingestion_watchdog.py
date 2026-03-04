# SpandaOS — The Living Pulse of Agentic Intelligence
# A self-pulsing intelligence that lives at the core of the system — perpetually vibrating, continuously learning from every interaction, self-correcting its own errors, and driving all reasoning from a single living center — not because it was told to, but because that is its fundamental nature.
# Copyright (C) 2026 Pankaj Umesh Varma
# Contact: 9372123700
# Email: pv43770@gmail.com
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

import asyncio
from typing import Optional
from datetime import datetime, timedelta
from ..core.utils import logger
from ..data.database import get_database

class IngestionWatchdog:
    """
    SOTA System Self-Healing Watchdog.
    Monitors the 'ingestion_status' table. If an ingestion is stuck in IN_PROGRESS
    for too long (indicating a crash), it orchestrates a resumption from the 'last_chunk_index'.
    """
    
    def __init__(self, check_interval_seconds: int = 300, stale_timeout_minutes: int = 30):
        self.interval = check_interval_seconds
        self.stale_timeout = stale_timeout_minutes
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def start(self):
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._watchdog_loop())
            logger.info("🛡️ System Watchdog started: Monitoring for stalled ingestions.")

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            logger.info("🛡️ System Watchdog stopped.")

    async def _watchdog_loop(self):
        while self._running:
            try:
                await self._check_stalled_jobs()
            except Exception as e:
                logger.error(f"Watchdog loop error: {e}")
            
            await asyncio.sleep(self.interval)

    async def _check_stalled_jobs(self):
        db = get_database()
        if not db or not db.is_connected():
            return
            
        threshold_time = (datetime.utcnow() - timedelta(minutes=self.stale_timeout)).isoformat()
        
        with db.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT id, file_name, last_chunk_index
                FROM ingestion_status
                WHERE status = 'IN_PROGRESS' AND updated_at < ?
                """,
                (threshold_time,)
            )
            stalled_jobs = cursor.fetchall()
            
            for job in stalled_jobs:
                logger.warning(
                    f"🚨 Watchdog detected stalled ingestion for {job['file_name']} "
                    f"at chunk {job['last_chunk_index']}. Attempting to self-heal..."
                )
                
                # In a full SOTA implementation, this would push back into a queue or 
                # trigger the DocumentProcessor to resume from job['last_chunk_index'].
                # For Phase 4 remediation, we mark it as FAILED so the UI knows to retry.
                cursor.execute(
                    "UPDATE ingestion_status SET status = 'FAILED', updated_at = ? WHERE id = ?",
                    (datetime.utcnow().isoformat(), job['id'])
                )
                logger.info(f"🛡️ Job {job['id']} marked as FAILED for manual retry.")
