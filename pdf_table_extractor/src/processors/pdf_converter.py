"""
PDF to Image Converter using PyMuPDF.

This module handles the conversion of PDF pages to images for processing
by the GPT-4o vision model. It uses PyMuPDF (fitz) which is:
- Faster than pdf2image
- No external dependencies (no poppler required)
- More features for PDF manipulation

Example:
    from src.processors.pdf_converter import PDFConverter
    
    converter = PDFConverter(dpi=200)
    images = converter.convert(
        pdf_path="contract.pdf",
        output_dir="./images",
        page_range=(70, 100)
    )
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

import fitz  # PyMuPDF

from src.utils.logger import get_logger
from src.utils.file_utils import ensure_directory

logger = get_logger(__name__)


@dataclass
class PageImage:
    """Represents a converted PDF page image."""
    
    page_number: int
    image_path: Path
    width: int
    height: int
    
    def __str__(self) -> str:
        return f"Page {self.page_number}: {self.image_path.name} ({self.width}x{self.height})"


class PDFConverter:
    """
    Converts PDF pages to images for vision model processing.
    
    This class uses PyMuPDF (fitz) to extract individual pages from PDF 
    files and converts them to image format (PNG by default) suitable for
    processing by GPT-4o's vision capabilities.
    
    Advantages of PyMuPDF over pdf2image:
    - No external dependencies (poppler not required)
    - Generally faster performance
    - Better memory handling for large PDFs
    - More control over rendering options
    
    Attributes:
        dpi: Resolution for the converted images
        image_format: Output image format (png, jpeg, etc.)
    
    Example:
        converter = PDFConverter(dpi=200)
        
        # Convert specific page range
        images = converter.convert(
            pdf_path="contract.pdf",
            output_dir="./temp_images",
            page_range=(70, 100)
        )
        
        for img in images:
            print(f"Converted {img}")
    """
    
    def __init__(
        self,
        dpi: int = 200,
        image_format: str = "png"
    ):
        """
        Initialize the PDF converter.
        
        Args:
            dpi: Resolution for converted images (recommended: 150-250)
            image_format: Output format ('png' recommended for quality, 'jpeg' for smaller files)
        """
        self.dpi = dpi
        self.image_format = image_format.lower()
        
        # Calculate zoom factor from DPI (72 is the base PDF resolution)
        self.zoom = dpi / 72.0
        
        # Validate settings
        if self.dpi < 72:
            logger.warning(f"DPI {dpi} is very low, quality may be poor")
        elif self.dpi > 400:
            logger.warning(f"DPI {dpi} is very high, processing may be slow")
        
        # Validate image format
        valid_formats = {'png', 'jpeg', 'jpg', 'ppm', 'pbm'}
        if self.image_format not in valid_formats:
            logger.warning(f"Unknown format '{image_format}', defaulting to PNG")
            self.image_format = 'png'
    
    def get_pdf_info(self, pdf_path: Union[str, Path]) -> dict:
        """
        Get information about a PDF file.
        
        Args:
            pdf_path: Path to the PDF file
        
        Returns:
            Dictionary with PDF information (page count, metadata, etc.)
        
        Raises:
            FileNotFoundError: If PDF file doesn't exist
            RuntimeError: If PDF cannot be opened
        """
        pdf_path = Path(pdf_path)
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        try:
            doc = fitz.open(str(pdf_path))
            
            # Get metadata
            metadata = doc.metadata
            
            # Get page size from first page
            page_size = ""
            if doc.page_count > 0:
                first_page = doc[0]
                rect = first_page.rect
                page_size = f"{rect.width:.1f} x {rect.height:.1f} pts"
            
            info = {
                "page_count": doc.page_count,
                "title": metadata.get("title", ""),
                "author": metadata.get("author", ""),
                "subject": metadata.get("subject", ""),
                "creator": metadata.get("creator", ""),
                "producer": metadata.get("producer", ""),
                "page_size": page_size,
                "file_size": pdf_path.stat().st_size,
                "is_encrypted": doc.is_encrypted,
                "is_pdf": doc.is_pdf,
            }
            
            doc.close()
            return info
            
        except Exception as e:
            raise RuntimeError(f"Failed to open PDF: {e}")
    
    def convert(
        self,
        pdf_path: Union[str, Path],
        output_dir: Union[str, Path],
        page_range: Optional[tuple[int, int]] = None,
        filename_prefix: str = "page"
    ) -> list[PageImage]:
        """
        Convert PDF pages to images.
        
        Args:
            pdf_path: Path to the PDF file
            output_dir: Directory to save converted images
            page_range: Optional (start, end) page range (1-indexed, inclusive)
            filename_prefix: Prefix for output filenames
        
        Returns:
            List of PageImage objects representing converted pages
        
        Raises:
            FileNotFoundError: If PDF file doesn't exist
            ValueError: If page range is invalid
        
        Example:
            images = converter.convert(
                "contract.pdf",
                "./images",
                page_range=(70, 100)
            )
        """
        pdf_path = Path(pdf_path)
        output_dir = Path(output_dir)
        
        # Validate PDF exists
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        # Open PDF
        doc = fitz.open(str(pdf_path))
        total_pages = doc.page_count
        logger.info(f"PDF has {total_pages} pages")
        
        # Validate and set page range (convert to 0-indexed for PyMuPDF)
        first_page = 0  # 0-indexed
        last_page = total_pages - 1  # 0-indexed, inclusive
        
        if page_range:
            # Convert from 1-indexed (user input) to 0-indexed (PyMuPDF)
            first_page = page_range[0] - 1
            last_page = page_range[1] - 1
            
            # Validate range
            if first_page < 0:
                first_page = 0
                logger.warning("Start page adjusted to 1")
            
            if last_page >= total_pages:
                last_page = total_pages - 1
                logger.warning(f"End page adjusted to {total_pages}")
            
            if first_page > last_page:
                doc.close()
                raise ValueError(
                    f"Invalid page range: start ({page_range[0]}) > end ({page_range[1]})"
                )
        
        # Create output directory
        ensure_directory(output_dir)
        
        # Set up transformation matrix for desired DPI
        matrix = fitz.Matrix(self.zoom, self.zoom)
        
        # Convert pages
        pages_to_convert = last_page - first_page + 1
        logger.info(f"Converting {pages_to_convert} pages at {self.dpi} DPI...")
        
        result = []
        
        for page_idx in range(first_page, last_page + 1):
            # Get page (0-indexed)
            page = doc[page_idx]
            
            # Render page to pixmap (image)
            pixmap = page.get_pixmap(matrix=matrix)
            
            # Generate filename (1-indexed for user-friendliness)
            page_num = page_idx + 1
            filename = f"{filename_prefix}_{page_num:03d}.{self.image_format}"
            image_path = output_dir / filename
            
            # Save image
            pixmap.save(str(image_path))
            
            # Create PageImage record
            page_image = PageImage(
                page_number=page_num,
                image_path=image_path,
                width=pixmap.width,
                height=pixmap.height
            )
            result.append(page_image)
            
            logger.debug(f"Saved {page_image}")
        
        doc.close()
        logger.info(f"Converted {len(result)} pages")
        
        return result
    
    def convert_single_page(
        self,
        pdf_path: Union[str, Path],
        page_number: int,
        output_path: Optional[Union[str, Path]] = None
    ) -> PageImage:
        """
        Convert a single PDF page to an image.
        
        Args:
            pdf_path: Path to the PDF file
            page_number: Page number to convert (1-indexed)
            output_path: Optional specific output path for the image
        
        Returns:
            PageImage object for the converted page
        
        Example:
            page = converter.convert_single_page("contract.pdf", 75)
        """
        pdf_path = Path(pdf_path)
        
        # Validate PDF exists
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        # Determine output path
        if output_path:
            output_path = Path(output_path)
            output_dir = output_path.parent
            filename = output_path.name
        else:
            output_dir = pdf_path.parent / "temp_images"
            filename = f"page_{page_number:03d}.{self.image_format}"
        
        # Ensure output directory exists
        ensure_directory(output_dir)
        
        # Open PDF and get the page
        doc = fitz.open(str(pdf_path))
        
        # Validate page number
        if page_number < 1 or page_number > doc.page_count:
            doc.close()
            raise ValueError(
                f"Page {page_number} out of range (1-{doc.page_count})"
            )
        
        # Get page (convert to 0-indexed)
        page = doc[page_number - 1]
        
        # Render to pixmap
        matrix = fitz.Matrix(self.zoom, self.zoom)
        pixmap = page.get_pixmap(matrix=matrix)
        
        # Save image
        final_path = output_dir / filename
        pixmap.save(str(final_path))
        
        # Create result
        result = PageImage(
            page_number=page_number,
            image_path=final_path,
            width=pixmap.width,
            height=pixmap.height
        )
        
        doc.close()
        return result
    
    def convert_page_to_bytes(
        self,
        pdf_path: Union[str, Path],
        page_number: int,
        image_format: str = "png"
    ) -> bytes:
        """
        Convert a single PDF page directly to image bytes (no file saved).
        
        This is useful when you want to process the image in memory
        without saving to disk.
        
        Args:
            pdf_path: Path to the PDF file
            page_number: Page number to convert (1-indexed)
            image_format: Output format ('png', 'jpeg', etc.)
        
        Returns:
            Image data as bytes
        
        Example:
            image_bytes = converter.convert_page_to_bytes("contract.pdf", 75)
            base64_image = base64.b64encode(image_bytes).decode()
        """
        pdf_path = Path(pdf_path)
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        doc = fitz.open(str(pdf_path))
        
        if page_number < 1 or page_number > doc.page_count:
            doc.close()
            raise ValueError(
                f"Page {page_number} out of range (1-{doc.page_count})"
            )
        
        # Get page and render
        page = doc[page_number - 1]
        matrix = fitz.Matrix(self.zoom, self.zoom)
        pixmap = page.get_pixmap(matrix=matrix)
        
        # Get bytes in the specified format
        image_bytes = pixmap.tobytes(output=image_format)
        
        doc.close()
        return image_bytes
    
    def extract_text(
        self,
        pdf_path: Union[str, Path],
        page_number: Optional[int] = None
    ) -> str:
        """
        Extract text from PDF (useful for checking if PDF has embedded text).
        
        Note: For scanned PDFs, this will return empty or minimal text.
        
        Args:
            pdf_path: Path to the PDF file
            page_number: Specific page to extract (1-indexed), or None for all pages
        
        Returns:
            Extracted text
        """
        pdf_path = Path(pdf_path)
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        doc = fitz.open(str(pdf_path))
        text = ""
        
        if page_number:
            # Single page
            if 1 <= page_number <= doc.page_count:
                page = doc[page_number - 1]
                text = page.get_text()
        else:
            # All pages
            for page in doc:
                text += page.get_text()
                text += "\n\n"
        
        doc.close()
        return text.strip()
    
    def is_scanned_pdf(
        self,
        pdf_path: Union[str, Path],
        sample_pages: int = 5
    ) -> bool:
        """
        Check if a PDF appears to be scanned (image-based) rather than text-based.
        
        Args:
            pdf_path: Path to the PDF file
            sample_pages: Number of pages to sample for the check
        
        Returns:
            True if PDF appears to be scanned (minimal embedded text)
        """
        pdf_path = Path(pdf_path)
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        doc = fitz.open(str(pdf_path))
        
        # Sample some pages
        pages_to_check = min(sample_pages, doc.page_count)
        total_text_length = 0
        
        for i in range(pages_to_check):
            page = doc[i]
            text = page.get_text().strip()
            total_text_length += len(text)
        
        doc.close()
        
        # If average text per page is very low, it's likely scanned
        avg_text_per_page = total_text_length / pages_to_check if pages_to_check > 0 else 0
        
        # Threshold: less than 100 characters per page on average
        return avg_text_per_page < 100
