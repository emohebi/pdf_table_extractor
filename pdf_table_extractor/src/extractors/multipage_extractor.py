"""
Multi-Page Table Extractor - Phase 2 of the extraction pipeline.

This module extracts complete tables by sending ALL pages of a table
together in a single API call. This ensures no data is lost at page
boundaries.

Example:
    from src.extractors.multipage_extractor import MultiPageExtractor
    
    extractor = MultiPageExtractor(gpt_extractor)
    
    # Extract a table spanning pages 70-73
    result = extractor.extract_table(
        table_range=table_range,
        image_paths=all_image_paths,
        page_offset=70
    )
"""

import json
import base64
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from src.utils.logger import get_logger
from src.utils.file_utils import ensure_directory
from .table_detector import TableRange

logger = get_logger(__name__)


# Extraction prompt for multi-page tables
MULTIPAGE_EXTRACTION_PROMPT = """You are extracting a complete table that spans {page_count} page(s).

## TABLE INFORMATION
- Table ID: {table_id}
- Table Type: {table_type}
- Title: {title}
- Pages: {start_page} to {end_page}
- Estimated Rows: {row_estimate}

## CRITICAL INSTRUCTIONS

1. I am showing you ALL {page_count} pages of this table together
2. Extract the COMPLETE table, combining data from ALL pages
3. The header row appears only ONCE (on the first page) - do NOT duplicate it
4. Preserve the EXACT order of rows from first page to last page
5. Extract ALL data values EXACTLY as shown - do not modify numbers
6. For rate cards: extract all staff levels, all countries, all rate values

## OUTPUT FORMAT

Return ONLY valid JSON:

```json
{{
  "table_id": "{table_id}",
  "table_type": "{table_type}",
  "title": "<full table title>",
  "extraction_info": {{
    "pages_extracted": {page_count},
    "start_page": {start_page},
    "end_page": {end_page},
    "extraction_date": "<timestamp>"
  }},
  "structure": {{
    "column_count": <number>,
    "row_count": <total data rows across all pages>,
    "header_rows": <number of header rows>
  }},
  "columns": [
    {{
      "name": "<column name>",
      "data_type": "<text|number|currency>",
      "parent_header": "<parent column if nested, null otherwise>",
      "currency_code": "<ISO currency code if applicable, null otherwise>"
    }}
  ],
  "data": [
    {{
      "row_number": <sequential row number starting from 1>,
      "row_group": "<category/section if applicable, null otherwise>",
      "row_label": "<primary row identifier>",
      "row_sublabel": "<secondary identifier if any, null otherwise>",
      "values": {{
        "<column_key>": <value as number or string>,
        ...
      }}
    }}
  ],
  "metadata": {{
    "rate_card_id": "<A, B, C, etc. if applicable>",
    "region": "<geographic region if applicable>",
    "currencies": ["<list of currency codes found>"],
    "footnotes": "<any footnotes or special notes>",
    "source_page_for_header": {start_page}
  }}
}}
```

IMPORTANT: This JSON must contain ALL rows from ALL {page_count} pages. Do not truncate."""


@dataclass
class ExtractedTable:
    """Result of extracting a single table."""
    
    table_id: str
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    pages_extracted: int = 0
    extraction_time: Optional[str] = None
    output_file: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)


class MultiPageExtractor:
    """
    Extracts complete tables by processing all pages together.
    
    This is Phase 2 of the extraction pipeline. For each table detected
    in Phase 1, this extractor:
    1. Loads all pages belonging to that table
    2. Sends all pages together in one API call
    3. Extracts the complete table without losing data at page boundaries
    4. Saves the result to an intermediate file
    
    Example:
        extractor = MultiPageExtractor(gpt_extractor)
        
        result = extractor.extract_table(
            table_range=table_range,
            image_paths=all_images,
            page_offset=70,
            intermediate_dir="./output/intermediate"
        )
        
        if result.success:
            print(f"Extracted {len(result.data['data'])} rows")
    """
    
    def __init__(
        self,
        extractor,
        max_tokens: int = 4096,
        max_pages_per_call: int = 8
    ):
        """
        Initialize the multi-page extractor.
        
        Args:
            extractor: GPT4VisionExtractor instance for API calls
            max_tokens: Maximum tokens for API response
            max_pages_per_call: Maximum pages to send in one API call
        """
        self.extractor = extractor
        self.max_tokens = max_tokens
        self.max_pages_per_call = max_pages_per_call
    
    def extract_table(
        self,
        table_range: TableRange,
        image_paths: list[Union[str, Path]],
        page_offset: int = 1,
        intermediate_dir: Optional[Union[str, Path]] = None
    ) -> ExtractedTable:
        """
        Extract a complete table using all its pages.
        
        Args:
            table_range: TableRange object with page boundaries
            image_paths: List of ALL page images
            page_offset: Page number of the first image in image_paths
            intermediate_dir: Directory to save intermediate JSON
        
        Returns:
            ExtractedTable with the extracted data
        """
        logger.info(f"\nExtracting: {table_range.table_id}")
        logger.info(f"  Type: {table_range.table_type}")
        logger.info(f"  Pages: {table_range.start_page} to {table_range.end_page} ({table_range.page_count} pages)")
        
        # Calculate which images we need
        start_idx = table_range.start_page - page_offset
        end_idx = table_range.end_page - page_offset + 1
        
        # Validate indices
        if start_idx < 0 or end_idx > len(image_paths):
            error = f"Page range out of bounds: need pages {table_range.start_page}-{table_range.end_page}, have {len(image_paths)} images starting at page {page_offset}"
            logger.error(f"  Error: {error}")
            return ExtractedTable(
                table_id=table_range.table_id,
                success=False,
                error=error
            )
        
        # Get the relevant images
        table_images = image_paths[start_idx:end_idx]
        
        try:
            # Check if we need to batch (very large tables)
            if len(table_images) > self.max_pages_per_call:
                logger.info(f"  Large table ({len(table_images)} pages) - extracting in batches")
                extracted_data = self._extract_large_table(table_range, table_images)
            else:
                # Extract in one call
                extracted_data = self._extract_single_call(table_range, table_images)
            
            # Validate we got data
            if not extracted_data or not extracted_data.get("data"):
                raise ValueError("Extraction returned empty data")
            
            row_count = len(extracted_data.get("data", []))
            logger.info(f"  Success: extracted {row_count} rows")
            
            # Save intermediate file
            output_file = None
            if intermediate_dir:
                output_file = self._save_intermediate(table_range, extracted_data, intermediate_dir)
            
            return ExtractedTable(
                table_id=table_range.table_id,
                success=True,
                data=extracted_data,
                pages_extracted=len(table_images),
                extraction_time=datetime.now().isoformat(),
                output_file=str(output_file) if output_file else None
            )
            
        except Exception as e:
            logger.error(f"  Failed: {e}")
            return ExtractedTable(
                table_id=table_range.table_id,
                success=False,
                error=str(e),
                pages_extracted=len(table_images)
            )
    
    def _extract_single_call(
        self,
        table_range: TableRange,
        image_paths: list[Union[str, Path]]
    ) -> dict:
        """Extract table in a single API call (for smaller tables)."""
        
        # Encode all images
        encoded_images = []
        for img_path in image_paths:
            with open(img_path, "rb") as f:
                encoded_images.append(base64.b64encode(f.read()).decode("utf-8"))
        
        # Build prompt
        prompt = MULTIPAGE_EXTRACTION_PROMPT.format(
            page_count=len(image_paths),
            table_id=table_range.table_id,
            table_type=table_range.table_type,
            title=table_range.title or "Unknown",
            start_page=table_range.start_page,
            end_page=table_range.end_page,
            row_estimate=table_range.total_rows_estimate or "Unknown"
        )
        
        # Build message content with all images
        content = [{"type": "text", "text": prompt}]
        
        for i, b64_image in enumerate(encoded_images):
            page_num = table_range.start_page + i
            content.append({
                "type": "text",
                "text": f"\n--- PAGE {page_num} ---"
            })
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{b64_image}",
                    "detail": "high"
                }
            })
        
        # Make API call
        response = self.extractor.client.chat.completions.create(
            model=self.extractor.deployment,
            messages=[{"role": "user", "content": content}],
            max_completion_tokens=self.max_tokens,
            temperature=0
        )
        
        result_text = response.choices[0].message.content
        return self._parse_response(result_text)
    
    def _extract_large_table(
        self,
        table_range: TableRange,
        image_paths: list[Union[str, Path]]
    ) -> dict:
        """Extract very large table in batches."""
        
        all_rows = []
        columns = None
        metadata = None
        structure = None
        
        # Process in overlapping batches
        batch_size = self.max_pages_per_call
        overlap = 1  # Overlap to catch boundary issues
        
        i = 0
        batch_num = 0
        
        while i < len(image_paths):
            batch_end = min(i + batch_size, len(image_paths))
            batch_images = image_paths[i:batch_end]
            
            batch_num += 1
            batch_start_page = table_range.start_page + i
            batch_end_page = table_range.start_page + batch_end - 1
            
            logger.info(f"    Batch {batch_num}: pages {batch_start_page}-{batch_end_page}")
            
            # Create batch table range
            batch_range = TableRange(
                table_id=f"{table_range.table_id}_batch{batch_num}",
                table_type=table_range.table_type,
                title=table_range.title,
                start_page=batch_start_page,
                end_page=batch_end_page,
                description=table_range.description
            )
            
            try:
                batch_data = self._extract_single_call(batch_range, batch_images)
                
                # Store structure from first batch
                if columns is None:
                    columns = batch_data.get("columns", [])
                    metadata = batch_data.get("metadata", {})
                    structure = batch_data.get("structure", {})
                
                # Add rows (avoid duplicates at overlap boundary)
                batch_rows = batch_data.get("data", [])
                if i > 0 and batch_rows and overlap > 0:
                    # Skip first row(s) if they might be duplicates
                    batch_rows = batch_rows[overlap:]
                
                all_rows.extend(batch_rows)
                
            except Exception as e:
                logger.error(f"    Batch {batch_num} failed: {e}")
            
            # Move to next batch
            if batch_end >= len(image_paths):
                break
            i = batch_end - overlap
        
        # Renumber rows
        for idx, row in enumerate(all_rows):
            row["row_number"] = idx + 1
        
        # Combine results
        return {
            "table_id": table_range.table_id,
            "table_type": table_range.table_type,
            "title": table_range.title,
            "extraction_info": {
                "pages_extracted": len(image_paths),
                "start_page": table_range.start_page,
                "end_page": table_range.end_page,
                "extraction_date": datetime.now().isoformat(),
                "extracted_in_batches": True,
                "batch_count": batch_num
            },
            "structure": {
                "column_count": len(columns) if columns else 0,
                "row_count": len(all_rows),
                **(structure or {})
            },
            "columns": columns or [],
            "data": all_rows,
            "metadata": metadata or {}
        }
    
    def _save_intermediate(
        self,
        table_range: TableRange,
        data: dict,
        output_dir: Union[str, Path]
    ) -> Path:
        """Save extracted table to intermediate directory."""
        output_dir = Path(output_dir)
        ensure_directory(output_dir)
        
        # Create safe filename
        safe_id = table_range.table_id.replace("/", "_").replace("\\", "_").replace(" ", "_")
        filename = f"{safe_id}_p{table_range.start_page}-{table_range.end_page}.json"
        output_path = output_dir / filename
        
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"  Saved: {filename}")
        return output_path
    
    def _parse_response(self, text: str) -> dict:
        """Parse JSON from model response."""
        text = text.strip()
        
        # Remove markdown code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            logger.debug(f"Response: {text[:500]}...")
            raise ValueError(f"Failed to parse extraction response: {e}")


def combine_extracted_tables(
    extracted_tables: list[ExtractedTable],
    metadata,
    source_file: str = ""
) -> dict:
    """
    Combine all extracted tables into final output.
    
    Args:
        extracted_tables: List of ExtractedTable results
        metadata: DetectionMetadata from Phase 1
        source_file: Source PDF filename
    
    Returns:
        Combined output dictionary
    """
    successful = [t for t in extracted_tables if t.success and t.data]
    failed = [t for t in extracted_tables if not t.success]
    
    return {
        "extraction_info": {
            "source_file": source_file,
            "extraction_date": datetime.now().isoformat(),
            "total_tables_detected": len(extracted_tables),
            "tables_extracted_successfully": len(successful),
            "tables_failed": len(failed),
            "page_range": list(metadata.page_range_scanned) if metadata else None
        },
        "tables": [t.data for t in successful],
        "failed_tables": [
            {"table_id": t.table_id, "error": t.error}
            for t in failed
        ],
        "detection_summary": metadata.to_dict() if metadata else None
    }
