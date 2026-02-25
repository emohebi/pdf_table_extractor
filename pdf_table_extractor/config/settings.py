"""
Configuration settings for the PDF Table Extractor.

This module provides centralized configuration management using environment
variables and sensible defaults. Settings can be overridden via:
1. Environment variables
2. A .env file in the project root
3. Programmatically when creating a Settings instance

Example:
    # Using defaults and environment variables
    settings = get_settings()
    
    # Override specific settings
    settings = Settings(dpi=300, temperature=0.1)
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Find the project root directory (where .env should be located)
def _find_project_root() -> Path:
    """Find the project root by looking for known project files."""
    current = Path(__file__).resolve().parent  # config/
    
    # Go up to find project root (look for requirements.txt or .env)
    for parent in [current, current.parent, current.parent.parent]:
        if (parent / "requirements.txt").exists() or (parent / ".env").exists():
            return parent
    
    # Fallback to current working directory
    return Path.cwd()


def _load_env_file() -> None:
    """Load environment variables from .env file if it exists."""
    try:
        from dotenv import load_dotenv
        
        # Try multiple locations for .env file
        possible_locations = [
            Path.cwd() / ".env",                    # Current working directory
            _find_project_root() / ".env",          # Project root
            Path(__file__).parent.parent / ".env",  # One level up from config/
        ]
        
        for env_path in possible_locations:
            if env_path.exists():
                load_dotenv(dotenv_path=env_path)
                return
        
        # If no .env file found, try default load_dotenv behavior
        load_dotenv()
        
    except ImportError:
        # python-dotenv not installed, skip
        pass


# Load environment variables
_load_env_file()


@dataclass
class AzureOpenAISettings:
    """Azure OpenAI API configuration."""
    
    api_key: str = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_API_KEY", "")
    )
    endpoint: str = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_ENDPOINT", "")
    )
    deployment: str = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
    )
    api_version: str = field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
    )
    
    def validate(self) -> bool:
        """Check if required credentials are set."""
        return bool(self.api_key and self.endpoint)


@dataclass
class PDFProcessingSettings:
    """Settings for PDF to image conversion."""
    
    # Image resolution (DPI) for PDF conversion
    # Higher values = better quality but larger files and slower processing
    # Recommended: 150-200 for most documents, 250-300 for fine print
    dpi: int = 200
    
    # Image format for converted pages
    image_format: str = "PNG"
    
    # Whether to save converted page images (useful for debugging)
    save_page_images: bool = False
    
    # Directory to save page images (if save_page_images is True)
    images_dir: str = "page_images"


@dataclass
class ExtractionSettings:
    """Settings for the GPT-4o extraction process."""
    
    # Maximum tokens for GPT-4o response
    # Increase if tables are being truncated
    max_tokens: int = 4096
    
    # Temperature setting (0 = deterministic, higher = more creative)
    # Use 0 for consistent data extraction
    temperature: float = 0.0
    
    # Image detail level for GPT-4o vision
    # "high" = better for tables with small text, costs more
    # "low" = faster and cheaper, may miss fine details
    image_detail: str = "high"
    
    # Whether to pass context from previous pages
    # Helps with tables that span multiple pages
    enable_context_passing: bool = True
    
    # Number of retries on API failure
    max_retries: int = 3
    
    # Delay between retries (seconds)
    retry_delay: float = 1.0


@dataclass
class FilteringSettings:
    """Settings for page filtering (to skip non-table pages)."""
    
    # Whether to pre-filter pages for table detection
    # Reduces API calls but may miss some tables
    enable_page_filter: bool = True
    
    # Minimum number of detected lines to consider a page as having a table
    min_table_lines: int = 5
    
    # Minimum line length (pixels) for table detection
    min_line_length: int = 100


@dataclass
class OutputSettings:
    """Settings for output files and formatting."""
    
    # Default output directory
    output_dir: str = "output"
    
    # Whether to pretty-print JSON output
    pretty_json: bool = True
    
    # JSON indentation level
    json_indent: int = 2
    
    # Whether to include empty tables in output
    include_empty_tables: bool = False


@dataclass
class Settings:
    """
    Main settings container combining all configuration categories.
    
    Example:
        settings = Settings()
        print(settings.azure.deployment)
        print(settings.pdf.dpi)
    """
    
    azure: AzureOpenAISettings = field(default_factory=AzureOpenAISettings)
    pdf: PDFProcessingSettings = field(default_factory=PDFProcessingSettings)
    extraction: ExtractionSettings = field(default_factory=ExtractionSettings)
    filtering: FilteringSettings = field(default_factory=FilteringSettings)
    output: OutputSettings = field(default_factory=OutputSettings)
    
    # Logging level
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO")
    )
    
    def validate(self) -> tuple[bool, list[str]]:
        """
        Validate all settings and return any errors.
        
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        # Check Azure credentials
        if not self.azure.api_key:
            errors.append("AZURE_OPENAI_API_KEY is not set")
        if not self.azure.endpoint:
            errors.append("AZURE_OPENAI_ENDPOINT is not set")
        
        # Check PDF settings
        if self.pdf.dpi < 72 or self.pdf.dpi > 600:
            errors.append(f"DPI {self.pdf.dpi} is out of range (72-600)")
        
        # Check extraction settings
        if self.extraction.temperature < 0 or self.extraction.temperature > 2:
            errors.append(f"Temperature {self.extraction.temperature} is out of range (0-2)")
        
        return len(errors) == 0, errors


# Singleton instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Get the global settings instance.
    
    Creates a new Settings instance on first call, then returns
    the same instance on subsequent calls.
    
    Returns:
        Settings instance
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Reset the global settings instance (useful for testing)."""
    global _settings
    _settings = None
