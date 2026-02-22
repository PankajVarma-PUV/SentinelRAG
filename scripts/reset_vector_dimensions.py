"""
SentinelRAG — Vector Dimension Reset Script
============================================
Run this script ONCE after changing your embedding model/dimension.
It will:
  1. Connect to the LanceDB database directory
  2. Inspect every table for vector dimension mismatches
  3. Drop and recreate any incompatible tables (data is cleared — must re-index)
  4. Print a clear summary of what was done

Usage:
  cd "c:/Users/pv786/OneDrive/Desktop/Projects/GEN AI based/SentinelRAG"
  python scripts/reset_vector_dimensions.py
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Load .env before importing anything else
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "Credentials", ".env"))

import lancedb
import pyarrow as pa
from pathlib import Path

# Now import after env is loaded
from src.core.config import Config
from src.core.utils import logger

# ─── Settings ────────────────────────────────────────────────────────────────
TARGET_DIMENSION = Config.embedding.DIMENSION
DB_PATH = Config.paths.SENTINEL_DB_DIR

# Tables that contain vector columns
VECTOR_TABLES = {"knowledge_base", "messages"}
ALL_TABLES = [
    "projects", "folders", "conversations", "messages",
    "user_personas", "knowledge_base", "conversation_assets",
    "scraped_content", "rag_analytics", "visual_cache",
    "enriched_content", "document_summaries"
]

def get_vector_dimension(table) -> int:
    """Returns the dimension of the vector field, or -1 if not found."""
    try:
        schema = table.schema
        for field in schema:
            if field.name == "vector":
                vtype = field.type
                if hasattr(vtype, "list_size"):
                    return vtype.list_size
    except Exception as e:
        print(f"  ⚠️  Could not inspect schema: {e}")
    return -1

def run_migration():
    print(f"\n{'='*60}")
    print(f"  SentinelRAG — Vector Dimension Reset")
    print(f"  Target Dimension : {TARGET_DIMENSION} (from .env EMBEDDING_DIMENSION)")
    print(f"  LanceDB Path     : {DB_PATH}")
    print(f"{'='*60}\n")

    if not Path(str(DB_PATH)).exists():
        print("❌ LanceDB directory not found. Run the server first to initialize.")
        return

    conn = lancedb.connect(str(DB_PATH))
    existing_tables = conn.table_names()
    print(f"Found {len(existing_tables)} tables: {existing_tables}\n")

    # Import schema registry to recreate tables correctly
    from src.core.database import SCHEMA_REGISTRY

    dropped = []
    already_correct = []
    no_vector = []
    missing = []

    for table_name in ALL_TABLES:
        if table_name not in existing_tables:
            missing.append(table_name)
            continue

        if table_name not in VECTOR_TABLES:
            no_vector.append(table_name)
            continue

        table = conn.open_table(table_name)
        dim = get_vector_dimension(table)

        if dim == -1:
            print(f"  ⚠️  {table_name}: no vector column found — skipping")
            no_vector.append(table_name)
        elif dim == TARGET_DIMENSION:
            print(f"  ✅ {table_name}: dimension={dim} — CORRECT, no action needed")
            already_correct.append(table_name)
        else:
            row_count = len(table.to_pandas()) if hasattr(table, 'to_pandas') else "?"
            print(f"  🚨 {table_name}: MISMATCH detected! On-disk={dim}D, Required={TARGET_DIMENSION}D ({row_count} rows will be CLEARED)")
            confirm = input(f"     Drop and recreate '{table_name}'? [y/N]: ").strip().lower()
            if confirm == "y":
                conn.drop_table(table_name)
                if table_name in SCHEMA_REGISTRY:
                    conn.create_table(table_name, schema=SCHEMA_REGISTRY[table_name])
                    print(f"  ✅ {table_name}: Recreated with {TARGET_DIMENSION}D vectors")
                dropped.append(table_name)
            else:
                print(f"  ⏭️  {table_name}: Skipped. Application will continue to crash on this table.")

    print(f"\n{'='*60}")
    print(f"  MIGRATION SUMMARY")
    print(f"{'='*60}")
    print(f"  ✅ Already correct : {already_correct or ['None']}")
    print(f"  🔄 Dropped+Rebuilt : {dropped or ['None']}")
    print(f"  📋 No vector field : {no_vector or ['None']}")
    print(f"  ❓ Missing tables  : {missing or ['None']}")
    print(f"\n  ⚠️  You must re-index all documents after this migration.")
    print(f"     Previously indexed content has been cleared from vector tables.")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    run_migration()
