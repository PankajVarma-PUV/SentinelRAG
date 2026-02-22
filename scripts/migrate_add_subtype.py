"""
Database Migration Script for SentinelRAG
Adds sub_type column to existing scraped_content table and migrates existing data.

Usage:
    python scripts/migrate_add_subtype.py

This script:
1. Adds sub_type column if it doesn't exist
2. Migrates existing data to 'text' default
3. Creates the new index on (file_id, sub_type)
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.database import get_database
from src.core.utils import logger


def migrate_sqlite(backend):
    """Apply migration to SQLite database."""
    logger.info("Starting SQLite migration...")
    
    try:
        with backend.get_cursor() as cursor:
            # Check if sub_type column already exists
            cursor.execute("PRAGMA table_info(scraped_content)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'sub_type' in columns:
                logger.info("sub_type column already exists in SQLite. Skipping migration.")
                return True
            
            # Add sub_type column with default 'text'
            logger.info("Adding sub_type column to scraped_content...")
            cursor.execute("""
                ALTER TABLE scraped_content 
                ADD COLUMN sub_type TEXT DEFAULT 'text'
            """)
            
            # Update all existing rows to have 'text' as sub_type
            cursor.execute("UPDATE scraped_content SET sub_type = 'text' WHERE sub_type IS NULL")
            
            # Create index
            logger.info("Creating index on (file_id, sub_type)...")
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_scraped_subtype 
                ON scraped_content(file_id, sub_type)
            """)
            
            # Count migrated rows
            cursor.execute("SELECT COUNT(*) FROM scraped_content")
            count = cursor.fetchone()[0]
            
        logger.info(f"SQLite migration complete. {count} rows migrated to sub_type='text'")
        return True
        
    except Exception as e:
        logger.error(f"SQLite migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def migrate_postgresql(backend):
    """Apply migration to PostgreSQL database."""
    logger.info("Starting PostgreSQL migration...")
    
    try:
        with backend.get_connection() as conn:
            with conn.cursor() as cur:
                # Check if sub_type column already exists
                cur.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'scraped_content' AND column_name = 'sub_type'
                """)
                
                if cur.fetchone():
                    logger.info("sub_type column already exists in PostgreSQL. Skipping migration.")
                    return True
                
                # Add sub_type column with default 'text' and CHECK constraint
                logger.info("Adding sub_type column to scraped_content...")
                cur.execute("""
                    ALTER TABLE scraped_content 
                    ADD COLUMN sub_type TEXT DEFAULT 'text'
                """)
                
                # Update all existing rows
                cur.execute("UPDATE scraped_content SET sub_type = 'text' WHERE sub_type IS NULL")
                
                # Add NOT NULL constraint and CHECK after migration
                cur.execute("""
                    ALTER TABLE scraped_content 
                    ALTER COLUMN sub_type SET NOT NULL
                """)
                cur.execute("""
                    ALTER TABLE scraped_content 
                    ADD CONSTRAINT scraped_content_subtype_check 
                    CHECK (sub_type IN ('text', 'image', 'audio', 'video_visual', 'video_audio'))
                """)
                
                # Create index
                logger.info("Creating index on (file_id, sub_type)...")
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_scraped_subtype 
                    ON scraped_content(file_id, sub_type)
                """)
                
                # Count migrated rows
                cur.execute("SELECT COUNT(*) FROM scraped_content")
                count = cur.fetchone()[0]
                
        logger.info(f"PostgreSQL migration complete. {count} rows migrated to sub_type='text'")
        return True
        
    except Exception as e:
        logger.error(f"PostgreSQL migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_migration():
    """Main migration entry point."""
    logger.info("=" * 60)
    logger.info("SentinelRAG Database Migration: Add sub_type column")
    logger.info("=" * 60)
    
    db = get_database()
    
    if not db.is_connected():
        if not db.connect():
            logger.error("Failed to connect to database")
            return False
    
    # Get the actual backend for direct access
    backend = db.backend
    
    if backend is None:
        logger.error("No database backend available")
        return False
    
    # Determine database type from backend class name
    backend_class = type(backend).__name__
    
    if "PostgreSQL" in backend_class:
        success = migrate_postgresql(backend)
    else:
        success = migrate_sqlite(backend)
    
    if success:
        logger.info("Migration completed successfully!")
    else:
        logger.error("Migration failed!")
    
    return success


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
