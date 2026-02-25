"""
Unit tests for the PDF Table Extractor.

Run tests with: pytest tests/ -v
"""

import pytest
from pathlib import Path


class TestSettings:
    """Tests for configuration settings."""
    
    def test_settings_creation(self):
        """Test that settings can be created."""
        from config.settings import Settings
        
        settings = Settings()
        assert settings is not None
        assert settings.pdf.dpi == 200
        assert settings.extraction.temperature == 0.0
    
    def test_settings_validation(self):
        """Test settings validation."""
        from config.settings import Settings
        
        settings = Settings()
        # Without credentials, validation should fail
        is_valid, errors = settings.validate()
        # We expect errors if env vars aren't set
        assert isinstance(errors, list)


class TestFileUtils:
    """Tests for file utilities."""
    
    def test_clean_filename(self):
        """Test filename cleaning."""
        from src.utils.file_utils import clean_filename
        
        assert clean_filename("test.pdf") == "test.pdf"
        assert clean_filename("test:file.pdf") == "test_file.pdf"
        assert clean_filename("test/file.pdf") == "test_file.pdf"
        assert clean_filename("  test  ") == "test"
    
    def test_ensure_directory(self, tmp_path):
        """Test directory creation."""
        from src.utils.file_utils import ensure_directory
        
        new_dir = tmp_path / "test_dir" / "nested"
        result = ensure_directory(new_dir)
        
        assert result.exists()
        assert result.is_dir()
    
    def test_get_output_path(self, tmp_path):
        """Test output path generation."""
        from src.utils.file_utils import get_output_path
        
        path = get_output_path(
            "contract.pdf",
            tmp_path,
            "json",
            suffix="extracted"
        )
        
        assert path.suffix == ".json"
        assert "extracted" in path.stem


class TestSchemas:
    """Tests for Pydantic schemas."""
    
    def test_extracted_table_creation(self):
        """Test creating an ExtractedTable."""
        from src.validators.schemas import ExtractedTable, TableType
        
        table = ExtractedTable(
            table_id="test_table",
            table_type=TableType.RATE_CARD,
            page_number=1,
            data=[{"row_label": "Test", "values": {"col1": 100}}]
        )
        
        assert table.table_id == "test_table"
        assert table.table_type == TableType.RATE_CARD
    
    def test_table_id_normalization(self):
        """Test that table IDs are normalized."""
        from src.validators.schemas import ExtractedTable, TableType
        
        table = ExtractedTable(
            table_id="Rate Card A - Americas",
            table_type=TableType.RATE_CARD,
            page_number=1,
            data=[]
        )
        
        # Should be lowercase with underscores
        assert table.table_id == "rate_card_a___americas"


class TestValidator:
    """Tests for the table validator."""
    
    def test_parse_numeric(self):
        """Test numeric value parsing."""
        from src.validators.validator import TableValidator
        
        validator = TableValidator()
        
        assert validator._parse_numeric(123) == 123.0
        assert validator._parse_numeric("1,234.56") == 1234.56
        assert validator._parse_numeric("$500") == 500.0
        assert validator._parse_numeric("not a number") is None
    
    def test_normalize_currency(self):
        """Test currency normalization."""
        from src.validators.validator import TableValidator
        
        validator = TableValidator()
        
        assert validator._normalize_currency("usd") == "USD"
        assert validator._normalize_currency("Real") == "BRL"
        assert validator._normalize_currency("Rupee") == "INR"
        assert validator._normalize_currency("XYZ") == "XYZ"


class TestPrompts:
    """Tests for system prompts."""
    
    def test_get_prompt(self):
        """Test prompt retrieval."""
        from src.extractors.prompts import SystemPrompts
        
        general = SystemPrompts.get_prompt("general")
        rate_card = SystemPrompts.get_prompt("rate_card")
        
        assert "extract" in general.lower()
        assert "rate card" in rate_card.lower()
    
    def test_with_context(self):
        """Test adding context to prompts."""
        from src.extractors.prompts import SystemPrompts
        
        base = "Base prompt"
        context = "Some context"
        
        result = SystemPrompts.with_context(base, context)
        
        assert base in result
        assert context in result


# Integration tests (require actual PDF files)
class TestIntegration:
    """Integration tests - these require sample files."""
    
    @pytest.mark.skip(reason="Requires sample PDF file")
    def test_pdf_conversion(self, tmp_path):
        """Test PDF to image conversion with PyMuPDF."""
        from src.processors.pdf_converter import PDFConverter
        
        converter = PDFConverter(dpi=150)
        # Would need a sample PDF file
        pass
    
    @pytest.mark.skip(reason="Requires sample PDF file")
    def test_is_scanned_pdf(self):
        """Test scanned PDF detection."""
        from src.processors.pdf_converter import PDFConverter
        
        converter = PDFConverter()
        # Would need a sample PDF file
        # result = converter.is_scanned_pdf("sample.pdf")
        pass
    
    @pytest.mark.skip(reason="Requires sample PDF file")
    def test_convert_page_to_bytes(self):
        """Test in-memory page conversion."""
        from src.processors.pdf_converter import PDFConverter
        
        converter = PDFConverter(dpi=150)
        # Would need a sample PDF file
        # bytes_data = converter.convert_page_to_bytes("sample.pdf", 1)
        # assert isinstance(bytes_data, bytes)
        pass
    
    @pytest.mark.skip(reason="Requires Azure OpenAI credentials")
    def test_extraction_pipeline(self):
        """Test the full extraction pipeline."""
        from src.main import PricingTableExtractor
        
        extractor = PricingTableExtractor()
        # Would need credentials and sample PDF
        pass
