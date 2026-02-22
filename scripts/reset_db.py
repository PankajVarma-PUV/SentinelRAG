"""
Standalone script to reset the SentinelRAG database.
Drops all tables and recreates the schema for the active backend.
"""
import sys
import os
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))

from src.data.database import get_database
from src.core.utils import logger

def reset():
    logger.info("Starting database reset...")
    try:
        db = get_database()
        if not db.connect():
            logger.error("Failed to connect to database for reset.")
            return
            
        db.reset_database()
        logger.info("Database has been successfully reset.")
    except Exception as e:
        logger.error(f"Error during database reset: {e}")
    finally:
        if 'db' in locals():
            db.disconnect()

if __name__ == "__main__":
    confirm = input("Are you sure you want to delete ALL data and reset the database? (y/N): ")
    if confirm.lower() == 'y':
        reset()
    else:
        logger.info("Reset cancelled.")
