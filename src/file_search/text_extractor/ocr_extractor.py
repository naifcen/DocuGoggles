# file_search/text_extractor/ocr_extractor.py

import pytesseract
from PIL import Image
from pathlib import Path
from typing import Dict, Optional

class OCRProcessor:
    """Basic OCR processor for image files."""
    
    SUPPORTED_FORMATS = {'.png', '.jpg', '.jpeg'}
    
    def __init__(self):
        self.initialized = False
        pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        
    def initialize(self) -> None:
        """
        Initialize OCR processor and verify Tesseract is available.
        """
        try:
            pytesseract.get_tesseract_version()
            self.initialized = True
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Tesseract OCR: {str(e)}")
    
    def is_supported_format(self, file_path: str) -> bool:
        """Check if file format is supported."""
        return Path(file_path).suffix.lower() in self.SUPPORTED_FORMATS
    
    def process_image(self, image_path: str) -> Dict[str, any]:
        """
        Process an image file and extract text using OCR.
        """
        if not self.initialized:
            self.initialize()
            
        if not self.is_supported_format(image_path):
            raise ValueError(f"Unsupported image format: {image_path}")
            
        try:
            image = Image.open(image_path)
            
            extracted_text = pytesseract.image_to_string(image)
            
            path = Path(image_path)
            return {
                'text': extracted_text.strip(),
                'metadata': {
                    'path': str(path),
                    'filename': path.name,
                    'format': path.suffix,
                    'size': image.size
                }
            }
        except Exception as e:
            raise RuntimeError(f"OCR processing failed for {image_path}: {str(e)}")