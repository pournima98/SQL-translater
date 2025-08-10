import os
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
import openai
import pandas as pd
from sqlalchemy import create_engine, inspect
from typing import Dict, List, Tuple, Optional, Set
import re

# Try to import AI models - graceful fallback if not available
try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
    spacy_available = True
except:
    print("SpaCy not available. Install with: pip install spacy && python -m spacy download en_core_web_sm")
    spacy_available = False

try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    sentence_model = SentenceTransformer('all-MiniLM-L6-v2')
    transformers_available = True
except:
    print("Sentence Transformers not available. Install with: pip install sentence-transformers")
    transformers_available = False

# Initialize OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")
llm = ChatOpenAI(temperature=0)

# Global caches
schema_cache = {}
value_cache = {}
actual_schema = {}
cache_initialized = False

def get_database_engine():
    """Get database engine - matches your app.py configuration"""
    db_url = os.getenv("DB_URL", "mysql+pymysql://root:Hemant%40123@localhost:3306/churn_analysis")
    return create_engine(db_url)

def load_actual_database_schema():
    """Load the ACTUAL database schema and available columns"""
    global actual_schema, cache_initialized
    
    if cache_initialized:
        return actual_schema
    
    try:
        engine = get_database_engine()
        inspector = inspect(engine)
        
        actual_schema = {
            'tables': {},
            'all_columns': set(),
            'relationships': {},
            'available_fields': set()
        }
        
        print("🔍 Loading ACTUAL database schema...")
        
        # Get all tables and their columns
        for table_name in inspector.get_table_names():
            columns = inspector.get_columns(table_name)
            column_names = [col['name'] for col in columns]
            actual_schema['tables'][table_name] = column_names
            actual_schema['all_columns'].update(column_names)
            
            print(f"✅ {table_name}: {', '.join(column_names)}")
        
        # Build available fields list (what users can actually query for)
        for table, columns in actual_schema['tables'].items():
            for column in columns:
                actual_schema['available_fields'].add(column.lower())
        
        # Load sample values for validation
        load_sample_values(engine)
        
        cache_initialized = True
        print(f"🎯 Schema loaded: {len(actual_schema['tables'])} tables, {len(actual_schema['all_columns'])} total columns")
        return actual_schema
        
    except Exception as e:
        print(f"⚠️ Could not load database schema: {e}")
        return {}

def load_sample_values(engine):
    """Load sample values from tables for entity matching"""
    global value_cache
    
    try:
        # Load regions
        regions_df = pd.read_sql("SELECT region_id, region_name FROM regions", engine)
        if not regions_df.empty:
            value_cache['regions'] = {
                'region_name': regions_df['region_name'].tolist(),
                'all_values': regions_df['region_name'].str.lower().tolist()
            }
        
        # Load plans
        plans_df = pd.read_sql("SELECT plan_id, plan_name FROM plans", engine)
        if not plans_df.empty:
            value_cache['plans'] = {
                'plan_name': plans_df['plan_name'].tolist(),
                'all_values': plans_df['plan_name'].str.lower().tolist()
            }
        
        # Load support categories
        try:
            categories_df = pd.read_sql("SELECT DISTINCT category FROM support_tickets LIMIT 20", engine)
            if not categories_df.empty:
                value_cache['categories'] = {
                    'category': categories_df['category'].tolist(),
                    'all_values': categories_df['category'].str.lower().tolist()
                }
        except:
            pass
        
        print("✅ Sample values loaded for validation")
        
    except Exception as e:
        print(f"⚠️ Could not load sample values: {e}")

def extract_requested_fields_from_question(question: str) -> Set[str]:
    """Extract what data fields the user is asking for"""
    
    # Common field patterns users might ask for
    field_patterns = {
        r'\bemail\b': 'email',
        r'\be-mail\b': 'email',
        r'\bphone\b': 'phone',
        r'\btelephone\b': 'phone', 
        r'\bmobile\b': 'phone',
        r'\baddress\b': 'address',
        r'\bstreet\b': 'address',
        r'\bcity\b': 'city',
        r'\bstate\b': 'state',
        r'\bzipcode\b': 'zipcode',
        r'\bzip\b': 'zipcode',
        r'\bpostal\b': 'zipcode',
        r'\bage\b': 'age',
        r'\bgender\b': 'gender',
        r'\bsex\b': 'gender',
        r'\bbirthdate\b': 'birthdate',
        r'\bbirthday\b': 'birthdate',
        r'\bdob\b': 'birthdate',
        r'\bproduct\b': 'product_name',
        r'\bitem\b': 'product_name',
        r'\bskus?\b': 'sku',
        r'\bcategory\b': 'category',
        r'\bdepartment\b': 'department',
        r'\bbrand\b': 'brand',
        r'\bcompany\b': 'company',
        r'\borganization\b': 'company',
        r'\bjob\s+title\b': 'job_title',
        r'\bposition\b': 'job_title',
        r'\brole\b': 'job_title',
        r'\bsalary\b': 'salary',
        r'\bincome\b': 'salary',
        r'\bwage\b': 'salary',
        r'\bwebsite\b': 'website',
        r'\burl\b': 'website',
        r'\bsocial\b': 'social_media',
        r'\btwitter\b': 'social_media',
        r'\bfacebook\b': 'social_media',
        r'\blinkedin\b': 'social_media',
        r'\bnotes\b': 'notes',
        r'\bcomments\b': 'comments',
        r'\bdescription\b': 'description',
        r'\btags\b': 'tags',
        r'\blabels\b': 'labels',
        r'\bstatus\b': 'status',  # This might exist
        r'\bpriority\b': 'priority',
        r'\brating\b': 'rating',
        r'\bscore\b': 'score',
        r'\breview\b': 'review',
        r'\bfeedback\b': 'feedback'
    }
    
    requested_fields = set()
    question_lower = question.lower()
    
    # Check for field patterns
    for pattern, field_name in field_patterns.items():
        if re.search(pattern, question_lower):
            requested_fields.add(field_name)
    
    # Also check for direct column name mentions
    if actual_schema:
        for column in actual_schema['available_fields']:
            if column in question_lower:
                requested_fields.add(column)
    
    return requested_fields

def validate_requested_fields(requested_fields: Set[str]) -> Dict[str, str]:
    """Check if requested fields actually exist in the database"""
    
    if not actual_schema:
        load_actual_database_schema()
    
    validation_results = {}
    available_fields = actual_schema.get('available_fields', set())
    
    for field in requested_fields:
        field_lower = field.lower()
        
        if field_lower in available_fields:
            # Find which table(s) contain this field
            tables_with_field = []
            for table, columns in actual_schema['tables'].items():
                if field_lower in [col.lower() for col in columns]:
                    tables_with_field.append(table)
            
            validation_results[field] = f"✅ Available in: {', '.join(tables_with_field)}"
        else:
            # Suggest similar fields if available
            similar_fields = find_similar_fields(field_lower, available_fields)
            if similar_fields:
                validation_results[field] = f"❌ '{field}' not available. Similar fields: {', '.join(similar_fields)}"
            else:
                validation_results[field] = f"❌ '{field}' not available in database"
    
    return validation_results

def find_similar_fields(requested_field: str, available_fields: Set[str]) -> List[str]:
    """Find similar field names in the database"""
    similar = []
    
    # Simple similarity check
    for field in available_fields:
        if requested_field in field or field in requested_field:
            similar.append(field)
        elif abs(len(requested_field) - len(field)) <= 2:  # Similar length
            # Simple character overlap check
            overlap = len(set(requested_field) & set(field))
            if overlap >= min(len(requested_field), len(field)) * 0.6:
                similar.append(field)
    
    return similar[:3]  # Return top 3 similar fields

def check_data_relationships(question: str) -> Optional[str]:
    """Check for impossible relationships or granularities"""
    
    question_lower = question.lower()
    
    # Check for geographical granularity issues
    geographic_issues = [
        (r'\bcountr(y|ies)\b', "country", "regions (North America, Europe, Asia, etc.)"),
        (r'\bcit(y|ies)\b', "city", "regions only"),
        (r'\bstate\b', "state", "regions only"), 
        (r'\bprovince\b', "province", "regions only"),
    ]
    
    for pattern, requested, available in geographic_issues:
        if re.search(pattern, question_lower):
            actual_regions = value_cache.get('regions', {}).get('region_name', ['North America', 'Europe', 'Asia', 'Australia', 'South America'])
            return f"❌ **{requested.title()} data not available**\n\nAvailable geographic data: {', '.join(actual_regions)}\n\n💡 Try: 'customers by region' or 'sales in Europe'"
    
    # Check for product-level data when no products exist
    if not any('product' in table for table in actual_schema.get('tables', {})):
        product_patterns = [r'\bproduct\b', r'\bitem\b', r'\bsku\b', r'\bcatalog\b']
        for pattern in product_patterns:
            if re.search(pattern, question_lower):
                return f"❌ **Product data not available**\n\nThis database contains customer subscription data, not product sales.\n\n💡 Try: 'revenue by plan', 'customer payments', or 'subscription trends'"
    
    return None

def create_comprehensive_validation_message(question: str) -> Optional[str]:
    """Comprehensive validation of the entire question"""
    
    # Load schema if not loaded
    if not actual_schema:
        load_actual_database_schema()
    
    # Extract what fields the user is asking for
    requested_fields = extract_requested_fields_from_question(question)
    
    # Check for relationship/granularity issues first
    relationship_issue = check_data_relationships(question)
    if relationship_issue:
        return relationship_issue
    
    # Validate requested fields
    if requested_fields:
        field_validation = validate_requested_fields(requested_fields)
        invalid_fields = {field: msg for field, msg in field_validation.items() if "❌" in msg}
        
        if invalid_fields:
            # Build comprehensive error message
            available_tables = list(actual_schema['tables'].keys())
            
            error_msg = "❌ **Requested data not available in database**\n\n"
            
            # Show what's missing
            error_msg += "**Missing fields:**\n"
            for field, validation in invalid_fields.items():
                error_msg += f"• {validation}\n"
            
            # Show what IS available  
            error_msg += f"\n**Available tables:** {', '.join(available_tables)}\n"
            
            # Show sample available columns
            if 'customers' in actual_schema['tables']:
                customer_cols = actual_schema['tables']['customers']
                error_msg += f"**Customer data available:** {', '.join(customer_cols)}\n"
            
            # Provide helpful suggestions
            error_msg += "\n💡 **Try asking for:**\n"
            error_msg += "• 'Top customers by revenue'\n"
            error_msg += "• 'Customer distribution by region'\n" 
            error_msg += "• 'Payment trends over time'\n"
            error_msg += "• 'Support ticket analysis'\n"
            
            return error_msg
    
    return None

def generate_enhanced_schema() -> str:
    """Generate schema description with actual database structure"""
    
    if not actual_schema:
        load_actual_database_schema()
    
    schema_text = "DATABASE SCHEMA (Actual Structure):\n\n"
    
    # Add actual table structures
    for table_name, columns in actual_schema['tables'].items():
        schema_text += f"{table_name}({', '.join(columns)})\n"
    
    schema_text += "\nRELATIONSHIPS:\n"
    schema_text += "- customers.region_id → regions.region_id\n"
    schema_text += "- customers.plan_id → plans.plan_id\n" 
    schema_text += "- All other tables link to customers via customer_id\n"
    
    schema_text += "\nAVAILABLE DATA:\n"
    if value_cache.get('regions'):
        schema_text += f"- Regions: {', '.join(value_cache['regions']['region_name'])}\n"
    if value_cache.get('plans'):
        schema_text += f"- Plans: {', '.join(value_cache['plans']['plan_name'])}\n"
    if value_cache.get('categories'):
        schema_text += f"- Support Categories: {', '.join(value_cache['categories']['category'])}\n"
    
    return schema_text

# Enhanced prompt template
enhanced_prompt_template = PromptTemplate.from_template("""
You are an expert SQL generator working with this EXACT database schema:

{schema}

CRITICAL RULES:
1. ONLY use tables and columns that exist in the schema above
2. For geographic queries, only use region-level data (North America, Europe, Asia, Australia, South America)
3. For customer data, available fields are: customer_id, name, signup_date, plan_id, region_id
4. For payment analysis, use the payments table with amount, status, payment_date
5. Always JOIN customers with regions for geographic analysis
6. Use proper SQL syntax with appropriate JOINs, WHERE clauses, and aggregations

EXAMPLES:
✅ GOOD: "SELECT r.region_name, COUNT(c.customer_id) FROM customers c JOIN regions r ON c.region_id = r.region_id"
❌ BAD: "SELECT email FROM customers" (email field doesn't exist)

Question: {question}

Generate MySQL query:
""")

def generate_sql_from_question(question: str) -> str:
    """
    Generate SQL with comprehensive validation against actual database schema
    """
    try:
        print(f"🔍 Analyzing question: '{question}'")
        
        # Load actual database schema
        if not actual_schema:
            load_actual_database_schema()
        
        # Comprehensive validation check
        validation_error = create_comprehensive_validation_message(question)
        if validation_error:
            print("🚫 Validation failed - returning error message")
            return validation_error
        
        # Generate enhanced schema description
        schema_description = generate_enhanced_schema()
        
        # Generate SQL using the enhanced prompt
        prompt = enhanced_prompt_template.format(
            schema=schema_description,
            question=question
        )
        
        response = llm.predict(prompt)
        sql_query = response.strip()
        
        # Clean up SQL response
        if sql_query.startswith('```'):
            lines = sql_query.split('\n')
            sql_query = '\n'.join([line for line in lines if not line.strip().startswith('```')])
            sql_query = sql_query.strip()
        
        # Final validation: check if generated SQL uses non-existent columns
        validation_issue = validate_generated_sql(sql_query)
        if validation_issue:
            return validation_issue
        
        print("✅ Valid SQL generated and validated")
        return sql_query
        
    except Exception as e:
        print(f"Error in SQL generation: {e}")
        return f"❌ **Error**: {str(e)}\n\nPlease try a simpler question or rephrase your query."

def validate_generated_sql(sql_query: str) -> Optional[str]:
    """Final validation of generated SQL against actual schema"""
    
    if not sql_query or sql_query.startswith('❌'):
        return None
        
    try:
        # Simple check for non-existent column references
        sql_lower = sql_query.lower()
        
        # Common non-existent columns that AI might hallucinate
        problematic_columns = [
            'email', 'phone', 'address', 'city', 'state', 'country', 
            'product_name', 'product_id', 'age', 'gender', 'birthdate'
        ]
        
        for col in problematic_columns:
            if col in sql_lower:
                available_cols = []
                for table, columns in actual_schema['tables'].items():
                    available_cols.extend([f"{table}.{c}" for c in columns])
                
                return f"❌ **Invalid SQL Generated**\n\nSQL contains non-existent column: '{col}'\n\n**Available columns:**\n{', '.join(available_cols[:20])}\n\nPlease rephrase your question."
        
        return None
        
    except Exception as e:
        return f"❌ **SQL Validation Error**: {str(e)}"

# Debug function for testing
def debug_question_analysis(question: str):
    """Debug comprehensive question analysis"""
    print(f"\n🔍 ANALYZING: '{question}'")
    print("=" * 70)
    
    # Load schema
    if not actual_schema:
        load_actual_database_schema()
    
    # Show what fields are being requested
    requested_fields = extract_requested_fields_from_question(question)
    print(f"📋 REQUESTED FIELDS: {requested_fields if requested_fields else 'None detected'}")
    
    # Show field validation
    if requested_fields:
        field_validation = validate_requested_fields(requested_fields)
        print(f"\n🔍 FIELD VALIDATION:")
        for field, result in field_validation.items():
            print(f"   {result}")
    
    # Check relationship issues
    relationship_issue = check_data_relationships(question)
    if relationship_issue:
        print(f"\n🚫 RELATIONSHIP ISSUE:")
        print(relationship_issue)
    
    # Show comprehensive validation
    comprehensive_validation = create_comprehensive_validation_message(question)
    if comprehensive_validation:
        print(f"\n🚫 COMPREHENSIVE VALIDATION FAILED:")
        print(comprehensive_validation)
    else:
        print(f"\n✅ VALIDATION PASSED - Question can be processed")

if __name__ == "__main__":
    # Test with various problematic questions
    test_questions = [
        "Give me email of customers",  # No email field
        "Show me phone numbers of top customers",  # No phone field  
        "Customer addresses in Europe",  # No address field
        "What's the age of our customers?",  # No age field
        "Top 10 countries in Europe",  # No country data, only regions
        "Sales by city",  # No city data
        "Product sales analysis",  # No products table
        "Show customer gender distribution",  # No gender field
        "What are customer job titles?",  # No job title field
        "Top customers by revenue",  # This should work
        "Customer distribution by region",  # This should work
        "Payment trends over time"  # This should work
    ]
    
    print("🧪 Testing comprehensive validation system...")
    
    for question in test_questions:
        debug_question_analysis(question)
        result = generate_sql_from_question(question)
        print(f"\n📝 RESULT:")
        print(result)
        print(f"\n{'='*70}")