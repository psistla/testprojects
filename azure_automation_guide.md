# Azure Automated Excel to JSON Processing Pipeline

## Architecture Overview

This solution uses Azure Functions with Blob Storage triggers to automatically process Excel files uploaded to a container, extract content using Azure Document Intelligence OCR, and save the results as JSON files.

## Required Azure Services

1. **Azure Storage Account** (2 containers)
   - Source container: `excel-input`
   - Destination container: `json-output`

2. **Azure Functions** (Consumption or Premium plan)
   - Runtime: Python 3.9+ or C#
   - Trigger: Blob Storage trigger

3. **Azure Document Intelligence** (Form Recognizer)
   - Used for OCR processing of Excel content

4. **Azure Key Vault** (recommended)
   - Store connection strings and API keys securely

## Implementation Steps

### Step 1: Create Azure Resources

```bash
# Create Resource Group
az group create --name rg-excel-processor --location eastus

# Create Storage Account
az storage account create \
  --name stexcelprocessor \
  --resource-group rg-excel-processor \
  --location eastus \
  --sku Standard_LRS

# Create containers
az storage container create --name excel-input --account-name stexcelprocessor
az storage container create --name json-output --account-name stexcelprocessor

# Create Document Intelligence resource
az cognitiveservices account create \
  --name doc-intelligence-processor \
  --resource-group rg-excel-processor \
  --kind FormRecognizer \
  --sku S0 \
  --location eastus

# Create Function App
az functionapp create \
  --resource-group rg-excel-processor \
  --consumption-plan-location eastus \
  --runtime python \
  --runtime-version 3.9 \
  --functions-version 4 \
  --name func-excel-processor \
  --storage-account stexcelprocessor
```

### Step 2: Python Function Implementation

Create the following files in your Function App:

**requirements.txt**
```text
azure-functions
azure-storage-blob
azure-ai-formrecognizer
azure-identity
openpyxl
pandas
```

**function_app.py**
```python
import azure.functions as func
import logging
import json
import io
from azure.storage.blob import BlobServiceClient
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
import pandas as pd
import openpyxl
from datetime import datetime
import os

app = func.FunctionApp()

# Configuration
STORAGE_CONNECTION_STRING = os.getenv("AzureWebJobsStorage")
DOC_INTELLIGENCE_ENDPOINT = os.getenv("DOC_INTELLIGENCE_ENDPOINT")
DOC_INTELLIGENCE_KEY = os.getenv("DOC_INTELLIGENCE_KEY")
OUTPUT_CONTAINER = "json-output"

@app.blob_trigger(
    arg_name="myblob", 
    path="excel-input/{name}",
    connection="AzureWebJobsStorage"
)
def excel_processor(myblob: func.InputStream):
    logging.info(f"Processing blob: {myblob.name}")
    
    try:
        # Initialize clients
        blob_service_client = BlobServiceClient.from_connection_string(STORAGE_CONNECTION_STRING)
        doc_client = DocumentAnalysisClient(
            endpoint=DOC_INTELLIGENCE_ENDPOINT,
            credential=AzureKeyCredential(DOC_INTELLIGENCE_KEY)
        )
        
        # Read Excel file
        excel_data = myblob.read()
        
        # Process Excel file with pandas for structured data
        excel_content = process_excel_with_pandas(excel_data)
        
        # Also process with Document Intelligence for OCR (useful for images/charts in Excel)
        ocr_content = process_with_document_intelligence(doc_client, excel_data)
        
        # Combine results
        final_result = {
            "metadata": {
                "source_file": myblob.name,
                "processed_timestamp": datetime.utcnow().isoformat(),
                "processing_method": "hybrid_excel_ocr"
            },
            "structured_data": excel_content,
            "ocr_data": ocr_content
        }
        
        # Save to output container
        output_filename = f"{myblob.name.split('.')[0]}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        save_json_to_blob(blob_service_client, final_result, output_filename)
        
        logging.info(f"Successfully processed {myblob.name} -> {output_filename}")
        
    except Exception as e:
        logging.error(f"Error processing {myblob.name}: {str(e)}")
        raise

def process_excel_with_pandas(excel_data):
    """Process Excel file using pandas for structured data extraction"""
    try:
        excel_file = io.BytesIO(excel_data)
        
        # Read all sheets
        sheets_data = {}
        with pd.ExcelFile(excel_file) as xls:
            for sheet_name in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet_name)
                # Convert DataFrame to dict, handling NaN values
                sheets_data[sheet_name] = df.fillna("").to_dict(orient='records')
        
        return sheets_data
        
    except Exception as e:
        logging.error(f"Error processing Excel with pandas: {str(e)}")
        return {"error": str(e)}

def process_with_document_intelligence(doc_client, file_data):
    """Process file with Azure Document Intelligence for OCR"""
    try:
        # Analyze document
        poller = doc_client.begin_analyze_document(
            "prebuilt-layout", 
            document=io.BytesIO(file_data)
        )
        result = poller.result()
        
        # Extract content
        ocr_result = {
            "pages": [],
            "tables": [],
            "key_value_pairs": []
        }
        
        # Extract pages and content
        for page in result.pages:
            page_data = {
                "page_number": page.page_number,
                "lines": [line.content for line in page.lines] if page.lines else [],
                "words": [{"content": word.content, "confidence": word.confidence} 
                         for word in page.words] if page.words else []
            }
            ocr_result["pages"].append(page_data)
        
        # Extract tables
        for table in result.tables:
            table_data = {
                "row_count": table.row_count,
                "column_count": table.column_count,
                "cells": []
            }
            for cell in table.cells:
                cell_data = {
                    "content": cell.content,
                    "row_index": cell.row_index,
                    "column_index": cell.column_index,
                    "confidence": cell.confidence
                }
                table_data["cells"].append(cell_data)
            ocr_result["tables"].append(table_data)
        
        # Extract key-value pairs
        for kv_pair in result.key_value_pairs or []:
            if kv_pair.key and kv_pair.value:
                ocr_result["key_value_pairs"].append({
                    "key": kv_pair.key.content,
                    "value": kv_pair.value.content,
                    "confidence": kv_pair.confidence
                })
        
        return ocr_result
        
    except Exception as e:
        logging.error(f"Error with Document Intelligence: {str(e)}")
        return {"error": str(e)}

def save_json_to_blob(blob_service_client, data, filename):
    """Save JSON data to blob storage"""
    try:
        blob_client = blob_service_client.get_blob_client(
            container=OUTPUT_CONTAINER,
            blob=filename
        )
        
        json_string = json.dumps(data, indent=2, ensure_ascii=False)
        blob_client.upload_blob(json_string, overwrite=True)
        
    except Exception as e:
        logging.error(f"Error saving to blob: {str(e)}")
        raise
```

### Step 3: Configuration Settings

Add these application settings to your Function App:

```bash
# Set Function App settings
az functionapp config appsettings set \
  --name func-excel-processor \
  --resource-group rg-excel-processor \
  --settings "DOC_INTELLIGENCE_ENDPOINT=https://doc-intelligence-processor.cognitiveservices.azure.com/"

az functionapp config appsettings set \
  --name func-excel-processor \
  --resource-group rg-excel-processor \
  --settings "DOC_INTELLIGENCE_KEY=your_document_intelligence_key"
```

### Step 4: Alternative C# Implementation

If you prefer C#, here's the key function:

```csharp
[FunctionName("ExcelProcessor")]
public static async Task Run(
    [BlobTrigger("excel-input/{name}", Connection = "AzureWebJobsStorage")] Stream myBlob,
    string name,
    ILogger log)
{
    try
    {
        log.LogInformation($"Processing blob: {name}");
        
        // Initialize clients
        var blobClient = new BlobServiceClient(Environment.GetEnvironmentVariable("AzureWebJobsStorage"));
        var docClient = new DocumentAnalysisClient(
            new Uri(Environment.GetEnvironmentVariable("DOC_INTELLIGENCE_ENDPOINT")),
            new AzureKeyCredential(Environment.GetEnvironmentVariable("DOC_INTELLIGENCE_KEY"))
        );
        
        // Process Excel and OCR
        var result = await ProcessExcelFile(myBlob, docClient, name);
        
        // Save result
        await SaveJsonResult(blobClient, result, name);
        
        log.LogInformation($"Successfully processed {name}");
    }
    catch (Exception ex)
    {
        log.LogError($"Error processing {name}: {ex.Message}");
        throw;
    }
}
```

## Deployment Options

### Option 1: Azure CLI Deployment
```bash
func azure functionapp publish func-excel-processor --python
```

### Option 2: GitHub Actions CI/CD
Create `.github/workflows/deploy.yml` for automated deployment.

### Option 3: Visual Studio Code
Use Azure Functions extension for local development and deployment.

## Monitoring and Troubleshooting

1. **Application Insights**: Enable for detailed logging and monitoring
2. **Storage Account Monitoring**: Track blob operations
3. **Function App Logs**: Monitor execution and errors
4. **Document Intelligence Usage**: Monitor API calls and costs

## Security Best Practices

1. Use **Managed Identity** instead of connection strings where possible
2. Store secrets in **Azure Key Vault**
3. Implement **RBAC** for blob access
4. Enable **diagnostic logging** for all services
5. Use **private endpoints** for enhanced security

## Cost Optimization

1. Use **Consumption plan** for Functions if processing is infrequent
2. Monitor **Document Intelligence** usage and costs
3. Implement **blob lifecycle policies** for automatic cleanup
4. Consider **batch processing** for high-volume scenarios

## Testing

1. Upload test Excel files to the `excel-input` container
2. Monitor Function execution in Azure portal
3. Check `json-output` container for results
4. Validate JSON structure and content

This solution provides a robust, scalable pipeline for automatically processing Excel files with OCR capabilities and structured data extraction.