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

## Step 2: Choose a Chunking Strategy

Select the appropriate chunking strategy based on your document's structure:

| Document Type      | Recommended Strategy | Use Case                                      |
| ------------------ | -------------------- | --------------------------------------------- |
| RV-C Specification | `SECTION_OVERLAP`    | Technical specifications with section numbers |
| Equipment Manuals  | `PARAGRAPH`          | User manuals with natural paragraphs          |
| Generic PDFs       | `SLIDING_WINDOW`     | General text with no clear structure          |
| Technical Docs     | `TOKEN`              | Fixed-size token-based chunks                 |

## Step 3: Process Your PDF with the Enhanced Document Processor

Use the enhanced document processor (`enhanced_document_processor.py`) which supports multiple chunking strategies and can automatically detect the most appropriate strategy for your document.

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

## Step 4: Test Your Index

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
- **Chunks too large**: Adjust chunking strategy for shorter text segments
- **Inconsistent metadata**: Ensure document_loader is used for all sources

### Testing Document Loader

Use the test_document_loader.py script to verify your chunks are correctly processed:

```bash
poetry run python dev_tools/test_document_loader.py
```

## References

- [LangChain FAISS Integration](https://docs.langchain.com/docs/integrations/vectorstores/faiss)
- [PyMuPDF Documentation](https://pymupdf.readthedocs.io/)
- [OpenAI Embeddings Documentation](https://platform.openai.com/docs/guides/embeddings)
