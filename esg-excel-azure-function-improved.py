# Improved Document Analyzer with Better Error Handling

## File: utils/document_analyzer_improved.py
```python
import os
import logging
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest, ContentFormat
from typing import Dict, Any, List, Optional
import time
from functools import wraps

def retry_on_exception(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """Decorator for retrying functions on exception."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retry_delay = delay
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    logging.warning(f"Attempt {attempt + 1} failed: {str(e)}. Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= backoff
            return None
        return wrapper
    return decorator

class DocumentAnalyzerImproved:
    """Enhanced document analyzer with better error handling and authentication."""
    
    # Maximum file size in MB
    MAX_FILE_SIZE_MB = 50
    
    def __init__(self, use_managed_identity: bool = False):
        """
        Initialize Document Intelligence client.
        
        Args:
            use_managed_identity: Use managed identity for authentication
        """
        endpoint = os.environ.get("DOCUMENTINTELLIGENCE_ENDPOINT")
        
        if not endpoint:
            raise ValueError("DOCUMENTINTELLIGENCE_ENDPOINT not configured")
        
        # Use managed identity in production, API key in development
        if use_managed_identity:
            credential = DefaultAzureCredential()
            logging.info("Using managed identity for authentication")
        else:
            api_key = os.environ.get("DOCUMENTINTELLIGENCE_API_KEY")
            if not api_key:
                raise ValueError("DOCUMENTINTELLIGENCE_API_KEY not configured")
            credential = AzureKeyCredential(api_key)
            logging.info("Using API key for authentication")
        
        self.client = DocumentIntelligenceClient(
            endpoint=endpoint,
            credential=credential
        )
    
    def validate_file(self, excel_content: bytes, filename: str) -> None:
        """
        Validate the input file.
        
        Args:
            excel_content: File content
            filename: File name
            
        Raises:
            ValueError: If file validation fails
        """
        # Check file size
        file_size_mb = len(excel_content) / (1024 * 1024)
        if file_size_mb > self.MAX_FILE_SIZE_MB:
            raise ValueError(f"File size {file_size_mb:.2f}MB exceeds maximum {self.MAX_FILE_SIZE_MB}MB")
        
        # Check file extension
        valid_extensions = ['.xlsx', '.xls', '.xlsm']
        file_ext = os.path.splitext(filename)[1].lower()
        if file_ext not in valid_extensions:
            raise ValueError(f"Invalid file extension {file_ext}. Supported: {valid_extensions}")
        
        logging.info(f"File validation passed: {filename} ({file_size_mb:.2f}MB)")
    
    @retry_on_exception(max_retries=3, delay=2.0)
    def analyze_excel(self, excel_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Analyze Excel file using Document Intelligence with retry logic.
        
        Args:
            excel_content: Excel file content as bytes
            filename: Name of the Excel file
            
        Returns:
            Extracted data as dictionary
        """
        # Validate file first
        self.validate_file(excel_content, filename)
        
        logging.info(f"Starting Document Intelligence analysis for {filename}")
        
        try:
            # Start analysis
            poller = self.client.begin_analyze_document(
                model_id="prebuilt-layout",
                analyze_request=AnalyzeDocumentRequest(
                    bytes_source=excel_content
                ),
                features=["tables", "keyValuePairs"],
                output_content_format=ContentFormat.MARKDOWN,
                locale="en-US"  # Specify locale for better accuracy
            )
            
            # Poll with timeout
            result = poller.result(timeout=300)  # 5 minute timeout
            
            # Extract and structure data
            extracted_data = self._structure_results(result, filename)
            
            logging.info(f"Successfully analyzed {filename}. Found {len(extracted_data.get('tables', []))} tables")
            return extracted_data
            
        except Exception as e:
            logging.error(f"Failed to analyze document: {str(e)}")
            raise
    
    def _structure_results(self, result: Any, filename: str) -> Dict[str, Any]:
        """Structure the analysis results."""
        extracted_data = {
            "filename": filename,
            "analysis_timestamp": time.time(),
            "pages": [],
            "tables": [],
            "key_value_pairs": [],
            "content": "",
            "metadata": {
                "page_count": len(getattr(result, 'pages', [])),
                "table_count": len(getattr(result, 'tables', [])),
                "confidence_scores": []
            }
        }
        
        # Extract content with error handling
        if hasattr(result, 'content'):
            extracted_data["content"] = result.content
        
        # Process pages safely
        if hasattr(result, 'pages'):
            for page in result.pages:
                try:
                    page_data = self._extract_page_data(page)
                    extracted_data["pages"].append(page_data)
                except Exception as e:
                    logging.warning(f"Error processing page {getattr(page, 'page_number', 'unknown')}: {str(e)}")
        
        # Process tables with validation
        if hasattr(result, 'tables'):
            for idx, table in enumerate(result.tables):
                try:
                    table_data = self._extract_table_data(table, idx)
                    if table_data["cells"]:  # Only add non-empty tables
                        extracted_data["tables"].append(table_data)
                except Exception as e:
                    logging.warning(f"Error processing table {idx}: {str(e)}")
        
        # Process key-value pairs with confidence filtering
        if hasattr(result, 'key_value_pairs'):
            for kvp in result.key_value_pairs:
                try:
                    if self._is_valid_kvp(kvp):
                        kvp_data = {
                            "key": kvp.key.content if kvp.key else "",
                            "value": kvp.value.content if kvp.value else "",
                            "confidence": getattr(kvp, 'confidence', 0.0)
                        }
                        extracted_data["key_value_pairs"].append(kvp_data)
                        extracted_data["metadata"]["confidence_scores"].append(kvp_data["confidence"])
                except Exception as e:
                    logging.warning(f"Error processing key-value pair: {str(e)}")
        
        # Calculate average confidence
        if extracted_data["metadata"]["confidence_scores"]:
            avg_confidence = sum(extracted_data["metadata"]["confidence_scores"]) / len(extracted_data["metadata"]["confidence_scores"])
            extracted_data["metadata"]["average_confidence"] = avg_confidence
        
        return extracted_data
    
    def _extract_page_data(self, page: Any) -> Dict[str, Any]:
        """Extract data from a page object."""
        return {
            "page_number": getattr(page, 'page_number', 0),
            "width": getattr(page, 'width', 0),
            "height": getattr(page, 'height', 0),
            "unit": getattr(page, 'unit', 'pixel'),
            "lines": [
                {
                    "content": line.content,
                    "polygon": getattr(line, 'polygon', [])
                }
                for line in getattr(page, 'lines', [])
                if hasattr(line, 'content')
            ]
        }
    
    def _extract_table_data(self, table: Any, table_idx: int) -> Dict[str, Any]:
        """Extract and validate table data."""
        table_data = {
            "table_id": table_idx,
            "row_count": getattr(table, 'row_count', 0),
            "column_count": getattr(table, 'column_count', 0),
            "cells": [],
            "headers": []
        }
        
        if hasattr(table, 'cells'):
            # Sort cells by position
            sorted_cells = sorted(
                table.cells,
                key=lambda c: (c.row_index, c.column_index)
            )
            
            for cell in sorted_cells:
                cell_data = {
                    "row_index": cell.row_index,
                    "column_index": cell.column_index,
                    "content": cell.content.strip() if cell.content else "",
                    "row_span": getattr(cell, 'row_span', 1),
                    "column_span": getattr(cell, 'column_span', 1),
                    "is_header": cell.row_index == 0  # Assume first row is header
                }
                
                table_data["cells"].append(cell_data)
                
                # Extract headers
                if cell_data["is_header"]:
                    table_data["headers"].append(cell_data["content"])
        
        return table_data
    
    def _is_valid_kvp(self, kvp: Any) -> bool:
        """Check if a key-value pair is valid."""
        if not kvp:
            return False
        
        # Must have both key and value
        if not hasattr(kvp, 'key') or not hasattr(kvp, 'value'):
            return False
        
        # Check confidence threshold
        confidence = getattr(kvp, 'confidence', 0.0)
        if confidence < 0.5:  # Minimum confidence threshold
            return False
        
        return True

## File: function_app_improved.py
```python
import azure.functions as func
import logging
import json
import os
from utils.document_analyzer_improved import DocumentAnalyzerImproved
from utils.data_processor import ESGDataProcessor
from typing import Optional
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Initialize the function app
app = func.FunctionApp()

# Global initialization for better performance
doc_analyzer: Optional[DocumentAnalyzerImproved] = None
data_processor: Optional[ESGDataProcessor] = None

def get_analyzers():
    """Get or create analyzer instances."""
    global doc_analyzer, data_processor
    
    if doc_analyzer is None:
        use_managed_identity = os.environ.get("USE_MANAGED_IDENTITY", "false").lower() == "true"
        doc_analyzer = DocumentAnalyzerImproved(use_managed_identity=use_managed_identity)
    
    if data_processor is None:
        data_processor = ESGDataProcessor()
    
    return doc_analyzer, data_processor

@app.blob_trigger(
    arg_name="inputblob",
    path="input-files/{name}",
    connection="AzureWebJobsStorage"
)
@app.blob_output(
    arg_name="outputblob",
    path="output-files/{name}.json",
    connection="AzureWebJobsStorage"
)
def process_esg_excel(inputblob: func.InputStream, outputblob: func.Out[str]) -> None:
    """
    Azure Function triggered by blob upload to process ESG Excel files.
    
    Args:
        inputblob: Input Excel file from blob storage
        outputblob: Output JSON file to blob storage
    """
    # Create correlation ID for tracking
    import uuid
    correlation_id = str(uuid.uuid4())
    
    logging.info(f"[{correlation_id}] Processing ESG Excel file: {inputblob.name}")
    logging.info(f"[{correlation_id}] File size: {inputblob.length} bytes")
    
    # Initialize error output
    error_output = {
        "status": "error",
        "filename": inputblob.name,
        "correlation_id": correlation_id,
        "error": None,
        "details": None
    }
    
    try:
        # Get analyzer instances
        doc_analyzer, data_processor = get_analyzers()
        
        # Read the Excel file content
        excel_content = inputblob.read()
        
        # Analyze document with Azure AI Document Intelligence
        extracted_data = doc_analyzer.analyze_excel(
            excel_content, 
            inputblob.name
        )
        
        # Log extraction metrics
        logging.info(f"[{correlation_id}] Extraction complete. "
                    f"Tables: {len(extracted_data.get('tables', []))}, "
                    f"KV Pairs: {len(extracted_data.get('key_value_pairs', []))}")
        
        # Process and structure ESG data
        esg_data = data_processor.process_esg_data(extracted_data)
        
        # Add processing metadata
        esg_data["processing_metadata"] = {
            "correlation_id": correlation_id,
            "status": "success",
            "file_size_bytes": inputblob.length,
            "processing_timestamp": extracted_data.get("analysis_timestamp"),
            "document_intelligence_metadata": extracted_data.get("metadata", {})
        }
        
        # Convert to JSON and save
        output_json = json.dumps(esg_data, indent=2, ensure_ascii=False)
        outputblob.set(output_json)
        
        logging.info(f"[{correlation_id}] Successfully processed {inputblob.name}. "
                    f"Found {len(esg_data.get('metrics', []))} ESG metrics")
        
    except ValueError as ve:
        # Validation errors
        error_output["error"] = "Validation Error"
        error_output["details"] = str(ve)
        logging.error(f"[{correlation_id}] Validation error: {str(ve)}")
        outputblob.set(json.dumps(error_output, indent=2))
        
    except Exception as e:
        # Unexpected errors
        error_output["error"] = type(e).__name__
        error_output["details"] = str(e)
        error_output["traceback"] = traceback.format_exc()
        
        logging.error(f"[{correlation_id}] Error processing file {inputblob.name}: {str(e)}")
        logging.error(f"[{correlation_id}] Traceback: {traceback.format_exc()}")
        
        # Save error output
        outputblob.set(json.dumps(error_output, indent=2))
        
        # Re-raise to mark function execution as failed
        raise

## File: test_esg_processor.py
```python
import unittest
from unittest.mock import Mock, patch, MagicMock
import json
from utils.data_processor import ESGDataProcessor
from models.esg_models import ESGMetric

class TestESGDataProcessor(unittest.TestCase):
    """Unit tests for ESG data processor."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.processor = ESGDataProcessor()
    
    def test_categorize_text_environmental(self):
        """Test environmental category detection."""
        test_cases = [
            "Carbon emissions",
            "GHG reduction",
            "Renewable energy usage",
            "Water consumption"
        ]
        
        for text in test_cases:
            category = self.processor._categorize_text(text)
            self.assertEqual(category, "environmental", f"Failed to categorize '{text}'")
    
    def test_categorize_text_social(self):
        """Test social category detection."""
        test_cases = [
            "Employee diversity",
            "Workplace safety",
            "Community engagement",
            "Customer privacy"
        ]
        
        for text in test_cases:
            category = self.processor._categorize_text(text)
            self.assertEqual(category, "social", f"Failed to categorize '{text}'")
    
    def test_parse_value(self):
        """Test value parsing."""
        test_cases = [
            ("123.45", (123.45, None)),
            ("1,234.56 kg", (1234.56, "kg")),
            ("45%", (45.0, "%")),
            ("invalid", None)
        ]
        
        for input_val, expected in test_cases:
            result = self.processor._parse_value(input_val)
            self.assertEqual(result, expected, f"Failed to parse '{input_val}'")
    
    def test_extract_metrics_from_table(self):
        """Test metric extraction from table data."""
        table = {
            "cells": [
                {"row_index": 0, "column_index": 0, "content": "Metric"},
                {"row_index": 0, "column_index": 1, "content": "Value"},
                {"row_index": 1, "column_index": 0, "content": "Carbon Emissions"},
                {"row_index": 1, "column_index": 1, "content": "1,234 tons"}
            ]
        }
        
        metrics = self.processor._extract_metrics_from_table(table, 0)
        
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].category, "environmental")
        self.assertEqual(metrics[0].metric_name, "Carbon Emissions")
        self.assertEqual(metrics[0].value, 1234.0)
        self.assertEqual(metrics[0].unit, "tons")

class TestDocumentAnalyzer(unittest.TestCase):
    """Unit tests for document analyzer."""
    
    @patch.dict(os.environ, {
        "DOCUMENTINTELLIGENCE_ENDPOINT": "https://test.cognitiveservices.azure.com/",
        "DOCUMENTINTELLIGENCE_API_KEY": "test-key"
    })
    def test_validate_file(self):
        """Test file validation."""
        from utils.document_analyzer_improved import DocumentAnalyzerImproved
        
        analyzer = DocumentAnalyzerImproved(use_managed_identity=False)
        
        # Test valid file
        valid_content = b"x" * (1024 * 1024)  # 1MB
        analyzer.validate_file(valid_content, "test.xlsx")
        
        # Test invalid size
        invalid_content = b"x" * (51 * 1024 * 1024)  # 51MB
        with self.assertRaises(ValueError):
            analyzer.validate_file(invalid_content, "test.xlsx")
        
        # Test invalid extension
        with self.assertRaises(ValueError):
            analyzer.validate_file(valid_content, "test.pdf")

if __name__ == "__main__":
    unittest.main()

## File: README.md
```markdown
# ESG Excel Analyzer Azure Function

This Azure Function automatically processes ESG (Environmental, Social, Governance) Excel files using Azure AI Document Intelligence and outputs structured JSON data.

## Features

- **Automatic Processing**: Triggered by Excel file uploads to Azure Blob Storage
- **AI-Powered Extraction**: Uses Azure AI Document Intelligence for accurate data extraction
- **ESG Metric Detection**: Automatically identifies and categorizes ESG metrics
- **Error Handling**: Comprehensive error handling with retry logic
- **Production Ready**: Supports managed identity authentication
- **Scalable**: Runs on Azure Functions consumption plan

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌────────────────────┐
│  Excel Upload   │────▶│  Blob Trigger    │────▶│ Document Intelligence│
│ (input-files)   │     │ Azure Function   │     │    Analysis         │
└─────────────────┘     └──────────────────┘     └────────────────────┘
                                 │                          │
                                 │                          ▼
                        ┌────────▼─────────┐     ┌────────────────────┐
                        │  JSON Output     │◀────│  ESG Processing    │
                        │ (output-files)   │     │  & Structuring     │
                        └──────────────────┘     └────────────────────┘
```

## Local Development

### Prerequisites

- Python 3.9+
- Azure Functions Core Tools v4
- Azurite (Storage Emulator)
- Visual Studio Code (recommended)

### Setup

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure local settings:
   - Copy `local.settings.json.example` to `local.settings.json`
   - Add your Document Intelligence endpoint and key

5. Start Azurite:
   ```bash
   azurite --silent --location c:\azurite --debug c:\azurite\debug.log
   ```

6. Run the function:
   ```bash
   func start
   ```

## Testing

Run unit tests:
```bash
python -m pytest test_esg_processor.py -v
```

## Deployment

See the deployment instructions in the main artifact for detailed Azure deployment steps.

## Configuration

### Environment Variables

- `DOCUMENTINTELLIGENCE_ENDPOINT`: Document Intelligence service endpoint
- `DOCUMENTINTELLIGENCE_API_KEY`: API key (for development)
- `USE_MANAGED_IDENTITY`: Set to "true" for production
- `AzureWebJobsStorage`: Storage account connection string

### Function Settings

- Maximum file size: 50MB
- Timeout: 10 minutes
- Retry attempts: 3 with exponential backoff

## Output Format

The function outputs JSON files with the following structure:

```json
{
  "filename": "esg_report_2024.xlsx",
  "extraction_date": "2024-06-14T10:30:00Z",
  "metrics": [
    {
      "category": "environmental",
      "metric_name": "Carbon Emissions",
      "value": 1234.5,
      "unit": "tons",
      "confidence": 0.95
    }
  ],
  "summary": {
    "total_metrics": 25,
    "metrics_by_category": {
      "environmental": 10,
      "social": 8,
      "governance": 7
    },
    "average_confidence": 0.87
  },
  "processing_metadata": {
    "correlation_id": "uuid",
    "status": "success",
    "processing_timestamp": 1718361000
  }
}
```

## Monitoring

- Enable Application Insights for production monitoring
- Check function logs in Azure Portal
- Use correlation IDs to track processing

## Security Best Practices

1. Use Managed Identity in production
2. Enable network restrictions on storage accounts
3. Implement API rate limiting
4. Regular security audits
5. Keep dependencies updated

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## License

MIT License - see LICENSE file for details
```