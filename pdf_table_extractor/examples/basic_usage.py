"""
Example: Two-Phase Table Extraction from PDF Contracts

This demonstrates the two-phase extraction approach:
1. Detection: Scan pages to find tables and their page ranges
2. Extraction: Extract each complete table using all its pages

This ensures tables spanning multiple pages are extracted completely.

Usage:
    python examples/basic_usage.py contract.pdf 70 100
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.main import PricingTableExtractor


def main():
    """Run two-phase table extraction."""
    
    if len(sys.argv) < 2:
        print("Usage: python basic_usage.py <pdf_path> [start_page] [end_page]")
        print("\nExample: python basic_usage.py contract.pdf 70 100")
        print("\nEnvironment variables required:")
        print("  AZURE_OPENAI_API_KEY")
        print("  AZURE_OPENAI_ENDPOINT")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    
    # Parse optional page range
    page_range = None
    if len(sys.argv) >= 4:
        page_range = (int(sys.argv[2]), int(sys.argv[3]))
    
    print("=" * 60)
    print("PDF Table Extractor - Two-Phase Extraction")
    print("=" * 60)
    print(f"\nPDF: {pdf_path}")
    if page_range:
        print(f"Pages: {page_range[0]} to {page_range[1]}")
    
    # Initialize extractor
    # Option 1: Use environment variables
    extractor = PricingTableExtractor(dpi=200)
    
    # Option 2: Pass credentials directly
    # extractor = PricingTableExtractor(
    #     api_key="your-api-key",
    #     endpoint="https://your-resource.openai.azure.com",
    #     deployment="gpt-4o",
    #     dpi=200
    # )
    
    # Run extraction
    result = extractor.extract(
        pdf_path=pdf_path,
        page_range=page_range,
        output_dir="./output"
    )
    
    # Display results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    
    info = result.get("extraction_info", {})
    print(f"\nTables detected: {info.get('total_tables_detected', 0)}")
    print(f"Tables extracted: {info.get('tables_extracted_successfully', 0)}")
    print(f"Tables failed: {info.get('tables_failed', 0)}")
    
    # List extracted tables
    tables = result.get("tables", [])
    if tables:
        print("\nExtracted tables:")
        for table in tables:
            title = table.get("title", "Untitled")
            table_type = table.get("table_type", "unknown")
            ext_info = table.get("extraction_info", {})
            start_page = ext_info.get("start_page", "?")
            end_page = ext_info.get("end_page", "?")
            row_count = len(table.get("data", []))
            
            print(f"\n  [{table_type}] {title}")
            print(f"    Pages: {start_page}-{end_page}")
            print(f"    Rows: {row_count}")
    
    # Show failed tables
    failed = result.get("failed_tables", [])
    if failed:
        print("\nFailed tables:")
        for f in failed:
            print(f"  - {f['table_id']}: {f['error']}")
    
    print(f"\nOutput saved to: ./output/")
    print("  - detection_metadata.json (table inventory)")
    print("  - intermediate/ (individual tables)")
    print(f"  - {Path(pdf_path).stem}_extracted.json (final output)")
    
    return result


if __name__ == "__main__":
    main()
