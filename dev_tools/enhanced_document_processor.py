#!/usr/bin/env python3
"""
Versatile PDF processor for FAISS embeddings.

This script processes a PDF document with various chunking strategies,
extracts text content, and generates chunks for embeddings generation.
It supports multiple document types and chunking strategies without requiring
custom scripts for each document type.
"""

import argparse
import json
import os
import re
import sys
from enum import Enum
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

# Import for document loader
from document_loader import ChunkingStrategy, load_chunk_with_metadata
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS


class ChunkingMethod(str, Enum):
    """Enumeration of supported chunking methods."""

    SECTION_OVERLAP = "section_overlap"  # Sections with overlap
    PARAGRAPH = "paragraph"  # Natural paragraphs
    TOKEN = "token"  # Fixed-size token chunks
    SLIDING_WINDOW = "sliding_window"  # Sliding window with overlap


def chunk_by_sections(
    pdf_path: Path,
    overlap: int = 5,
    skip_pages: int = 0,
    section_pattern: str = r"^(\d+\.\d+(\.\d+)?)(\s+)(.+)",
) -> list[dict[str, Any]]:
    """
    Process PDF into chunks using section headings with overlapping lines.

    Best for technical specifications with clear section numbering.

    Args:
        pdf_path: Path to the PDF file
        overlap: Number of lines to overlap between chunks
        skip_pages: Number of pages to skip from the beginning (for TOC, cover, etc.)
        section_pattern: Regex pattern to identify section headings

    Returns:
        List of dictionaries with text chunks and metadata
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    doc = fitz.open(pdf_path)
    section_regex = re.compile(section_pattern)

    chunks = []
    current_chunk = []
    current_meta = {}
    previous_tail = []

    for page_num in range(len(doc)):
        # Skip initial pages (TOC, cover pages, etc.)
        if page_num < skip_pages:
            continue

        page = doc[page_num]
        text = page.get_text("text")
        lines = text.splitlines()

        for line in lines:
            match = section_regex.match(line.strip())
            if match:
                if current_chunk:
                    # Append previous tail for overlap
                    if previous_tail:
                        current_chunk = previous_tail + current_chunk
                    chunks.append(
                        {
                            "text": "\n".join(current_chunk).strip(),
                            "section": current_meta.get("section"),
                            "title": current_meta.get("title"),
                            "pages": list(set(current_meta.get("pages", []))),
                        }
                    )
                    # Save tail of current chunk for next overlap
                    previous_tail = (
                        current_chunk[-overlap:] if len(current_chunk) >= overlap else current_chunk
                    )
                    current_chunk = []

                section = match.group(1)
                title = match.group(4)
                current_meta = {
                    "section": section,
                    "title": title,
                    "pages": [page_num + 1],
                }
                current_chunk.append(f"Section: {section} {title}")
            elif current_chunk:
                current_chunk.append(line.strip())
                current_meta["pages"].append(page_num + 1)

    # Add last chunk
    if current_chunk:
        if previous_tail:
            current_chunk = previous_tail + current_chunk
        chunks.append(
            {
                "text": "\n".join(current_chunk).strip(),
                "section": current_meta.get("section"),
                "title": current_meta.get("title"),
                "pages": list(set(current_meta.get("pages", []))),
            }
        )

    return chunks


def chunk_by_paragraphs(
    pdf_path: Path, min_length: int = 50, skip_pages: int = 0
) -> list[dict[str, Any]]:
    """
    Process PDF into chunks by paragraphs.

    Best for manuals and documents with natural paragraph breaks.

    Args:
        pdf_path: Path to the PDF file
        min_length: Minimum character length for a paragraph to be included
        skip_pages: Number of pages to skip from the beginning (for TOC, cover, etc.)

    Returns:
        List of dictionaries with text chunks and metadata
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    doc = fitz.open(pdf_path)
    chunks = []

    for page_num in range(len(doc)):
        # Skip initial pages (TOC, cover pages, etc.)
        if page_num < skip_pages:
            continue

        page = doc[page_num]
        text = page.get_text("text")

        # Split by double newlines (common paragraph separator)
        paragraphs = re.split(r"\n\s*\n", text)

        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if paragraph and len(paragraph) >= min_length:
                # Check for potential heading
                lines = paragraph.splitlines()
                first_line = lines[0] if lines else ""
                title = ""

                # Simple heuristic for identifying headers
                if len(first_line) < 80 and (first_line.isupper() or first_line.endswith(":")):
                    title = first_line

                chunks.append(
                    {
                        "text": paragraph,
                        "title": title,
                        "pages": [page_num + 1],
                    }
                )

    return chunks


def chunk_by_sliding_window(
    pdf_path: Path, window_size: int = 10, overlap: int = 3, skip_pages: int = 0
) -> list[dict[str, Any]]:
    """
    Process PDF into chunks using a sliding window of lines.

    Best for generic documents with no clear structure.

    Args:
        pdf_path: Path to the PDF file
        window_size: Number of lines per chunk
        overlap: Number of lines to overlap between chunks
        skip_pages: Number of pages to skip from the beginning (for TOC, cover, etc.)

    Returns:
        List of dictionaries with text chunks and metadata
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    doc = fitz.open(pdf_path)
    all_lines = []
    page_map = []  # Maps line index to page number

    # First pass: collect all lines and page mappings
    for page_num in range(len(doc)):
        # Skip initial pages (TOC, cover pages, etc.)
        if page_num < skip_pages:
            continue

        page = doc[page_num]
        text = page.get_text("text")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        all_lines.extend(lines)
        page_map.extend([page_num + 1] * len(lines))

    chunks = []
    step = window_size - overlap

    # Create sliding window chunks
    for i in range(0, len(all_lines), step):
        window = all_lines[i : i + window_size]
        if window:  # Skip empty windows
            # Get page range for this window
            start_idx = i
            end_idx = min(i + window_size - 1, len(page_map) - 1)
            pages = list(set(page_map[start_idx : end_idx + 1]))

            chunks.append(
                {
                    "text": "\n".join(window),
                    "pages": pages,
                }
            )

    return chunks


def chunk_by_fixed_token_size(
    pdf_path: Path,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    skip_pages: int = 0,
    separator: str = " ",
) -> list[dict[str, Any]]:
    """
    Process PDF into chunks of approximately fixed token sizes.

    This is a simplified version that uses characters as a proxy for tokens.
    For more accurate token counts, a tokenizer should be used.

    Args:
        pdf_path: Path to the PDF file
        chunk_size: Target size of each chunk in approximate tokens
        chunk_overlap: Number of tokens to overlap between chunks
        skip_pages: Number of pages to skip from the beginning (for TOC, cover, etc.)
        separator: Token separator (space for English)

    Returns:
        List of dictionaries with text chunks and metadata
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    doc = fitz.open(pdf_path)
    full_text = ""
    page_breaks = [0]  # Character position of page breaks
    page_mapping = {}  # Map original page numbers to adjusted ones

    # Extract full text with page break positions
    adjusted_page = 0
    for page_num in range(len(doc)):
        # Skip initial pages (TOC, cover pages, etc.)
        if page_num < skip_pages:
            continue

        page = doc[page_num]
        text = page.get_text("text")
        page_mapping[adjusted_page] = page_num + 1  # Store original page number
        adjusted_page += 1
        full_text += text
        page_breaks.append(len(full_text))

    # Split into tokens (words for simplicity)
    tokens = full_text.split(separator)
    chunks = []

    # Create chunks of approximately chunk_size tokens
    for i in range(0, len(tokens), chunk_size - chunk_overlap):
        chunk_tokens = tokens[i : i + chunk_size]
        if chunk_tokens:
            chunk_text = separator.join(chunk_tokens)

            # Find pages this chunk appears on
            chunk_start = sum(len(t) + len(separator) for t in tokens[:i])
            chunk_end = chunk_start + len(chunk_text)

            # Find pages this chunk appears on
            pages = []
            for p in range(1, len(page_breaks)):
                if (
                    (page_breaks[p - 1] <= chunk_start < page_breaks[p])
                    or (page_breaks[p - 1] <= chunk_end < page_breaks[p])
                    or (chunk_start <= page_breaks[p - 1] and chunk_end >= page_breaks[p])
                ):
                    pages.append(p)

            chunks.append(
                {
                    "text": chunk_text,
                    "pages": pages,
                }
            )

    return chunks


def detect_document_type(pdf_path: Path) -> ChunkingMethod:
    """
    Auto-detect the best chunking strategy based on document content.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Recommended chunking method
    """
    doc = fitz.open(pdf_path)

    # Sample first few pages to analyze structure
    section_pattern = re.compile(r"^\d+\.\d+(\.\d+)?\s+\w+")
    section_matches = 0
    paragraph_breaks = 0
    sampled_pages = min(5, len(doc))

    for page_num in range(sampled_pages):
        page = doc[page_num]
        text = page.get_text("text")
        lines = text.splitlines()

        # Count section heading patterns
        for line in lines:
            if section_pattern.match(line.strip()):
                section_matches += 1

        # Count paragraph breaks
        paragraph_breaks += text.count("\n\n")

    # Make recommendation based on document structure
    if section_matches > 5:
        return ChunkingMethod.SECTION_OVERLAP  # Clear section structure
    if paragraph_breaks > 10:
        return ChunkingMethod.PARAGRAPH  # Clear paragraph structure
    return ChunkingMethod.SLIDING_WINDOW  # Default to sliding window


def process_pdf(
    pdf_path: Path, output_path: Path | None, chunking_method: ChunkingMethod, **kwargs
) -> list[dict[str, Any]]:
    """
    Process PDF using the specified chunking method.

    Args:
        pdf_path: Path to the PDF file
        output_path: Path to save the chunked JSON output, or None in dry-run mode
        chunking_method: Method used to chunk the document
        **kwargs: Additional parameters for specific chunking methods

    Returns:
        List of dictionaries containing chunked text with metadata

    Raises:
        ValueError: If an invalid chunking method is specified
        FileNotFoundError: If the PDF file cannot be opened
        RuntimeError: If document processing fails
    """
    # Check if the PDF exists and is readable
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    if not pdf_path.is_file():
        raise ValueError(f"Not a file: {pdf_path}")

    # Select processing function and handle potential errors
    try:
        if chunking_method == ChunkingMethod.SECTION_OVERLAP:
            chunks = chunk_by_sections(
                pdf_path,
                overlap=kwargs.get("overlap", 5),
                skip_pages=kwargs.get("skip_pages", 0),
                section_pattern=kwargs.get("section_pattern", r"^(\d+\.\d+(\.\d+)?)(\s+)(.+)"),
            )
        elif chunking_method == ChunkingMethod.PARAGRAPH:
            chunks = chunk_by_paragraphs(
                pdf_path,
                min_length=kwargs.get("min_length", 50),
                skip_pages=kwargs.get("skip_pages", 0),
            )
        elif chunking_method == ChunkingMethod.SLIDING_WINDOW:
            chunks = chunk_by_sliding_window(
                pdf_path,
                window_size=kwargs.get("window_size", 10),
                overlap=kwargs.get("overlap", 3),
                skip_pages=kwargs.get("skip_pages", 0),
            )
        elif chunking_method == ChunkingMethod.TOKEN:
            chunks = chunk_by_fixed_token_size(
                pdf_path,
                chunk_size=kwargs.get("chunk_size", 512),
                chunk_overlap=kwargs.get("chunk_overlap", 50),
                skip_pages=kwargs.get("skip_pages", 0),
            )
        else:
            raise ValueError(f"Invalid chunking method: {chunking_method}")
    except Exception as e:
        raise RuntimeError(f"Failed to process {pdf_path} with {chunking_method}: {e!s}") from e

    # Validate that chunks were successfully generated
    if not chunks:
        raise RuntimeError(
            f"No chunks were generated using {chunking_method}. Try a different method."
        )

    # Add source and chunking strategy to all chunks
    for chunk in chunks:
        chunk["source"] = pdf_path.name
        chunk["chunking"] = chunking_method

    # Write chunks to output file if path is provided (not in dry-run mode)
    if output_path:
        try:
            # Create output directory if it doesn't exist
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Write chunks to output file
            with open(output_path, "w") as f:
                json.dump(chunks, f, indent=2)
        except Exception as e:
            raise RuntimeError(f"Failed to write output to {output_path}: {e!s}") from e

    return chunks


def add_to_faiss_index(
    chunks: list[dict[str, Any]],
    source_path: Path,
    chunking_strategy: ChunkingStrategy,
    index_path: Path,
    model_name: str = "text-embedding-3-large",
    create_new: bool = False,
) -> None:
    """
    Add document chunks to a FAISS index.

    Args:
        chunks: List of chunk dictionaries
        source_path: Path to the source document
        chunking_strategy: Chunking strategy used
        index_path: Path to the FAISS index
        model_name: OpenAI embedding model to use
        create_new: Whether to create a new index instead of adding to existing

    Raises:
        ValueError: If chunks list is empty or invalid
        RuntimeError: If there's an error in document conversion or FAISS operations
    """
    if not chunks:
        raise ValueError("No chunks provided to add to the FAISS index")

    # Convert chunks to Document objects with metadata
    try:
        docs = load_chunk_with_metadata(
            chunks_data=chunks,
            source_path=source_path,
            chunking_strategy=chunking_strategy,
        )

        if not docs:
            raise ValueError("No valid documents were generated from the chunks")

    except Exception as e:
        raise RuntimeError(f"Failed to convert chunks to documents: {e!s}") from e

    # Initialize embeddings
    try:
        # Check if using Azure OpenAI or custom endpoint
        api_type = os.getenv("OPENAI_API_TYPE", "").lower()

        if api_type == "azure":
            # Using Azure OpenAI
            embeddings = OpenAIEmbeddings(
                model=model_name,  # Still used for non-Azure
                deployment=os.getenv(
                    "OPENAI_DEPLOYMENT_NAME", model_name
                ),  # Azure uses deployment name
                openai_api_base=os.getenv(
                    "OPENAI_API_BASE"
                ),  # e.g., https://<resource>.openai.azure.com/
                openai_api_type="azure",
                openai_api_version=os.getenv("OPENAI_API_VERSION", "2023-05-15"),
            )
            print("Using Azure OpenAI for embeddings")
        elif os.getenv("OPENAI_API_BASE"):
            # Using custom OpenAI-compatible endpoint (like local server, proxy, etc.)
            embeddings = OpenAIEmbeddings(
                model=model_name,
                openai_api_base=os.getenv("OPENAI_API_BASE"),
            )
            print(f"Using custom OpenAI-compatible endpoint: {os.getenv('OPENAI_API_BASE')}")
        else:
            # Default to standard OpenAI
            embeddings = OpenAIEmbeddings(model=model_name)
            print(f"Using standard OpenAI API with model: {model_name}")
    except Exception as e:
        raise RuntimeError(f"Failed to initialize OpenAI embeddings: {e!s}") from e

    # Process FAISS index
    try:
        if create_new or not index_path.exists():
            # Create new FAISS index
            vectorstore = FAISS.from_documents(docs, embeddings)
            print(f"Created new FAISS index with {len(docs)} documents")
        else:
            # Add to existing index
            vectorstore = FAISS.load_local(
                str(index_path), embeddings, allow_dangerous_deserialization=True
            )
            print(f"Loaded existing FAISS index from {index_path}")
            vectorstore.add_documents(docs)
            print(f"Added {len(docs)} new documents to index")

        # Ensure the directory exists
        index_path.parent.mkdir(parents=True, exist_ok=True)

        # Save the index
        vectorstore.save_local(str(index_path))
        print(f"Saved FAISS index to {index_path}")

    except Exception as e:
        raise RuntimeError(f"FAISS index operation failed: {e!s}") from e


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Process PDF documents for FAISS embeddings with multiple chunking strategies"
    )

    parser.add_argument(
        "--pdf", "-p", type=Path, required=True, help="Path to the PDF file to process"
    )

    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Path for the output JSON file with chunks (default: based on PDF name)",
    )

    parser.add_argument(
        "--chunking",
        "-c",
        type=str,
        choices=[m.value for m in ChunkingMethod],
        help="Chunking strategy to use (default: auto-detect)",
    )

    parser.add_argument(
        "--add-to-index",
        "-i",
        type=Path,
        help="Add chunks to FAISS index at specified path (default: don't add to index)",
    )

    parser.add_argument(
        "--create-new-index",
        "-n",
        action="store_true",
        help="Create a new FAISS index instead of adding to existing",
    )

    parser.add_argument(
        "--source-tag",
        type=str,
        help="Override the source tag in the metadata (default: uses normalized filename)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Process the document but don't save output or add to index",
    )

    parser.add_argument(
        "--overlap",
        type=int,
        default=5,
        help="Number of lines/tokens to overlap between chunks (default: 5)",
    )

    parser.add_argument(
        "--window-size",
        type=int,
        default=10,
        help="Number of lines per chunk for sliding window (default: 10)",
    )

    parser.add_argument(
        "--chunk-size",
        type=int,
        default=512,
        help="Target token size for token-based chunking (default: 512)",
    )

    parser.add_argument(
        "--section-pattern",
        type=str,
        default=r"^(\d+\.\d+(\.\d+)?)(\s+)(.+)",
        help="Regex pattern to identify section headings (default: numbered sections)",
    )

    parser.add_argument(
        "--skip-pages",
        type=int,
        default=0,
        help="Number of pages to skip from the beginning (for TOC, cover pages, etc.)",
    )

    parser.add_argument(
        "--model",
        type=str,
        default="text-embedding-3-large",
        help="OpenAI embedding model to use (default: text-embedding-3-large)",
    )

    parser.add_argument(
        "--auto-detect",
        "-a",
        action="store_true",
        help="Auto-detect the best chunking strategy based on document structure",
    )

    # API endpoint configuration options
    parser.add_argument(
        "--api-type",
        type=str,
        choices=["openai", "azure", "custom"],
        help="API type to use (default: use OPENAI_API_TYPE env var or 'openai')",
    )

    parser.add_argument(
        "--api-base",
        type=str,
        help="Base URL for API (default: use OPENAI_API_BASE env var)",
    )

    parser.add_argument(
        "--api-version",
        type=str,
        help="API version for Azure (default: use OPENAI_API_VERSION env var or '2023-05-15')",
    )

    parser.add_argument(
        "--deployment-name",
        type=str,
        help="Azure OpenAI deployment name (default: use OPENAI_DEPLOYMENT_NAME env var or model name)",
    )

    return parser.parse_args()


def main() -> None:
    """Process PDF and generate chunks for embeddings."""
    args = parse_arguments()

    # Validate PDF exists
    if not args.pdf.exists():
        print(f"Error: PDF file not found: {args.pdf}")
        sys.exit(1)

    # Determine chunking method
    chunking_method = None
    if args.chunking:
        chunking_method = ChunkingMethod(args.chunking)
    elif args.auto_detect:
        print("Auto-detecting best chunking strategy...")
        chunking_method = detect_document_type(args.pdf)
        print(f"Detected document structure: {chunking_method}")
    else:
        # Default to auto-detect
        print("Auto-detecting best chunking strategy...")
        chunking_method = detect_document_type(args.pdf)
        print(f"Detected document structure: {chunking_method}")

    # Determine output path if not specified and not in dry-run mode
    output_path = None
    if not args.dry_run:
        if not args.output:
            pdf_stem = args.pdf.stem
            output_path = Path(f"resources/{pdf_stem}_chunks.json")
        else:
            output_path = args.output

    # Process PDF with selected chunking method
    print(f"Processing PDF: {args.pdf}")
    print(f"Using chunking method: {chunking_method}")

    if args.dry_run:
        print("DRY RUN MODE: No files will be saved or modified")

    # Collection statistics for summary report
    stats = {
        "pdf_path": str(args.pdf),
        "chunking_method": str(chunking_method),
        "chunks_generated": 0,
        "start_time": None,
        "end_time": None,
        "success": False,
        "error_message": None,
    }

    import time

    stats["start_time"] = time.time()

    kwargs = {
        "overlap": args.overlap,
        "window_size": args.window_size,
        "chunk_size": args.chunk_size,
        "section_pattern": args.section_pattern,
        "skip_pages": args.skip_pages,
    }

    try:
        chunks = process_pdf(
            args.pdf,
            output_path if not args.dry_run else None,
            chunking_method,
            **kwargs,
        )
        stats["chunks_generated"] = len(chunks)
        stats["success"] = True

        print(f"Generated {len(chunks)} chunks")

        # Save chunks to file if not in dry run mode
        if not args.dry_run and output_path:
            print(f"Saved chunks to: {output_path}")

        # Add to FAISS index if specified and not in dry run mode
        if args.add_to_index and not args.dry_run:
            if not os.getenv("OPENAI_API_KEY"):
                print("Error: OPENAI_API_KEY environment variable not set")
                print("Set your API key with: export OPENAI_API_KEY=your-api-key")
                sys.exit(1)

            print(f"Adding chunks to FAISS index at {args.add_to_index}")
            try:
                chunking_strategy = ChunkingStrategy(chunking_method)

                # Use source_tag override if provided
                source_path = args.pdf
                if args.source_tag:
                    # Create a custom Path object that returns the source_tag when .name is accessed
                    class CustomPath(Path):
                        @property
                        def name(self):
                            return args.source_tag

                    source_path = CustomPath(args.pdf)
                    print(f"Using custom source tag: {args.source_tag}")

                # Set environment variables if provided by command line
                if args.api_type:
                    os.environ["OPENAI_API_TYPE"] = args.api_type
                if args.api_base:
                    os.environ["OPENAI_API_BASE"] = args.api_base
                if args.api_version:
                    os.environ["OPENAI_API_VERSION"] = args.api_version
                if args.deployment_name:
                    os.environ["OPENAI_DEPLOYMENT_NAME"] = args.deployment_name

                add_to_faiss_index(
                    chunks=chunks,
                    source_path=source_path,
                    chunking_strategy=chunking_strategy,
                    index_path=args.add_to_index,
                    model_name=args.model,
                    create_new=args.create_new_index,
                )

                print("\nYou can now search the index with:")
                if args.source_tag:
                    print(
                        f"  python dev_tools/query_faiss.py 'your search query' --source '{args.source_tag}'"
                    )
                else:
                    print(
                        f"  python dev_tools/query_faiss.py 'your search query' --source '{args.pdf.name}'"
                    )

            except Exception as e:
                error_msg = f"Error adding to FAISS index: {e}"
                print(error_msg)
                stats["error_message"] = error_msg
                stats["success"] = False

    except Exception as e:
        error_msg = f"Error processing document: {e}"
        print(error_msg)
        stats["error_message"] = error_msg
        stats["success"] = False
        sys.exit(1)

    finally:
        # Complete the summary report
        stats["end_time"] = time.time()
        duration = stats["end_time"] - stats["start_time"]

        # Print summary report
        print("\n" + "=" * 60)
        print("DOCUMENT PROCESSING SUMMARY")
        print("=" * 60)
        print(f"Document: {args.pdf}")
        print(f"Chunking method: {chunking_method}")
        print(f"Chunks generated: {stats['chunks_generated']}")
        print(f"Processing time: {duration:.2f} seconds")

        if args.dry_run:
            print("Mode: DRY RUN (no files modified)")

        if stats["success"]:
            print("Status: SUCCESS")
            if output_path and not args.dry_run:
                print(f"Output chunks: {output_path}")
            if args.add_to_index and not args.dry_run:
                print(f"Added to index: {args.add_to_index}")
        else:
            print("Status: FAILED")
            print(f"Error: {stats['error_message']}")
        print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)
