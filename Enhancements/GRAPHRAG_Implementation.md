# GraphRAG Implementation Guide for SentinelRAG
*Implementation Architecture & Codebase Conversion Plan*

---

> [!WARNING]
> This document is strictly an implementation guide. **DO NOT run this code on constrained systems** (e.g., 6GB VRAM, 16GB RAM) as the ingestion phase will cause severe bottlenecking and out-of-memory errors due to heavy LLM inference and JVM overheads.

---

## 1. System Requirements (Minimum & Recommended)

To run a true GraphRAG architecture combining a Knowledge Graph (Neo4j) with Vector Search (LanceDB), the hardware must support parallel database operations and continuous LLM inference for entity extraction.

### Minimum Specifications (Extremely Slow Ingestion)
- **GPU**: NVIDIA RTX 3060 / 4060 Ti with 12GB+ VRAM
- **RAM**: 32GB System RAM (required for Neo4j JVM overhead and OS operations)
- **Storage**: M.2 NVMe SSD (Gen 3 or higher)
- **Models**:
  - *Extractor Model*: **Ministral-8B-Instruct** or **Qwen2.5-7B-Instruct** (Fast, highly accurate JSON formatting at 4-bit)
  - *Reasoning Model*: **Llama-3.1-8B-Instruct** or **Gemma-3-12B** (4-bit quantization)

### Recommended Specifications (Production Level Fast Ingestion)
- **GPU**: NVIDIA RTX 3090 / 4090 / A6000 with 24GB+ VRAM (for vLLM batching)
- **RAM**: 64GB System RAM
- **Storage**: M.2 NVMe SSD (Gen 4 or Gen 5) for ultra-fast Graph traversal I/O.
- **Models**:
  - *Extractor Model*: **Phi-4 (14B)** or **Mistral-Nemo-12B** (Exceptional benchmark performance for strict JSON structured output and entity relationships).
  - *Reasoning Model*: **DeepSeek-R1** (Distilled 32B/70B) or **Llama-3.3-70B-Instruct** (State-of-the-art for multi-step logical deduction and complex graph traversal synthesis).

---

## 2. Architectural Paradigm Shift

Upgrading SentinelRAG from standard Vector RAG to GraphRAG requires adding a new structural pipeline to every phase of the application.

1. **Ingestion (The Extractor Agent)**: Instead of just pushing paragraphs to LanceDB, every paragraph is also sent to an LLM. The LLM extracts JSON arrays of Nodes (`Person`, `Organization`, `Concept`) and Edges (`ACQUIRED`, `WORKS_FOR`). These are written to Neo4j.
2. **Querying (The Analyzer Agent)**: The Analyzer splits a user query into two intents:
   - *Semantic Intent*: "What does this company do?" -> LanceDB vector search.
   - *Structural Intent*: "Who is the CEO of the company who..." -> Neo4j Cypher query generation.
3. **Retrieval**: The Retriever pulls paragraph chunks from LanceDB and relationship paths from Neo4j in parallel.
4. **Synthesis**: The Synthesizer fuses the vector text and graph paths to answer complex, multi-hop reasoning questions.

---

## 3. Step-by-Step Codebase Conversion Plan

### Step 1: Infrastructure & Dependencies Setup
*Files to modify: `requirements.txt`, `docker-compose.yml` (if applicable)*

1.  **Add Graph Dependencies**:
    *   Install `neo4j` Python driver.
    *   Install `networkx` for local graph manipulation and topological sorting before DB insertion.
    *   Add: `pip install neo4j networkx pydantic`
2.  **Initialize Neo4j Server**:
    *   Run a local instance of Neo4j Desktop or use Docker (`docker run -d --name neo4j -p 7474:7474 -p 7687:7687 neo4j`).

### Step 2: The Graph Database Handler
*Files to create: `src/database/graph_db.py`*

Create a dedicated connection manager for Neo4j, similar to `lancedb_manager.py`.

```python
from neo4j import GraphDatabase

class Neo4jManager:
    def __init__(self, uri, user, password):
        # Establish connection to the Neo4j instance
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        # Best practice: always close the driver when shutting down
        self.driver.close()

    def create_node(self, label: str, properties: dict):
        # Cypher: MATCH or CREATE (MERGE prevents duplicates based on a unique ID)
        # Using parameterized queries to prevent Cypher injection
        query = f"MERGE (n:{label} {{id: $id}}) SET n += $props RETURN n"
        with self.driver.session() as session:
            node_id = properties.get("id")
            result = session.run(query, id=node_id, props=properties)
            return result.single()

    def create_relationship(self, source_id: str, target_id: str, rel_type: str):
        # Cypher: Safely link two existing nodes
        query = (
            f"MATCH (a {{id: $source_id}}), (b {{id: $target_id}}) "
            f"MERGE (a)-[r:{rel_type}]->(b) RETURN r"
        )
        with self.driver.session() as session:
            result = session.run(query, source_id=source_id, target_id=target_id)
            return result.single()
        
    def query_graph(self, cypher_query: str):
        # Execute raw cypher and return JSON paths
        with self.driver.session() as session:
            result = session.run(cypher_query)
            return [record.data() for record in result]
```

### Step 3: Implement The Entity Extractor Agent
*Files to create: `src/agents/extractor.py`*

This is the most critical and resource-intensive agent. It sits in the ingestion pipeline (`add_knowledge`).

1.  **Define Pydantic Schemas** for the LLM output:
    ```python
    from pydantic import BaseModel, Field
    
    class Node(BaseModel):
        id: str
        label: str = Field(description="Person, Organization, Process, Concept")
        
    class Edge(BaseModel):
        source_id: str
        target_id: str
        relationship: str = Field(description="ACQUIRED, WORKS_FOR, DEPENDS_ON")
        
    class GraphExtraction(BaseModel):
        nodes: list[Node]
        edges: list[Edge]
    ```
2.  **Modify Ingestion Flow** in `src/workflows/ingestion.py` (or `database.py`):
    *   After creating a chunk of text, send it to the Extractor Agent.
    *   Parse the JSON response and pass the nodes/edges to `Neo4jManager`.
    *   *Warning*: Implement Entity Resolution logic here (e.g., merging "Apple" and "Apple Inc.") before inserting into Neo4j.

### Step 4: Upgrade the Query Analyzer Agent
*Files to modify: `src/agents/analyzer.py`*

The Analyzer must now generate **Cypher queries** alongside standard search terms.

1.  Inject the Graph Schema (Node Labels, Edge Types) into the Analyzer's prompt.
2.  Instruct the LLM (e.g., `Llama-3`) to translate questions into Cypher:
    *   *User*: "Who is the CEO of LanceDB?"
    *   *LLM Output*:
        ```json
        {
          "semantic_query": "LanceDB CEO leadership team",
          "cypher_query": "MATCH (p:Person)-[:WORKS_FOR {role: 'CEO'}]->(o:Organization {name: 'LanceDB'}) RETURN p.name"
        }
        ```

### Step 5: Upgrade the Retriever Agent
*Files to modify: `src/agents/retriever.py`*

The Retriever must perform parallel dual-searches.

1.  **Vector Search**: Call LanceDB with `semantic_query`.
2.  **Graph Search**: Execute `cypher_query` against `Neo4jManager`.
3.  **Hybridization**: Format the outputs into a unified context dictionary.
    ```python
    # Example hybrid return structure
    hybrid_context = {
        "Vector_Context": [
            "Chunk 1: ...",
            "Chunk 2: ..."
        ],
        "Graph_Context": [
            "(John Doe)-[:WORKS_FOR]->(LanceDB)",
            "(LanceDB)-[:ACQUIRED]->(VectorFlow)"
        ]
    }
    return hybrid_context
    ```

### Step 6: Upgrade the Synthesizer Agent
*Files to modify: `src/agents/synthesizer.py`*

Update the final system prompt to teach the LLM how to read and synthesize Graph Context.
1.  Add instructions: "You are provided with semantic text blocks and structural graph paths. Use the graph paths to establish deterministic relationships (who owns what, sequence of events) and use the text blocks to provide descriptive context. Combine them seamlessly."

---

## 4. Final Deployment Considerations

If you proceed with these changes on a capable machine:
- **Index Time**: Expect document ingestion to take **10x to 20x longer** than standard RAG.
- **Graph Pruning**: You must build logic to periodically prune orphaned nodes in Neo4j when documents are deleted from LanceDB. 
- **LLM Selection**: Use specialized JSON-mode enabled LLMs for the Extractor Agent to prevent ingestion pipeline crashes from malformed JSON.
