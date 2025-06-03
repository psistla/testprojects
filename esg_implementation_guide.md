# ESG Platform - Step-by-Step Implementation Guide

## Prerequisites

Before starting, ensure you have:
- Azure subscription with appropriate permissions
- Python 3.9+ installed
- Azure CLI installed
- Git installed
- Code editor (VS Code recommended)

## Step 1: Azure Environment Setup

### 1.1 Login to Azure and Set Subscription

```bash
# Login to Azure
az login

# List available subscriptions
az account list --output table

# Set your subscription (replace with your subscription ID)
az account set --subscription "your-subscription-id"

# Verify current subscription
az account show
```

### 1.2 Create Resource Group

```bash
# Create resource group
az group create \
    --name rg-esg-poc \
    --location eastus

# Verify creation
az group show --name rg-esg-poc
```

### 1.3 Create Storage Account

```bash
# Create storage account (name must be globally unique)
az storage account create \
    --name stesgstorage$(date +%s) \
    --resource-group rg-esg-poc \
    --location eastus \
    --sku Standard_LRS \
    --kind StorageV2

# Get storage account name (if you used timestamp)
STORAGE_NAME=$(az storage account list --resource-group rg-esg-poc --query "[0].name" -o tsv)
echo "Storage account name: $STORAGE_NAME"

# Create container for file uploads
az storage container create \
    --name esg-uploads \
    --account-name $STORAGE_NAME \
    --auth-mode login

# Get connection string
az storage account show-connection-string \
    --name $STORAGE_NAME \
    --resource-group rg-esg-poc \
    --output tsv
```

### 1.4 Create Document Intelligence Service

```bash
# Create Document Intelligence resource
az cognitiveservices account create \
    --name esg-doc-intelligence \
    --resource-group rg-esg-poc \
    --kind FormRecognizer \
    --sku S0 \
    --location eastus \
    --yes

# Get endpoint and key
az cognitiveservices account show \
    --name esg-doc-intelligence \
    --resource-group rg-esg-poc \
    --query "properties.endpoint" -o tsv

az cognitiveservices account keys list \
    --name esg-doc-intelligence \
    --resource-group rg-esg-poc
```

### 1.5 Set Up AI Foundry Workspace

```bash
# Install Azure ML extension
az extension add -n ml

# Create AI Foundry workspace
az ml workspace create \
    --name ws-esg-analysis \
    --resource-group rg-esg-poc \
    --location eastus

# Create compute instance for development
az ml compute create \
    --name esg-compute \
    --type ComputeInstance \
    --size Standard_DS3_v2 \
    --workspace-name ws-esg-analysis \
    --resource-group rg-esg-poc
```

## Step 2: Local Development Environment Setup

### 2.1 Create Project Directory

```bash
# Create project directory
mkdir esg-analysis-platform
cd esg-analysis-platform

# Initialize git repository
git init

# Create directory structure
mkdir -p src/{api,processors,analyzers,generators,tests,config}
mkdir -p data/{input,output,temp}
mkdir -p docs
mkdir -p deployment/{docker,azure}
```

### 2.2 Set Up Python Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip
```

### 2.3 Create Requirements File

```bash
# Create requirements.txt
cat > requirements.txt << EOF
flask==2.3.3
flask-cors==4.0.0
azure-storage-blob==12.17.0
azure-ai-formrecognizer==3.3.0
azure-identity==1.14.0
azure-ai-ml==1.9.0
pandas==2.0.3
openpyxl==3.1.2
python-docx==0.8.11
reportlab==4.0.4
python-dotenv==1.0.0
requests==2.31.0
numpy==1.24.3
pytest==7.4.2
pytest-mock==3.11.1
gunicorn==21.2.0
werkzeug==2.3.7
azure-monitor-opentelemetry==1.0.0
opentelemetry-api==1.20.0
opentelemetry-sdk==1.20.0
EOF

# Install packages
pip install -r requirements.txt
```

### 2.4 Create Environment Configuration

```bash
# Create .env file
cat > .env << EOF
# Azure Storage
AZURE_STORAGE_CONNECTION_STRING=your_storage_connection_string_here
AZURE_STORAGE_CONTAINER=esg-uploads

# Document Intelligence
AZURE_DOC_INTELLIGENCE_ENDPOINT=your_doc_intelligence_endpoint_here
AZURE_DOC_INTELLIGENCE_KEY=your_doc_intelligence_key_here

# AI Foundry
AI_FOUNDRY_ENDPOINT=your_ai_foundry_endpoint_here
AI_FOUNDRY_KEY=your_ai_foundry_key_here
AI_FOUNDRY_MODEL=gpt-4

# Application
SECRET_KEY=your-secret-key-here
FLASK_ENV=development
FLASK_DEBUG=True

# Logging
LOG_LEVEL=INFO
APPLICATIONINSIGHTS_CONNECTION_STRING=your_app_insights_connection_string_here
EOF

# Create .env.example for reference
cp .env .env.example
```

## Step 3: Implement Core Components

### 3.1 Create Configuration Module

```bash
# Create src/config/config.py
cat > src/config/config.py << 'EOF'
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Azure Storage
    AZURE_STORAGE_CONNECTION_STRING = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
    AZURE_STORAGE_CONTAINER = os.getenv('AZURE_STORAGE_CONTAINER', 'esg-uploads')
    
    # Document Intelligence
    AZURE_DOC_INTELLIGENCE_ENDPOINT = os.getenv('AZURE_DOC_INTELLIGENCE_ENDPOINT')
    AZURE_DOC_INTELLIGENCE_KEY = os.getenv('AZURE_DOC_INTELLIGENCE_KEY')
    
    # AI Foundry
    AI_FOUNDRY_ENDPOINT = os.getenv('AI_FOUNDRY_ENDPOINT')
    AI_FOUNDRY_KEY = os.getenv('AI_FOUNDRY_KEY')
    AI_FOUNDRY_MODEL = os.getenv('AI_FOUNDRY_MODEL', 'gpt-4')
    
    # Application
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    APPLICATIONINSIGHTS_CONNECTION_STRING = os.getenv('APPLICATIONINSIGHTS_CONNECTION_STRING')

class DevelopmentConfig(Config):
    DEBUG = True
    FLASK_ENV = 'development'

class ProductionConfig(Config):
    DEBUG = False
    FLASK_ENV = 'production'

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
EOF
```

### 3.2 Create ESG Master Prompt File

```bash
# Create src/config/esg_master_prompt.txt
cat > src/config/esg_master_prompt.txt << 'EOF'
# ESG Data Analysis Master Prompt

You are an expert ESG (Environmental, Social, Governance) analyst with deep expertise in sustainability reporting, regulatory frameworks, and data interpretation. Your task is to analyze ESG-related data from Excel spreadsheets and provide comprehensive insights.

## Core Analysis Framework

When analyzing ESG data, systematically evaluate the following dimensions:

### Environmental (E) Metrics
- **Carbon Footprint**: GHG emissions (Scope 1, 2, 3), carbon intensity, reduction targets
- **Energy Management**: Energy consumption, renewable energy usage, energy efficiency improvements
- **Water Usage**: Water consumption, water recycling, wastewater management
- **Waste Management**: Waste generation, recycling rates, circular economy initiatives
- **Biodiversity**: Land use impact, conservation efforts, ecosystem protection
- **Climate Risk**: Physical and transition risks, climate adaptation strategies

### Social (S) Metrics
- **Human Capital**: Employee satisfaction, diversity & inclusion, training hours, retention rates
- **Labor Practices**: Health & safety incidents, labor standards compliance, fair wages
- **Community Impact**: Community investment, local economic development, social programs
- **Product Responsibility**: Product safety, customer satisfaction, ethical marketing
- **Supply Chain**: Supplier assessments, human rights compliance, responsible sourcing
- **Data Privacy**: Cybersecurity measures, data protection, privacy policies

### Governance (G) Metrics
- **Board Composition**: Independence, diversity, expertise, meeting attendance
- **Executive Compensation**: Pay ratios, performance alignment, compensation philosophy
- **Business Ethics**: Code of conduct, anti-corruption measures, whistleblower programs
- **Risk Management**: Risk assessment frameworks, internal controls, audit processes
- **Transparency**: Reporting quality, stakeholder engagement, disclosure practices
- **Regulatory Compliance**: Legal violations, fines, regulatory relationships

## Analysis Instructions

### Step 1: Data Reconnaissance
1. **Identify Data Structure**: Examine sheet names, headers, data types, and time periods
2. **Assess Data Quality**: Note missing values, inconsistencies, and potential errors
3. **Map ESG Categories**: Categorize each metric into E, S, or G pillars
4. **Benchmark Context**: Identify industry, company size, and geographic scope

### Step 2: Quantitative Analysis
1. **Trend Analysis**: Calculate year-over-year changes, growth rates, and trajectories
2. **Performance Ratios**: Compute intensity metrics (per revenue, per employee, per unit)
3. **Target Tracking**: Assess progress against stated ESG goals and commitments
4. **Peer Comparison**: Compare against industry benchmarks where applicable
5. **Statistical Insights**: Identify correlations, outliers, and significant patterns

### Step 3: Qualitative Assessment
1. **Materiality Evaluation**: Assess which metrics are most relevant to the business
2. **Risk Assessment**: Identify potential ESG risks and opportunities
3. **Strategy Alignment**: Evaluate consistency with business strategy and stakeholder expectations
4. **Regulatory Compliance**: Check alignment with relevant frameworks (GRI, SASB, TCFD, etc.)

### Step 4: Actionable Insights
1. **Key Findings**: Summarize the most significant insights in order of importance
2. **Performance Gaps**: Identify areas where performance lags expectations or benchmarks
3. **Improvement Opportunities**: Suggest specific, measurable improvements
4. **Strategic Recommendations**: Provide strategic advice for ESG program enhancement

## Output Format

Structure your analysis as follows:

### Executive Summary
- 3-5 bullet points highlighting the most critical findings
- Overall ESG maturity assessment (Emerging/Developing/Advanced/Leading)

### Performance Overview
**Environmental Performance:**
- Key metrics summary with trend analysis
- Notable achievements and concerns
- Regulatory compliance status

**Social Performance:**
- Workforce and community impact highlights
- Stakeholder engagement effectiveness
- Social risk assessment

**Governance Performance:**
- Leadership and oversight evaluation
- Ethics and transparency assessment
- Risk management effectiveness

### Detailed Findings
For each significant finding:
- **Metric**: Specific data point or trend
- **Context**: Industry comparison or historical performance
- **Implication**: Business or stakeholder impact
- **Recommendation**: Specific action item

### Risk and Opportunity Matrix
- **High Priority**: Critical issues requiring immediate attention
- **Medium Priority**: Important areas for improvement
- **Low Priority**: Minor enhancements or monitoring items

### Implementation Roadmap
- **Short-term (0-6 months)**: Quick wins and urgent fixes
- **Medium-term (6-18 months)**: Strategic initiatives and system improvements
- **Long-term (18+ months)**: Transformational changes and innovation

Please provide a comprehensive analysis following this framework when presented with ESG data.
EOF
```

### 3.3 Create File Processor

```bash
# Create src/processors/file_processor.py
cat > src/processors/file_processor.py << 'EOF'
from azure.storage.blob import BlobServiceClient
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
import pandas as pd
import io
import os
import logging
from typing import Dict, Any, List
from ..config.config import Config

logger = logging.getLogger(__name__)

class ESGFileProcessor:
    def __init__(self):
        self.blob_client = BlobServiceClient.from_connection_string(
            Config.AZURE_STORAGE_CONNECTION_STRING
        )
        self.doc_client = DocumentAnalysisClient(
            endpoint=Config.AZURE_DOC_INTELLIGENCE_ENDPOINT,
            credential=AzureKeyCredential(Config.AZURE_DOC_INTELLIGENCE_KEY)
        )
        self.container_name = Config.AZURE_STORAGE_CONTAINER
        
    def upload_file(self, file_data: bytes, filename: str) -> str:
        """Upload file to Azure Blob Storage"""
        try:
            blob_client = self.blob_client.get_blob_client(
                container=self.container_name, 
                blob=filename
            )
            blob_client.upload_blob(file_data, overwrite=True)
            logger.info(f"File {filename} uploaded successfully")
            return blob_client.url
        except Exception as e:
            logger.error(f"Error uploading file {filename}: {str(e)}")
            raise
    
    def process_excel_file(self, blob_url: str) -> Dict[str, Any]:
        """Process Excel file using Document Intelligence"""
        try:
            poller = self.doc_client.begin_analyze_document_from_url(
                "prebuilt-layout", blob_url
            )
            result = poller.result()
            
            # Extract tables and data
            extracted_data = self._extract_esg_data(result)
            logger.info("Excel file processed successfully")
            return extracted_data
        except Exception as e:
            logger.error(f"Error processing Excel file: {str(e)}")
            raise
    
    def _extract_esg_data(self, analysis_result) -> Dict[str, Any]:
        """Extract and structure ESG data from analysis result"""
        esg_data = {
            'environmental': {},
            'social': {},
            'governance': {},
            'metadata': {
                'total_tables': len(analysis_result.tables),
                'total_pages': len(analysis_result.pages)
            }
        }
        
        # Process tables and extract relevant ESG metrics
        for table_idx, table in enumerate(analysis_result.tables):
            table_data = []
            for cell in table.cells:
                table_data.append({
                    'row': cell.row_index,
                    'column': cell.column_index,
                    'content': cell.content,
                    'confidence': getattr(cell, 'confidence', 0.0)
                })
            
            # Categorize data based on ESG framework
            categorized_data = self._categorize_esg_metrics(table_data, table_idx)
            
            # Merge categorized data
            for category in ['environmental', 'social', 'governance']:
                if category in categorized_data:
                    esg_data[category].update(categorized_data[category])
        
        return esg_data
    
    def _categorize_esg_metrics(self, table_data: List[Dict], table_idx: int) -> Dict[str, Any]:
        """Categorize metrics into ESG pillars"""
        categorized = {
            'environmental': {},
            'social': {},
            'governance': {}
        }
        
        # Define ESG keywords for categorization
        esg_keywords = {
            'environmental': [
                'carbon', 'emission', 'energy', 'water', 'waste', 'renewable',
                'ghg', 'scope', 'climate', 'environmental', 'sustainability',
                'recycling', 'biodiversity', 'pollution'
            ],
            'social': [
                'employee', 'diversity', 'inclusion', 'safety', 'training',
                'community', 'human rights', 'labor', 'health', 'social',
                'workforce', 'supplier', 'customer', 'stakeholder'
            ],
            'governance': [
                'board', 'governance', 'compliance', 'ethics', 'audit',
                'risk', 'transparency', 'executive', 'compensation',
                'regulatory', 'oversight', 'independence'
            ]
        }
        
        # Convert table data to DataFrame for easier processing
        if table_data:
            df_data = []
            for cell in table_data:
                df_data.append({
                    'row': cell['row'],
                    'column': cell['column'],
                    'content': str(cell['content']).lower(),
                    'original_content': cell['content'],
                    'confidence': cell['confidence']
                })
            
            # Group by rows to create metric-value pairs
            rows = {}
            for cell in df_data:
                row_idx = cell['row']
                if row_idx not in rows:
                    rows[row_idx] = []
                rows[row_idx].append(cell)
            
            # Process each row
            for row_idx, row_cells in rows.items():
                if len(row_cells) >= 2:  # Need at least metric name and value
                    metric_name = row_cells[0]['original_content']
                    metric_value = row_cells[1]['original_content']
                    
                    # Categorize based on keywords
                    content_lower = metric_name.lower()
                    for category, keywords in esg_keywords.items():
                        if any(keyword in content_lower for keyword in keywords):
                            categorized[category][f"table_{table_idx}_{metric_name}"] = {
                                'value': metric_value,
                                'confidence': row_cells[0]['confidence']
                            }
                            break
        
        return categorized
    
    def validate_file(self, file_data: bytes, filename: str) -> bool:
        """Validate uploaded file"""
        try:
            # Check file size
            if len(file_data) > Config.MAX_CONTENT_LENGTH:
                raise ValueError("File size exceeds maximum limit")
            
            # Check file extension
            allowed_extensions = ['.xlsx', '.xls']
            if not any(filename.lower().endswith(ext) for ext in allowed_extensions):
                raise ValueError("Invalid file format. Only Excel files are allowed.")
            
            # Try to read as Excel to validate format
            try:
                pd.read_excel(io.BytesIO(file_data))
            except Exception as e:
                raise ValueError(f"Invalid Excel file format: {str(e)}")
            
            return True
        except Exception as e:
            logger.error(f"File validation failed: {str(e)}")
            raise
EOF
```

### 3.4 Update the File Processor with Proper Imports

```bash
# Create src/processors/__init__.py
touch src/processors/__init__.py

# Create src/__init__.py
touch src/__init__.py

# Update the file processor to fix import issues
cat > src/processors/file_processor.py << 'EOF'
from azure.storage.blob import BlobServiceClient
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
import pandas as pd
import io
import os
import logging
from typing import Dict, Any, List
import sys
import os

# Add the src directory to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config import Config

logger = logging.getLogger(__name__)

class ESGFileProcessor:
    def __init__(self):
        self.blob_client = BlobServiceClient.from_connection_string(
            Config.AZURE_STORAGE_CONNECTION_STRING
        )
        self.doc_client = DocumentAnalysisClient(
            endpoint=Config.AZURE_DOC_INTELLIGENCE_ENDPOINT,
            credential=AzureKeyCredential(Config.AZURE_DOC_INTELLIGENCE_KEY)
        )
        self.container_name = Config.AZURE_STORAGE_CONTAINER
        
    def upload_file(self, file_data: bytes, filename: str) -> str:
        """Upload file to Azure Blob Storage"""
        try:
            blob_client = self.blob_client.get_blob_client(
                container=self.container_name, 
                blob=filename
            )
            blob_client.upload_blob(file_data, overwrite=True)
            logger.info(f"File {filename} uploaded successfully")
            return blob_client.url
        except Exception as e:
            logger.error(f"Error uploading file {filename}: {str(e)}")
            raise
    
    def process_excel_file(self, blob_url: str) -> Dict[str, Any]:
        """Process Excel file using Document Intelligence"""
        try:
            poller = self.doc_client.begin_analyze_document_from_url(
                "prebuilt-layout", blob_url
            )
            result = poller.result()
            
            # Extract tables and data
            extracted_data = self._extract_esg_data(result)
            logger.info("Excel file processed successfully")
            return extracted_data
        except Exception as e:
            logger.error(f"Error processing Excel file: {str(e)}")
            raise
    
    def _extract_esg_data(self, analysis_result) -> Dict[str, Any]:
        """Extract and structure ESG data from analysis result"""
        esg_data = {
            'environmental': {},
            'social': {},
            'governance': {},
            'metadata': {
                'total_tables': len(analysis_result.tables),
                'total_pages': len(analysis_result.pages)
            }
        }
        
        # Process tables and extract relevant ESG metrics
        for table_idx, table in enumerate(analysis_result.tables):
            table_data = []
            for cell in table.cells:
                table_data.append({
                    'row': cell.row_index,
                    'column': cell.column_index,
                    'content': cell.content,
                    'confidence': getattr(cell, 'confidence', 0.0)
                })
            
            # Categorize data based on ESG framework
            categorized_data = self._categorize_esg_metrics(table_data, table_idx)
            
            # Merge categorized data
            for category in ['environmental', 'social', 'governance']:
                if category in categorized_data:
                    esg_data[category].update(categorized_data[category])
        
        return esg_data
    
    def _categorize_esg_metrics(self, table_data: List[Dict], table_idx: int) -> Dict[str, Any]:
        """Categorize metrics into ESG pillars"""
        categorized = {
            'environmental': {},
            'social': {},
            'governance': {}
        }
        
        # Define ESG keywords for categorization
        esg_keywords = {
            'environmental': [
                'carbon', 'emission', 'energy', 'water', 'waste', 'renewable',
                'ghg', 'scope', 'climate', 'environmental', 'sustainability',
                'recycling', 'biodiversity', 'pollution'
            ],
            'social': [
                'employee', 'diversity', 'inclusion', 'safety', 'training',
                'community', 'human rights', 'labor', 'health', 'social',
                'workforce', 'supplier', 'customer', 'stakeholder'
            ],
            'governance': [
                'board', 'governance', 'compliance', 'ethics', 'audit',
                'risk', 'transparency', 'executive', 'compensation',
                'regulatory', 'oversight', 'independence'
            ]
        }
        
        # Convert table data to DataFrame for easier processing
        if table_data:
            df_data = []
            for cell in table_data:
                df_data.append({
                    'row': cell['row'],
                    'column': cell['column'],
                    'content': str(cell['content']).lower(),
                    'original_content': cell['content'],
                    'confidence': cell['confidence']
                })
            
            # Group by rows to create metric-value pairs
            rows = {}
            for cell in df_data:
                row_idx = cell['row']
                if row_idx not in rows:
                    rows[row_idx] = []
                rows[row_idx].append(cell)
            
            # Process each row
            for row_idx, row_cells in rows.items():
                if len(row_cells) >= 2:  # Need at least metric name and value
                    metric_name = row_cells[0]['original_content']
                    metric_value = row_cells[1]['original_content']
                    
                    # Categorize based on keywords
                    content_lower = metric_name.lower()
                    for category, keywords in esg_keywords.items():
                        if any(keyword in content_lower for keyword in keywords):
                            categorized[category][f"table_{table_idx}_{metric_name}"] = {
                                'value': metric_value,
                                'confidence': row_cells[0]['confidence']
                            }
                            break
        
        return categorized
    
    def validate_file(self, file_data: bytes, filename: str) -> bool:
        """Validate uploaded file"""
        try:
            # Check file size
            if len(file_data) > Config.MAX_CONTENT_LENGTH:
                raise ValueError("File size exceeds maximum limit")
            
            # Check file extension
            allowed_extensions = ['.xlsx', '.xls']
            if not any(filename.lower().endswith(ext) for ext in allowed_extensions):
                raise ValueError("Invalid file format. Only Excel files are allowed.")
            
            # Try to read as Excel to validate format
            try:
                pd.read_excel(io.BytesIO(file_data))
            except Exception as e:
                raise ValueError(f"Invalid Excel file format: {str(e)}")
            
            return True
        except Exception as e:
            logger.error(f"File validation failed: {str(e)}")
            raise
EOF
```

### 3.5 Create AI Analyzer

```bash
# Create src/analyzers/ai_analyzer.py
cat > src/analyzers/ai_analyzer.py << 'EOF'
import json
import requests
import logging
from typing import Dict, Any, Optional
import sys
import os

# Add the src directory to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config import Config

logger = logging.getLogger(__name__)

class ESGAnalyzer:
    def __init__(self):
        self.endpoint = Config.AI_FOUNDRY_ENDPOINT
        self.api_key = Config.AI_FOUNDRY_KEY
        self.model = Config.AI_FOUNDRY_MODEL
        self.esg_prompt = self._load_esg_prompt()
    
    def _load_esg_prompt(self) -> str:
        """Load the ESG analysis master prompt"""
        try:
            prompt_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'config', 'esg_master_prompt.txt'
            )
            with open(prompt_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error loading ESG prompt: {str(e)}")
            return "You are an expert ESG analyst. Analyze the provided data and provide comprehensive insights."
    
    def analyze_esg_data(self, esg_data: Dict[str, Any], company_context: Optional[str] = None) -> Dict[str, Any]:
        """Analyze ESG data using AI Foundry"""
        try:
            analysis_prompt = self._build_analysis_prompt(esg_data, company_context)
            
            # Call AI Foundry endpoint
            response = self._call_ai_foundry(analysis_prompt)
            
            # Parse and structure the response
            structured_analysis = self._structure_analysis(response)
            
            logger.info("ESG data analysis completed successfully")
            return structured_analysis
            
        except Exception as e:
            logger.error(f"Error analyzing ESG data: {str(e)}")
            raise
    
    def _build_analysis_prompt(self, esg_data: Dict[str, Any], company_context: Optional[str]) -> str:
        """Build comprehensive analysis prompt"""
        prompt = f"""
        {self.esg_prompt}
        
        ## Company Context
        {company_context or "No specific company context provided"}
        
        ## ESG Data for Analysis
        {json.dumps(esg_data, indent=2)}
        
        Please provide a comprehensive ESG analysis following the framework outlined above.
        Structure your response as a JSON object with the following sections:
        - executive_summary: Array of key findings (3-5 bullet points)
        - esg_maturity: Overall maturity level (Emerging/Developing/Advanced/Leading)
        - environmental: Environmental performance analysis
        - social: Social performance analysis  
        - governance: Governance performance analysis
        - recommendations: Object with high/medium/low priority recommendations
        - risk_opportunities: Risk and opportunity assessment
        - implementation_roadmap: Short/medium/long term action items
        """
        return prompt
    
    def _call_ai_foundry(self, prompt: str) -> Dict[str, Any]:
        """Call Microsoft AI Foundry API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "messages": [
                {"role": "system", "content": "You are an expert ESG analyst. Provide comprehensive, structured analysis in JSON format."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 4000,
            "temperature": 0.3,
            "model": self.model
        }
        
        try:
            response = requests.post(self.endpoint, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {str(e)}")
            raise
    
    def _structure_analysis(self, ai_response: Dict[str, Any]) -> Dict[str, Any]:
        """Structure AI response into standardized format"""
        try:
            # Extract content from AI response
            if 'choices' in ai_response and ai_response['choices']:
                content = ai_response['choices'][0]['message']['content']
                
                # Try to parse as JSON
                try:
                    structured_data = json.loads(content)
                    return structured_data
                except json.JSONDecodeError:
                    # If not valid JSON, create structure from text
                    return self._parse_text_response(content)
            else:
                raise ValueError("Invalid AI response format")
                
        except Exception as e:
            logger.error(f"Error structuring analysis: {str(e)}")
            # Return a basic structure with the raw response
            return {
                'executive_summary': ['Analysis completed with raw response'],
                'esg_maturity': 'Unknown',
                'environmental': {'raw_response': str(ai_response)},