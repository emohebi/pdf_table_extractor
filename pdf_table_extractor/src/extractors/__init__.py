"""
Table extraction modules for the PDF Table Extractor.

Two-Phase Extraction Pipeline:
    Phase 1 - Detection (table_detector.py):
        Scans pages to detect tables and their page boundaries
    
    Phase 2 - Extraction (multipage_extractor.py):
        Extracts complete tables using all their pages together
    
    Pipeline (pipeline.py):
        Orchestrates the complete two-phase process
"""

from .base import BaseExtractor
from .gpt4_extractor import GPT4VisionExtractor
from .prompts import SystemPrompts
from .table_detector import TableDetector, TableRange, DetectionMetadata
from .multipage_extractor import MultiPageExtractor, ExtractedTable, combine_extracted_tables
from .pipeline import TwoPhaseExtractionPipeline

__all__ = [
    # Base
    "BaseExtractor",
    "GPT4VisionExtractor",
    "SystemPrompts",
    # Phase 1 - Detection
    "TableDetector",
    "TableRange", 
    "DetectionMetadata",
    # Phase 2 - Extraction
    "MultiPageExtractor",
    "ExtractedTable",
    "combine_extracted_tables",
    # Pipeline
    "TwoPhaseExtractionPipeline",
]
