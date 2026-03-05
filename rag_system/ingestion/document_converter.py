from typing import List, Tuple, Dict, Any
from docling.document_converter import DocumentConverter as DoclingConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions, OcrMacOptions
from docling.datamodel.base_models import InputFormat
import fitz  # PyMuPDF for quick text inspection
import os
import tempfile

class DocumentConverter:
    """
    A class to convert various document formats to structured Markdown using the docling library.
    Supports PDF, DOCX, HTML, and other formats.
    """
    
    # Mapping of file extensions to InputFormat
    SUPPORTED_FORMATS = {
        '.pdf': InputFormat.PDF,
        '.docx': InputFormat.DOCX,
        '.html': InputFormat.HTML,
        '.htm': InputFormat.HTML,
        '.md': InputFormat.MD,
        '.txt': 'TXT',  # Special handling for plain text files
    }

    DEFAULT_LARGE_PDF_SIZE_MB = 40
    DEFAULT_LARGE_PDF_PAGE_COUNT = 150
    DEFAULT_SEGMENTED_PDF_PAGE_THRESHOLD = 8
    DEFAULT_SEGMENT_PAGE_WINDOW = 5
    
    def __init__(self):
        """Initializes the docling document converter with forced OCR enabled for macOS."""
        self.large_pdf_size_bytes = int(
            float(os.getenv("RAG_LARGE_PDF_SIZE_MB", str(self.DEFAULT_LARGE_PDF_SIZE_MB))) * 1024 * 1024
        )
        self.large_pdf_page_threshold = int(
            os.getenv("RAG_LARGE_PDF_PAGE_THRESHOLD", str(self.DEFAULT_LARGE_PDF_PAGE_COUNT))
        )
        self.segmented_pdf_threshold = int(
            os.getenv("RAG_SEGMENTED_PDF_PAGE_THRESHOLD", str(self.DEFAULT_SEGMENTED_PDF_PAGE_THRESHOLD))
        )
        self.segment_page_window = max(
            1,
            int(os.getenv("RAG_SEGMENT_PAGE_WINDOW", str(self.DEFAULT_SEGMENT_PAGE_WINDOW))),
        )

        try:
            # --- Converter WITHOUT OCR (fast path) ---
            pipeline_no_ocr = PdfPipelineOptions()
            pipeline_no_ocr.do_ocr = False
            format_no_ocr = {
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_no_ocr)
            }
            self.converter_no_ocr = DoclingConverter(format_options=format_no_ocr)

            # --- Converter WITH OCR (fallback) ---
            pipeline_ocr = PdfPipelineOptions()
            pipeline_ocr.do_ocr = True
            # Use non-full-page OCR to reduce peak memory usage on large/scanned pages.
            ocr_options = OcrMacOptions(force_full_page_ocr=False)
            pipeline_ocr.ocr_options = ocr_options
            format_ocr = {
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_ocr)
            }
            self.converter_ocr = DoclingConverter(format_options=format_ocr)
            
            self.converter_general = DoclingConverter()

            print("docling DocumentConverter(s) initialized (OCR + no-OCR + general).")
        except Exception as e:
            print(f"Error initializing docling DocumentConverter(s): {e}")
            self.converter_no_ocr = None
            self.converter_ocr = None
            self.converter_general = None

    def _should_bypass_docling_for_pdf(self, pdf_path: str) -> bool:
        """Decide whether to skip Docling pre-process for large PDFs to avoid OOM."""
        try:
            file_size = os.path.getsize(pdf_path)
            if file_size >= self.large_pdf_size_bytes:
                print(
                    f"Large PDF detected by size ({file_size / (1024 * 1024):.1f}MB >= "
                    f"{self.large_pdf_size_bytes / (1024 * 1024):.1f}MB). "
                    f"Bypassing docling for {pdf_path}."
                )
                return True

            with fitz.open(pdf_path) as doc:
                page_count = len(doc)
            if page_count >= self.large_pdf_page_threshold:
                print(
                    f"Large PDF detected by page count ({page_count} >= "
                    f"{self.large_pdf_page_threshold}). Bypassing docling for {pdf_path}."
                )
                return True
        except Exception as e:
            print(f"Could not evaluate large-PDF guard for {pdf_path}: {e}")
        return False

    def convert_to_markdown(self, file_path: str) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Converts a document to a single Markdown string, preserving layout and tables.
        Supports PDF, DOCX, HTML, and other formats.
        """
        file_ext = os.path.splitext(file_path)[1].lower()
        if file_ext not in self.SUPPORTED_FORMATS:
            print(f"Unsupported file format: {file_ext}")
            return []

        if not (self.converter_no_ocr and self.converter_ocr and self.converter_general):
            if file_ext == '.pdf':
                print("docling converters not available. Using PDF fallback conversion.")
                return self._fallback_pdf_to_markdown(file_path, RuntimeError("docling converters unavailable"))
            print("docling converters not available. Skipping conversion.")
            return []
        
        input_format = self.SUPPORTED_FORMATS[file_ext]
        
        if input_format == InputFormat.PDF:
            return self._convert_pdf_to_markdown(file_path)
        elif input_format == 'TXT':
            return self._convert_txt_to_markdown(file_path)
        else:
            return self._convert_general_to_markdown(file_path, input_format)
    
    def _convert_pdf_to_markdown(self, pdf_path: str) -> List[Tuple[str, Dict[str, Any]]]:
        """Convert PDF with OCR detection logic."""
        if self._should_bypass_docling_for_pdf(pdf_path):
            return self._fallback_pdf_to_markdown(pdf_path, RuntimeError("large-pdf guard triggered"))

        total_pages = 0
        try:
            with fitz.open(pdf_path) as doc:
                total_pages = len(doc)
        except Exception as e:
            print(f"Could not determine page count for {pdf_path}: {e}")

        if total_pages >= self.segmented_pdf_threshold:
            return self._convert_pdf_to_markdown_segmented(pdf_path, total_pages)

        # Quick heuristic: if the PDF already contains a text layer, skip OCR for speed
        def _pdf_has_text(path: str) -> bool:
            try:
                with fitz.open(path) as doc:
                    for page in doc:
                        if page.get_text("text").strip():
                            return True
            except Exception:
                pass
            return False

        use_ocr = not _pdf_has_text(pdf_path)
        converter = self.converter_ocr if use_ocr else self.converter_no_ocr
        ocr_msg = "(OCR enabled)" if use_ocr else "(no OCR)"

        print(f"Converting {pdf_path} to Markdown using docling {ocr_msg}...")
        return self._perform_conversion(pdf_path, converter, ocr_msg)

    def _convert_pdf_to_markdown_segmented(self, pdf_path: str, total_pages: int) -> List[Tuple[str, Dict[str, Any]]]:
        """Convert PDFs in small page windows to reduce peak memory and isolate bad pages."""
        print(
            f"Using segmented PDF conversion for {pdf_path}: "
            f"{total_pages} pages, window={self.segment_page_window}."
        )

        aggregated_pages_data: List[Tuple[str, Dict[str, Any]]] = []

        # Prefer no-OCR segmented conversion first for memory efficiency.
        converters = [
            (self.converter_no_ocr, "(segmented no OCR)"),
            (self.converter_ocr, "(segmented OCR)"),
        ]

        try:
            with fitz.open(pdf_path) as source_doc:
                for start_page in range(0, total_pages, self.segment_page_window):
                    end_page = min(total_pages, start_page + self.segment_page_window) - 1

                    segment_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                    segment_path = segment_file.name
                    segment_file.close()

                    try:
                        segment_doc = fitz.open()
                        try:
                            segment_doc.insert_pdf(source_doc, from_page=start_page, to_page=end_page)
                            segment_doc.save(segment_path)
                        finally:
                            segment_doc.close()

                        segment_converted = False
                        for converter, mode_label in converters:
                            if converter is None:
                                continue

                            pages_data = self._perform_conversion(segment_path, converter, mode_label)
                            if pages_data:
                                for tpl in pages_data:
                                    if len(tpl) == 3:
                                        markdown_content, metadata, _doc_obj = tpl
                                    else:
                                        markdown_content, metadata = tpl

                                    seg_meta = {
                                        **metadata,
                                        "source": pdf_path,
                                        "segment_start_page": start_page + 1,
                                        "segment_end_page": end_page + 1,
                                    }
                                    aggregated_pages_data.append((markdown_content, seg_meta))

                                segment_converted = True
                                break

                        if not segment_converted:
                            fallback_segment = self._fallback_pdf_to_markdown(
                                segment_path,
                                RuntimeError(
                                    f"Segment docling conversion failed for pages {start_page + 1}-{end_page + 1}"
                                ),
                            )
                            for markdown_content, metadata in fallback_segment:
                                seg_meta = {
                                    **metadata,
                                    "source": pdf_path,
                                    "segment_start_page": start_page + 1,
                                    "segment_end_page": end_page + 1,
                                }
                                aggregated_pages_data.append((markdown_content, seg_meta))
                    finally:
                        try:
                            if os.path.exists(segment_path):
                                os.remove(segment_path)
                        except Exception as e:
                            print(f"Could not remove temporary segment file {segment_path}: {e}")

        except Exception as e:
            print(f"Segmented conversion failed for {pdf_path}: {e}")
            return self._fallback_pdf_to_markdown(pdf_path, e)

        if aggregated_pages_data:
            print(f"Segmented conversion succeeded for {pdf_path} ({len(aggregated_pages_data)} segment outputs).")
            return aggregated_pages_data

        return self._fallback_pdf_to_markdown(
            pdf_path,
            RuntimeError("all segmented conversions failed"),
        )

    def _fallback_pdf_to_markdown(self, pdf_path: str, original_error: Exception) -> List[Tuple[str, Dict[str, Any]]]:
        """Memory-safe fallback: extract plain text page-by-page with PyMuPDF."""
        print(
            f"Falling back to lightweight PDF text extraction for {pdf_path} "
            f"after docling failure: {original_error}"
        )
        pages_data: List[Tuple[str, Dict[str, Any]]] = []
        try:
            page_markdown: List[str] = []
            non_empty_pages = 0

            with fitz.open(pdf_path) as doc:
                page_count = len(doc)
                for page_index, page in enumerate(doc):
                    text = page.get_text("text")
                    cleaned = text.strip()
                    if cleaned:
                        non_empty_pages += 1
                        page_markdown.append(f"## Page {page_index + 1}\n\n{cleaned}")

            if not page_markdown:
                print(f"No extractable text found in fallback for {pdf_path}.")
                return []

            markdown_content = "\n\n".join(page_markdown)
            metadata: Dict[str, Any] = {
                "source": pdf_path,
                "conversion_method": "pymupdf_fallback",
                "page_count": page_count,
                "text_pages": non_empty_pages,
            }
            pages_data.append((markdown_content, metadata))
            print(f"Fallback conversion succeeded for {pdf_path}: {non_empty_pages}/{page_count} pages with text.")
            return pages_data
        except Exception as fallback_error:
            print(f"Fallback PDF extraction failed for {pdf_path}: {fallback_error}")
            return []
    
    def _convert_txt_to_markdown(self, file_path: str) -> List[Tuple[str, Dict[str, Any]]]:
        """Convert plain text files to markdown by reading content directly."""
        print(f"Converting {file_path} (TXT) to Markdown...")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            markdown_content = f"```\n{content}\n```"
            metadata = {"source": file_path}
            
            print(f"Successfully converted {file_path} (TXT) to Markdown.")
            return [(markdown_content, metadata)]
        except Exception as e:
            print(f"Error processing TXT file {file_path}: {e}")
            return []
    
    def _convert_general_to_markdown(self, file_path: str, input_format: InputFormat) -> List[Tuple[str, Dict[str, Any]]]:
        """Convert non-PDF formats using general converter."""
        print(f"Converting {file_path} ({input_format.name}) to Markdown using docling...")
        return self._perform_conversion(file_path, self.converter_general, f"({input_format.name})")
    
    def _perform_conversion(self, file_path: str, converter, format_msg: str) -> List[Tuple[str, Dict[str, Any]]]:
        """Perform the actual conversion using the specified converter."""
        pages_data = []
        try:
            result = converter.convert(file_path)
            markdown_content = result.document.export_to_markdown()
            
            metadata = {"source": file_path}
            # Return the *DoclingDocument* object as third tuple element so downstream
            # chunkers that understand the element tree can use it.  Legacy callers that
            # expect only (markdown, metadata) can simply ignore the extra value.
            pages_data.append((markdown_content, metadata, result.document))
            print(f"Successfully converted {file_path} with docling {format_msg}.")
            return pages_data
        except Exception as e:
            print(f"Error processing {file_path} with docling: {e}")
            if os.path.splitext(file_path)[1].lower() == '.pdf':
                return self._fallback_pdf_to_markdown(file_path, e)
            return []
