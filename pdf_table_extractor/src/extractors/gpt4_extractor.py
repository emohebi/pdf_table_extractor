"""
GPT-4o Vision-based table extractor.

This module implements table extraction using Azure OpenAI's GPT-4o
vision capabilities. It handles:
- Image encoding and API communication
- Prompt management and context passing
- Response parsing and error handling
- Rate limiting and retries

Example:
    from src.extractors.gpt4_extractor import GPT4VisionExtractor
    
    extractor = GPT4VisionExtractor()
    
    # Test connection first
    success, message = extractor.test_connection()
    if not success:
        print(f"Connection failed: {message}")
    
    # Extract from a single page
    result = extractor.extract_from_image("page_075.png")
"""

import base64
import json
import time
from pathlib import Path
from typing import Any, Optional, Union
from urllib.parse import urlparse

from openai import AzureOpenAI, APIError, APIConnectionError, RateLimitError, APIStatusError

from config.settings import get_settings
from src.utils.logger import get_logger
from .base import BaseExtractor
from .prompts import SystemPrompts

logger = get_logger(__name__)


def validate_azure_endpoint(endpoint: str) -> str:
    """
    Validate and normalize Azure OpenAI endpoint URL.
    
    Args:
        endpoint: The endpoint URL to validate
        
    Returns:
        Normalized endpoint URL
        
    Raises:
        ValueError: If endpoint is invalid
    """
    if not endpoint:
        raise ValueError("Azure OpenAI endpoint is required")
    
    # Remove trailing slashes
    endpoint = endpoint.rstrip("/")
    
    # Parse URL
    parsed = urlparse(endpoint)
    
    # Check if it looks like an Azure endpoint
    if not parsed.scheme:
        raise ValueError(
            f"Invalid endpoint URL (missing https://): {endpoint}\n"
            f"Expected format: https://YOUR-RESOURCE-NAME.openai.azure.com"
        )
    
    if parsed.scheme != "https":
        logger.warning(f"Endpoint should use HTTPS, got: {parsed.scheme}")
    
    # Check for common mistakes
    if "/openai" in endpoint.lower():
        # User included the API path in the endpoint
        logger.warning(
            "Endpoint should be the base URL only, not include '/openai/...' path. "
            "Attempting to fix..."
        )
        # Extract just the base URL
        endpoint = f"{parsed.scheme}://{parsed.netloc}"
    
    if not parsed.netloc:
        raise ValueError(
            f"Invalid endpoint URL: {endpoint}\n"
            f"Expected format: https://YOUR-RESOURCE-NAME.openai.azure.com"
        )
    
    return endpoint


class GPT4VisionExtractor(BaseExtractor):
    """
    Extracts tables from PDF page images using GPT-4o vision.
    
    This extractor uses Azure OpenAI's GPT-4o model with vision
    capabilities to analyze page images and extract structured
    table data.
    
    Example:
        # Basic usage
        extractor = GPT4VisionExtractor(
            api_key="your-key",
            endpoint="https://your-resource.openai.azure.com",
            deployment="gpt-4o"
        )
        
        # Test connection first
        success, msg = extractor.test_connection()
        if success:
            result = extractor.extract_from_image("page.png")
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        deployment: Optional[str] = None,
        api_version: Optional[str] = None
    ):
        """
        Initialize the GPT-4o extractor.
        
        Args:
            api_key: Azure OpenAI API key (uses settings/env if not provided)
            endpoint: Azure OpenAI endpoint URL (e.g., https://myresource.openai.azure.com)
            deployment: Model deployment name (e.g., gpt-4o)
            api_version: API version (default: 2024-08-01-preview)
        
        Raises:
            ValueError: If required credentials are not provided
        """
        settings = get_settings()
        
        # Use provided values or fall back to settings/environment
        self.api_key = api_key or settings.azure.api_key
        self.endpoint = endpoint or settings.azure.endpoint
        self.deployment = deployment or settings.azure.deployment or "gpt-4o"
        
        # Use a known working API version (2024-08-01-preview works well)
        default_api_version = "2024-08-01-preview"
        self.api_version = api_version or settings.azure.api_version or default_api_version
        
        # Validate credentials
        if not self.api_key:
            raise ValueError(
                "Azure OpenAI API key not configured.\n"
                "Options:\n"
                "  1. Set AZURE_OPENAI_API_KEY environment variable\n"
                "  2. Pass api_key parameter to constructor\n"
                "  3. Use --api-key command line argument"
            )
        
        if not self.endpoint:
            raise ValueError(
                "Azure OpenAI endpoint not configured.\n"
                "Options:\n"
                "  1. Set AZURE_OPENAI_ENDPOINT environment variable\n"
                "  2. Pass endpoint parameter to constructor\n"
                "  3. Use --endpoint command line argument\n\n"
                "Expected format: https://YOUR-RESOURCE-NAME.openai.azure.com"
            )
        
        # Validate and normalize endpoint
        self.endpoint = validate_azure_endpoint(self.endpoint)
        
        # Log configuration (mask sensitive data)
        logger.info(f"Azure OpenAI Configuration:")
        logger.info(f"  Endpoint: {self.endpoint}")
        logger.info(f"  Deployment: {self.deployment}")
        logger.info(f"  API Version: {self.api_version}")
        masked_key = f"{'*' * 8}...{self.api_key[-4:]}" if len(self.api_key) > 4 else "****"
        logger.info(f"  API Key: {masked_key}")
        
        # Initialize client
        # from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        import httpx
        # token_provider = get_bearer_token_provider(
        #     DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
        # )
        http_client = httpx.Client(verify=False)
        try:
            # self.client = AzureOpenAI(
            #     azure_ad_token_provider=token_provider,
            #     api_version=self.api_version,
            #     azure_endpoint=self.endpoint,
            #     http_client=http_client
            # )
            self.client = AzureOpenAI(
                azure_endpoint=self.endpoint, api_key=self.api_key,
                api_version=self.api_version,
                http_client=http_client
            )
        except Exception as e:
            raise ValueError(f"Failed to initialize Azure OpenAI client: {e}")
        
        # Extraction settings from config
        self.max_tokens = settings.extraction.max_tokens
        self.temperature = settings.extraction.temperature
        self.image_detail = settings.extraction.image_detail
        self.max_retries = settings.extraction.max_retries
        self.retry_delay = settings.extraction.retry_delay
        
        logger.info(f"GPT4VisionExtractor initialized successfully")
    
    def test_connection(self) -> tuple[bool, str]:
        """
        Test the API connection with a simple request.
        
        This helps diagnose connection issues before processing pages.
        
        Returns:
            Tuple of (success: bool, message: str)
            
        Example:
            success, message = extractor.test_connection()
            if not success:
                print(f"Error: {message}")
        """
        logger.info("Testing Azure OpenAI connection...")
        
        try:
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "user", "content": "Reply with just the word 'OK'."}
                ],
                max_completion_tokens=10
            )
            
            result = response.choices[0].message.content
            msg = f"Connection successful! Response: {result}"
            logger.info(msg)
            return True, msg
                
        except APIConnectionError as e:
            msg = (
                f"Connection failed!\n\n"
                f"Error: {e}\n\n"
                f"Please check:\n"
                f"  1. Endpoint URL is correct: {self.endpoint}\n"
                f"  2. You have network access to Azure (no firewall/proxy blocking)\n"
                f"  3. The Azure OpenAI resource exists and is deployed"
            )
            logger.error(msg)
            return False, msg
            
        except APIStatusError as e:
            if e.status_code == 401:
                msg = (
                    f"Authentication failed (401 Unauthorized)\n\n"
                    f"Your API key appears to be invalid.\n"
                    f"Please check your AZURE_OPENAI_API_KEY."
                )
            elif e.status_code == 404:
                msg = (
                    f"Resource not found (404)\n\n"
                    f"Please check:\n"
                    f"  1. Deployment name '{self.deployment}' exists in your Azure resource\n"
                    f"  2. Endpoint URL is correct: {self.endpoint}\n"
                    f"  3. API version is supported: {self.api_version}"
                )
            elif e.status_code == 429:
                msg = f"Rate limited (429). Please wait and try again."
            else:
                msg = f"API error ({e.status_code}): {e.message}"
            logger.error(msg)
            return False, msg
            
        except Exception as e:
            msg = f"Unexpected error: {type(e).__name__}: {e}"
            logger.error(msg)
            return False, msg
    
    def extract_from_image(
        self,
        image_path: Union[str, Path],
        context: Optional[str] = None,
        prompt_type: str = "general"
    ) -> dict[str, Any]:
        """
        Extract tables from a single page image.
        
        Args:
            image_path: Path to the page image
            context: Optional context from previous pages
            prompt_type: Type of prompt ('general', 'rate_card', 'service_matrix')
        
        Returns:
            Dictionary with extraction results
        """
        image_path = Path(image_path)
        
        # Validate image
        if not self.validate_image(image_path):
            raise ValueError(f"Invalid image file: {image_path}")
        
        # Encode image
        base64_image = self._encode_image(image_path)
        
        # Get appropriate prompt
        system_prompt = SystemPrompts.get_prompt(prompt_type)
        if context:
            system_prompt = SystemPrompts.with_context(system_prompt, context)
        
        # Build user message
        user_message = "Extract all tables from this document page."
        
        # Make API call with retries
        response = self._call_api_with_retry(
            system_prompt=system_prompt,
            user_message=user_message,
            base64_image=base64_image
        )
        
        # Parse response
        result = self._parse_response(response)
        
        return result
    
    def extract_batch(
        self,
        image_paths: list[Union[str, Path]],
        start_page: int = 1,
        prompt_type: str = "general",
        enable_context: bool = True,
        progress_callback: Optional[callable] = None
    ) -> list[dict[str, Any]]:
        """
        Extract tables from multiple page images.
        """
        if not image_paths:
            return []
        
        results = []
        context = None
        total_pages = len(image_paths)
        
        for i, image_path in enumerate(image_paths):
            page_num = start_page + i
            
            logger.info(f"Processing page {page_num} ({i + 1}/{total_pages})")
            
            if progress_callback:
                progress_callback(page_num, total_pages)
            
            try:
                result = self.extract_from_image(
                    image_path,
                    context=context if enable_context else None,
                    prompt_type=prompt_type
                )
                
                result["page_number"] = page_num
                
                if enable_context and result.get("tables"):
                    context = self._build_context(result)
                
                table_count = result.get("page_info", {}).get("table_count", 0)
                logger.info(f"  Found {table_count} table(s)")
                
                results.append(result)
                
            except Exception as e:
                logger.error(f"  Error processing page {page_num}: {e}")
                results.append({
                    "page_number": page_num,
                    "page_info": {"has_tables": False, "table_count": 0},
                    "tables": [],
                    "error": str(e)
                })
        
        return results
    
    def _encode_image(self, image_path: Path) -> str:
        """Encode an image file to base64."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    
    def _call_api_with_retry(
        self,
        system_prompt: str,
        user_message: str,
        base64_image: str
    ) -> str:
        """Make API call with automatic retry on failures."""
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.deployment,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": user_message},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{base64_image}",
                                        "detail": self.image_detail
                                    }
                                }
                            ]
                        }
                    ],
                    max_completion_tokens=self.max_tokens,
                    temperature=self.temperature
                )
                
                return response.choices[0].message.content
            
            except APIConnectionError as e:
                last_error = e
                logger.error(
                    f"Connection error (attempt {attempt + 1}/{self.max_retries})\n"
                    f"  Endpoint: {self.endpoint}\n"
                    f"  Error: {e}\n"
                    f"  Check your network connection and endpoint URL."
                )
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
                
            except RateLimitError as e:
                last_error = e
                wait_time = self.retry_delay * (2 ** attempt)
                logger.warning(f"Rate limited, waiting {wait_time}s (attempt {attempt + 1})")
                time.sleep(wait_time)
            
            except APIStatusError as e:
                last_error = e
                if e.status_code == 401:
                    raise ValueError("Invalid API key (401 Unauthorized)")
                elif e.status_code == 404:
                    raise ValueError(
                        f"Deployment '{self.deployment}' not found (404).\n"
                        f"Check your deployment name and endpoint URL."
                    )
                elif attempt < self.max_retries - 1:
                    logger.warning(f"API error ({e.status_code}), retrying: {e.message}")
                    time.sleep(self.retry_delay)
                else:
                    raise
                
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    logger.warning(f"Error, retrying (attempt {attempt + 1}): {e}")
                    time.sleep(self.retry_delay)
                else:
                    raise
        
        # All retries failed
        error_msg = f"All {self.max_retries} attempts failed. Last error: {last_error}"
        logger.error(error_msg)
        raise Exception(error_msg)
    
    def _parse_response(self, response_text: str) -> dict[str, Any]:
        """Parse the model response into a dictionary."""
        text = response_text.strip()
        
        # Remove markdown code blocks if present
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
            logger.error(f"Failed to parse JSON: {e}")
            logger.debug(f"Response: {text[:500]}...")
            return {
                "page_info": {"has_tables": False, "table_count": 0},
                "tables": [],
                "parse_error": str(e)
            }
    
    def _build_context(self, result: dict) -> str:
        """Build context string from extraction results."""
        tables = result.get("tables", [])
        if not tables:
            return ""
        
        context_parts = []
        for table in tables:
            table_type = table.get("table_type", "unknown")
            title = table.get("title", "untitled")
            part = f"- {table_type}: {title}"
            
            metadata = table.get("metadata", {})
            if metadata.get("rate_card_id"):
                part += f" (Rate Card {metadata['rate_card_id']})"
            if metadata.get("region"):
                part += f" - {metadata['region']}"
            
            context_parts.append(part)
        
        return "Previous page contained:\n" + "\n".join(context_parts)
