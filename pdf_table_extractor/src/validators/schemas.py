"""
Pydantic schemas for extracted table data.

This module defines the data structures used to represent extracted
tables. Using Pydantic provides:
- Automatic validation
- Type hints and documentation
- Easy JSON serialization/deserialization

Example:
    from src.validators.schemas import ExtractedTable, ExtractionResult
    
    table = ExtractedTable(
        table_id="rate_card_a",
        table_type="rate_card",
        page_number=80,
        data=[...]
    )
    
    # Export to JSON
    print(table.model_dump_json(indent=2))
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional, Union

from pydantic import BaseModel, Field, field_validator


class TableType(str, Enum):
    """Types of tables that can be extracted."""
    
    RATE_CARD = "rate_card"
    SERVICE_MATRIX = "service_matrix"
    FORM = "form"
    OTHER = "other"


class ColumnInfo(BaseModel):
    """Information about a table column."""
    
    name: str = Field(description="Column header name")
    data_type: str = Field(
        default="text",
        description="Data type: text, number, currency, date"
    )
    parent: Optional[str] = Field(
        default=None,
        description="Parent header for nested columns"
    )
    currency: Optional[str] = Field(
        default=None,
        description="Currency code if this is a currency column"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "USA",
                "data_type": "currency",
                "parent": "North America",
                "currency": "USD"
            }
        }


class TableMetadata(BaseModel):
    """Additional metadata about a table."""
    
    rate_card_id: Optional[str] = Field(
        default=None,
        description="Rate card identifier (A, B, C, etc.)"
    )
    region: Optional[str] = Field(
        default=None,
        description="Geographic region"
    )
    sub_region: Optional[str] = Field(
        default=None,
        description="Sub-region or country group"
    )
    currencies: Optional[list[str]] = Field(
        default=None,
        description="List of currencies in this table"
    )
    effective_date: Optional[str] = Field(
        default=None,
        description="Date when rates become effective"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Additional notes or footnotes"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "rate_card_id": "A",
                "region": "Americas",
                "currencies": ["USD", "CAD", "BRL"],
                "notes": "Rates effective from January 2024"
            }
        }


class TableRow(BaseModel):
    """A single row of table data."""
    
    row_group: Optional[str] = Field(
        default=None,
        description="Category or group this row belongs to"
    )
    row_label: str = Field(
        description="Row identifier or label"
    )
    row_description: Optional[str] = Field(
        default=None,
        description="Additional description for the row"
    )
    values: dict[str, Any] = Field(
        description="Column values for this row"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "row_group": "IT Consulting",
                "row_label": "Level 1 (Partner)",
                "row_description": "equivalent; >15 years",
                "values": {
                    "brazil": 8597.38,
                    "usa": 5387.66,
                    "canada": 5395.55
                }
            }
        }


class ExtractedTable(BaseModel):
    """
    A complete extracted table with all its data.
    
    This is the main data structure for representing extracted tables.
    It includes the table structure, data, and metadata.
    """
    
    table_id: str = Field(
        description="Unique identifier for this table"
    )
    table_type: TableType = Field(
        description="Type of table"
    )
    title: Optional[str] = Field(
        default=None,
        description="Table title or heading"
    )
    page_number: int = Field(
        description="Page number where this table was found"
    )
    columns: Optional[list[ColumnInfo]] = Field(
        default=None,
        description="Column definitions"
    )
    data: list[Union[TableRow, dict[str, Any]]] = Field(
        description="Table data rows"
    )
    metadata: Optional[TableMetadata] = Field(
        default=None,
        description="Additional metadata"
    )
    raw_structure: Optional[dict] = Field(
        default=None,
        description="Raw structure information from extraction"
    )
    
    @field_validator("table_id")
    @classmethod
    def validate_table_id(cls, v: str) -> str:
        """Ensure table_id is a valid identifier."""
        # Replace spaces with underscores, lowercase
        return v.lower().replace(" ", "_").replace("-", "_")
    
    class Config:
        json_schema_extra = {
            "example": {
                "table_id": "rate_card_a_americas",
                "table_type": "rate_card",
                "title": "RATE CARD A - AMERICAS",
                "page_number": 80,
                "data": [
                    {
                        "row_label": "Level 1 (Partner)",
                        "values": {"usa": 5387.66}
                    }
                ]
            }
        }


class PageInfo(BaseModel):
    """Information about table presence on a page."""
    
    has_tables: bool = Field(description="Whether tables were found")
    table_count: int = Field(description="Number of tables found")


class PageResult(BaseModel):
    """Extraction results for a single page."""
    
    page_number: int = Field(description="Page number")
    page_info: PageInfo = Field(description="Summary of table detection")
    tables: list[ExtractedTable] = Field(
        default_factory=list,
        description="Extracted tables from this page"
    )


class ExtractionMetadata(BaseModel):
    """Metadata about the extraction process."""
    
    source_file: str = Field(description="Name of the source PDF file")
    extraction_date: datetime = Field(
        default_factory=datetime.now,
        description="When the extraction was performed"
    )
    page_range: list[int] = Field(
        description="Page range that was processed [start, end]"
    )
    pages_processed: int = Field(description="Number of pages processed")
    pages_with_tables: int = Field(description="Number of pages with tables")
    total_tables: int = Field(description="Total number of tables extracted")
    extractor_version: str = Field(
        default="1.0.0",
        description="Version of the extractor"
    )


class ExtractionSummary(BaseModel):
    """Summary of extracted tables."""
    
    total_tables: int = Field(description="Total number of tables")
    tables_by_type: dict[str, int] = Field(
        description="Count of tables by type"
    )
    tables_by_page: dict[int, int] = Field(
        description="Count of tables per page"
    )
    table_list: list[dict[str, Any]] = Field(
        description="Brief info about each table"
    )


class ExtractionResult(BaseModel):
    """
    Complete result of a table extraction operation.
    
    This is the top-level structure returned by the extractor,
    containing all extracted tables organized by page along with
    metadata and summary information.
    
    Example:
        result = extractor.extract("contract.pdf")
        
        print(f"Found {result.metadata.total_tables} tables")
        
        for page in result.pages:
            for table in page.tables:
                print(f"Table: {table.title}")
    """
    
    metadata: ExtractionMetadata = Field(
        description="Information about the extraction"
    )
    pages: list[PageResult] = Field(
        description="Results organized by page"
    )
    summary: ExtractionSummary = Field(
        description="Summary statistics"
    )
    
    @property
    def all_tables(self) -> list[ExtractedTable]:
        """Get all tables from all pages as a flat list."""
        tables = []
        for page in self.pages:
            tables.extend(page.tables)
        return tables
    
    def get_tables_by_type(self, table_type: TableType) -> list[ExtractedTable]:
        """Get all tables of a specific type."""
        return [t for t in self.all_tables if t.table_type == table_type]
    
    def get_table_by_id(self, table_id: str) -> Optional[ExtractedTable]:
        """Find a table by its ID."""
        for table in self.all_tables:
            if table.table_id == table_id:
                return table
        return None
    
    def to_json(self, indent: int = 2) -> str:
        """Export to JSON string."""
        return self.model_dump_json(indent=indent)
    
    def to_dict(self) -> dict:
        """Export to dictionary."""
        return self.model_dump()
    
    class Config:
        json_schema_extra = {
            "example": {
                "metadata": {
                    "source_file": "contract.pdf",
                    "total_tables": 15
                },
                "pages": [],
                "summary": {
                    "total_tables": 15,
                    "tables_by_type": {"rate_card": 10, "service_matrix": 5}
                }
            }
        }
