# PDF Processing Guide for Vector Search

This guide explains how to process PDF files through the enhanced document processor to generate embeddings for the FAISS index in the RVC2API project. The tool supports multiple chunking strategies and can automatically detect the most appropriate strategy for your document.

## Workflow Overview

The process of adding a new PDF document to the searchable FAISS index involves these steps:

1. **Prepare the PDF document** - Place in resources directory
2. **Process the PDF into chunks** - Generate text chunks with appropriate strategy
3. **Create embeddings and update the index** - Convert chunks to vectors and add to FAISS
4. **Verify and test the search** - Ensure the new content is searchable

## Prerequisites

- Python 3.9+ with proper type annotations
- OpenAI API key set in your environment (`export OPENAI_API_KEY=your-api-key`)
- Poetry dependencies installed with `poetry install --with devtools`
- PDF document(s) you want to add to the search index

## Step 1: Prepare Your PDF Document

1. Place your PDF file in the `resources/` directory
2. Recommended: Use a consistent naming convention that describes content and version
   ```
   resources/your-document-name-2023.pdf
   ```

## Step 2: Process Your PDF with the Enhanced Document Processor

The enhanced document processor (`enhanced_document_processor.py`) supports multiple chunking strategies and can automatically detect the most appropriate strategy for your document.

### Basic Usage (Auto-Detect)

```bash
poetry run python dev_tools/enhanced_document_processor.py --pdf resources/your-document-name-2023.pdf
```

This will:

1. Auto-detect the best chunking strategy based on document structure
2. Process the document with the selected strategy
3. Save chunks to `resources/your-document-name-2023_chunks.json`

### Specify Chunking Strategy

You can specify a chunking strategy if you know what works best for your document:

```bash
poetry run python dev_tools/enhanced_document_processor.py \
  --pdf resources/your-document-name-2023.pdf \
  --chunking section_overlap
```

Available chunking strategies:

- `section_overlap`: For technical specifications with clear section numbering
- `paragraph`: For manuals and documents with natural paragraph breaks
- `sliding_window`: For generic documents with no clear structure
- `token`: For fixed-size token-based chunking

### Process and Add to FAISS Index in One Step

```bash
poetry run python dev_tools/enhanced_document_processor.py \
  --pdf resources/your-document-name-2023.pdf \
  --add-to-index resources/vector_store/rvc_spec_index
```

This processes the PDF and adds it to an existing FAISS index in one operation.

### Create a New FAISS Index

```bash
poetry run python dev_tools/enhanced_document_processor.py \
  --pdf resources/your-document-name-2023.pdf \
  --add-to-index resources/vector_store/new_index \
  --create-new-index
```

This processes the PDF and creates a new FAISS index.

## Chunking Strategy Options

### Section-Based Chunking

Best for technical specifications with clear section numbering:

```bash
poetry run python dev_tools/enhanced_document_processor.py \
  --pdf resources/your-document-name-2023.pdf \
  --chunking section_overlap \
  --section-pattern "^(\d+\.\d+(\.\d+)?)(\s+)(.+)" \
  --overlap 5
```

### Paragraph-Based Chunking

Best for manuals and documents with natural paragraph breaks:

```bash
poetry run python dev_tools/enhanced_document_processor.py \
  --pdf resources/your-document-name-2023.pdf \
  --chunking paragraph
```

### Sliding Window Chunking

Best for generic documents with no clear structure:

```bash
poetry run python dev_tools/enhanced_document_processor.py \
  --pdf resources/your-document-name-2023.pdf \
  --chunking sliding_window \
  --window-size 10 \
  --overlap 3
```

### Token-Based Chunking

Best for fixed-size chunks:

```bash
poetry run python dev_tools/enhanced_document_processor.py \
  --pdf resources/your-document-name-2023.pdf \
  --chunking token \
  --chunk-size 512 \
  --overlap 50
```

## Advanced Options

### Custom Output Path

```bash
poetry run python dev_tools/enhanced_document_processor.py \
  --pdf resources/your-document-name-2023.pdf \
  --output resources/custom_output_name.json
```

### Specify Embedding Model

```bash
poetry run python dev_tools/enhanced_document_processor.py \
  --pdf resources/your-document-name-2023.pdf \
  --add-to-index resources/vector_store/rvc_spec_index \
  --model text-embedding-3-small
```

### Custom Source Tag

Override the source tag in the metadata when you want to use a standardized name:

```bash
poetry run python dev_tools/enhanced_document_processor.py \
  --pdf resources/rvc-spec-2023-11-local-copy.pdf \
  --add-to-index resources/vector_store/rvc_spec_index \
  --source-tag "rvc-spec-2023-11.pdf"
```

### Skip Initial Pages

Skip cover pages, table of contents, or other front matter pages that might contain section-like patterns but aren't actual content:

```bash
poetry run python dev_tools/enhanced_document_processor.py \
  --pdf resources/your-document-name-2023.pdf \
  --skip-pages 5 \
  --chunking section_overlap
```

This is particularly useful when processing technical PDFs where the table of contents might match section patterns but shouldn't be included in the chunks.

### Dry Run Mode

Process a document without saving the output or modifying the index:

```bash
poetry run python dev_tools/enhanced_document_processor.py \
  --pdf resources/your-document-name-2023.pdf \
  --dry-run
```

This is useful for testing chunking strategies on new document types.

## Step 3: Test Your Index

Verify that your document is properly indexed and searchable:

```bash
# Test searching in the index
poetry run python dev_tools/query_faiss.py "your search query" --source "your-document-name-2023.pdf"
```

## Examples by Document Type

### Technical Specification

```bash
poetry run python dev_tools/enhanced_document_processor.py \
  --pdf resources/rvc-spec-2023-11.pdf \
  --chunking section_overlap \
  --skip-pages 5 \
  --add-to-index resources/vector_store/rvc_spec_index
```

### User Manual

```bash
poetry run python dev_tools/enhanced_document_processor.py \
  --pdf resources/victron-multiplus-manual.pdf \
  --chunking paragraph \
  --add-to-index resources/vector_store/manuals_index
```

### Generic PDF

```bash
poetry run python dev_tools/enhanced_document_processor.py \
  --pdf resources/misc-document.pdf \
  --chunking sliding_window \
  --add-to-index resources/vector_store/misc_index
```

## Troubleshooting

### Common Issues

- **Missing API key**: Set `export OPENAI_API_KEY=your-api-key`
- **PDF extraction errors**: Use PyMuPDF debugging tools and check PDF encoding
- **Table of contents being chunked**: Use `--skip-pages` to skip TOC/front matter
- **Chunks too large**: Adjust chunking strategy for shorter text segments
- **Inconsistent metadata**: Ensure document_loader is used for all sources
- **Source tag conflicts**: Use `--source-tag` to ensure consistent naming
- **Processing errors**: Check the detailed error messages in the summary report
- **Index confusion**: Use `--dry-run` to test processing without modifying files

### Testing Document Loader

Use the test_document_loader.py script to verify your chunks are correctly processed:

```bash
poetry run python dev_tools/test_document_loader.py
```

### Viewing Processing Summary

The enhanced document processor now provides a detailed summary at the end of processing:

```
========================================================
DOCUMENT PROCESSING SUMMARY
========================================================
Document: resources/your-document-name-2023.pdf
Chunking method: section_overlap
Chunks generated: 42
Processing time: 3.25 seconds
Status: SUCCESS
Output chunks: resources/your-document-name-2023_chunks.json
Added to index: resources/vector_store/rvc_spec_index
========================================================
```

This summary helps identify any issues in the processing workflow.

## Using Alternative OpenAI API Endpoints

The enhanced document processor now supports Azure OpenAI and other OpenAI-compatible endpoints.

### Azure OpenAI

To use Azure OpenAI for embeddings, set the required environment variables:

```bash
export OPENAI_API_KEY="your-azure-api-key"
export OPENAI_API_BASE="https://your-resource-name.openai.azure.com/"
export OPENAI_API_VERSION="2023-05-15"
export OPENAI_API_TYPE="azure"
export OPENAI_DEPLOYMENT_NAME="your-deployment-id"
```

Then run the document processor normally:

```bash
poetry run python dev_tools/enhanced_document_processor.py \
  --pdf resources/your-document-name-2023.pdf \
  --add-to-index resources/vector_store/your_index
```

Alternatively, you can specify API details via command-line arguments:

```bash
poetry run python dev_tools/enhanced_document_processor.py \
  --pdf resources/your-document-name-2023.pdf \
  --add-to-index resources/vector_store/your_index \
  --api-type azure \
  --api-base "https://your-resource-name.openai.azure.com/" \
  --api-version "2023-05-15" \
  --deployment-name "your-deployment-id"
```

> **Note**: For Azure OpenAI, `deployment-name` is used instead of `model`, but you should still set the `--model` parameter for fallback purposes.

### Custom OpenAI-Compatible Endpoints

You can also use other OpenAI-compatible endpoints, such as local servers, proxies, or alternative providers:

```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_API_BASE="http://localhost:8000/v1"
```

Or via command-line:

```bash
poetry run python dev_tools/enhanced_document_processor.py \
  --pdf resources/your-document-name-2023.pdf \
  --add-to-index resources/vector_store/your_index \
  --api-type custom \
  --api-base "http://localhost:8000/v1"
```

This allows you to use services like:
- vLLM in OpenAI-compatible mode
- LM Studio local servers
- Other OpenAI-compatible API providers

## References

- [LangChain FAISS Integration](https://docs.langchain.com/docs/integrations/vectorstores/faiss)
- [PyMuPDF Documentation](https://pymupdf.readthedocs.io/)
- [OpenAI Embeddings Documentation](https://platform.openai.com/docs/guides/embeddings)
- [Azure OpenAI Service Documentation](https://learn.microsoft.com/en-us/azure/ai-services/openai/)
