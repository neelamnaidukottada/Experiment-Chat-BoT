"""File processing service for extracting text from uploaded files."""

import logging
from io import BytesIO
from typing import Optional

logger = logging.getLogger(__name__)


class FileService:
    """Service for processing and extracting text from various file types."""
    
    @staticmethod
    def extract_text_from_file(file_content: bytes, filename: str, content_type: str) -> Optional[str]:
        """
        Extract text content from various file types.
        
        Supports: .txt, .pdf, .docx, .doc, .xlsx
        
        Args:
            file_content: Raw file bytes
            filename: Name of the file (used for extension detection)
            content_type: MIME type of the file
            
        Returns:
            Extracted text content, or None if extraction failed
        """
        try:
            if not file_content:
                logger.warning(f"[FileService] Empty file content for {filename}")
                return "[Empty file - no content to extract]"
            
            # Get file extension
            ext = filename.lower().split('.')[-1] if '.' in filename else ''
            logger.info(f"[FileService] Processing {filename}, extension: {ext}, size: {len(file_content)} bytes")
            
            # Handle text files
            if ext == 'txt' or 'text' in content_type.lower():
                logger.info(f"[FileService] Processing as TXT file")
                return FileService._extract_text_from_txt(file_content)
            
            # Handle PDF files
            elif ext == 'pdf' or 'pdf' in content_type.lower():
                logger.info(f"[FileService] Processing as PDF file")
                return FileService._extract_text_from_pdf(file_content)
            
            # Handle Word documents (.docx)
            elif ext == 'docx' or 'openxmlformats-officedocument.wordprocessingml' in content_type.lower():
                logger.info(f"[FileService] Processing as DOCX file")
                return FileService._extract_text_from_docx(file_content)
            
            # Handle older Word documents (.doc)
            elif ext == 'doc' or 'msword' in content_type.lower():
                logger.info(f"[FileService] Processing as DOC file")
                return FileService._extract_text_from_doc(file_content)
            
            # Handle Excel files
            elif ext in ['xlsx', 'xls'] or 'spreadsheet' in content_type.lower():
                logger.info(f"[FileService] Processing as Excel file")
                return FileService._extract_text_from_excel(file_content)
            
            else:
                logger.warning(f"[FileService] Unsupported file type: {ext} ({content_type})")
                return f"[Unsupported file type: {ext}. Supported types: txt, pdf, docx, doc, xlsx, xls]"
                
        except Exception as e:
            logger.error(f"[FileService] Error extracting text from {filename}: {str(e)}", exc_info=True)
            return f"[Error reading file {filename}: {str(e)}]"
    
    @staticmethod
    def _extract_text_from_txt(file_content: bytes) -> str:
        """Extract text from .txt files."""
        try:
            text = file_content.decode('utf-8', errors='ignore').strip()
            logger.info(f"[FileService] Extracted {len(text)} characters from TXT file")
            return text if text else "[Empty text file]"
        except Exception as e:
            logger.error(f"[FileService] Error extracting from txt: {str(e)}")
            return "[Error reading text file]"
    
    @staticmethod
    def _extract_text_from_pdf(file_content: bytes) -> Optional[str]:
        """Extract text from PDF files."""
        try:
            import PyPDF2
            logger.info(f"[FileService] PyPDF2 imported successfully")
            
            pdf_reader = PyPDF2.PdfReader(BytesIO(file_content))
            num_pages = len(pdf_reader.pages)
            logger.info(f"[FileService] PDF has {num_pages} pages")
            
            text_content = []
            
            for page_num, page in enumerate(pdf_reader.pages):
                try:
                    text = page.extract_text()
                    if text and text.strip():
                        text_content.append(f"[Page {page_num + 1}]\n{text}")
                        logger.debug(f"[FileService] Extracted {len(text)} chars from page {page_num + 1}")
                except Exception as e:
                    logger.warning(f"[FileService] Error extracting page {page_num}: {str(e)}")
            
            result = "\n\n".join(text_content) if text_content else "[No text found in PDF]"
            logger.info(f"[FileService] Extracted {len(result)} total characters from PDF")
            return result
            
        except ImportError:
            logger.error(f"[FileService] PyPDF2 not installed")
            return "[PDF support not available - PyPDF2 not installed. Please install: pip install PyPDF2]"
        except Exception as e:
            logger.error(f"[FileService] Error extracting from PDF: {str(e)}", exc_info=True)
            return f"[Error reading PDF file: {str(e)}]"
    
    @staticmethod
    def _extract_text_from_docx(file_content: bytes) -> Optional[str]:
        """Extract text from .docx files."""
        try:
            from docx import Document
            logger.info(f"[FileService] python-docx imported successfully")
            
            doc = Document(BytesIO(file_content))
            text_content = []
            
            for para in doc.paragraphs:
                if para.text.strip():
                    text_content.append(para.text)
            
            # Also extract from tables
            for table in doc.tables:
                for row in table.rows:
                    row_text = ' | '.join(
                        cell.text.strip() for cell in row.cells
                    )
                    if row_text.strip():
                        text_content.append(row_text)
            
            result = "\n".join(text_content) if text_content else "[Empty Word document]"
            logger.info(f"[FileService] Extracted {len(result)} characters from DOCX")
            return result
            
        except ImportError:
            logger.error(f"[FileService] python-docx not installed")
            return "[DOCX support not available - python-docx not installed. Please install: pip install python-docx]"
        except Exception as e:
            logger.error(f"[FileService] Error extracting from docx: {str(e)}", exc_info=True)
            return f"[Error reading DOCX file: {str(e)}]"
    
    @staticmethod
    def _extract_text_from_doc(file_content: bytes) -> Optional[str]:
        """Extract text from old .doc files (Word 97-2003)."""
        try:
            # Try python-docx first (works for some .doc files)
            try:
                from docx import Document
                doc = Document(BytesIO(file_content))
                text_content = []
                
                for para in doc.paragraphs:
                    if para.text.strip():
                        text_content.append(para.text)
                
                result = "\n".join(text_content) if text_content else "[Empty Word document]"
                logger.info(f"[FileService] Successfully extracted from DOC using python-docx")
                return result
            except:
                # Fall back to docx2txt
                logger.info(f"[FileService] python-docx failed, trying docx2txt")
                import docx2txt
                import tempfile
                import os
                
                # docx2txt needs a file path, so write to temp file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.doc') as tmp:
                    tmp.write(file_content)
                    tmp_path = tmp.name
                
                try:
                    text = docx2txt.process(tmp_path)
                    result = text.strip() if text else "[Empty Word document]"
                    logger.info(f"[FileService] Extracted from DOC using docx2txt")
                    return result
                finally:
                    os.unlink(tmp_path)
            
        except ImportError as e:
            logger.error(f"[FileService] Required library not installed: {str(e)}")
            return "[DOC support not available - please install: pip install python-docx docx2txt]"
        except Exception as e:
            logger.error(f"[FileService] Error extracting from doc: {str(e)}", exc_info=True)
            return f"[Error reading DOC file: {str(e)}]"
    
    @staticmethod
    def _extract_text_from_excel(file_content: bytes) -> Optional[str]:
        """Extract text from Excel files (.xlsx, .xls)."""
        try:
            import openpyxl
            logger.info(f"[FileService] openpyxl imported successfully")
            
            workbook = openpyxl.load_workbook(BytesIO(file_content))
            text_content = []
            
            for sheet_name in workbook.sheetnames:
                worksheet = workbook[sheet_name]
                text_content.append(f"[Sheet: {sheet_name}]")
                
                for row in worksheet.iter_rows(values_only=True):
                    row_text = ' | '.join(
                        str(cell) if cell is not None else '' 
                        for cell in row
                    ).strip()
                    if row_text:
                        text_content.append(row_text)
                
                text_content.append("")  # Separator between sheets
            
            result = "\n".join(text_content) if text_content else "[Empty Excel file]"
            logger.info(f"[FileService] Extracted {len(result)} characters from Excel")
            return result
            
        except ImportError:
            logger.error(f"[FileService] openpyxl not installed")
            return "[Excel support not available - openpyxl not installed. Please install: pip install openpyxl]"
        except Exception as e:
            logger.error(f"[FileService] Error extracting from Excel: {str(e)}", exc_info=True)
            return f"[Error reading Excel file: {str(e)}]"
