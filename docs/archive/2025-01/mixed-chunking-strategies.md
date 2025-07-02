# Mixed Chunking Strategies

This guide describes how to use the enhanced document chunking and FAISS indexing system that supports multiple document sources and chunking strategies in a single vector database.

## Overview

The RVC2API project supports a unified approach to semantic search across multiple document types using a single FAISS index. This enables:

- Different chunking strategies for different document types
- Source-aware filtering of search results
- Consistent metadata across all documents
- Better search results by selecting the most appropriate chunking method for each document type

## Document Sources and Chunking Strategies

| Document Type      | Recommended Chunking | Description                                                  |
| ------------------ | -------------------- | ------------------------------------------------------------ |
| RV-C Specification | `SECTION_OVERLAP`    | Chunks by specification sections with overlap between chunks |
| Victron Manuals    | `PARAGRAPH`          | Chunks by natural paragraphs                                 |
| Firefly Docs       | `TOKEN`              | Fixed-size token chunking                                    |
| General PDFs       | `SLIDING_WINDOW`     | Sliding window with configurable overlap                     |

## Using the Document Loader API

### Basic Usage

```python
from pathlib import Path
from document_loader import ChunkingStrategy, load_chunk_with_metadata

# Process chunks with consistent metadata
docs = load_chunk_with_metadata(
    chunks_data=your_chunks,
    source_path=Path("your-document.pdf"),
    chunking_strategy=ChunkingStrategy.SECTION_OVERLAP
)
```

### Filtering Search Results

```python
from document_loader import filter_results_by_source

# Get results from a specific source
filtered_results = filter_results_by_source(
    results=search_results,
    source="rvc-spec-2023-11.pdf",
    limit=3
)

# Or by chunking strategy
filtered_results = filter_results_by_source(
    results=search_results,
    chunking=ChunkingStrategy.PARAGRAPH,
    limit=3
)
```

## Command-Line Tools

### Query with Source Filtering

```bash
python dev_tools/query_faiss.py "battery temperature" --source "rvc-spec-2023-11.pdf"
```

### Query with Chunking Strategy Filtering

```bash
python dev_tools/query_faiss.py "solar panel configuration" --chunking "paragraph"
```

### Specify Result Count

```bash
python dev_tools/query_faiss.py "water tank level" --count 5
```

## Adding New Document Sources

To add a new document source with its own chunking strategy:

1. Process your document into chunks with appropriate metadata
2. Use `load_chunk_with_metadata()` to standardize metadata
3. Add to the existing FAISS index or create a new one
4. Use the `query_faiss.py` script with `--source` parameter to search

## Best Practices

1. **Source Naming**: Use the standardized `normalize_source_name()` function to ensure consistent source names
2. **Metadata Fields**: Always include `source`, `chunking`, and other relevant fields in your metadata
3. **Chunking Strategy**: Select the most appropriate chunking strategy for each document type
4. **Mixed Index**: When searching a mixed index, always consider filtering by source when relevant

## Example: Adding Victron Manual

```python
import json
from pathlib import Path
from document_loader import ChunkingStrategy, load_chunk_with_metadata
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import OpenAIEmbeddings

# Process Victron manual with paragraph chunking
with open("victron_chunks.json") as f:
    victron_chunks = json.load(f)

# Load with standardized metadata
docs = load_chunk_with_metadata(
    chunks_data=victron_chunks,
    source_path=Path("victron-multiplus-2023.pdf"),
    chunking_strategy=ChunkingStrategy.PARAGRAPH
)

# Load existing index and add new documents
vectorstore = FAISS.load_local("resources/vector_store/rvc_spec_index", OpenAIEmbeddings())
vectorstore.add_documents(docs)
vectorstore.save_local("resources/vector_store/combined_index")
```

## Advanced Usage

See the implementation in `document_loader.py` for additional utilities and options for working with mixed document sources and chunking strategies.
