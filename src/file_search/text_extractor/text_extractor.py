import re
from typing import List, Dict
from pathlib import Path
from datetime import datetime
import chardet
import PyPDF2
from docx import Document as DocxDocument




class TextExtractor: 
    """
    A class for extracting and processing text from text files.
    """

    def __init__(self):
        self.supported_extensions = {
            '.txt': self._extract_from_txt,
            '.pdf': self._extract_from_pdf,
            '.docx': self._extract_from_docx,
            '.png': self._extract_text_from_image,
            '.jpg': self._extract_text_from_image,
            '.jpeg': self._extract_text_from_image
        }
        self.ocr_processor = None
        
    def _get_ocr_processor(self):
        """Lazy initialization of OCR processor"""
        if self.ocr_processor is None:
            from file_search.text_extractor.ocr_extractor import OCRProcessor
            self.ocr_processor = OCRProcessor()
            self.ocr_processor.initialize()
        return self.ocr_processor
    
    def is_supported_extension(self, extension: str) -> bool:
        """Check if the file extension is supported."""
        return extension.lower() in self.supported_extensions
        
    def read_file(self, file_path: str) -> Dict[str, any]:
        """
        Extract content and metadata from a file.
        
        Args:
            file_path: Path to the file to process
            
        Returns:
            Dictionary containing:
                - metadata: File information
                - content: Raw text content for vector database
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if not path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        extension = path.suffix.lower()
        extract_func = self.supported_extensions.get(extension)

        if not extract_func:
            raise ValueError(f"Unsupported file type: {extension}")

        try:
            content = extract_func(path)
        except Exception as e:
            raise IOError(f"Error reading file {file_path}: {str(e)}")

        metadata = {
            'name': path.name,
            'path': str(path.resolve()),
            'size': path.stat().st_size,
            'created': datetime.fromtimestamp(path.stat().st_ctime),
            'modified': datetime.fromtimestamp(path.stat().st_mtime),
            'extension': extension,
            'parent_dir': str(path.parent.resolve())
        }

        return {
            'metadata': metadata,
            'content': content
        }
        
    def _extract_from_txt(self, path: Path) -> str:
        raw_bytes = path.read_bytes()
        result = chardet.detect(raw_bytes)
        encoding = result['encoding'] if result['encoding'] else 'utf-8'
        
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            return path.read_text(encoding='utf-8')

    def _extract_from_pdf(self, path: Path) -> str:
        content = []
        with open(path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                content.append(page.extract_text())
        return '\n'.join(content)

    def _extract_from_docx(self, path: Path) -> str:
        doc = DocxDocument(path)
        return '\n'.join(paragraph.text for paragraph in doc.paragraphs)
        
    def _extract_text_from_image(self, path: Path) -> str:
        """Extract text from an image using OCR."""
        ocr_processor = self._get_ocr_processor()
        try:
            result = ocr_processor.process_image(str(path))
            return result.get('text', '')
        except Exception as e:
            print(f"OCR processing failed for {path}: {e}")
            return f"[OCR FAILED: {str(e)}]"