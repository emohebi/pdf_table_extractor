"""
Data validation and normalization for extracted tables.

This module provides validation logic to ensure extracted data
is correct and consistent. It handles:
- Numeric value parsing
- Currency normalization
- Data type validation
- Error detection and reporting

Example:
    from src.validators.validator import TableValidator
    
    validator = TableValidator()
    
    # Validate raw extraction results
    validated = validator.validate(raw_data)
    
    # Check for issues
    if validator.has_warnings:
        print("Warnings:", validator.warnings)
"""

import re
from typing import Any, Optional

from src.utils.logger import get_logger
from .schemas import (
    ExtractedTable,
    PageResult,
    ExtractionResult,
    ExtractionMetadata,
    ExtractionSummary,
    TableType,
    PageInfo,
)

logger = get_logger(__name__)


class TableValidator:
    """
    Validates and normalizes extracted table data.
    
    This class processes raw extraction results from GPT-4o and ensures
    the data is properly formatted, validated, and ready for use.
    
    Features:
    - Parse and validate numeric values
    - Normalize currency codes
    - Detect and report data quality issues
    - Convert to standardized schema
    
    Example:
        validator = TableValidator()
        result = validator.validate_extraction(raw_pages, metadata)
        
        if validator.warnings:
            for warning in validator.warnings:
                print(f"Warning: {warning}")
    """
    
    # Standard currency code mappings
    CURRENCY_MAP = {
        # Text to ISO code
        "real": "BRL",
        "reais": "BRL",
        "peso": "CLP",  # Chilean peso
        "dollar": "USD",
        "dollars": "USD",
        "rupee": "INR",
        "rupees": "INR",
        "yen": "JPY",
        "yuan": "CNY",
        "rmb": "CNY",
        # Already ISO codes
        "usd": "USD",
        "brl": "BRL",
        "clp": "CLP",
        "cad": "CAD",
        "aud": "AUD",
        "ttd": "TTD",
        "sgd": "SGD",
        "inr": "INR",
        "cny": "CNY",
        "jpy": "JPY",
        "gbp": "GBP",
        "eur": "EUR",
    }
    
    def __init__(self):
        """Initialize the validator."""
        self.warnings: list[str] = []
        self.errors: list[str] = []
    
    @property
    def has_warnings(self) -> bool:
        """Check if any warnings were recorded."""
        return len(self.warnings) > 0
    
    @property
    def has_errors(self) -> bool:
        """Check if any errors were recorded."""
        return len(self.errors) > 0
    
    def clear(self) -> None:
        """Clear all warnings and errors."""
        self.warnings = []
        self.errors = []
    
    def validate_extraction(
        self,
        raw_pages: list[dict],
        source_file: str,
        page_range: tuple[int, int]
    ) -> ExtractionResult:
        """
        Validate and structure raw extraction results.
        
        Args:
            raw_pages: List of raw page extraction results from GPT-4o
            source_file: Name of the source PDF file
            page_range: (start, end) page range that was processed
        
        Returns:
            Validated ExtractionResult
        """
        self.clear()
        
        validated_pages = []
        all_tables = []
        
        for raw_page in raw_pages:
            page_result = self._validate_page(raw_page)
            validated_pages.append(page_result)
            all_tables.extend(page_result.tables)
        
        # Build metadata
        metadata = ExtractionMetadata(
            source_file=source_file,
            page_range=list(page_range),
            pages_processed=page_range[1] - page_range[0] + 1,
            pages_with_tables=len([p for p in validated_pages if p.tables]),
            total_tables=len(all_tables)
        )
        
        # Build summary
        summary = self._build_summary(all_tables)
        
        return ExtractionResult(
            metadata=metadata,
            pages=validated_pages,
            summary=summary
        )
    
    def _validate_page(self, raw_page: dict) -> PageResult:
        """Validate a single page's extraction results."""
        page_number = raw_page.get("page_number", 0)
        
        # Get page info
        page_info_raw = raw_page.get("page_info", {})
        page_info = PageInfo(
            has_tables=page_info_raw.get("has_tables", False),
            table_count=page_info_raw.get("table_count", 0)
        )
        
        # Validate each table
        validated_tables = []
        for raw_table in raw_page.get("tables", []):
            try:
                table = self._validate_table(raw_table, page_number)
                if table:
                    validated_tables.append(table)
            except Exception as e:
                self.errors.append(
                    f"Page {page_number}: Failed to validate table: {e}"
                )
                logger.warning(f"Table validation error on page {page_number}: {e}")
        
        return PageResult(
            page_number=page_number,
            page_info=page_info,
            tables=validated_tables
        )
    
    def _validate_table(
        self,
        raw_table: dict,
        page_number: int
    ) -> Optional[ExtractedTable]:
        """Validate a single table."""
        
        # Get table ID (generate if missing)
        table_id = raw_table.get("table_id")
        if not table_id:
            table_type = raw_table.get("table_type", "unknown")
            table_id = f"{table_type}_page{page_number}"
            self.warnings.append(
                f"Page {page_number}: Generated table_id '{table_id}'"
            )
        
        # Parse table type
        table_type_str = raw_table.get("table_type", "other").lower()
        try:
            table_type = TableType(table_type_str)
        except ValueError:
            table_type = TableType.OTHER
            self.warnings.append(
                f"Page {page_number}: Unknown table type '{table_type_str}'"
            )
        
        # Validate data
        data = raw_table.get("data", [])
        validated_data = self._validate_table_data(data, page_number)
        
        # Validate metadata
        metadata = raw_table.get("metadata")
        if metadata:
            metadata = self._normalize_metadata(metadata)
        
        return ExtractedTable(
            table_id=table_id,
            table_type=table_type,
            title=raw_table.get("title"),
            page_number=page_number,
            columns=raw_table.get("columns"),
            data=validated_data,
            metadata=metadata,
            raw_structure=raw_table.get("structure")
        )
    
    def _validate_table_data(
        self,
        data: list[dict],
        page_number: int
    ) -> list[dict]:
        """Validate and normalize table data rows."""
        validated_rows = []
        
        for i, row in enumerate(data):
            validated_row = {}
            
            # Copy non-value fields
            for key in ["row_group", "row_label", "row_description"]:
                if key in row:
                    validated_row[key] = row[key]
            
            # Validate values
            if "values" in row:
                validated_row["values"] = self._validate_values(
                    row["values"], page_number, i
                )
            else:
                # If no 'values' key, treat the whole row as values
                validated_row["values"] = self._validate_values(
                    row, page_number, i
                )
            
            validated_rows.append(validated_row)
        
        return validated_rows
    
    def _validate_values(
        self,
        values: dict,
        page_number: int,
        row_index: int
    ) -> dict:
        """Validate and normalize value fields."""
        validated = {}
        
        for key, value in values.items():
            # Skip metadata fields
            if key in ["row_group", "row_label", "row_description"]:
                continue
            
            # Try to parse as number if it looks like one
            parsed_value = self._parse_numeric(value)
            if parsed_value is not None:
                validated[key] = parsed_value
            else:
                validated[key] = value
        
        return validated
    
    def _parse_numeric(self, value: Any) -> Optional[float]:
        """
        Try to parse a value as a number.
        
        Handles:
        - Plain numbers
        - Strings with commas (1,234.56)
        - Strings with spaces (1 234.56)
        - Currency symbols ($1,234)
        """
        if isinstance(value, (int, float)):
            return float(value)
        
        if not isinstance(value, str):
            return None
        
        # Remove common formatting
        cleaned = value.strip()
        
        # Remove currency symbols and letters
        cleaned = re.sub(r"[$€£¥₹]", "", cleaned)
        
        # Remove thousands separators (comma or space)
        cleaned = cleaned.replace(",", "").replace(" ", "")
        
        # Try to parse
        try:
            return float(cleaned)
        except ValueError:
            return None
    
    def _normalize_metadata(self, metadata: dict) -> dict:
        """Normalize table metadata."""
        normalized = dict(metadata)
        
        # Normalize currencies
        if "currencies" in normalized and normalized["currencies"]:
            normalized["currencies"] = [
                self._normalize_currency(c)
                for c in normalized["currencies"]
            ]
        
        if "currency" in normalized:
            normalized["currency"] = self._normalize_currency(
                normalized["currency"]
            )
        
        return normalized
    
    def _normalize_currency(self, currency: str) -> str:
        """Normalize a currency string to ISO code."""
        if not currency:
            return currency
        
        lower = currency.lower().strip()
        return self.CURRENCY_MAP.get(lower, currency.upper())
    
    def _build_summary(self, tables: list[ExtractedTable]) -> ExtractionSummary:
        """Build summary statistics."""
        # Count by type
        by_type: dict[str, int] = {}
        for table in tables:
            type_name = table.table_type.value
            by_type[type_name] = by_type.get(type_name, 0) + 1
        
        # Count by page
        by_page: dict[int, int] = {}
        for table in tables:
            page = table.page_number
            by_page[page] = by_page.get(page, 0) + 1
        
        # Brief list
        table_list = [
            {
                "table_id": t.table_id,
                "table_type": t.table_type.value,
                "title": t.title,
                "page": t.page_number
            }
            for t in tables
        ]
        
        return ExtractionSummary(
            total_tables=len(tables),
            tables_by_type=by_type,
            tables_by_page=by_page,
            table_list=table_list
        )
    
    def validate_rate_values(
        self,
        table: ExtractedTable,
        min_value: float = 0,
        max_value: float = 10_000_000
    ) -> list[str]:
        """
        Validate that rate values are within expected ranges.
        
        Args:
            table: Table to validate
            min_value: Minimum acceptable rate value
            max_value: Maximum acceptable rate value
        
        Returns:
            List of validation warnings
        """
        warnings = []
        
        for row in table.data:
            values = row.get("values", row)
            for key, value in values.items():
                if isinstance(value, (int, float)):
                    if value < min_value:
                        warnings.append(
                            f"Value {value} for {key} is below minimum {min_value}"
                        )
                    elif value > max_value:
                        warnings.append(
                            f"Value {value} for {key} exceeds maximum {max_value}"
                        )
        
        return warnings
