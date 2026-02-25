"""
Two-Phase Extraction Pipeline.

This module orchestrates the complete extraction process:

Phase 1 - DETECTION:
    - Scan pages incrementally
    - Detect table boundaries (start/end pages)
    - Handle multi-page tables
    - Output: detection_metadata.json

Phase 2 - EXTRACTION:
    - For each detected table:
        - Load ALL pages of that table
        - Extract complete table in one API call
        - Save intermediate result
    - Output: intermediate/*.json

Phase 3 - ASSEMBLY:
    - Combine all extracted tables
    - Output: final_output.json

Example:
    from src.extractors.pipeline import TwoPhaseExtractionPipeline
    
    pipeline = TwoPhaseExtractionPipeline(
        api_key="...",
        endpoint="...",
        deployment="gpt-4o"
    )
    
    result = pipeline.extract(
        pdf_path="contract.pdf",
        page_range=(70, 100),
        output_dir="./output"
    )
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from openai import AzureOpenAI

from config.settings import get_settings
from src.processors.pdf_converter import PDFConverter
from src.utils.logger import get_logger
from src.utils.file_utils import ensure_directory
from .gpt4_extractor import GPT4VisionExtractor
from .table_detector import TableDetector, TableRange, DetectionMetadata
from .multipage_extractor import MultiPageExtractor, ExtractedTable, combine_extracted_tables

logger = get_logger(__name__)


class TwoPhaseExtractionPipeline:
    """
    Complete two-phase extraction pipeline for PDF tables.
    
    This pipeline properly handles tables that span multiple pages by:
    1. First detecting all tables and their page ranges
    2. Then extracting each table using ALL its pages together
    
    Output structure:
        output/
        ├── page_images/              # Converted PDF pages
        ├── intermediate/             # Individual table JSONs
        │   ├── rate_card_a_p70-73.json
        │   └── rate_card_b_p74-77.json
        ├── detection_metadata.json   # Table inventory
        └── contract_extracted.json   # Final combined output
    
    Example:
        pipeline = TwoPhaseExtractionPipeline(
            api_key="your-key",
            endpoint="https://your-resource.openai.azure.com",
            deployment="gpt-4o"
        )
        
        result = pipeline.extract(
            pdf_path="contract.pdf",
            page_range=(70, 100),
            output_dir="./output"
        )
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        deployment: Optional[str] = None,
        api_version: Optional[str] = None,
        dpi: int = 200,
        window_size: int = 6
    ):
        """
        Initialize the extraction pipeline.
        
        Args:
            api_key: Azure OpenAI API key
            endpoint: Azure OpenAI endpoint URL
            deployment: Model deployment name
            api_version: API version
            dpi: Image resolution for PDF conversion
            window_size: Number of pages to scan together in each chunk (default: 6)
        """
        settings = get_settings()
        
        # Get credentials
        self.api_key = api_key or settings.azure.api_key
        self.endpoint = endpoint or settings.azure.endpoint
        self.deployment = deployment or settings.azure.deployment or "gpt-4o"
        self.api_version = api_version or settings.azure.api_version or "2024-08-01-preview"
        self.dpi = dpi
        self.window_size = window_size
        
        # Validate
        if not self.api_key or not self.endpoint:
            raise ValueError(
                "Azure OpenAI credentials required.\n"
                "Set AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT environment variables\n"
                "or pass api_key and endpoint to the constructor."
            )
        
        # Initialize PDF converter
        self.pdf_converter = PDFConverter(dpi=dpi)
        
        # Initialize GPT extractor
        self.gpt_extractor = GPT4VisionExtractor(
            api_key=self.api_key,
            endpoint=self.endpoint,
            deployment=self.deployment,
            api_version=self.api_version
        )
        
        # Initialize phase-specific components
        self.table_detector = TableDetector(self.gpt_extractor, window_size=self.window_size)
        self.table_extractor = MultiPageExtractor(self.gpt_extractor)
        
        logger.info("TwoPhaseExtractionPipeline initialized")
        logger.info(f"  Endpoint: {self.endpoint}")
        logger.info(f"  Deployment: {self.deployment}")
        logger.info(f"  DPI: {self.dpi}")
        logger.info(f"  Window Size: {self.window_size} pages")
    
    def extract(
        self,
        pdf_path: Union[str, Path],
        page_range: Optional[tuple[int, int]] = None,
        output_dir: Union[str, Path] = "./output"
    ) -> dict:
        """
        Run the complete extraction pipeline.
        
        Args:
            pdf_path: Path to the PDF file
            page_range: Optional (start, end) page range (1-indexed, inclusive)
            output_dir: Directory for all output files
        
        Returns:
            Combined extraction result dictionary
        """
        pdf_path = Path(pdf_path)
        output_dir = Path(output_dir)
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        # Create output directories
        ensure_directory(output_dir)
        images_dir = output_dir / "page_images"
        intermediate_dir = output_dir / "intermediate"
        ensure_directory(images_dir)
        ensure_directory(intermediate_dir)
        
        # Get PDF info
        pdf_info = self.pdf_converter.get_pdf_info(pdf_path)
        total_pages = pdf_info["page_count"]
        
        if page_range is None:
            page_range = (1, total_pages)
        
        # Print header
        logger.info("\n" + "=" * 70)
        logger.info("TWO-PHASE TABLE EXTRACTION PIPELINE")
        logger.info("=" * 70)
        logger.info(f"PDF File: {pdf_path.name}")
        logger.info(f"Total Pages: {total_pages}")
        logger.info(f"Processing: Pages {page_range[0]} to {page_range[1]}")
        logger.info(f"Output Directory: {output_dir}")
        logger.info("=" * 70)
        
        # =====================================================================
        # STEP 1: Convert PDF to images
        # =====================================================================
        logger.info("\n[STEP 1] Converting PDF pages to images...")
        
        page_images = self.pdf_converter.convert(
            pdf_path,
            images_dir,
            page_range
        )
        
        image_paths = [img.image_path for img in page_images]
        logger.info(f"  Converted {len(image_paths)} pages to images")
        
        # =====================================================================
        # PHASE 1: Detection
        # =====================================================================
        logger.info("\n" + "-" * 70)
        
        table_ranges, detection_metadata = self.table_detector.detect_tables(
            image_paths=image_paths,
            start_page=page_range[0],
            source_file=pdf_path.name
        )
        
        # Save detection metadata
        metadata_path = output_dir / "detection_metadata.json"
        detection_metadata.save(metadata_path)
        
        if not table_ranges:
            logger.warning("\nNo tables detected! Exiting.")
            return {
                "extraction_info": {
                    "source_file": pdf_path.name,
                    "extraction_date": datetime.now().isoformat(),
                    "total_tables_detected": 0,
                    "tables_extracted_successfully": 0,
                    "tables_failed": 0,
                    "page_range": list(page_range)
                },
                "tables": [],
                "failed_tables": [],
                "detection_summary": detection_metadata.to_dict()
            }
        
        # =====================================================================
        # PHASE 2: Extraction
        # =====================================================================
        logger.info("\n" + "-" * 70)
        logger.info(f"PHASE 2: TABLE EXTRACTION")
        logger.info("-" * 70)
        logger.info(f"Extracting {len(table_ranges)} tables...")
        
        extracted_tables: list[ExtractedTable] = []
        
        for i, table_range in enumerate(table_ranges):
            logger.info(f"\n[{i + 1}/{len(table_ranges)}] {table_range}")
            
            result = self.table_extractor.extract_table(
                table_range=table_range,
                image_paths=image_paths,
                page_offset=page_range[0],
                intermediate_dir=intermediate_dir
            )
            
            extracted_tables.append(result)
        
        # =====================================================================
        # PHASE 3: Assembly
        # =====================================================================
        logger.info("\n" + "-" * 70)
        logger.info("PHASE 3: ASSEMBLY")
        logger.info("-" * 70)
        
        final_output = combine_extracted_tables(
            extracted_tables=extracted_tables,
            metadata=detection_metadata,
            source_file=pdf_path.name
        )
        
        # Save final output
        output_path = output_dir / f"{pdf_path.stem}_extracted.json"
        with open(output_path, "w") as f:
            json.dump(final_output, f, indent=2)
        
        logger.info(f"Final output saved: {output_path}")
        
        # =====================================================================
        # Summary
        # =====================================================================
        successful_count = final_output["extraction_info"]["tables_extracted_successfully"]
        failed_count = final_output["extraction_info"]["tables_failed"]
        
        logger.info("\n" + "=" * 70)
        logger.info("EXTRACTION COMPLETE")
        logger.info("=" * 70)
        logger.info(f"Tables detected: {len(table_ranges)}")
        logger.info(f"Tables extracted: {successful_count}")
        logger.info(f"Tables failed: {failed_count}")
        
        # Count total rows
        total_rows = sum(
            len(t.get("data", [])) 
            for t in final_output.get("tables", [])
        )
        logger.info(f"Total rows extracted: {total_rows}")
        
        logger.info(f"\nOutput files:")
        logger.info(f"  - {metadata_path.name}")
        logger.info(f"  - intermediate/ ({successful_count} files)")
        logger.info(f"  - {output_path.name}")
        logger.info("=" * 70)
        
        return final_output
    
    def test_connection(self) -> tuple[bool, str]:
        """Test the API connection."""
        return self.gpt_extractor.test_connection()
