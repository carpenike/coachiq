# RV-C Documentation Search

This guide explains how to set up and use the RV-C documentation search functionality in the CoachIQ project.

## Overview

The CoachIQ project includes a semantic search feature that allows users to query RV-C specification and other technical documentation using natural language. This feature is powered by:

1. FAISS vector database for efficient similarity search
2. OpenAI embeddings for converting text to vectors
3. [Mixed chunking strategies](archive/2025-01/mixed-chunking-strategies.md) to support multiple document formats
4. FastAPI endpoints for accessing the search functionality

## Setup Instructions

### 1. Prepare the Documentation PDFs

Place the RV-C specification PDF in the resources directory with a standardized name:

```bash
cp /path/to/your/rv-c-spec.pdf resources/rvc-spec-2023-11.pdf
```

You can also add additional documentation sources:

```bash
# Add equipment manuals
cp /path/to/victron/manual.pdf resources/victron-multiplus-manual.pdf
cp /path/to/firefly/manual.pdf resources/firefly-g31-manual.pdf
```

### 2. Set up OpenAI API Key

The embedding generation requires an OpenAI API key. Set it in your environment:

```bash
# For bash/zsh shells:
export OPENAI_API_KEY="your-openai-api-key"

# For fish shell:
set -x OPENAI_API_KEY "your-openai-api-key"
```

You can obtain an API key from [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys)

### 3. Building the Index (Recommended)

Use the document processor to chunk the PDF and build the FAISS index in one step:

```bash
poetry run python dev_tools/enhanced_document_processor.py \
  --pdf resources/rv-c-spec.pdf \
  --chunking section_overlap \
  --add-to-index resources/vector_store/
```

### 4. Manual Setup (Alternative)

If you prefer to set up each component manually:

First, generate text chunks from the PDFs:

```bash
# For RV-C spec with section-based chunking
poetry run python dev_tools/generate_embeddings.py

# You can create custom chunking scripts for other document types
# Example: For paragraph-based chunking of equipment manuals
poetry run python dev_tools/chunk_paragraphs.py resources/victron-multiplus-manual.pdf
```

This will:

- Process the PDFs into text chunks with metadata
- Apply appropriate chunking strategies based on document type
- Save the chunks to JSON files (e.g., `resources/rvc_spec_chunks_with_overlap.json`)

Then, generate the FAISS vector index:

```bash
# Generate index from RV-C spec chunks
poetry run python dev_tools/generate_faiss_index.py
```

This will:

- Convert the text chunks to document objects with standardized metadata
- Add source and chunking strategy information to enable filtering
- Generate embeddings using OpenAI's model
- Generate embeddings using the OpenAI API
- Create and save a FAISS index to `resources/vector_store/rvc_spec_index`

### 5. Start/Restart the Server

Start or restart the FastAPI server to load the new index:

```bash
poetry run python run_server.py
```

## Using the Documentation Search

### Command Line Usage (New!)

You can query the documentation directly from the command line:

```bash
# Basic search
poetry run python dev_tools/query_faiss.py "how to calculate battery state of charge"

# Filter by document source
poetry run python dev_tools/query_faiss.py "battery monitoring" --source rvc-spec-2023-11.pdf

# Filter by chunking strategy
poetry run python dev_tools/query_faiss.py "battery monitoring" --chunking section_overlap

# Limit number of results
poetry run python dev_tools/query_faiss.py "battery monitoring" --count 5
```

### Via Web Interface

The easiest way to use the search in the application is through the web interface:

1. Open the web UI in your browser (typically at [http://localhost:8000](http://localhost:8000) or [http://localhost:5173](http://localhost:5173) for development)
2. Navigate to the "Documentation" page from the navigation menu
3. Use the search box to enter your query

### Via API Endpoint

You can query the documentation search through the API endpoint:

```bash
curl "http://localhost:8000/api/docs/search?query=battery%20charging%20parameters&k=3"
```

Parameters:

- `query`: (Required) Your natural language search query
- `k`: (Optional, default=3) Number of results to return (1-10)

## Adding Multiple Document Sources

You can now mix different document types in the search index:

### Adding New Documents

1. **Process your document** with an appropriate chunking strategy
2. **Generate embeddings** for these chunks
3. **Add to the existing index** with source and chunking metadata

For a complete step-by-step guide on processing new PDF files and adding them to the FAISS index, refer to the [PDF Processing Guide](archive/2025-01/pdf-processing-guide.md).

Example code:

```python
from pathlib import Path
from document_loader import ChunkingStrategy, load_chunk_with_metadata
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS

# Process your document with appropriate chunking (See PDF Processing Guide for details)
# This would create your_chunks with appropriate text and metadata

# Load chunks with standard metadata
new_docs = load_chunk_with_metadata(
    chunks_data=your_chunks,
    source_path=Path("resources/your-document.pdf"),
    chunking_strategy=ChunkingStrategy.PARAGRAPH
)

# Load existing index
embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
vectorstore = FAISS.load_local("resources/vector_store/rvc_spec_index", embeddings)

# Add new documents to index
vectorstore.add_documents(new_docs)

# Save updated index
vectorstore.save_local("resources/vector_store/rvc_spec_index")
```

### Supported Chunking Strategies

The `document_loader` module provides several chunking strategies for different document types:

| Strategy          | Description                             | Best For                                     |
| ----------------- | --------------------------------------- | -------------------------------------------- |
| `SECTION_OVERLAP` | Based on document sections with overlap | Technical specifications with clear sections |
| `PARAGRAPH`       | Based on natural paragraphs             | Prose-heavy manuals and guides               |
| `TOKEN`           | Fixed token size chunks                 | Consistent embeddings for mixed content      |
| `SLIDING_WINDOW`  | Window with configurable overlap        | Code or dense technical content              |

### Filtering Results By Source

When querying, you can filter by document source to focus on specific documentation:

```python
from document_loader import filter_results_by_source

# Get initial results
results = vectorstore.similarity_search(query, k=10)

# Filter to specific sources
rvc_results = filter_results_by_source(results, source="rvc-spec-2023-11.pdf", limit=3)
victron_results = filter_results_by_source(results, source="victron-multiplus-manual.pdf", limit=3)
```

## Troubleshooting

If you encounter issues with the documentation search:

### Common Issues

1. **Search Not Available Error**: This typically means either:

   - The FAISS index hasn't been created yet
   - The OpenAI API key is missing or invalid
   - The server can't find the vector store files

2. **Missing PDF**: If you're missing the RV-C specification PDF:

   - Check your RV manufacturer's resources
   - Contact RVIA for access to the specification

3. **OpenAI API Issues**:
   - Verify your API key is valid and has sufficient quota
   - Check your billing status on the OpenAI dashboard
   - Try using a different API key if available

### Diagnostic Steps

1. Check the search service status to identify issues:

   ```bash
   curl "http://localhost:8000/api/docs/status"
   ```

2. Verify file paths:

   - PDF: `resources/rv-c-spec.pdf`
   - Chunks file: `resources/rvc_spec_chunks_with_overlap.json`
   - FAISS index: `resources/vector_store/rvc_spec_index/`

3. Check server logs for specific error messages:

   ```bash
   # On most systems
   journalctl -u coachiq.service -f

   # When running manually, check the terminal output
   ```

4. Test the search endpoint directly:

   ```bash
   curl -v "http://localhost:8000/api/docs/search?query=test"
   ```

### Advanced Troubleshooting

If the above steps don't resolve your issue:

1. Regenerate the chunks and index:

   ```bash
   rm resources/rvc_spec_chunks_with_overlap.json
   rm -rf resources/vector_store/rvc_spec_index
   poetry run python dev_tools/enhanced_document_processor.py \
     --pdf resources/rv-c-spec.pdf \
     --chunking section_overlap \
     --add-to-index resources/vector_store/
   ```

2. Check for Python package issues:

   ```bash
   poetry install
   ```

3. Verify the HTTP status from the API endpoint (503 means service unavailable)

For more detailed help, see the project documentation or create an issue on GitHub.
