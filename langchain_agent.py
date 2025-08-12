#######

import os
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
import openai
import pandas as pd
from sqlalchemy import create_engine, inspect, text
from typing import Dict, List, Tuple, Optional, Set, Any
import re
import json
from datetime import datetime, timedelta
import re
from typing import Dict, List, Tuple, Optional

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
query_cache = {}
performance_stats = {'queries_generated': 0, 'validation_errors': 0, 'successful_queries': 0}

class SQLValidationError(Exception):
    """Custom exception for SQL validation errors"""
    pass

class DatabaseSchemaAnalyzer:
    """Handles database schema analysis and caching"""
    
    def __init__(self, db_url: str = None):
        #self.db_url = db_url or os.getenv("DB_URL", "mysql+pymysql://root:Hemant%40123@localhost:3306/churn_analysis")
        self.db_url = db_url or os.getenv("DB_URL")
        if not self.db_url:
            raise ValueError("DB_URL environment variable is required")
        self.engine = None
        self.schema_data = {}
        self.sample_data = {}
        
    def get_engine(self):
        """Get or create database engine"""
        if not self.engine:
            self.engine = create_engine(self.db_url)
        return self.engine
    
    def analyze_schema(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Comprehensive schema analysis"""
        global actual_schema, cache_initialized
        
        if cache_initialized and not force_refresh:
            return actual_schema
            
        try:
            engine = self.get_engine()
            inspector = inspect(engine)
            
            actual_schema = {
                'tables': {},
                'all_columns': set(),
                'relationships': {},
                'available_fields': set(),
                'table_sizes': {},
                'column_types': {},
                'constraints': {},
                'indexes': {}
            }
            
            print("🔍 Loading ACTUAL database schema...")
            
            # Get all tables and detailed column information
            for table_name in inspector.get_table_names():
                columns = inspector.get_columns(table_name)
                column_info = {}
                column_names = []
                
                for col in columns:
                    col_name = col['name']
                    column_names.append(col_name)
                    column_info[col_name] = {
                        'type': str(col['type']),
                        'nullable': col['nullable'],
                        'default': col.get('default', None),
                        'autoincrement': col.get('autoincrement', False)
                    }
                
                actual_schema['tables'][table_name] = column_names
                actual_schema['column_types'][table_name] = column_info
                actual_schema['all_columns'].update(column_names)
                
                # Get foreign keys
                foreign_keys = inspector.get_foreign_keys(table_name)
                if foreign_keys:
                    actual_schema['relationships'][table_name] = foreign_keys
                
                # Get indexes
                indexes = inspector.get_indexes(table_name)
                if indexes:
                    actual_schema['indexes'][table_name] = indexes
                
                # Get table size (row count)
                try:
                    with engine.connect() as conn:
                        result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                        row_count = result.scalar()
                        actual_schema['table_sizes'][table_name] = row_count
                except Exception as e:
                    actual_schema['table_sizes'][table_name] = 0
                
                print(f"✅ {table_name}: {', '.join(column_names)} ({actual_schema['table_sizes'][table_name]} rows)")
            
            # Build available fields list
            for table, columns in actual_schema['tables'].items():
                for column in columns:
                    actual_schema['available_fields'].add(column.lower())
            
            # Load sample values for validation
            self.load_sample_values(engine)
            
            cache_initialized = True
            print(f"🎯 Schema loaded: {len(actual_schema['tables'])} tables, {len(actual_schema['all_columns'])} total columns")
            return actual_schema
            
        except Exception as e:
            print(f"⚠️ Could not load database schema: {e}")
            raise SQLValidationError(f"Schema analysis failed: {e}")
    
    def load_sample_values(self, engine):
        """Load comprehensive sample values from tables"""
        global value_cache
        
        sample_queries = {
            'regions': "SELECT region_id, region_name FROM regions LIMIT 100",
            'plans': "SELECT plan_id, plan_name FROM plans LIMIT 100",
            'customers': "SELECT customer_id, name, signup_date FROM customers LIMIT 10",
            'support_categories': "SELECT DISTINCT category FROM support_tickets LIMIT 50"
        }
        
        for key, query in sample_queries.items():
            try:
                df = pd.read_sql(query, engine)
                if not df.empty:
                    value_cache[key] = {
                        'data': df,
                        'columns': df.columns.tolist(),
                        'sample_values': {col: df[col].unique()[:10].tolist() for col in df.columns}
                    }
                    print(f"✅ Sample {key} data loaded: {len(df)} records")
            except Exception as e:
                print(f"⚠️ Could not load {key}: {e}")

class QueryFieldExtractor:
    """Extracts and validates requested fields from natural language queries"""
    
    def __init__(self):
        self.field_patterns = self._build_field_patterns()
        self.excluded_patterns = self._build_excluded_patterns()
    
    def _build_field_patterns(self) -> Dict[str, str]:
        """Build comprehensive field pattern dictionary"""
        return {
            # Personal Information
            r'(?:customer|user|client)s?\s+email': 'email',
            r'email\s+(?:address|field|column|data)': 'email',
            r'\b(?:show|get|list|display)\s+email': 'email',
            
            r'(?:customer|user|client)s?\s+phone': 'phone_number',
            r'phone\s+(?:number|field|column|data)': 'phone_number',
            r'\b(?:show|get|list|display)\s+phone': 'phone_number',
            
            r'(?:customer|user|client)s?\s+address': 'address',
            r'address\s+(?:field|column|data)': 'address',
            r'\b(?:show|get|list|display)\s+address': 'address',
            r'\bstreet\s+address': 'address',
            
            # Geographic Information
            r'\bcity\s+(?:wise|breakdown|distribution|analysis)': 'city',
            r'(?:by|from|in)\s+city': 'city',
            r'\b(?:show|get|list|display)\s+cit(?:y|ies)': 'city',
            
            r'\bstate\s+(?:wise|breakdown|distribution|analysis)': 'state',
            r'(?:by|from|in)\s+state': 'state',
            r'\b(?:show|get|list|display)\s+state': 'state',
            
            r'\bcountr(?:y|ies)\s+(?:wise|breakdown|distribution|analysis)': 'country',
            r'(?:by|from|in)\s+countr(?:y|ies)': 'country',
            
            # Demographics
            r'(?:customer|user|client)s?\s+age': 'age',
            r'age\s+(?:group|bracket|range|distribution)': 'age',
            r'\b(?:show|get|list|display)\s+age': 'age',
            
            r'(?:customer|user|client)s?\s+gender': 'gender',
            r'gender\s+(?:breakdown|distribution|analysis)': 'gender',
            r'\b(?:show|get|list|display)\s+gender': 'gender',
            
            # Professional Information
            r'job\s+title': 'job_title',
            r'(?:customer|user|client)s?\s+(?:position|role|occupation)': 'job_title',
            r'\b(?:show|get|list|display)\s+(?:position|role|job)': 'job_title',
            
            r'(?:customer|user|client)s?\s+(?:salary|income)': 'salary',
            r'\b(?:show|get|list|display)\s+(?:salary|income)': 'salary',
            
            # Product Information
            r'product\s+(?:name|catalog|list|inventory)': 'product_name',
            r'individual\s+product': 'product_name',
            r'\b(?:show|get|list|display)\s+products': 'product_name',
            
            # Other Personal Data
            r'(?:birth|date\s+of\s+birth|birthdate)': 'birth_date',
            r'(?:social\s+security|ssn)': 'ssn',
            r'(?:credit\s+score|credit\s+rating)': 'credit_score',
        }
    
    def _build_excluded_patterns(self) -> List[str]:
        """Build patterns that should NOT trigger field extraction"""
        return [
            r'(?:how\s+many\s+)?years?\s+of\s+data',
            r'data\s+(?:age|span|range|period)',
            r'time\s+(?:range|span|period)',
            r'age\s+of\s+(?:data|records|information)',
            r'historical\s+data',
            r'product\s+(?:data|analysis|plan|service)',
            r'email\s+(?:report|results|me|notification)',
            r'status\s+(?:report|analysis|update)',
            r'phone\s+(?:support|call|contact)',
            r'address\s+(?:this|that|the\s+issue)',
            r'city\s+(?:of\s+)?(?:birth|residence)\s+data',
            r'state\s+(?:of\s+the\s+)?(?:art|market|economy)',
        ]
    
    def extract_fields(self, question: str) -> Set[str]:
        """Extract requested fields with enhanced context awareness"""
        question_lower = question.lower()
        requested_fields = set()
        
        # Check excluded patterns first
        for pattern in self.excluded_patterns:
            if re.search(pattern, question_lower):
                print(f"🔍 Excluded pattern matched: {pattern}")
                return set()
        
        # Extract fields using patterns
        for pattern, field_name in self.field_patterns.items():
            if re.search(pattern, question_lower):
                requested_fields.add(field_name)
                print(f"🎯 Field requested: {field_name} (pattern: {pattern})")
        
        # Check for direct column mentions in proper context
        if actual_schema:
            for column in actual_schema['available_fields']:
                column_patterns = [
                    rf'\b{column}\s+(?:field|column|data|values?)\b',
                    rf'\b(?:show|get|list|display)\s+{column}\b',
                    rf'\bselect\s+{column}\b'
                ]
                for pattern in column_patterns:
                    if re.search(pattern, question_lower):
                        requested_fields.add(column)
        
        return requested_fields

class DataRelationshipValidator:
    """Validates data relationships and constraints"""
    
    def __init__(self):
        self.geographic_constraints = {
            'country': 'regions',
            'state': 'regions', 
            'province': 'regions',
            'city': 'regions'
        }
        
    def validate_relationships(self, question: str) -> Optional[str]:
        """Check for impossible relationships or data constraints"""
        question_lower = question.lower()
        
        # Geographic granularity validation
        for requested_level, available_level in self.geographic_constraints.items():
            pattern = rf'\b{requested_level}(?:s|ies)?\b'
            if re.search(pattern, question_lower):
                if available_level == 'regions':
                    actual_regions = value_cache.get('regions', {}).get('sample_values', {}).get('region_name', [])
                    if actual_regions:
                        return f"❌ **{requested_level.title()} data not available**\n\nAvailable geographic data: {', '.join(actual_regions[:5])}\n\n💡 Try: 'customers by region' or 'sales in {actual_regions[0] if actual_regions else 'Europe'}'"
        
        # Product data validation
        if not any('product' in table for table in actual_schema.get('tables', {})):
            product_patterns = [r'\bproduct(?:s)?\b', r'\bitem(?:s)?\b', r'\bsku\b', r'\bcatalog\b']
            for pattern in product_patterns:
                if re.search(pattern, question_lower) and not re.search(r'product\s+(?:data|analysis|plan)', question_lower):
                    return f"❌ **Product inventory data not available**\n\nThis database contains customer subscription data, not product catalogs.\n\n💡 Try: 'revenue by plan', 'customer payments', or 'subscription trends'"
        
        # Time range validation
        if 'customers' in actual_schema.get('tables', {}):
            try:
                # Check actual date ranges in the database
                engine = get_database_engine()
                with engine.connect() as conn:
                    result = conn.execute(text("SELECT MIN(signup_date), MAX(signup_date) FROM customers WHERE signup_date IS NOT NULL"))
                    min_date, max_date = result.fetchone()
                    
                    # Check if user is asking for data outside available range
                    year_patterns = [r'(\d{4})', r'year\s+(\d{4})', r'in\s+(\d{4})']
                    for pattern in year_patterns:
                        matches = re.findall(pattern, question_lower)
                        for year_str in matches:
                            try:
                                requested_year = int(year_str)
                                if min_date and max_date:
                                    if requested_year < min_date.year or requested_year > max_date.year:
                                        return f"❌ **Data for {requested_year} not available**\n\nAvailable date range: {min_date.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')}\n\n💡 Try asking for data within the available range."
                            except ValueError:
                                pass
            except Exception as e:
                print(f"Could not validate date ranges: {e}")
        
        return None

class FieldValidator:
    """Validates requested fields against actual database schema"""
    
    def validate_fields(self, requested_fields: Set[str]) -> Dict[str, str]:
        """Comprehensive field validation with suggestions"""
        if not actual_schema:
            analyzer = DatabaseSchemaAnalyzer()
            analyzer.analyze_schema()
        
        validation_results = {}
        available_fields = actual_schema.get('available_fields', set())
        
        for field in requested_fields:
            field_lower = field.lower()
            
            if field_lower in available_fields:
                # Find tables containing this field
                tables_with_field = []
                for table, columns in actual_schema['tables'].items():
                    if field_lower in [col.lower() for col in columns]:
                        tables_with_field.append(table)
                        # Get column type info
                        column_type = actual_schema.get('column_types', {}).get(table, {}).get(field_lower, {}).get('type', 'unknown')
                
                validation_results[field] = f"✅ Available in: {', '.join(tables_with_field)} (type: {column_type})"
            else:
                similar_fields = self.find_similar_fields(field_lower, available_fields)
                if similar_fields:
                    validation_results[field] = f"❌ '{field}' not available. Similar: {', '.join(similar_fields)}"
                else:
                    validation_results[field] = f"❌ '{field}' not found in database"
        
        return validation_results
    
    def find_similar_fields(self, requested_field: str, available_fields: Set[str]) -> List[str]:
        """Advanced similarity matching for field names"""
        similar = []
        
        # Exact substring match
        for field in available_fields:
            if requested_field in field or field in requested_field:
                similar.append(field)
        
        # Fuzzy matching using character overlap
        if not similar:
            for field in available_fields:
                if abs(len(requested_field) - len(field)) <= 3:
                    overlap = len(set(requested_field) & set(field))
                    if overlap >= min(len(requested_field), len(field)) * 0.5:
                        similar.append(field)
        
        # Use transformers for semantic similarity if available
        if transformers_available and not similar:
            try:
                requested_embedding = sentence_model.encode([requested_field])
                field_embeddings = sentence_model.encode(list(available_fields))
                
                similarities = np.dot(requested_embedding, field_embeddings.T)[0]
                top_indices = np.argsort(similarities)[-3:][::-1]
                
                for idx in top_indices:
                    if similarities[idx] > 0.6:  # Similarity threshold
                        similar.append(list(available_fields)[idx])
            except Exception as e:
                print(f"Semantic similarity failed: {e}")
        
        return similar[:3]

class EnhancedSQLGenerator:
    """Enhanced SQL generation with comprehensive validation"""
    
    def __init__(self):
        self.field_extractor = QueryFieldExtractor()
        self.relationship_validator = DataRelationshipValidator()
        self.field_validator = FieldValidator()
        self.query_templates = self._build_query_templates()
    
    def _build_query_templates(self) -> Dict[str, str]:
        """Build common query templates"""
        return {
            'customer_count_by_region': """
                SELECT r.region_name, COUNT(c.customer_id) as customer_count
                FROM customers c 
                JOIN regions r ON c.region_id = r.region_id 
                GROUP BY r.region_name 
                ORDER BY customer_count DESC
            """,
            'revenue_by_plan': """
                SELECT p.plan_name, SUM(pay.amount) as total_revenue
                FROM plans p
                JOIN customers c ON p.plan_id = c.plan_id
                JOIN payments pay ON c.customer_id = pay.customer_id
                WHERE pay.status = 'completed'
                GROUP BY p.plan_name
                ORDER BY total_revenue DESC
            """,
            'monthly_signups': """
                SELECT 
                    YEAR(signup_date) as year,
                    MONTH(signup_date) as month,
                    COUNT(*) as signups
                FROM customers 
                WHERE signup_date IS NOT NULL
                GROUP BY YEAR(signup_date), MONTH(signup_date)
                ORDER BY year, month
            """
        }
    
    def create_enhanced_prompt(self) -> PromptTemplate:
        """Create enhanced prompt template with examples and constraints"""
        template = """
You are an expert SQL generator for a customer analytics database. 

EXACT DATABASE SCHEMA:
{schema}

CRITICAL CONSTRAINTS:
1. ONLY use tables and columns that exist in the schema above
2. Always use proper JOINs when referencing multiple tables
3. For geographic analysis, only region-level data is available
4. Use MySQL syntax (LIMIT, not TOP; proper date functions)
5. Always include proper error handling in aggregations

AVAILABLE SAMPLE DATA:
{sample_data}

SUCCESSFUL QUERY EXAMPLES:
{examples}

COMMON MISTAKES TO AVOID:
❌ Using non-existent columns (email, phone, address, city, state)
❌ Forgetting to JOIN related tables
❌ Using incorrect date functions
❌ Missing WHERE clauses for data quality

User Question: {question}

Generate a clean, executable MySQL query (no markdown formatting):
"""
        return PromptTemplate.from_template(template)
    
    def generate_schema_description(self) -> str:
        """Generate comprehensive schema description"""
        if not actual_schema:
            analyzer = DatabaseSchemaAnalyzer()
            analyzer.analyze_schema()
        
        schema_text = "DATABASE TABLES AND COLUMNS:\n\n"
        
        for table_name, columns in actual_schema['tables'].items():
            row_count = actual_schema.get('table_sizes', {}).get(table_name, 0)
            schema_text += f"{table_name} ({row_count:,} rows):\n"
            
            # Add column details
            column_types = actual_schema.get('column_types', {}).get(table_name, {})
            for col in columns:
                col_info = column_types.get(col, {})
                col_type = col_info.get('type', 'unknown')
                nullable = "NULL" if col_info.get('nullable', True) else "NOT NULL"
                schema_text += f"  - {col} ({col_type}, {nullable})\n"
            schema_text += "\n"
        
        # Add relationships
        schema_text += "RELATIONSHIPS:\n"
        for table, fks in actual_schema.get('relationships', {}).items():
            for fk in fks:
                schema_text += f"- {table}.{fk['constrained_columns'][0]} → {fk['referred_table']}.{fk['referred_columns'][0]}\n"
        
        return schema_text
    
    def generate_sample_data_description(self) -> str:
        """Generate sample data description"""
        sample_text = ""
        
        for key, data in value_cache.items():
            if 'sample_values' in data:
                sample_text += f"\n{key.upper()}:\n"
                for col, values in data['sample_values'].items():
                    sample_text += f"  {col}: {', '.join(map(str, values[:5]))}\n"
        
        return sample_text
    
    def generate_sql(self, question: str) -> str:
        """Main SQL generation method with comprehensive validation"""
        try:
            performance_stats['queries_generated'] += 1
            print(f"🔍 Generating SQL for: '{question}'")
            
            # Load schema if needed
            if not actual_schema:
                analyzer = DatabaseSchemaAnalyzer()
                analyzer.analyze_schema()
            
            # Extract and validate requested fields
            requested_fields = self.field_extractor.extract_fields(question)
            
            # Validate data relationships
            relationship_error = self.relationship_validator.validate_relationships(question)
            if relationship_error:
                performance_stats['validation_errors'] += 1
                return relationship_error
            
            # Validate requested fields
            if requested_fields:
                field_validation = self.field_validator.validate_fields(requested_fields)
                invalid_fields = {f: msg for f, msg in field_validation.items() if "❌" in msg}
                
                if invalid_fields:
                    performance_stats['validation_errors'] += 1
                    return self._create_field_error_message(invalid_fields)
            
            # Check query cache
            cache_key = hash(question.lower().strip())
            if cache_key in query_cache:
                print("📋 Using cached query")
                return query_cache[cache_key]
            
            # Generate SQL using LLM
            prompt = self.create_enhanced_prompt()
            
            formatted_prompt = prompt.format(
                schema=self.generate_schema_description(),
                sample_data=self.generate_sample_data_description(),
                examples=self._get_example_queries(),
                question=question
            )
            
            response = llm.predict(formatted_prompt)
            sql_query = self._clean_sql_response(response)
            
            # Final validation
            validation_error = self._validate_generated_sql(sql_query)
            if validation_error:
                performance_stats['validation_errors'] += 1
                return validation_error
            
            # Cache successful query
            query_cache[cache_key] = sql_query
            performance_stats['successful_queries'] += 1
            
            print("✅ SQL generated and validated successfully")
            return sql_query
            
        except Exception as e:
            performance_stats['validation_errors'] += 1
            print(f"❌ Error in SQL generation: {e}")
            return f"❌ **Generation Error**: {str(e)}\n\nPlease try rephrasing your question."
    
    def _create_field_error_message(self, invalid_fields: Dict[str, str]) -> str:
        """Create comprehensive error message for invalid fields"""
        error_msg = "❌ **Requested data not available in database**\n\n"
        
        error_msg += "**Missing fields:**\n"
        for field, validation in invalid_fields.items():
            error_msg += f"• {validation}\n"
        
        # Show available data
        available_tables = list(actual_schema['tables'].keys())
        error_msg += f"\n**Available tables:** {', '.join(available_tables)}\n"
        
        if 'customers' in actual_schema['tables']:
            customer_cols = actual_schema['tables']['customers']
            error_msg += f"**Customer fields:** {', '.join(customer_cols)}\n"
        
        # Suggestions
        error_msg += "\n💡 **Try these queries:**\n"
        suggestions = [
            "Top customers by revenue",
            "Customer distribution by region", 
            "Monthly signup trends",
            "Payment analysis by plan",
            "Support ticket categories"
        ]
        for suggestion in suggestions:
            error_msg += f"• '{suggestion}'\n"
        
        return error_msg
    
    def _get_example_queries(self) -> str:
        """Get example queries for the prompt"""
        examples = []
        for name, query in self.query_templates.items():
            examples.append(f"-- {name.replace('_', ' ').title()}\n{query.strip()}\n")
        return "\n".join(examples)
    
    def _clean_sql_response(self, response: str) -> str:
        """Clean SQL response from LLM"""
        sql_query = response.strip()
        
        # Remove markdown formatting
        if sql_query.startswith('```'):
            lines = sql_query.split('\n')
            sql_query = '\n'.join([line for line in lines if not line.strip().startswith('```')])
            sql_query = sql_query.strip()
        
        # Remove common prefixes
        prefixes_to_remove = ['sql', 'query:', 'answer:', 'result:']
        for prefix in prefixes_to_remove:
            if sql_query.lower().startswith(prefix):
                sql_query = sql_query[len(prefix):].strip()
        
        return sql_query
    
    def _validate_generated_sql(self, sql_query: str) -> Optional[str]:
        """Final validation of generated SQL"""
        if not sql_query or sql_query.startswith('❌'):
            return "❌ No valid SQL query generated"
        
        try:
            sql_lower = sql_query.lower()
            
            # Get actual column names
            actual_columns = set()
            for table, columns in actual_schema.get('tables', {}).items():
                for col in columns:
                    actual_columns.add(col.lower())
            
            # Check for non-existent columns in SQL context
            problematic_columns = [
                'email', 'phone_number', 'phone', 'address', 'street_address',
                'city', 'state', 'country', 'zipcode', 'postal_code',
                'product_name', 'product_id', 'item_name', 'sku',
                'age', 'gender', 'birthdate', 'birth_date', 'date_of_birth',
                'job_title', 'position', 'salary', 'income'
            ]
            
            for col in problematic_columns:
                if col not in actual_columns:
                    sql_patterns = [
                        rf'\bselect\s+.*\b{col}\b',
                        rf'\b{col}\s*[,\s]',
                        rf'\bwhere\s+.*\b{col}\b',
                        rf'\bgroup\s+by\s+.*\b{col}\b',
                        rf'\border\s+by\s+.*\b{col}\b',
                        rf'\b{col}\s*=',
                        rf'=\s*{col}\b',
                    ]
                    
                    for pattern in sql_patterns:
                        if re.search(pattern, sql_lower):
                            available_cols = []
                            for table, columns in actual_schema['tables'].items():
                                available_cols.extend([f"{table}.{c}" for c in columns])
                            
                            return f"❌ **Invalid SQL: Column '{col}' does not exist**\n\n**Available columns:**\n{', '.join(available_cols[:15])}{'...' if len(available_cols) > 15 else ''}\n\nPlease rephrase your question."
            
            # Basic SQL syntax validation
            required_keywords = ['select', 'from']
            for keyword in required_keywords:
                if keyword not in sql_lower:
                    return f"❌ **Invalid SQL: Missing {keyword.upper()} clause**"
            
            return None
            
        except Exception as e:
            return f"❌ **SQL Validation Error**: {str(e)}"

# Convenience functions
# def get_database_engine():
#     """Get database engine - matches your app.py configuration"""
#     db_url = os.getenv("DB_URL", "mysql+pymysql://root:Hemant%40123@localhost:3306/churn_analysis")
#     return create_engine(db_url)

def get_database_engine():
    """Get database engine - uses environment variable only"""
    db_url = os.getenv("DB_URL")
    if not db_url:
        raise ValueError("DB_URL environment variable is required")
    return create_engine(db_url)

def generate_sql_from_question(question: str) -> str:
    """Main entry point for SQL generation - maintains backward compatibility"""
    generator = EnhancedSQLGenerator()
    return generator.generate_sql(question)

def execute_sql_query(sql_query: str, return_dataframe: bool = True) -> Tuple[bool, Any, str]:
    """Execute SQL query safely with error handling"""
    try:
        engine = get_database_engine()
        
        # Security check - prevent dangerous operations
        dangerous_keywords = ['drop', 'delete', 'truncate', 'alter', 'create', 'insert', 'update']
        sql_lower = sql_query.lower()
        
        for keyword in dangerous_keywords:
            if re.search(rf'\b{keyword}\b', sql_lower):
                return False, None, f"❌ Dangerous operation '{keyword}' not allowed"
        
        # Execute query
        if return_dataframe:
            df = pd.read_sql(sql_query, engine)
            return True, df, "Query executed successfully"
        else:
            with engine.connect() as conn:
                result = conn.execute(text(sql_query))
                return True, result.fetchall(), "Query executed successfully"
                
    except Exception as e:
        error_msg = str(e)
        # Provide helpful error messages
        if "doesn't exist" in error_msg.lower():
            return False, None, f"❌ **Table/Column Error**: {error_msg}\n\nPlease check the table and column names in your query."
        elif "syntax error" in error_msg.lower():
            return False, None, f"❌ **SQL Syntax Error**: {error_msg}\n\nPlease check your SQL syntax."
        else:
            return False, None, f"❌ **Database Error**: {error_msg}"

def get_query_suggestions(partial_question: str = "") -> List[str]:
    """Get smart query suggestions based on available data"""
    if not actual_schema:
        analyzer = DatabaseSchemaAnalyzer()
        analyzer.analyze_schema()
    
    suggestions = []
    
    # Basic analytics suggestions
    basic_suggestions = [
        "How many customers do we have?",
        "Show customer distribution by region",
        "What are the most popular subscription plans?",
        "Monthly revenue trends",
        "Customer signup trends over time",
        "Average revenue per customer by plan",
        "Top paying customers",
        "Customer retention analysis"
    ]
    
    # Advanced suggestions based on available tables
    tables = actual_schema.get('tables', {})
    
    if 'support_tickets' in tables:
        basic_suggestions.extend([
            "Support ticket volume by category",
            "Average resolution time for support tickets",
            "Customers with most support tickets"
        ])
    
    if 'payments' in tables:
        basic_suggestions.extend([
            "Failed payment analysis",
            "Payment method distribution",
            "Revenue by payment status"
        ])
    
    if 'usage_data' in tables:
        basic_suggestions.extend([
            "Customer usage patterns",
            "High usage customers",
            "Usage trends by plan type"
        ])
    
    # Filter suggestions based on partial question if provided
    if partial_question:
        partial_lower = partial_question.lower()
        suggestions = [s for s in basic_suggestions if any(word in s.lower() for word in partial_lower.split())]
    else:
        suggestions = basic_suggestions
    
    return suggestions[:10]  # Return top 10 suggestions

def analyze_query_performance() -> Dict[str, Any]:
    """Analyze query generation performance"""
    total_queries = performance_stats['queries_generated']
    successful_queries = performance_stats['successful_queries']
    validation_errors = performance_stats['validation_errors']
    
    success_rate = (successful_queries / total_queries * 100) if total_queries > 0 else 0
    error_rate = (validation_errors / total_queries * 100) if total_queries > 0 else 0
    
    return {
        'total_queries': total_queries,
        'successful_queries': successful_queries,
        'validation_errors': validation_errors,
        'success_rate': f"{success_rate:.1f}%",
        'error_rate': f"{error_rate:.1f}%",
        'cached_queries': len(query_cache)
    }

def clear_cache():
    """Clear all caches and force schema reload"""
    global cache_initialized, query_cache, value_cache, actual_schema
    cache_initialized = False
    query_cache.clear()
    value_cache.clear()
    actual_schema.clear()
    print("🧹 All caches cleared")

def get_database_summary() -> Dict[str, Any]:
    """Get comprehensive database summary"""
    if not actual_schema:
        analyzer = DatabaseSchemaAnalyzer()
        analyzer.analyze_schema()
    
    summary = {
        'tables': {},
        'total_records': 0,
        'date_ranges': {},
        'key_metrics': {}
    }
    
    # Table information
    for table, columns in actual_schema['tables'].items():
        row_count = actual_schema.get('table_sizes', {}).get(table, 0)
        summary['tables'][table] = {
            'columns': columns,
            'row_count': row_count,
            'column_types': actual_schema.get('column_types', {}).get(table, {})
        }
        summary['total_records'] += row_count
    
    # Get date ranges for time-based analysis
    try:
        engine = get_database_engine()
        
        # Check customers signup date range
        if 'customers' in actual_schema['tables'] and 'signup_date' in actual_schema['tables']['customers']:
            with engine.connect() as conn:
                result = conn.execute(text("SELECT MIN(signup_date), MAX(signup_date), COUNT(*) FROM customers WHERE signup_date IS NOT NULL"))
                min_date, max_date, count = result.fetchone()
                if min_date and max_date:
                    summary['date_ranges']['customers'] = {
                        'earliest': min_date.strftime('%Y-%m-%d'),
                        'latest': max_date.strftime('%Y-%m-%d'),
                        'total_days': (max_date - min_date).days,
                        'records_with_dates': count
                    }
        
        # Check payments date range
        if 'payments' in actual_schema['tables'] and 'payment_date' in actual_schema['tables']['payments']:
            with engine.connect() as conn:
                result = conn.execute(text("SELECT MIN(payment_date), MAX(payment_date), COUNT(*) FROM payments WHERE payment_date IS NOT NULL"))
                min_date, max_date, count = result.fetchone()
                if min_date and max_date:
                    summary['date_ranges']['payments'] = {
                        'earliest': min_date.strftime('%Y-%m-%d'),
                        'latest': max_date.strftime('%Y-%m-%d'),
                        'total_days': (max_date - min_date).days,
                        'records_with_dates': count
                    }
        
        # Calculate key business metrics
        if 'customers' in actual_schema['tables'] and 'payments' in actual_schema['tables']:
            with engine.connect() as conn:
                # Total revenue
                result = conn.execute(text("SELECT SUM(amount) FROM payments WHERE status = 'completed'"))
                total_revenue = result.scalar() or 0
                summary['key_metrics']['total_revenue'] = total_revenue
                
                # Average revenue per customer
                result = conn.execute(text("SELECT COUNT(DISTINCT customer_id) FROM customers"))
                total_customers = result.scalar() or 0
                if total_customers > 0:
                    summary['key_metrics']['avg_revenue_per_customer'] = total_revenue / total_customers
                
                summary['key_metrics']['total_customers'] = total_customers
        
    except Exception as e:
        print(f"Could not calculate database summary metrics: {e}")
    
    return summary

def validate_question_before_sql_generation(question: str) -> Tuple[bool, str]:
    """Pre-validate question before SQL generation to save resources"""
    if not question or len(question.strip()) < 3:
        return False, "❌ Question too short. Please provide a more detailed question."
    
    # Check for completely unrelated questions
    unrelated_patterns = [
        r'\b(?:weather|temperature|climate)\b',
        r'\b(?:recipe|cooking|food)\b',
        r'\b(?:movie|film|entertainment)\b',
        r'\b(?:sports|football|basketball)\b',
        r'\b(?:politics|election|government)\b'
    ]
    
    question_lower = question.lower()
    for pattern in unrelated_patterns:
        if re.search(pattern, question_lower):
            return False, "❌ This question appears to be unrelated to the database content. Please ask about customers, payments, plans, regions, or support tickets."
    
    # Check if question is actually asking for data analysis
    data_keywords = [
        'show', 'list', 'get', 'find', 'count', 'sum', 'total', 'average', 'avg',
        'how many', 'what is', 'what are', 'which', 'top', 'bottom', 'highest', 'lowest',
        'analyze', 'analysis', 'trend', 'pattern', 'distribution', 'breakdown',
        'customer', 'payment', 'revenue', 'plan', 'region', 'support', 'ticket'
    ]
    
    has_data_keyword = any(keyword in question_lower for keyword in data_keywords)
    if not has_data_keyword:
        return False, f"❌ Question doesn't appear to be requesting data analysis. Try questions like: {', '.join(get_query_suggestions()[:3])}"
    
    return True, "Valid question"

def debug_question_analysis(question: str) -> Dict[str, Any]:
    """Comprehensive debug analysis of question processing"""
    print(f"\n🔍 DEBUGGING ANALYSIS FOR: '{question}'")
    print("=" * 80)
    
    # Load schema if needed
    if not actual_schema:
        analyzer = DatabaseSchemaAnalyzer()
        analyzer.analyze_schema()
    
    debug_info = {
        'question': question,
        'preprocessing': {},
        'field_extraction': {},
        'validation': {},
        'sql_generation': {},
        'recommendations': []
    }
    
    # Pre-validation
    is_valid, validation_msg = validate_question_before_sql_generation(question)
    debug_info['preprocessing']['pre_validation'] = {'valid': is_valid, 'message': validation_msg}
    print(f"📋 PRE-VALIDATION: {'✅ PASS' if is_valid else '❌ FAIL'} - {validation_msg}")
    
    if not is_valid:
        return debug_info
    
    # Field extraction
    extractor = QueryFieldExtractor()
    requested_fields = extractor.extract_fields(question)
    debug_info['field_extraction']['requested_fields'] = list(requested_fields)
    print(f"📋 REQUESTED FIELDS: {requested_fields if requested_fields else 'None detected'}")
    
    # Field validation
    if requested_fields:
        validator = FieldValidator()
        field_validation = validator.validate_fields(requested_fields)
        debug_info['field_extraction']['validation'] = field_validation
        print(f"\n🔍 FIELD VALIDATION:")
        for field, result in field_validation.items():
            print(f"   {result}")
    
    # Relationship validation
    rel_validator = DataRelationshipValidator()
    relationship_issue = rel_validator.validate_relationships(question)
    debug_info['validation']['relationship_issue'] = relationship_issue
    if relationship_issue:
        print(f"\n🚫 RELATIONSHIP ISSUE:")
        print(relationship_issue)
    else:
        print(f"\n✅ RELATIONSHIP VALIDATION PASSED")
    
    # SQL generation attempt
    try:
        generator = EnhancedSQLGenerator()
        sql_result = generator.generate_sql(question)
        debug_info['sql_generation']['result'] = sql_result
        debug_info['sql_generation']['success'] = not sql_result.startswith('❌')
        
        if debug_info['sql_generation']['success']:
            print(f"\n✅ SQL GENERATED SUCCESSFULLY:")
            print(sql_result)
        else:
            print(f"\n❌ SQL GENERATION FAILED:")
            print(sql_result)
    except Exception as e:
        debug_info['sql_generation']['error'] = str(e)
        print(f"\n💥 SQL GENERATION ERROR: {e}")
    
    # Recommendations
    if not debug_info['sql_generation'].get('success', False):
        suggestions = get_query_suggestions(question)
        debug_info['recommendations'] = suggestions
        print(f"\n💡 SUGGESTED QUESTIONS:")
        for i, suggestion in enumerate(suggestions[:5], 1):
            print(f"   {i}. {suggestion}")
    
    return debug_info

# Main testing and demo functions
def run_comprehensive_tests():
    """Run comprehensive tests of the SQL generation system"""
    test_cases = [
        # Should work - valid questions
        ("How many customers do we have?", True),
        ("Show customer distribution by region", True),
        ("Top 10 customers by revenue", True),
        ("Monthly signup trends", True),
        ("Average payment amount by plan", True),
        ("Support tickets by category", True),
        ("How many years of data do we have?", True),
        ("What is the date range of our data?", True),
        
        # Should be blocked - invalid field requests
        ("Give me customer email addresses", False),
        ("Show me phone numbers of customers", False),
        ("List customer addresses in Europe", False),
        ("Customer age distribution analysis", False),
        ("Show gender breakdown of customers", False),
        ("Product sales by city", False),
        ("Customer salary information", False),
        
        # Should be blocked - impossible relationships
        ("Sales by country", False),
        ("Customer distribution by city", False),
        ("State-wise revenue analysis", False),
        ("Product inventory report", False),
        
        # Edge cases
        ("", False),
        ("What's the weather today?", False),
        ("How to cook pasta?", False),
    ]
    
    print("🧪 RUNNING COMPREHENSIVE TESTS")
    print("=" * 80)
    
    passed = 0
    failed = 0
    
    for question, should_succeed in test_cases:
        print(f"\n📝 Testing: '{question}'")
        
        try:
            result = generate_sql_from_question(question)
            success = not result.startswith('❌')
            
            if success == should_succeed:
                print(f"✅ PASS - Expected: {'Success' if should_succeed else 'Failure'}, Got: {'Success' if success else 'Failure'}")
                passed += 1
            else:
                print(f"❌ FAIL - Expected: {'Success' if should_succeed else 'Failure'}, Got: {'Success' if success else 'Failure'}")
                print(f"   Result: {result[:100]}...")
                failed += 1
                
        except Exception as e:
            print(f"💥 ERROR: {e}")
            if should_succeed:
                failed += 1
            else:
                passed += 1
    
    print(f"\n🏁 TEST RESULTS: {passed} passed, {failed} failed")
    print(f"📊 Performance: {analyze_query_performance()}")
    
    return passed, failed

if __name__ == "__main__":
    print("🚀 Enhanced SQL Generation System")
    print("=" * 50)
    
    # Initialize system
    try:
        analyzer = DatabaseSchemaAnalyzer()
        schema = analyzer.analyze_schema()
        print(f"✅ System initialized with {len(schema['tables'])} tables")
        
        # Show database summary
        summary = get_database_summary()
        print(f"\n📊 DATABASE SUMMARY:")
        print(f"   Total records: {summary['total_records']:,}")
        print(f"   Tables: {', '.join(summary['tables'].keys())}")
        if 'key_metrics' in summary:
            metrics = summary['key_metrics']
            if 'total_customers' in metrics:
                print(f"   Customers: {metrics['total_customers']:,}")
            if 'total_revenue' in metrics:
                print(f"   Total revenue: ${metrics['total_revenue']:,.2f}")
        
        # Run tests
        print(f"\n{'='*50}")
        run_comprehensive_tests()
        
        # Interactive demo
        print(f"\n💡 Try some example questions:")
        suggestions = get_query_suggestions()
        for i, suggestion in enumerate(suggestions[:5], 1):
            print(f"   {i}. {suggestion}")
        
        print(f"\n🔧 Debug any question with: debug_question_analysis('your question')")
        print(f"🧹 Clear caches with: clear_cache()")
        
    except Exception as e:
        print(f"❌ System initialization failed: {e}")
        print("Please check your database connection and configuration.")