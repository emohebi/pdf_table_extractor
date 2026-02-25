"""
Base extractor class defining the interface for table extractors.

This module provides an abstract base class that all extractors must
implement. This allows for different extraction backends while maintaining
a consistent interface.

Example:
    class MyCustomExtractor(BaseExtractor):
        def extract_from_image(self, image_path, context=None):
            # Custom implementation
            pass
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional, Union


class BaseExtractor(ABC):
    """
    Abstract base class for table extractors.
    
    All extraction implementations (GPT-4o, local models, etc.) should
    inherit from this class and implement the required methods.
    
    This ensures a consistent interface across different extraction
    backends and makes it easy to swap implementations.
    """
    
    @abstractmethod
    def extract_from_image(
        self,
        image_path: Union[str, Path],
        context: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Extract tables from a single page image.
        
        Args:
            image_path: Path to the page image file
            context: Optional context from previous pages
        
        Returns:
            Dictionary containing extracted tables in standard format:
            {
                "page_info": {"has_tables": bool, "table_count": int},
                "tables": [...]
            }
        """
        pass
    
    @abstractmethod
    def extract_batch(
        self,
        image_paths: list[Union[str, Path]],
        start_page: int = 1
    ) -> list[dict[str, Any]]:
        """
        Extract tables from multiple page images.
        
        Args:
            image_paths: List of paths to page images
            start_page: Page number of the first image
        
        Returns:
            List of extraction results, one per page
        """
        pass
    
    def validate_image(self, image_path: Union[str, Path]) -> bool:
        """
        Check if an image file is valid for processing.
        
        Args:
            image_path: Path to the image file
        
        Returns:
            True if the image can be processed
        """
        path = Path(image_path)
        
        # Check file exists
        if not path.exists():
            return False
        
        # Check file extension
        valid_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
        if path.suffix.lower() not in valid_extensions:
            return False
        
        # Check file size (must be non-empty, less than 20MB)
        size = path.stat().st_size
        if size == 0 or size > 20 * 1024 * 1024:
            return False
        
        return True
