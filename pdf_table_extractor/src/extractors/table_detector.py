"""
Table Detector - Accumulative Window Approach

This detector uses an accumulative (growing) window strategy:

1. Scan page N to find tables that START there (have column headers)
2. If table found, grow the window: [N], [N, N+1], [N, N+1, N+2]...
3. At each step, send ALL pages in window and ask "does table continue on last page?"
4. Model always sees the origin (with headers) so it can compare
5. When table ends, record it and continue scanning for next table

Key advantage: Model always has full context from table origin.
"""

import json
import base64
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Union, List, Set

from src.utils.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# PROMPTS
# =============================================================================

INITIAL_SCAN_PROMPT = """Analyze this page for tables.

All the tables on page {page_num} have COLUMN HEADERS (the row with column names) or table titles.

## OUTPUT FORMAT
Return ONLY valid JSON:

```json
{{
  "page_number": {page_num},
  "tables_starting_here": [
    {{
      "table_id": "<descriptive_id>",
      "title": "<exact title from document or null>",
      "section_name": "<section/chapter name or null>",
      "column_headers": ["<column1>", "<column2>", "..."],
      "row_count_this_page": <number of data rows on this page>,
      "reaches_page_bottom": <true if table data reaches bottom of page>
    }}
  ]
}}
```

IMPORTANT:
- Only list tables whose COLUMN HEADERS are visible on this page
- Set title to null if no title is visible (don't make one up)
"""

CONTINUATION_CHECK_PROMPT = """I'm showing you {total_pages} pages of a table to check if it continues.

## TABLE INFORMATION
- Title: {title}
- Column Headers: {columns}
- Table STARTED on: Page {start_page}
- Currently checking: Page {check_page}

## PAGES SHOWN
Pages {start_page} to {check_page} are shown below.
- Page {start_page} is the ORIGIN (has the column headers)
- Page {check_page} is the page I'm asking about

# DEFINITIONS
The table CONTINUES:
    1- The END of the table {title} is not obvious on page {check_page} i.e. it has reached the bottom of the page.
    2- If page {check_page} has data rows matching the columns from page {start_page}. Check from the top of the page until you reach an END indications defined above.
    3- Note that if the table reached the bottom of page {check_page} then it CONTINUES.
    4- Even if you are sure the table {title} has ENDED at the bottom of the page but CONTINUE to the next page. 
    5- If {start_page} is not same as {check_page} AND If a new table (with COLUMN HEADERS) starts followed by one or many rows (without COLUMN HEADERS) table continuing from the page before {check_page} then the table CONTINUES and ENDS on page {check_page}.
    6- CONTINUE If The table's last row is visible on page {check_page} AND doesn't reach the bottom of the page
    
The table ENDS:
    1- If a new table (with COLUMN HEADERS) starts after rows of table {title} on page {check_page}.
    
## YOUR TASK
Look at PAGES from {start_page} to {check_page} (the last page shown). Answer:
1. Does the table from page {start_page} CONTINUE onto page {check_page}?
2. If yes, does the table END on page {check_page}, or continue further?
3. Are there any NEW tables starting on page {check_page}?

## OUTPUT FORMAT
Return ONLY valid JSON:

```json
{{
  "check_page": {check_page},
  "table_continues": <true if the table from {start_page} continues on {check_page}>,
  "rows_on_this_page": <number of rows from this table on page {check_page}>,
  "table_ends_here": <true if the table ends on page {check_page}>,
  "new_tables_start": [
    {{
      "title": "<title or null>",
      "section_name": "<section or null>",
      "column_headers": ["<columns>"],
      "starts_after_row": <approximate row number where old table ends and new begins>
    }}
  ],
  "reason": "<brief explanation>"
}}
```
"""


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class TableRange:
    """Detected table with page range."""
    table_id: str
    table_type: str
    title: Optional[str]
    start_page: int
    end_page: int
    total_rows_estimate: int = 0
    column_headers: list[str] = field(default_factory=list)
    section_name: Optional[str] = None
    
    @property
    def page_count(self) -> int:
        return self.end_page - self.start_page + 1
    
    @property
    def is_multipage(self) -> bool:
        return self.page_count > 1
    
    def to_dict(self) -> dict:
        d = asdict(self)
        d["page_count"] = self.page_count
        d["is_multipage"] = self.is_multipage
        return d
    
    def __str__(self) -> str:
        title = self.title or "(no title)"
        pages = f"page {self.start_page}" if self.page_count == 1 else f"pages {self.start_page}-{self.end_page}"
        return f"'{title}' [{self.table_type}]: {pages}"


@dataclass
class DetectionMetadata:
    """Detection process metadata."""
    source_file: str
    detection_date: str
    page_range_scanned: tuple[int, int]
    total_pages_scanned: int
    total_tables_found: int
    multipage_tables: int
    max_window_size: int
    tables: list[dict]
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    def save(self, path: Union[str, Path]) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)


# =============================================================================
# MAIN DETECTOR CLASS
# =============================================================================

class TableDetector:
    """
    Accumulative Window Table Detector.
    
    Uses a growing window approach for accurate multi-page table detection:
    1. Scan each page to find tables that START there
    2. For each table, grow window until table ends
    3. Model always sees origin + all intermediate pages
    
    Args:
        extractor: GPT4VisionExtractor instance
        window_size: Maximum pages in window before assuming continuation (default: 10)
    """
    
    def __init__(self, extractor, window_size: int = 10):
        self.extractor = extractor
        self.window_size = window_size
        self._image_cache = {}
    
    def detect_tables(
        self,
        image_paths: list[Union[str, Path]],
        start_page: int = 1,
        source_file: str = "",
        progress_callback: Optional[callable] = None
    ) -> tuple[list[TableRange], DetectionMetadata]:
        """
        Detect all tables using accumulative window approach.
        """
        if not image_paths:
            return [], self._create_empty_metadata(source_file, start_page)
        
        total_pages = len(image_paths)
        end_page_num = start_page + total_pages - 1
        
        logger.info("=" * 70)
        logger.info("TABLE DETECTION - Accumulative Window Approach")
        logger.info("=" * 70)
        logger.info(f"Source: {source_file or 'Unknown'}")
        logger.info(f"Pages: {start_page} to {end_page_num} ({total_pages} pages)")
        logger.info(f"Max window size: {self.window_size} pages")
        logger.info("=" * 70)
        
        completed_tables: List[TableRange] = []
        claimed_pages: Set[int] = set()  # Pages already assigned to tables
        pending_tables: List[tuple] = []  # (table_info, start_page) - tables discovered during tracing
        
        current_page = start_page
        
        while current_page <= end_page_num:
            # Skip if already claimed
            if current_page in claimed_pages:
                current_page += 1
                if current_page > end_page_num: break

            page_idx = current_page - start_page
            
            if progress_callback:
                progress_callback(page_idx + 1, total_pages, f"Processing page {current_page}")
            
            logger.info(f"\n{'='*50}")
            logger.info(f"Scanning page {current_page}...")
            claimed_pages.add(current_page)
            # Step 1: Scan this page for tables that START here
            scan_result = self._scan_single_page(image_paths[page_idx], current_page)
            tables_starting = scan_result.get("tables_starting_here", [])
            
            if not tables_starting:
                logger.info(f"  No tables start on page {current_page}")
                current_page += 1
                continue
            
            # Step 2: For each table found, trace its extent
            for table_info in tables_starting:
                title = table_info.get("title") or "(no title)"
                section = table_info.get("section_name")
                full_title = f"{section} - {title}" if section and title else (section or title)
                
                logger.info(f"\n  Found: '{full_title}'")
                logger.info(f"    Columns: {table_info.get('column_headers', [])}")
                
                # Trace using accumulative window
                end_page, total_rows, new_tables = self._trace_table_accumulative(
                    table_info=table_info,
                    table_start_page=current_page,
                    image_paths=image_paths,
                    page_offset=start_page,
                    max_page=end_page_num
                )
                
                # Create TableRange
                table_range = TableRange(
                    table_id=table_info.get("table_id", f"table_p{current_page}"),
                    table_type=self._infer_table_type(table_info),
                    title=full_title,
                    start_page=current_page,
                    end_page=end_page,
                    total_rows_estimate=total_rows,
                    column_headers=table_info.get("column_headers", []),
                    section_name=section
                )
                completed_tables.append(table_range)
                
                logger.info(f"    → {table_range}")
                current_page = end_page
                
        # Sort by start page
        completed_tables.sort(key=lambda t: t.start_page)
        
        # Create metadata
        multipage_count = sum(1 for t in completed_tables if t.is_multipage)
        metadata = DetectionMetadata(
            source_file=source_file,
            detection_date=datetime.now().isoformat(),
            page_range_scanned=(start_page, end_page_num),
            total_pages_scanned=total_pages,
            total_tables_found=len(completed_tables),
            multipage_tables=multipage_count,
            max_window_size=self.window_size,
            tables=[t.to_dict() for t in completed_tables]
        )
        
        # Final summary
        logger.info("\n" + "=" * 70)
        logger.info("DETECTION COMPLETE")
        logger.info("=" * 70)
        logger.info(f"Total tables: {len(completed_tables)} ({multipage_count} multi-page)")
        for t in completed_tables:
            logger.info(f"  • {t}")
        logger.info("=" * 70)
        
        self._image_cache.clear()
        return completed_tables, metadata
    
    def _scan_single_page(self, image_path: Union[str, Path], page_num: int) -> dict:
        """Scan a single page to find tables that START here."""
        
        b64 = self._get_b64(image_path)
        prompt = INITIAL_SCAN_PROMPT.format(page_num=page_num)
        
        try:
            response = self.extractor.client.chat.completions.create(
                model=self.extractor.deployment,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"}}
                    ]
                }],
                max_completion_tokens=1024,
                temperature=0
            )
            
            return self._parse_json(response.choices[0].message.content)
            
        except Exception as e:
            logger.error(f"Error scanning page {page_num}: {e}")
            return {"tables_starting_here": []}
    
    def _trace_table_accumulative(
        self,
        table_info: dict,
        table_start_page: int,
        image_paths: list,
        page_offset: int,
        max_page: int
    ) -> tuple[int, int, List[dict]]:
        """
        Trace table extent using accumulative window.
        
        Grows window from [start] to [start, start+1] to [start, start+1, start+2]...
        until the table ends.
        
        Returns:
            (end_page, total_rows, new_tables_discovered)
        """
        title = table_info.get("title") or "Unknown"
        columns = table_info.get("column_headers", [])
        total_rows = table_info.get("row_count_this_page", 0)
        new_tables: List[dict] = []
        
        # If table doesn't reach bottom of page, it ends on this page
        if not table_info.get("reaches_page_bottom", True):
            logger.info(f"    Table ends on page {table_start_page} (doesn't reach bottom)")
            return table_start_page, total_rows, new_tables
        
        current_end = table_start_page
        
        # Grow window page by page
        while current_end < max_page:
            next_page = current_end
            window_size = next_page - table_start_page + 1
            
            # Check max window size
            if window_size > self.window_size:
                logger.info(f"    Reached max window ({self.window_size} pages), assuming continuation")
                current_end = next_page
                total_rows += 10  # Estimate
                continue
            
            logger.info(f"    Checking page {next_page} (window: {table_start_page}-{next_page})...")
            
            # Build accumulative window
            window_pages = []
            for p in range(table_start_page, next_page + 1):
                idx = p - page_offset
                if 0 <= idx < len(image_paths):
                    window_pages.append((p, image_paths[idx]))
            
            # Ask if table continues
            result = self._check_continuation(
                table_info=table_info,
                window_pages=window_pages,
                start_page=table_start_page,
                check_page=next_page
            )
            
            if result.get("table_continues"):
                
                total_rows += result.get("rows_on_this_page", 0)
                logger.info(f"      ✓ Continues (+{result.get('rows_on_this_page', 0)} rows)")
                
                # Check if table ends here
                if result.get("table_ends_here"):
                    logger.info(f"    Table ends on page {current_end}")
                    
                    # Record any new tables that start on this page
                    for new_t in result.get("new_tables_start", []):
                        new_t["discovered_on_page"] = next_page
                        new_tables.append(new_t)
                    break

            else:
                logger.info(f"      ✗ Does not continue (reason: {result.get('reason', 'unknown')})")
                
                # Record any new tables
                for new_t in result.get("new_tables_start", []):
                    new_t["discovered_on_page"] = next_page
                    new_tables.append(new_t)
                break
            current_end = next_page + 1
        return current_end, total_rows, new_tables
    
    def _check_continuation(
        self,
        table_info: dict,
        window_pages: List[tuple],
        start_page: int,
        check_page: int
    ) -> dict:
        """
        Check if table continues on check_page using full window context.
        
        Sends all pages from start_page to check_page so model can see
        the original headers and all intermediate data.
        """
        title = table_info.get("title") or "Unknown"
        columns = ", ".join(table_info.get("column_headers", [])) or "Not specified"
        
        prompt = CONTINUATION_CHECK_PROMPT.format(
            total_pages=len(window_pages),
            title=title,
            columns=columns,
            start_page=start_page,
            check_page=check_page
        )
        
        # Build content with all window pages
        content = [{"type": "text", "text": prompt}]
        
        for page_num, img_path in window_pages:
            b64 = self._get_b64(img_path)
            label = "(ORIGIN - has column headers)" if page_num == start_page else ""
            content.append({"type": "text", "text": f"\n--- PAGE {page_num} {label} ---"})
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"}
            })
        
        try:
            response = self.extractor.client.chat.completions.create(
                model=self.extractor.deployment,
                messages=[{"role": "user", "content": content}],
                max_tokens=1024,
                temperature=0
            )
            
            return self._parse_json(response.choices[0].message.content)
            
        except Exception as e:
            logger.error(f"Error checking continuation to page {check_page}: {e}")
            return {"table_continues": False, "reason": str(e)}
    
    def _infer_table_type(self, table_info: dict) -> str:
        """Infer table type from title and columns."""
        title = (table_info.get("title") or "").lower()
        columns = [c.lower() for c in table_info.get("column_headers", [])]
        
        if "rate" in title or "rate card" in title:
            return "rate_card"
        if any("rate" in c for c in columns):
            return "rate_card"
        if "service" in title and ("type" in title or "definition" in title):
            return "service_matrix"
        
        return "other"
    
    def _get_b64(self, image_path: Union[str, Path]) -> str:
        """Get base64 encoded image with caching."""
        key = str(image_path)
        if key not in self._image_cache:
            with open(image_path, "rb") as f:
                self._image_cache[key] = base64.b64encode(f.read()).decode("utf-8")
        return self._image_cache[key]
    
    def _parse_json(self, text: str) -> dict:
        """Parse JSON from model response."""
        text = text.strip()
        
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
            logger.debug(f"Response text: {text[:500]}...")
            return {}
    
    def _create_empty_metadata(self, source_file: str, start_page: int) -> DetectionMetadata:
        """Create empty metadata."""
        return DetectionMetadata(
            source_file=source_file,
            detection_date=datetime.now().isoformat(),
            page_range_scanned=(start_page, start_page),
            total_pages_scanned=0,
            total_tables_found=0,
            multipage_tables=0,
            max_window_size=self.window_size,
            tables=[]
        )
