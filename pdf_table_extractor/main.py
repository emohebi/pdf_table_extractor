"""
PDF Pricing Table Extractor - Main Entry Point

This tool extracts pricing tables from PDF contracts using a two-phase approach:

Phase 1 - Detection:
    Scans pages incrementally to detect tables and their page ranges.
    Properly handles tables that span multiple pages.

Phase 2 - Extraction:
    Extracts each table by sending ALL its pages together,
    ensuring no data is lost at page boundaries.

Usage:
    # Command line
    python -m src.main contract.pdf --pages 70-100 --output ./results
    
    # Python API
    from src.main import PricingTableExtractor
    
    extractor = PricingTableExtractor(
        api_key="your-key",
        endpoint="https://your-resource.openai.azure.com"
    )
    result = extractor.extract("contract.pdf", page_range=(70, 100))

Output:
    output/
    ├── page_images/              # Converted PDF pages
    ├── intermediate/             # Individual table JSONs
    │   ├── rate_card_a_p70-73.json
    │   └── service_matrix_p74-75.json
    ├── detection_metadata.json   # Table inventory with page ranges
    └── contract_extracted.json   # Final combined output
"""

import argparse
import sys
from pathlib import Path
from typing import Optional, Union

from src.extractors.pipeline import TwoPhaseExtractionPipeline
from src.utils.logger import setup_logger, get_logger

logger = get_logger(__name__)


class PricingTableExtractor:
    """
    High-level interface for extracting pricing tables from PDF contracts.
    
    Uses a two-phase approach to properly handle multi-page tables:
    1. Detection: Find tables and determine their page ranges
    2. Extraction: Extract each table using all its pages together
    
    Example:
        # Initialize with credentials
        extractor = PricingTableExtractor(
            api_key="your-key",
            endpoint="https://your-resource.openai.azure.com",
            deployment="gpt-4o"
        )
        
        # Extract tables from pages 70-100
        result = extractor.extract(
            pdf_path="contract.pdf",
            page_range=(70, 100),
            output_dir="./output"
        )
        
        # Access extracted tables
        for table in result['tables']:
            print(f"Table: {table['title']}")
            print(f"Pages: {table['extraction_info']['start_page']}-{table['extraction_info']['end_page']}")
            print(f"Rows: {len(table['data'])}")
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
        Initialize the extractor.
        
        Args:
            api_key: Azure OpenAI API key (or set AZURE_OPENAI_API_KEY env var)
            endpoint: Azure OpenAI endpoint URL (or set AZURE_OPENAI_ENDPOINT env var)
            deployment: Model deployment name (default: gpt-4o)
            api_version: API version (default: 2024-08-01-preview)
            dpi: Image resolution for PDF conversion (default: 200)
            window_size: Number of pages to scan together in each chunk (default: 6)
        """
        self.pipeline = TwoPhaseExtractionPipeline(
            api_key=api_key,
            endpoint=endpoint,
            deployment=deployment,
            api_version=api_version,
            dpi=dpi,
            window_size=window_size
        )
        
        logger.info("PricingTableExtractor initialized (two-phase mode)")
    
    def extract(
        self,
        pdf_path: Union[str, Path],
        page_range: Optional[tuple[int, int]] = None,
        output_dir: Union[str, Path] = "./output"
    ) -> dict:
        """
        Extract pricing tables from a PDF file.
        
        Args:
            pdf_path: Path to the PDF file
            page_range: Optional (start, end) page range (1-indexed, inclusive)
            output_dir: Directory for output files
        
        Returns:
            Dictionary containing:
            - extraction_info: Metadata about the extraction
            - tables: List of extracted table data
            - failed_tables: Any tables that failed to extract
            - detection_summary: Table inventory from Phase 1
        """
        return self.pipeline.extract(
            pdf_path=pdf_path,
            page_range=page_range,
            output_dir=output_dir
        )
    
    def test_connection(self) -> tuple[bool, str]:
        """
        Test the Azure OpenAI API connection.
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        return self.pipeline.test_connection()


def cli_main():
    """Command-line interface entry point."""
    parser = argparse.ArgumentParser(
        description="Extract pricing tables from PDF contracts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Two-Phase Extraction Process:
  Phase 1: Scan pages in chunks to detect tables and their page ranges
  Phase 2: Extract each table using ALL its pages together

This ensures tables spanning multiple pages are extracted completely.

Examples:
  # Basic extraction
  python -m src.main contract.pdf --pages 70-100
  
  # With larger window size for better context
  python -m src.main contract.pdf --pages 70-100 --window-size 8
  
  # With explicit credentials
  python -m src.main contract.pdf --pages 70-100 \\
      --api-key YOUR_KEY \\
      --endpoint https://YOUR_RESOURCE.openai.azure.com
  
  # Test connection first
  python -m src.main --test-connection \\
      --api-key YOUR_KEY \\
      --endpoint https://YOUR_RESOURCE.openai.azure.com

Output files:
  detection_metadata.json    - Table inventory with page ranges
  intermediate/              - Individual table JSON files
  <filename>_extracted.json  - Final combined output
        """
    )
    
    parser.add_argument(
        "pdf_path",
        nargs="?",
        help="Path to the PDF contract file"
    )
    
    parser.add_argument(
        "--pages", "-p",
        help="Page range to process (e.g., '70-100')"
    )
    
    parser.add_argument(
        "--output", "-o",
        default="./output",
        help="Output directory (default: ./output)"
    )
    
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="Image resolution for PDF conversion (default: 200)"
    )
    
    parser.add_argument(
        "--window-size", "-w",
        type=int,
        default=6,
        help="Number of pages to scan together in each chunk (default: 6)"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    # Azure OpenAI credentials
    parser.add_argument(
        "--api-key",
        help="Azure OpenAI API key"
    )
    
    parser.add_argument(
        "--endpoint",
        help="Azure OpenAI endpoint URL"
    )
    
    parser.add_argument(
        "--deployment",
        help="Azure OpenAI deployment name (default: gpt-4o)"
    )
    
    parser.add_argument(
        "--test-connection",
        action="store_true",
        help="Test the Azure OpenAI connection and exit"
    )
    
    args = parser.parse_args()
    args.pdf_path = "pdf_table_extractor/input/Amended and Restated GPSFA – KPMG – Fully Executed 151221 (2).pdf"
    args.test_connection = False
    args.pages = None
    args.dpi = 200
    # Configure logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logger("pdf_extractor", level=log_level)
    
    # Handle --test-connection
    if args.test_connection:
        print("\nTesting Azure OpenAI connection...")
        try:
            extractor = PricingTableExtractor(
                api_key=args.api_key,
                endpoint=args.endpoint,
                deployment=args.deployment,
                window_size=args.window_size
            )
            success, message = extractor.test_connection()
            print(f"\n{message}")
            sys.exit(0 if success else 1)
        except Exception as e:
            print(f"\nError: {e}")
            sys.exit(1)
    
    # Require pdf_path for normal operation
    if not args.pdf_path:
        parser.print_help()
        print("\nError: pdf_path is required")
        sys.exit(1)
    
    # Validate PDF exists
    if not Path(args.pdf_path).exists():
        print(f"Error: PDF file not found: {args.pdf_path}")
        sys.exit(1)
    
    # Parse page range
    page_range = None
    if args.pages:
        try:
            start, end = map(int, args.pages.split("-"))
            page_range = (start, end)
        except ValueError:
            print(f"Error: Invalid page range '{args.pages}'. Use format: start-end (e.g., 70-100)")
            sys.exit(1)
    
    # Run extraction
    try:
        extractor = PricingTableExtractor(
            api_key=args.api_key,
            endpoint=args.endpoint,
            deployment=args.deployment,
            dpi=args.dpi,
            window_size=args.window_size
        )
        
        result = extractor.extract(
            pdf_path=args.pdf_path,
            page_range=page_range,
            output_dir=args.output
        )
        
        # Print final summary
        info = result.get("extraction_info", {})
        print("\n" + "=" * 60)
        print("EXTRACTION SUMMARY")
        print("=" * 60)
        print(f"Tables detected: {info.get('total_tables_detected', 0)}")
        print(f"Tables extracted: {info.get('tables_extracted_successfully', 0)}")
        print(f"Tables failed: {info.get('tables_failed', 0)}")
        
        total_rows = sum(len(t.get("data", [])) for t in result.get("tables", []))
        print(f"Total rows: {total_rows}")
        
        print(f"\nOutput saved to: {args.output}/")
        
    except FileNotFoundError as e:
        print(f"\nError: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"\nConfiguration error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    cli_main()
