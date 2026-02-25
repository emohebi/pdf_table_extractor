# PDF Pricing Table Extractor

A Python tool for extracting pricing and rate tables from scanned PDF contracts using Azure OpenAI GPT-4o vision capabilities.

## Key Feature: Two-Phase Extraction

This tool uses a **two-phase approach** to handle tables that span multiple pages:

```
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 1: DETECTION                                             │
│  ─────────────────                                              │
│  • Scan each page to identify tables                            │
│  • Determine if tables continue across pages                    │
│  • Build table inventory with page ranges                       │
│  • Output: detection_metadata.json                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 2: EXTRACTION                                            │
│  ──────────────────                                             │
│  • For each detected table:                                     │
│    - Load ALL pages belonging to that table                     │
│    - Send all pages together in one API call                    │
│    - Extract complete table without data loss                   │
│  • Output: intermediate/*.json + final_extracted.json           │
└─────────────────────────────────────────────────────────────────┘
```

**Why this matters:** Traditional page-by-page extraction loses data at page boundaries. Our approach ensures complete extraction of multi-page tables.

## Features

- **Multi-Page Table Support**: Tables spanning 2-10+ pages are extracted completely
- **Scanned PDF Support**: Works with image-based PDFs using GPT-4o vision
- **Intermediate Results**: Each table saved separately for inspection
- **Detection Metadata**: JSON inventory of all tables with page ranges
- **Flexible Configuration**: DPI, credentials, page ranges all configurable

## Project Structure

```
pdf_table_extractor/
├── src/
│   ├── __init__.py
│   ├── main.py                  # Main entry point & CLI
│   ├── extractors/
│   │   ├── base.py              # Abstract base class
│   │   ├── gpt4_extractor.py    # GPT-4o vision extractor
│   │   ├── table_detector.py    # Phase 1: Table detection
│   │   ├── multipage_extractor.py  # Phase 2: Multi-page extraction
│   │   ├── pipeline.py          # Two-phase orchestration
│   │   └── prompts.py           # System prompts
│   ├── processors/
│   │   ├── pdf_converter.py     # PDF to image (PyMuPDF)
│   │   └── page_analyzer.py     # Page pre-analysis
│   ├── validators/
│   │   ├── schemas.py           # Pydantic schemas
│   │   └── validator.py         # Validation logic
│   └── utils/
│       ├── file_utils.py        # File operations
│       └── logger.py            # Logging setup
├── config/
│   └── settings.py              # Configuration
├── tests/                       # Unit tests
├── examples/                    # Example scripts
├── requirements.txt
├── setup.py
└── README.md
```

### Output Files

After extraction, you'll find:

```
output/
├── page_images/                 # Converted PDF pages
├── intermediate/                # Individual table JSONs
│   ├── rate_card_a_pages_75-78.json
│   └── service_matrix_pages_83-85.json
├── detection_metadata.json      # Table inventory
└── <filename>_extracted.json    # Final combined output
```

## Installation

### 1. Clone the repository

```bash
git clone <repository-url>
cd pdf_table_extractor
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

PyMuPDF is used for PDF processing and has no external system dependencies.

### 4. Configure Azure OpenAI

You have three options for configuring credentials:

**Option A: Environment Variables (Recommended for production)**
```bash
export AZURE_OPENAI_API_KEY="your-api-key-here"
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT="gpt-4o"
```

**Option B: `.env` File (Recommended for development)**

Create a `.env` file in the project root:
```env
AZURE_OPENAI_API_KEY=your-api-key-here
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4o
```

Note: Requires `python-dotenv` package: `pip install python-dotenv`

**Option C: Pass Directly in Code**
```python
from src.extractors.gpt4_extractor import GPT4VisionExtractor

extractor = GPT4VisionExtractor(
    api_key="your-api-key-here",
    endpoint="https://your-resource.openai.azure.com/",
    deployment="gpt-4o"
)
```

## Quick Start

### Command Line Usage

```bash
# Basic usage
python -m src.main path/to/contract.pdf

# Specify page range
python -m src.main path/to/contract.pdf --pages 70-100

# Custom output location
python -m src.main path/to/contract.pdf --output ./results/

# Enable verbose logging
python -m src.main path/to/contract.pdf --verbose
```

### Python API Usage

```python
from src.main import PricingTableExtractor

# Initialize the extractor
extractor = PricingTableExtractor()

# Extract tables from a PDF
result = extractor.extract(
    pdf_path="path/to/contract.pdf",
    page_range=(70, 100)
)

# Access the extracted data
for page in result.pages:
    for table in page.tables:
        print(f"Found {table.table_type}: {table.title}")
        print(table.data)
```

## Output Format

The extractor produces JSON output with the following structure:

```json
{
  "metadata": {
    "source_file": "contract.pdf",
    "extraction_date": "2024-01-15T10:30:00",
    "page_range": [70, 100],
    "total_tables": 15
  },
  "tables": [
    {
      "table_id": "rate_card_a_americas",
      "table_type": "rate_card",
      "title": "RATE CARD A - AMERICAS",
      "page_number": 80,
      "columns": [...],
      "data": [...],
      "metadata": {
        "rate_card_id": "A",
        "region": "Americas",
        "currencies": ["USD", "BRL", "CAD"]
      }
    }
  ]
}
```

## Configuration Options

See `config/settings.py` for all available configuration options:

| Option | Default | Description |
|--------|---------|-------------|
| `DPI` | 200 | Image resolution for PDF conversion |
| `MAX_TOKENS` | 4096 | Maximum tokens for GPT-4o response |
| `TEMPERATURE` | 0 | Model temperature (0 = deterministic) |
| `ENABLE_PAGE_FILTER` | True | Skip pages without tables |
| `SAVE_PAGE_IMAGES` | False | Keep converted page images |

## Development

### Running Tests

```bash
pytest tests/ -v
```

### Code Formatting

```bash
black src/
isort src/
```

### Type Checking

```bash
mypy src/
```

## License

MIT License - See LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request
