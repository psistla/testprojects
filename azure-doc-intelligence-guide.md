# Azure Document Intelligence OCR with Logic Apps - Code Approach

## Overview
This solution uses Azure Logic Apps with inline code functions to leverage the latest Azure AI Document Intelligence OCR/Read operations for processing Excel files.

## Architecture Components

### Required Azure Services
- **Azure Storage Account** - For blob containers
- **Azure Document Intelligence** (Latest version with OCR capabilities)
- **Azure Logic Apps** - With code execution capabilities
- **Azure Key Vault** (Recommended for secrets)

## Step-by-Step Implementation

### Step 1: Set Up Azure Document Intelligence (Latest Version)

```bash
# Create Document Intelligence resource with latest API version
az cognitiveservices account create \
  --name "your-doc-intelligence" \
  --resource-group "your-rg" \
  --kind "FormRecognizer" \
  --sku "S0" \
  --location "eastus" \
  --custom-domain "your-doc-intelligence"
```

**Key Information to Note:**
- Endpoint: `https://your-doc-intelligence.cognitiveservices.azure.com/`
- API Version: `2024-02-29-preview` (Latest with enhanced OCR)
- Subscription Key

### Step 2: Create Storage Account with Containers

```json
{
  "storageAccount": "yourstorageaccount",
  "containers": [
    {
      "name": "excel-input",
      "access": "private"
    },
    {
      "name": "json-output", 
      "access": "private"
    },
    {
      "name": "processing-logs",
      "access": "private"
    }
  ]
}
```

### Step 3: Logic App Workflow with Code Components

#### Trigger Configuration
```json
{
  "type": "ApiConnection",
  "inputs": {
    "host": {
      "connection": {
        "name": "@parameters('$connections')['azureblob']['connectionId']"
      }
    },
    "method": "get",
    "path": "/v2/datasets/@{encodeURIComponent('yourstorageaccount')}/triggers/batch/onupdatedfile",
    "queries": {
      "folderId": "L2V4Y2VsLWlucHV0",
      "maxFileCount": 1,
      "checkBothCreatedAndModifiedDateTime": false
    }
  },
  "recurrence": {
    "frequency": "Minute",
    "interval": 2
  }
}
```

#### Action 1: Initialize Variables (Code Function)
```javascript
// JavaScript code for Logic App inline function
const initializeProcessing = () => {
    const timestamp = new Date().toISOString();
    const processId = `proc_${timestamp.replace(/[:.]/g, '_')}`;
    
    return {
        processId: processId,
        timestamp: timestamp,
        status: 'initialized',
        apiVersion: '2024-02-29-preview'
    };
};

// Return the result
return initializeProcessing();
```

#### Action 2: Get File Content and Prepare for OCR
```javascript
// JavaScript code to prepare file for Document Intelligence
const prepareFileForOCR = (fileContent, fileName) => {
    // Validate file type
    const supportedExtensions = ['.xlsx', '.xls', '.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.bmp'];
    const fileExtension = fileName.toLowerCase().substring(fileName.lastIndexOf('.'));
    
    if (!supportedExtensions.includes(fileExtension)) {
        throw new Error(`Unsupported file type: ${fileExtension}`);
    }
    
    // Prepare headers for Document Intelligence API
    const headers = {
        'Content-Type': 'application/octet-stream',
        'Ocp-Apim-Subscription-Key': '@parameters(\'docIntelligenceKey\')',
        'User-Agent': 'LogicApp-DocumentIntelligence/1.0'
    };
    
    // Prepare request body
    return {
        headers: headers,
        body: fileContent,
        fileName: fileName,
        fileSize: fileContent.length || 0
    };
};

// Execute the function
const fileData = workflowContext.trigger.outputs.body;
const fileName = workflowContext.trigger.outputs.headers['x-ms-file-name'];
return prepareFileForOCR(fileData, fileName);
```

#### Action 3: Submit to Document Intelligence OCR
```json
{
  "type": "Http",
  "inputs": {
    "method": "POST",
    "uri": "https://your-doc-intelligence.cognitiveservices.azure.com/documentintelligence/documentModels/prebuilt-read:analyze?api-version=2024-02-29-preview&features=ocrHighResolution,languages&pages=1-10",
    "headers": {
      "Content-Type": "application/octet-stream",
      "Ocp-Apim-Subscription-Key": "@parameters('docIntelligenceKey')",
      "User-Agent": "LogicApp-Enhanced-OCR/1.0"
    },
    "body": "@outputs('Get_blob_content_using_path')?['body']"
  }
}
```

#### Action 4: Enhanced Polling Logic (Code Function)
```javascript
// Advanced polling function for Document Intelligence
const pollDocumentAnalysis = async (operationLocation, subscriptionKey) => {
    const maxRetries = 30; // 5 minutes max wait time
    const pollInterval = 10000; // 10 seconds
    
    for (let attempt = 0; attempt < maxRetries; attempt++) {
        try {
            const response = await fetch(operationLocation, {
                method: 'GET',
                headers: {
                    'Ocp-Apim-Subscription-Key': subscriptionKey,
                    'User-Agent': 'LogicApp-Enhanced-OCR/1.0'
                }
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const result = await response.json();
            
            // Check status
            if (result.status === 'succeeded') {
                return {
                    success: true,
                    data: result,
                    attempts: attempt + 1,
                    processingTime: (attempt + 1) * pollInterval / 1000
                };
            } else if (result.status === 'failed') {
                throw new Error(`Document analysis failed: ${result.error?.message || 'Unknown error'}`);
            }
            
            // Still running, wait before next attempt
            if (attempt < maxRetries - 1) {
                await new Promise(resolve => setTimeout(resolve, pollInterval));
            }
            
        } catch (error) {
            if (attempt === maxRetries - 1) {
                throw error;
            }
            await new Promise(resolve => setTimeout(resolve, pollInterval));
        }
    }
    
    throw new Error('Document analysis timed out after maximum retries');
};

// Execute polling
const operationLocation = workflowContext.actions['Submit_to_Document_Intelligence'].outputs.headers['Operation-Location'];
const subscriptionKey = '@parameters(\'docIntelligenceKey\')';
return pollDocumentAnalysis(operationLocation, subscriptionKey);
```

#### Action 5: Process OCR Results (Code Function)
```javascript
// Enhanced OCR result processing
const processOCRResults = (analysisResult, originalFileName) => {
    const result = analysisResult.data.analyzeResult;
    
    // Extract comprehensive data
    const processedData = {
        metadata: {
            fileName: originalFileName,
            processedAt: new Date().toISOString(),
            modelVersion: result.modelVersion,
            apiVersion: result.apiVersion,
            totalPages: result.pages?.length || 0
        },
        content: {
            fullText: result.content || '',
            pages: [],
            tables: [],
            keyValuePairs: [],
            entities: []
        },
        statistics: {
            characterCount: (result.content || '').length,
            wordCount: (result.content || '').split(/\s+/).filter(word => word.length > 0).length,
            confidence: 0
        }
    };
    
    // Process pages with enhanced OCR data
    if (result.pages) {
        result.pages.forEach((page, pageIndex) => {
            const pageData = {
                pageNumber: page.pageNumber,
                dimensions: {
                    width: page.width,
                    height: page.height,
                    unit: page.unit
                },
                angle: page.angle,
                words: [],
                lines: [],
                selectionMarks: page.selectionMarks || []
            };
            
            // Extract words with bounding boxes and confidence
            if (page.words) {
                pageData.words = page.words.map(word => ({
                    text: word.content,
                    confidence: word.confidence,
                    boundingBox: word.polygon,
                    span: word.span
                }));
            }
            
            // Extract lines
            if (page.lines) {
                pageData.lines = page.lines.map(line => ({
                    text: line.content,
                    boundingBox: line.polygon,
                    words: line.words || []
                }));
            }
            
            processedData.content.pages.push(pageData);
        });
    }
    
    // Process tables (for Excel files)
    if (result.tables) {
        result.tables.forEach(table => {
            const tableData = {
                rowCount: table.rowCount,
                columnCount: table.columnCount,
                cells: table.cells.map(cell => ({
                    content: cell.content,
                    rowIndex: cell.rowIndex,
                    columnIndex: cell.columnIndex,
                    rowSpan: cell.rowSpan || 1,
                    columnSpan: cell.columnSpan || 1,
                    confidence: cell.confidence,
                    isHeader: cell.kind === 'columnHeader' || cell.kind === 'rowHeader'
                }))
            };
            processedData.content.tables.push(tableData);
        });
    }
    
    // Process key-value pairs
    if (result.keyValuePairs) {
        processedData.content.keyValuePairs = result.keyValuePairs.map(kvp => ({
            key: kvp.key?.content || '',
            value: kvp.value?.content || '',
            confidence: kvp.confidence
        }));
    }
    
    // Calculate average confidence
    const confidenceValues = [];
    processedData.content.pages.forEach(page => {
        page.words.forEach(word => {
            if (word.confidence) confidenceValues.push(word.confidence);
        });
    });
    
    if (confidenceValues.length > 0) {
        processedData.statistics.confidence = confidenceValues.reduce((a, b) => a + b, 0) / confidenceValues.length;
    }
    
    return processedData;
};

// Execute processing
const analysisResult = workflowContext.actions['Poll_Document_Analysis'].outputs.body;
const fileName = workflowContext.trigger.outputs.headers['x-ms-file-name'];
return processOCRResults(analysisResult, fileName);
```

#### Action 6: Save Enhanced JSON Output
```javascript
// Generate comprehensive output file
const generateOutputFile = (processedData, processId) => {
    const outputFileName = `${processId}_${processedData.metadata.fileName.replace(/\.[^/.]+$/, '')}_ocr_result.json`;
    
    // Create enhanced output structure
    const output = {
        ...processedData,
        processing: {
            processId: processId,
            version: '2.0',
            capabilities: [
                'OCR_HIGH_RESOLUTION',
                'TABLE_EXTRACTION', 
                'KEY_VALUE_PAIRS',
                'MULTI_LANGUAGE_SUPPORT',
                'BOUNDING_BOXES',
                'CONFIDENCE_SCORES'
            ]
        }
    };
    
    return {
        fileName: outputFileName,
        content: JSON.stringify(output, null, 2),
        contentType: 'application/json'
    };
};

// Execute
const processedData = workflowContext.actions['Process_OCR_Results'].outputs.body;
const processId = workflowContext.actions['Initialize_Variables'].outputs.body.processId;
return generateOutputFile(processedData, processId);
```

### Step 4: Error Handling and Logging

#### Error Handler Configuration
```json
{
  "type": "Scope",
  "actions": {
    "Log_Error": {
      "type": "Function",
      "inputs": {
        "code": "const logError = (error, context) => { return { timestamp: new Date().toISOString(), error: error.message, context: context, severity: 'ERROR' }; }; return logError(workflowContext.error, workflowContext.instanceId);"
      }
    },
    "Save_Error_Log": {
      "type": "ApiConnection",
      "inputs": {
        "host": {
          "connection": {
            "name": "@parameters('$connections')['azureblob']['connectionId']"
          }
        },
        "method": "post",
        "path": "/v2/datasets/@{encodeURIComponent('yourstorageaccount')}/files",
        "queries": {
          "folderPath": "/processing-logs",
          "name": "@{concat('error_', utcNow(), '.json')}"
        },
        "body": "@outputs('Log_Error')"
      }
    }
  },
  "runAfter": {
    "Main_Processing": [
      "Failed",
      "Skipped",
      "TimedOut"
    ]
  }
}
```

## API Features Used

### Latest Document Intelligence Capabilities
- **OCR High Resolution**: Enhanced text recognition
- **Multiple Language Support**: Automatic language detection
- **Table Structure Recognition**: Advanced table parsing
- **Key-Value Pair Extraction**: Form field detection
- **Bounding Box Coordinates**: Precise text location
- **Confidence Scores**: Quality metrics for each element

### Enhanced Parameters
```
?api-version=2024-02-29-preview
&features=ocrHighResolution,languages,keyValuePairs
&pages=1-10
&locale=auto
```

## Deployment Script

```bash
#!/bin/bash
# Deploy the complete solution

# Variables
RESOURCE_GROUP="doc-intelligence-rg"
LOCATION="eastus"
STORAGE_ACCOUNT="yourstorageaccount"
DOC_INTELLIGENCE="your-doc-intelligence"
LOGIC_APP="excel-ocr-processor"

# Create resource group
az group create --name $RESOURCE_GROUP --location $LOCATION

# Create storage account
az storage account create \
  --name $STORAGE_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku Standard_LRS

# Create Document Intelligence
az cognitiveservices account create \
  --name $DOC_INTELLIGENCE \
  --resource-group $RESOURCE_GROUP \
  --kind FormRecognizer \
  --sku S0 \
  --location $LOCATION

# Create containers
az storage container create --name excel-input --account-name $STORAGE_ACCOUNT
az storage container create --name json-output --account-name $STORAGE_ACCOUNT  
az storage container create --name processing-logs --account-name $STORAGE_ACCOUNT

# Create Logic App
az logic workflow create \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --name $LOGIC_APP
```

## Monitoring and Optimization

### Performance Metrics to Track
- Processing time per file
- OCR accuracy (confidence scores)
- API response times
- Error rates
- Storage costs

### Optimization Tips
1. **File Preprocessing**: Optimize image quality before OCR
2. **Batch Processing**: Process multiple files together
3. **Caching**: Store frequently accessed results
4. **Parallel Processing**: Use multiple Logic App instances
5. **Cost Management**: Monitor API usage and storage costs

## Security Considerations

### Best Practices
- Store API keys in Azure Key Vault
- Use Managed Identity for authentication
- Implement IP restrictions
- Enable diagnostic logging
- Regular key rotation
- Data encryption at rest and in transit

This enhanced approach provides production-ready OCR processing with the latest Azure AI Document Intelligence capabilities, comprehensive error handling, and detailed logging for enterprise use.