"""
Page Analyzer for detecting table structures in PDF page images.

This module provides heuristic-based analysis to identify pages that
likely contain tables. This pre-filtering step helps reduce API costs
by skipping pages without tabular content.

Example:
    from src.processors.page_analyzer import PageAnalyzer
    
    analyzer = PageAnalyzer()
    
    if analyzer.has_table(image_path):
        # Process this page with GPT-4o
        pass
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from PIL import Image

from src.utils.logger import get_logger

logger = get_logger(__name__)


# Optional: Import OpenCV for advanced analysis
# If not available, fall back to basic PIL-based analysis
try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    logger.debug("OpenCV not available, using basic analysis")


@dataclass
class PageAnalysisResult:
    """Results from analyzing a page for table content."""
    
    page_number: int
    has_table: bool
    confidence: float  # 0.0 to 1.0
    horizontal_lines: int
    vertical_lines: int
    grid_score: float
    
    @property
    def summary(self) -> str:
        """Get a human-readable summary."""
        status = "TABLE DETECTED" if self.has_table else "No table"
        return f"Page {self.page_number}: {status} (confidence: {self.confidence:.1%})"


class PageAnalyzer:
    """
    Analyzes PDF page images to detect table structures.
    
    Uses line detection heuristics to identify pages that likely contain
    tables. This helps optimize processing by skipping text-only pages.
    
    The analyzer looks for:
    - Horizontal and vertical lines (table borders)
    - Grid-like patterns
    - Regular spacing indicative of table structure
    
    Attributes:
        min_lines: Minimum number of lines to consider a table present
        min_line_length: Minimum line length (pixels) to count
        confidence_threshold: Minimum confidence to report a table
    
    Example:
        analyzer = PageAnalyzer(min_lines=5)
        
        result = analyzer.analyze(image_path)
        if result.has_table:
            print(f"Found table with {result.confidence:.1%} confidence")
    """
    
    def __init__(
        self,
        min_lines: int = 5,
        min_line_length: int = 100,
        confidence_threshold: float = 0.5
    ):
        """
        Initialize the page analyzer.
        
        Args:
            min_lines: Minimum lines (horizontal + vertical) to detect a table
            min_line_length: Minimum length of lines to consider (pixels)
            confidence_threshold: Minimum confidence score to report table
        """
        self.min_lines = min_lines
        self.min_line_length = min_line_length
        self.confidence_threshold = confidence_threshold
    
    def analyze(
        self,
        image_path: Union[str, Path],
        page_number: int = 0
    ) -> PageAnalysisResult:
        """
        Analyze a page image for table structures.
        
        Args:
            image_path: Path to the page image
            page_number: Page number (for reference in results)
        
        Returns:
            PageAnalysisResult with detection details
        """
        image_path = Path(image_path)
        
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        
        # Use OpenCV if available, otherwise fall back to basic analysis
        if OPENCV_AVAILABLE:
            return self._analyze_with_opencv(image_path, page_number)
        else:
            return self._analyze_basic(image_path, page_number)
    
    def has_table(self, image_path: Union[str, Path]) -> bool:
        """
        Quick check if a page likely contains a table.
        
        Args:
            image_path: Path to the page image
        
        Returns:
            True if table is likely present
        """
        result = self.analyze(image_path)
        return result.has_table
    
    def _analyze_with_opencv(
        self,
        image_path: Path,
        page_number: int
    ) -> PageAnalysisResult:
        """
        Analyze using OpenCV line detection.
        
        This method uses Canny edge detection and Hough line transform
        to identify horizontal and vertical lines that form tables.
        """
        # Read image in grayscale
        img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        
        if img is None:
            logger.warning(f"Could not read image: {image_path}")
            return PageAnalysisResult(
                page_number=page_number,
                has_table=False,
                confidence=0.0,
                horizontal_lines=0,
                vertical_lines=0,
                grid_score=0.0
            )
        
        # Apply edge detection
        edges = cv2.Canny(img, 50, 150, apertureSize=3)
        
        # Detect horizontal lines
        horizontal_kernel = np.ones((1, self.min_line_length // 2), np.uint8)
        horizontal = cv2.morphologyEx(edges, cv2.MORPH_OPEN, horizontal_kernel)
        h_lines = cv2.HoughLinesP(
            horizontal, 1, np.pi / 180, 100,
            minLineLength=self.min_line_length,
            maxLineGap=10
        )
        h_count = len(h_lines) if h_lines is not None else 0
        
        # Detect vertical lines
        vertical_kernel = np.ones((self.min_line_length // 2, 1), np.uint8)
        vertical = cv2.morphologyEx(edges, cv2.MORPH_OPEN, vertical_kernel)
        v_lines = cv2.HoughLinesP(
            vertical, 1, np.pi / 180, 100,
            minLineLength=self.min_line_length,
            maxLineGap=10
        )
        v_count = len(v_lines) if v_lines is not None else 0
        
        # Calculate grid score (intersection potential)
        total_lines = h_count + v_count
        grid_score = min(h_count, v_count) / max(total_lines, 1)
        
        # Calculate confidence
        # Higher confidence when we have both horizontal and vertical lines
        if total_lines < self.min_lines:
            confidence = 0.0
        else:
            # Score based on line counts and balance
            line_score = min(total_lines / 20, 1.0)  # Cap at 20 lines
            balance_score = grid_score
            confidence = (line_score * 0.6 + balance_score * 0.4)
        
        has_table = (
            confidence >= self.confidence_threshold and
            h_count >= 2 and
            v_count >= 2
        )
        
        return PageAnalysisResult(
            page_number=page_number,
            has_table=has_table,
            confidence=confidence,
            horizontal_lines=h_count,
            vertical_lines=v_count,
            grid_score=grid_score
        )
    
    def _analyze_basic(
        self,
        image_path: Path,
        page_number: int
    ) -> PageAnalysisResult:
        """
        Basic analysis using PIL when OpenCV is not available.
        
        This is a simplified version that looks for contrast patterns
        that might indicate table structures.
        """
        try:
            img = Image.open(image_path).convert("L")  # Grayscale
        except Exception as e:
            logger.warning(f"Could not open image: {e}")
            return PageAnalysisResult(
                page_number=page_number,
                has_table=False,
                confidence=0.0,
                horizontal_lines=0,
                vertical_lines=0,
                grid_score=0.0
            )
        
        # Convert to numpy array for analysis
        try:
            import numpy as np
            pixels = np.array(img)
            
            # Look for horizontal patterns (rows of similar intensity)
            row_variance = np.var(pixels, axis=1)
            h_patterns = np.sum(row_variance < np.mean(row_variance) * 0.5)
            
            # Look for vertical patterns
            col_variance = np.var(pixels, axis=0)
            v_patterns = np.sum(col_variance < np.mean(col_variance) * 0.5)
            
            # Estimate line counts
            h_count = h_patterns // 20  # Rough estimate
            v_count = v_patterns // 20
            
        except ImportError:
            # Numpy not available, use very basic heuristics
            h_count = 5  # Assume some structure
            v_count = 5
        
        total_lines = h_count + v_count
        grid_score = min(h_count, v_count) / max(total_lines, 1)
        
        if total_lines < self.min_lines:
            confidence = 0.3  # Low confidence with basic analysis
        else:
            confidence = min(total_lines / 20, 0.7)  # Cap confidence
        
        has_table = confidence >= self.confidence_threshold
        
        return PageAnalysisResult(
            page_number=page_number,
            has_table=has_table,
            confidence=confidence,
            horizontal_lines=int(h_count),
            vertical_lines=int(v_count),
            grid_score=grid_score
        )
    
    def analyze_batch(
        self,
        image_paths: list[Union[str, Path]],
        start_page: int = 1
    ) -> list[PageAnalysisResult]:
        """
        Analyze multiple page images.
        
        Args:
            image_paths: List of image paths to analyze
            start_page: Starting page number for numbering
        
        Returns:
            List of PageAnalysisResult for each image
        """
        results = []
        
        for i, path in enumerate(image_paths):
            page_num = start_page + i
            result = self.analyze(path, page_num)
            results.append(result)
            logger.debug(result.summary)
        
        # Log summary
        tables_found = sum(1 for r in results if r.has_table)
        logger.info(f"Analyzed {len(results)} pages, {tables_found} with tables")
        
        return results
    
    def filter_table_pages(
        self,
        image_paths: list[Union[str, Path]],
        start_page: int = 1
    ) -> list[tuple[int, Path]]:
        """
        Filter to return only pages that likely contain tables.
        
        Args:
            image_paths: List of image paths to analyze
            start_page: Starting page number
        
        Returns:
            List of (page_number, image_path) tuples for pages with tables
        """
        results = self.analyze_batch(image_paths, start_page)
        
        return [
            (r.page_number, image_paths[i])
            for i, r in enumerate(results)
            if r.has_table
        ]
