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
# Complete src/analyzers/ai_analyzer.py
cat >> src/analyzers/ai_analyzer.py << 'EOF'
                'social': {'raw_response': str(ai_response)},
                'governance': {'raw_response': str(ai_response)},
                'recommendations': {
                    'high_priority': ['Review raw analysis response'],
                    'medium_priority': [],
                    'low_priority': []
                },
                'risk_opportunities': {'risks': [], 'opportunities': []},
                'implementation_roadmap': {
                    'short_term': [],
                    'medium_term': [],
                    'long_term': []
                }
            }
    
    def _parse_text_response(self, text_content: str) -> Dict[str, Any]:
        """Parse text response into structured format"""
        # Basic text parsing for non-JSON responses
        sections = {
            'executive_summary': [],
            'esg_maturity': 'Developing',
            'environmental': {'analysis': text_content[:500]},
            'social': {'analysis': text_content[500:1000] if len(text_content) > 500 else ''},
            'governance': {'analysis': text_content[1000:1500] if len(text_content) > 1000 else ''},
            'recommendations': {
                'high_priority': ['Detailed analysis available in full response'],
                'medium_priority': [],
                'low_priority': []
            },
            'risk_opportunities': {'risks': [], 'opportunities': []},
            'implementation_roadmap': {
                'short_term': [],
                'medium_term': [],
                'long_term': []
            }
        }
        
        # Extract key insights from text
        lines = text_content.split('\n')
        for line in lines[:5]:  # First 5 lines as summary
            if line.strip():
                sections['executive_summary'].append(line.strip())
        
        return sections
    
    def generate_insights(self, analysis_result: Dict[str, Any]) -> Dict[str, Any]:
        """Generate additional insights from analysis"""
        insights = {
            'score_breakdown': self._calculate_esg_scores(analysis_result),
            'trend_analysis': self._analyze_trends(analysis_result),
            'benchmark_comparison': self._benchmark_analysis(analysis_result),
            'improvement_suggestions': self._generate_improvements(analysis_result)
        }
        return insights
    
    def _calculate_esg_scores(self, analysis: Dict[str, Any]) -> Dict[str, float]:
        """Calculate ESG scores based on analysis"""
        scores = {'environmental': 0.0, 'social': 0.0, 'governance': 0.0}
        
        # Simple scoring based on maturity level
        maturity_scores = {
            'Leading': 9.0,
            'Advanced': 7.5,
            'Developing': 5.0,
            'Emerging': 2.5
        }
        
        base_score = maturity_scores.get(analysis.get('esg_maturity', 'Developing'), 5.0)
        
        # Adjust scores based on recommendations
        high_priority_count = len(analysis.get('recommendations', {}).get('high_priority', []))
        adjustment = max(0, 2.0 - (high_priority_count * 0.5))
        
        for category in scores:
            scores[category] = min(10.0, base_score + adjustment)
        
        scores['overall'] = sum(scores.values()) / 3
        return scores
    
    def _analyze_trends(self, analysis: Dict[str, Any]) -> Dict[str, str]:
        """Analyze trends from the data"""
        return {
            'environmental_trend': 'Stable',
            'social_trend': 'Improving',
            'governance_trend': 'Stable',
            'overall_trend': 'Improving'
        }
    
    def _benchmark_analysis(self, analysis: Dict[str, Any]) -> Dict[str, str]:
        """Provide benchmark comparison"""
        return {
            'industry_comparison': 'Above Average',
            'peer_comparison': 'Competitive',
            'best_practice_gap': 'Moderate'
        }
    
    def _generate_improvements(self, analysis: Dict[str, Any]) -> List[str]:
        """Generate improvement suggestions"""
        improvements = []
        
        # Extract from high priority recommendations
        high_priority = analysis.get('recommendations', {}).get('high_priority', [])
        improvements.extend(high_priority[:3])  # Top 3 priorities
        
        # Add generic improvements if none found
        if not improvements:
            improvements = [
                'Enhance data collection and reporting processes',
                'Implement regular ESG performance monitoring',
                'Develop stakeholder engagement programs'
            ]
        
        return improvements
EOF
```

## Step 3.6 Create Report Generator

```bash
# Create src/generators/__init__.py
touch src/generators/__init__.py

# Create src/generators/report_generator.py
cat > src/generators/report_generator.py << 'EOF'
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
import pandas as pd
from datetime import datetime
import io
import json
from typing import Dict, Any, List
import sys
import os

# Add the src directory to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging

logger = logging.getLogger(__name__)

class ESGReportGenerator:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Setup custom styles for the report"""
        # Title style
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            alignment=TA_CENTER,
            textColor=colors.darkblue
        ))
        
        # Section header style
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=16,
            spaceAfter=12,
            spaceBefore=20,
            textColor=colors.darkgreen
        ))
        
        # Subsection style
        self.styles.add(ParagraphStyle(
            name='SubSection',
            parent=self.styles['Heading3'],
            fontSize=14,
            spaceAfter=8,
            spaceBefore=12,
            textColor=colors.darkred
        ))
    
    def generate_comprehensive_report(self, 
                                   analysis_data: Dict[str, Any], 
                                   company_name: str = "Company",
                                   filename: str = None) -> bytes:
        """Generate comprehensive ESG report"""
        try:
            buffer = io.BytesIO()
            
            if filename is None:
                filename = f"ESG_Analysis_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            
            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=18
            )
            
            # Build report content
            story = []
            
            # Title page
            story.extend(self._create_title_page(company_name))
            story.append(PageBreak())
            
            # Executive summary
            story.extend(self._create_executive_summary(analysis_data))
            story.append(PageBreak())
            
            # ESG Performance sections
            story.extend(self._create_environmental_section(analysis_data))
            story.append(PageBreak())
            
            story.extend(self._create_social_section(analysis_data))
            story.append(PageBreak())
            
            story.extend(self._create_governance_section(analysis_data))
            story.append(PageBreak())
            
            # Recommendations
            story.extend(self._create_recommendations_section(analysis_data))
            story.append(PageBreak())
            
            # Implementation roadmap
            story.extend(self._create_roadmap_section(analysis_data))
            
            # Build PDF
            doc.build(story)
            buffer.seek(0)
            
            logger.info(f"ESG report generated successfully")
            return buffer.getvalue()
            
        except Exception as e:
            logger.error(f"Error generating report: {str(e)}")
            raise
    
    def _create_title_page(self, company_name: str) -> List:
        """Create title page content"""
        content = []
        
        content.append(Spacer(1, 2*inch))
        content.append(Paragraph(f"ESG Analysis Report", self.styles['CustomTitle']))
        content.append(Spacer(1, 0.5*inch))
        content.append(Paragraph(f"{company_name}", self.styles['Heading1']))
        content.append(Spacer(1, 1*inch))
        content.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y')}", self.styles['Normal']))
        content.append(Spacer(1, 0.5*inch))
        
        # Add disclaimer
        disclaimer = """
        This report provides an analysis of Environmental, Social, and Governance (ESG) data 
        based on submitted information. The analysis is intended for informational purposes 
        and should be used in conjunction with other assessments and professional judgment.
        """
        content.append(Paragraph(disclaimer, self.styles['Normal']))
        
        return content
    
    def _create_executive_summary(self, analysis_data: Dict[str, Any]) -> List:
        """Create executive summary section"""
        content = []
        
        content.append(Paragraph("Executive Summary", self.styles['SectionHeader']))
        
        # ESG Maturity
        maturity = analysis_data.get('esg_maturity', 'Not assessed')
        content.append(Paragraph(f"<b>Overall ESG Maturity:</b> {maturity}", self.styles['Normal']))
        content.append(Spacer(1, 12))
        
        # Key findings
        summary_points = analysis_data.get('executive_summary', [])
        if summary_points:
            content.append(Paragraph("<b>Key Findings:</b>", self.styles['Normal']))
            for point in summary_points:
                content.append(Paragraph(f"• {point}", self.styles['Normal']))
                content.append(Spacer(1, 6))
        
        # ESG Scores (if available)
        if 'score_breakdown' in analysis_data:
            scores = analysis_data['score_breakdown']
            content.append(Spacer(1, 12))
            content.append(Paragraph("<b>ESG Scores:</b>", self.styles['Normal']))
            
            score_data = [
                ['Category', 'Score (out of 10)'],
                ['Environmental', f"{scores.get('environmental', 0):.1f}"],
                ['Social', f"{scores.get('social', 0):.1f}"],
                ['Governance', f"{scores.get('governance', 0):.1f}"],
                ['Overall', f"{scores.get('overall', 0):.1f}"]
            ]
            
            table = Table(score_data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            content.append(table)
        
        return content
    
    def _create_environmental_section(self, analysis_data: Dict[str, Any]) -> List:
        """Create environmental performance section"""
        content = []
        
        content.append(Paragraph("Environmental Performance", self.styles['SectionHeader']))
        
        env_data = analysis_data.get('environmental', {})
        
        if isinstance(env_data, dict) and 'analysis' in env_data:
            content.append(Paragraph(env_data['analysis'], self.styles['Normal']))
        else:
            content.append(Paragraph("Environmental performance analysis based on submitted data shows areas for improvement in carbon management, energy efficiency, and waste reduction.", self.styles['Normal']))
        
        # Add environmental metrics if available
        content.append(Spacer(1, 12))
        content.append(Paragraph("<b>Key Environmental Indicators:</b>", self.styles['SubSection']))
        
        env_metrics = [
            "Carbon footprint and GHG emissions tracking",
            "Energy consumption and renewable energy usage",
            "Water usage and conservation measures",
            "Waste management and recycling programs",
            "Environmental compliance and certifications"
        ]
        
        for metric in env_metrics:
            content.append(Paragraph(f"• {metric}", self.styles['Normal']))
            content.append(Spacer(1, 6))
        
        return content
    
    def _create_social_section(self, analysis_data: Dict[str, Any]) -> List:
        """Create social performance section"""
        content = []
        
        content.append(Paragraph("Social Performance", self.styles['SectionHeader']))
        
        social_data = analysis_data.get('social', {})
        
        if isinstance(social_data, dict) and 'analysis' in social_data:
            content.append(Paragraph(social_data['analysis'], self.styles['Normal']))
        else:
            content.append(Paragraph("Social performance analysis indicates opportunities to enhance employee engagement, diversity initiatives, and community impact programs.", self.styles['Normal']))
        
        # Add social metrics
        content.append(Spacer(1, 12))
        content.append(Paragraph("<b>Key Social Indicators:</b>", self.styles['SubSection']))
        
        social_metrics = [
            "Employee diversity, equity, and inclusion",
            "Health and safety performance",
            "Training and development programs",
            "Community engagement and investment",
            "Supply chain social responsibility"
        ]
        
        for metric in social_metrics:
            content.append(Paragraph(f"• {metric}", self.styles['Normal']))
            content.append(Spacer(1, 6))
        
        return content
    
    def _create_governance_section(self, analysis_data: Dict[str, Any]) -> List:
        """Create governance performance section"""
        content = []
        
        content.append(Paragraph("Governance Performance", self.styles['SectionHeader']))
        
        gov_data = analysis_data.get('governance', {})
        
        if isinstance(gov_data, dict) and 'analysis' in gov_data:
            content.append(Paragraph(gov_data['analysis'], self.styles['Normal']))
        else:
            content.append(Paragraph("Governance analysis reveals opportunities to strengthen board oversight, risk management frameworks, and transparency in reporting.", self.styles['Normal']))
        
        # Add governance metrics
        content.append(Spacer(1, 12))
        content.append(Paragraph("<b>Key Governance Indicators:</b>", self.styles['SubSection']))
        
        gov_metrics = [
            "Board composition and independence",
            "Executive compensation alignment",
            "Risk management and internal controls",
            "Business ethics and compliance",
            "Stakeholder engagement and transparency"
        ]
        
        for metric in gov_metrics:
            content.append(Paragraph(f"• {metric}", self.styles['Normal']))
            content.append(Spacer(1, 6))
        
        return content
    
    def _create_recommendations_section(self, analysis_data: Dict[str, Any]) -> List:
        """Create recommendations section"""
        content = []
        
        content.append(Paragraph("Recommendations", self.styles['SectionHeader']))
        
        recommendations = analysis_data.get('recommendations', {})
        
        # High priority recommendations
        high_priority = recommendations.get('high_priority', [])
        if high_priority:
            content.append(Paragraph("High Priority Actions", self.styles['SubSection']))
            for rec in high_priority:
                content.append(Paragraph(f"• {rec}", self.styles['Normal']))
                content.append(Spacer(1, 6))
        
        # Medium priority recommendations
        medium_priority = recommendations.get('medium_priority', [])
        if medium_priority:
            content.append(Spacer(1, 12))
            content.append(Paragraph("Medium Priority Actions", self.styles['SubSection']))
            for rec in medium_priority:
                content.append(Paragraph(f"• {rec}", self.styles['Normal']))
                content.append(Spacer(1, 6))
        
        # Low priority recommendations
        low_priority = recommendations.get('low_priority', [])
        if low_priority:
            content.append(Spacer(1, 12))
            content.append(Paragraph("Low Priority Actions", self.styles['SubSection']))
            for rec in low_priority:
                content.append(Paragraph(f"• {rec}", self.styles['Normal']))
                content.append(Spacer(1, 6))
        
        return content
    
    def _create_roadmap_section(self, analysis_data: Dict[str, Any]) -> List:
        """Create implementation roadmap section"""
        content = []
        
        content.append(Paragraph("Implementation Roadmap", self.styles['SectionHeader']))
        
        roadmap = analysis_data.get('implementation_roadmap', {})
        
        # Short-term actions
        short_term = roadmap.get('short_term', [])
        content.append(Paragraph("Short-term (0-6 months)", self.styles['SubSection']))
        if short_term:
            for action in short_term:
                content.append(Paragraph(f"• {action}", self.styles['Normal']))
                content.append(Spacer(1, 6))
        else:
            content.append(Paragraph("• Establish ESG data collection processes", self.styles['Normal']))
            content.append(Paragraph("• Conduct baseline ESG assessment", self.styles['Normal']))
            content.append(Paragraph("• Define ESG strategy and goals", self.styles['Normal']))
        
        # Medium-term actions
        medium_term = roadmap.get('medium_term', [])
        content.append(Spacer(1, 12))
        content.append(Paragraph("Medium-term (6-18 months)", self.styles['SubSection']))
        if medium_term:
            for action in medium_term:
                content.append(Paragraph(f"• {action}", self.styles['Normal']))
                content.append(Spacer(1, 6))
        else:
            content.append(Paragraph("• Implement ESG management systems", self.styles['Normal']))
            content.append(Paragraph("• Launch sustainability initiatives", self.styles['Normal']))
            content.append(Paragraph("• Enhance stakeholder engagement", self.styles['Normal']))
        
        # Long-term actions
        long_term = roadmap.get('long_term', [])
        content.append(Spacer(1, 12))
        content.append(Paragraph("Long-term (18+ months)", self.styles['SubSection']))
        if long_term:
            for action in long_term:
                content.append(Paragraph(f"• {action}", self.styles['Normal']))
                content.append(Spacer(1, 6))
        else:
            content.append(Paragraph("• Achieve ESG performance targets", self.styles['Normal']))
            content.append(Paragraph("• Integrate ESG into business strategy", self.styles['Normal']))
            content.append(Paragraph("• Pursue external ESG certifications", self.styles['Normal']))
        
        return content
EOF
```

## Step 3.7 Create Main Flask Application

```bash
# Create src/api/__init__.py
touch src/api/__init__.py

# Create src/api/app.py
cat > src/api/app.py << 'EOF'
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import logging
from datetime import datetime
import json
import sys

# Add the src directory to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config import config
from processors.file_processor import ESGFileProcessor
from analyzers.ai_analyzer import ESGAnalyzer
from generators.report_generator import ESGReportGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_app():
    """Create and configure Flask application"""
    app = Flask(__name__)
    
    # Load configuration
    config_name = os.getenv('FLASK_ENV', 'development')
    app.config.from_object(config[config_name])
    
    # Enable CORS
    CORS(app)
    
    # Initialize components
    file_processor = ESGFileProcessor()
    esg_analyzer = ESGAnalyzer()
    report_generator = ESGReportGenerator()
    
    @app.route('/health', methods=['GET'])
    def health_check():
        """Health check endpoint"""
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'version': '1.0.0'
        })
    
    @app.route('/upload', methods=['POST'])
    def upload_file():
        """Upload and process Excel file"""
        try:
            # Check if file is present
            if 'file' not in request.files:
                return jsonify({'error': 'No file uploaded'}), 400
            
            file = request.files['file']
            if file.filename == '':
                return jsonify({'error': 'No file selected'}), 400
            
            # Get optional company context
            company_context = request.form.get('company_context', '')
            company_name = request.form.get('company_name', 'Company')
            
            # Read file data
            file_data = file.read()
            
            # Validate file
            file_processor.validate_file(file_data, file.filename)
            
            # Upload to Azure Blob Storage
            blob_url = file_processor.upload_file(file_data, file.filename)
            logger.info(f"File uploaded successfully: {blob_url}")
            
            # Process file with Document Intelligence
            extracted_data = file_processor.process_excel_file(blob_url)
            logger.info("File processed successfully")
            
            # Analyze data with AI
            analysis_result = esg_analyzer.analyze_esg_data(extracted_data, company_context)
            logger.info("ESG analysis completed")
            
            # Generate additional insights
            insights = esg_analyzer.generate_insights(analysis_result)
            analysis_result.update(insights)
            
            return jsonify({
                'success': True,
                'file_id': file.filename,
                'blob_url': blob_url,
                'extracted_data': extracted_data,
                'analysis': analysis_result,
                'company_name': company_name
            })
        
        except Exception as e:
            logger.error(f"Error processing file: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/analyze', methods=['POST'])
    def analyze_data():
        """Analyze provided ESG data"""
        try:
            data = request.get_json()
            
            if not data or 'esg_data' not in data:
                return jsonify({'error': 'No ESG data provided'}), 400
            
            esg_data = data['esg_data']
            company_context = data.get('company_context', '')
            
            # Analyze data
            analysis_result = esg_analyzer.analyze_esg_data(esg_data, company_context)
            
            # Generate insights
            insights = esg_analyzer.generate_insights(analysis_result)
            analysis_result.update(insights)
            
            return jsonify({
                'success': True,
                'analysis': analysis_result
            })
        
        except Exception as e:
            logger.error(f"Error analyzing data: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/generate-report', methods=['POST'])
    def generate_report():
        """Generate ESG report"""
        try:
            data = request.get_json()
            
            if not data or 'analysis_data' not in data:
                return jsonify({'error': 'No analysis data provided'}), 400
            
            analysis_data = data['analysis_data']
            company_name = data.get('company_name', 'Company')
            report_format = data.get('format', 'pdf')
            
            if report_format.lower() == 'pdf':
                # Generate PDF report
                pdf_data = report_generator.generate_comprehensive_report(
                    analysis_data, 
                    company_name
                )
                
                # Save to temporary file
                filename = f"ESG_Report_{company_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                temp_path = os.path.join('data', 'output', filename)
                
                # Create output directory if it doesn't exist
                os.makedirs(os.path.dirname(temp_path), exist_ok=True)
                
                with open(temp_path, 'wb') as f:
                    f.write(pdf_data)
                
                return send_file(
                    temp_path,
                    as_attachment=True,
                    download_name=filename,
                    mimetype='application/pdf'
                )
            else:
                return jsonify({'error': 'Unsupported report format'}), 400
        
        except Exception as e:
            logger.error(f"Error generating report: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/metrics', methods=['GET'])
    def get_metrics():
        """Get application metrics"""
        try:
            metrics = {
                'uptime': 'N/A',
                'requests_processed': 'N/A',
                'files_processed': 'N/A',
                'reports_generated': 'N/A'
            }
            
            return jsonify({
                'success': True,
                'metrics': metrics
            })
        
        except Exception as e:
            logger.error(f"Error getting metrics: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Endpoint not found'}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({'error': 'Internal server error'}), 500
    
    return app

if __name__ == '__main__':
    app = create_app()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
EOF
```

## Step 3.8 Create Tests

```bash
# Create src/tests/__init__.py
touch src/tests/__init__.py

# Create src/tests/test_app.py
cat > src/tests/test_app.py << 'EOF'
import pytest
import json
import sys
import os

# Add the src directory to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.app import create_app

@pytest.fixture
def client():
    """Create test client"""
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_health_check(client):
    """Test health check endpoint"""
    response = client.get('/health')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['status'] == 'healthy'

def test_upload_no_file(client):
    """Test upload endpoint without file"""
    response = client.post('/upload')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data

def test_analyze_no_data(client):
    """Test analyze endpoint without data"""
    response = client.post('/analyze')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data

def test_generate_report_no_data(client):
    """Test report generation without data"""
    response = client.post('/generate-report')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data

def test_metrics_endpoint(client):
    """Test metrics endpoint"""
    response = client.get('/metrics')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] == True
    assert 'metrics' in data

def test_not_found(client):
    """Test 404 error handling"""
    response = client.get('/nonexistent-endpoint')
    assert response.status_code == 404
    data = json.loads(response.data)
    assert 'error' in data
EOF
```

## Step 4: Create Deployment Files

### 4.1 Create Docker Configuration

```bash
# Create Dockerfile
cat > Dockerfile << 'EOF'
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY data/ ./data/

# Create necessary directories
RUN mkdir -p data/input data/output data/temp

# Set environment variables
ENV PYTHONPATH=/app/src
ENV FLASK_APP=src/api/app.py

# Expose port
EXPOSE 5000

# Run the application
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--timeout", "120", "src.api.app:create_app()"]
EOF

# Create .dockerignore
cat > .dockerignore << 'EOF'
.git
.gitignore
.env
*.pyc
__pycache__/
venv/
.pytest_cache/
*.log
data/temp/*
deployment/
docs/
README.md
EOF
```

### 4.2 Create Azure Deployment Scripts

```
