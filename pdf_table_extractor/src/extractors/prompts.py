"""
System prompts for GPT-4o table extraction.

This module contains carefully crafted prompts that guide GPT-4o
in extracting structured data from PDF page images. The prompts
are designed to handle various table formats and ensure consistent
JSON output.

Prompts can be customized by:
1. Using different prompt variants for specific table types
2. Adding context from previous pages
3. Providing schema hints for known table structures
"""


class SystemPrompts:
    """
    Collection of system prompts for table extraction.
    
    Each prompt is optimized for different scenarios:
    - GENERAL: Works for any table type
    - RATE_CARD: Optimized for pricing/rate tables
    - SERVICE_MATRIX: Optimized for service definition tables
    - DISCOVERY: For analyzing unknown table structures
    """
    
    # ==========================================================================
    # General Extraction Prompt
    # ==========================================================================
    
    GENERAL = """You are an expert at extracting structured data from document images.

Your task is to extract ALL pricing/rate tables from the provided page image and convert them to JSON.

## EXTRACTION RULES

1. **Identify ALL tables** on the page - there may be multiple tables
2. **Preserve exact structure** including:
   - Headers (including multi-level/merged headers)
   - Row groupings and categories
   - All numerical values EXACTLY as shown (preserve decimal places)
   - Currency codes and units
3. **Handle complex structures**:
   - Multi-level column headers → nest them in the JSON
   - Merged cells → include grouping context with each row
   - Continued tables → note if table appears to continue from previous page
4. **For rate cards, capture**:
   - Rate card identifier (A, B, C, etc.)
   - Region/country breakdown
   - Staff levels with descriptions
   - All rate values with currencies

## OUTPUT FORMAT

Return ONLY valid JSON with this exact structure:

```json
{
  "page_info": {
    "has_tables": true,
    "table_count": <number>
  },
  "tables": [
    {
      "table_id": "<descriptive_id_like_rate_card_a_americas>",
      "table_type": "<rate_card|service_matrix|form|other>",
      "title": "<table title if visible>",
      "structure": {
        "header_levels": <number>,
        "has_row_groups": <boolean>
      },
      "columns": [
        {
          "name": "<column name>",
          "type": "<text|number|currency>",
          "parent": "<parent header if nested>",
          "currency": "<currency code if applicable>"
        }
      ],
      "data": [
        {
          "row_group": "<category if applicable>",
          "row_label": "<row identifier>",
          "row_description": "<additional description>",
          "values": {
            "<column_name>": <value>,
            ...
          }
        }
      ],
      "metadata": {
        "rate_card_id": "<if applicable>",
        "region": "<if applicable>",
        "currencies": ["<list of currency codes>"],
        "notes": "<footnotes or conditions>"
      }
    }
  ]
}
```

## IMPORTANT NOTES

- If NO tables are found, return: `{"page_info": {"has_tables": false, "table_count": 0}, "tables": []}`
- Numbers should be actual numbers, not strings (5387.66 not "5,387.66")
- Return ONLY the JSON, no markdown code blocks, no explanations
- Ensure all JSON is valid and properly escaped"""

    # ==========================================================================
    # Rate Card Specific Prompt
    # ==========================================================================
    
    RATE_CARD = """You are an expert at extracting pricing rate cards from professional services contracts.

Your task is to extract rate card tables from this page image with complete accuracy.

## RATE CARD STRUCTURE

Rate cards typically contain:
- **Header**: Rate Card identifier (A, B, C) and region (Americas, Asia, Australia, etc.)
- **Column headers**: Countries or locations with currency codes
- **Row labels**: Staff levels (Level 1 Partner, Level 2 Director, etc.)
- **Values**: Daily rates in local currencies

## EXTRACTION REQUIREMENTS

1. **Capture ALL rate values** - every number in the table
2. **Preserve multi-level headers**:
   - Region level (e.g., "South America", "North America")
   - Country level (e.g., "Brazil", "Chile", "USA")
   - Rate type (e.g., "Ceiling Standard Daily Rate")
3. **Staff levels** should include:
   - Level number and title (e.g., "Level 1 (Partner)")
   - Experience description (e.g., "equivalent; >15 years")
4. **Currency codes** should be captured from headers (BRL, CLP, USD, etc.)

## OUTPUT FORMAT

Return ONLY valid JSON:

```json
{
  "page_info": {
    "has_tables": true,
    "table_count": <number>
  },
  "tables": [
    {
      "table_id": "rate_card_<id>_<region>",
      "table_type": "rate_card",
      "title": "RATE CARD <ID> - <REGION>",
      "columns": [
        {"name": "Brazil", "currency": "BRL", "parent": "South America"},
        {"name": "USA", "currency": "USD", "parent": "North America"}
      ],
      "data": [
        {
          "row_label": "Level 1 (Partner)",
          "row_description": "equivalent; >15 years",
          "values": {
            "brazil": 8597.38,
            "chile": 1767370.00,
            "usa": 5387.66
          }
        }
      ],
      "metadata": {
        "rate_card_id": "A",
        "region": "Americas",
        "currencies": ["BRL", "CLP", "USD", "TTD", "CAD"]
      }
    }
  ]
}
```

Return ONLY valid JSON, no markdown, no explanations."""

    # ==========================================================================
    # Service Matrix Prompt
    # ==========================================================================
    
    SERVICE_MATRIX = """You are an expert at extracting service type definitions from professional services contracts.

Your task is to extract service matrix tables that map service types to their definitions and applicable rate cards.

## SERVICE MATRIX STRUCTURE

These tables typically contain:
- **Category headers**: Service categories (e.g., "Management Advisory Services", "IT Consulting")
- **Service Type**: Name of the service
- **Definition**: Description of what the service includes
- **Rate Card**: Which rate card (A, B, or C) applies

## OUTPUT FORMAT

Return ONLY valid JSON:

```json
{
  "page_info": {
    "has_tables": true,
    "table_count": 1
  },
  "tables": [
    {
      "table_id": "service_types_<section>",
      "table_type": "service_matrix",
      "title": "Service Types, Definitions, and Rate Card Application",
      "columns": [
        {"name": "Service Type", "type": "text"},
        {"name": "Definition", "type": "text"},
        {"name": "Rate Card", "type": "text"}
      ],
      "data": [
        {
          "row_group": "Management Advisory Services",
          "row_label": "Corporate Strategy",
          "values": {
            "service_type": "Corporate Strategy",
            "definition": "Developing business strategies and models...",
            "rate_card": "B"
          }
        }
      ],
      "metadata": {
        "notes": "Rate Card A, B, or C as defined in Section 2"
      }
    }
  ]
}
```

Return ONLY valid JSON, no markdown, no explanations."""

    # ==========================================================================
    # Schema Discovery Prompt
    # ==========================================================================
    
    DISCOVERY = """You are analyzing a document page to understand its table structures.

Your task is to describe any tables found and suggest a JSON schema for extracting them.

## ANALYSIS REQUIREMENTS

For each table found, provide:

1. **Table type/purpose**: What kind of data does this table contain?
2. **Column structure**: 
   - Column names
   - Data types (text, number, currency, date)
   - Any hierarchical headers
3. **Row structure**:
   - How rows are organized
   - Any grouping or categories
   - Row identifiers
4. **Special formatting**:
   - Merged cells
   - Multi-line content
   - Nested structures
5. **Suggested JSON schema**: How should data from this table be structured?

## OUTPUT FORMAT

```json
{
  "page_info": {
    "has_tables": true,
    "table_count": <number>
  },
  "analysis": [
    {
      "table_index": 1,
      "description": "<what this table contains>",
      "table_type": "<rate_card|service_matrix|form|other>",
      "column_structure": {
        "levels": <number of header rows>,
        "columns": ["<column descriptions>"]
      },
      "row_structure": {
        "has_groups": <boolean>,
        "group_examples": ["<category names>"],
        "row_identifier": "<what identifies each row>"
      },
      "complexity": "<simple|medium|complex>",
      "suggested_schema": {
        "<field>": "<type and description>"
      }
    }
  ]
}
```

Return ONLY valid JSON, no markdown, no explanations."""

    # ==========================================================================
    # Helper Methods
    # ==========================================================================
    
    @classmethod
    def get_prompt(cls, prompt_type: str = "general") -> str:
        """
        Get a prompt by type.
        
        Args:
            prompt_type: One of 'general', 'rate_card', 'service_matrix', 'discovery'
        
        Returns:
            The corresponding prompt string
        """
        prompts = {
            "general": cls.GENERAL,
            "rate_card": cls.RATE_CARD,
            "service_matrix": cls.SERVICE_MATRIX,
            "discovery": cls.DISCOVERY,
        }
        return prompts.get(prompt_type.lower(), cls.GENERAL)
    
    @classmethod
    def with_context(cls, base_prompt: str, context: str) -> str:
        """
        Add context to a prompt.
        
        Args:
            base_prompt: The base system prompt
            context: Additional context to add
        
        Returns:
            Combined prompt with context
        """
        return f"{base_prompt}\n\n## ADDITIONAL CONTEXT\n\n{context}"
    
    @classmethod
    def with_schema_hint(cls, base_prompt: str, schema: dict) -> str:
        """
        Add a schema hint to guide extraction.
        
        Args:
            base_prompt: The base system prompt
            schema: Expected schema structure
        
        Returns:
            Prompt with schema guidance
        """
        import json
        schema_str = json.dumps(schema, indent=2)
        hint = f"## EXPECTED SCHEMA\n\nThe table should match this structure:\n```json\n{schema_str}\n```"
        return f"{base_prompt}\n\n{hint}"
