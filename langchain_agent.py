import os
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
import openai
import pandas as pd
from sqlalchemy import create_engine
from typing import Dict, List, Tuple, Optional
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

# Global caches for performance
schema_cache = {}
value_cache = {}
cache_initialized = False

# Basic schema matching your existing database
basic_schema = """
You have access to the following MySQL schema:
customers(customer_id, name, signup_date, plan_id, region_id)
subscriptions(subscription_id, customer_id, start_date, end_date, is_active)
usage(customer_id, date, logins, sessions, features_used)
support_tickets(ticket_id, customer_id, category, resolved, time_to_resolve)
payments(payment_id, customer_id, amount, status, payment_date)
plans(plan_id, plan_name, price, features)
regions(region_id, region_name)

RELATIONSHIPS:
- customers.region_id → regions.region_id
- customers.plan_id → plans.plan_id
- Other tables link to customers via customer_id
"""

def get_database_engine():
    """Get database engine - matches your app.py configuration"""
    return create_engine("mysql+pymysql://root:Hemant%40123@localhost:3306/churn_analysis")

def initialize_ai_cache():
    """Load actual values from your existing tables for smart matching"""
    global schema_cache, value_cache, cache_initialized
    
    if cache_initialized:
        return
    
    try:
        engine = get_database_engine()
        
        # Load actual region names from your regions table
        print("🔍 Loading actual data from your database...")
        
        regions_df = pd.read_sql("SELECT region_id, region_name FROM regions", engine)
        if not regions_df.empty:
            value_cache['regions'] = {
                'region_name': regions_df['region_name'].tolist()
            }
            print(f"✅ Loaded {len(regions_df)} regions: {', '.join(regions_df['region_name'].tolist())}")
        
        # Load plan names if plans table exists
        try:
            plans_df = pd.read_sql("SELECT plan_id, plan_name FROM plans LIMIT 10", engine)
            if not plans_df.empty:
                value_cache['plans'] = {
                    'plan_name': plans_df['plan_name'].tolist()
                }
                print(f"✅ Loaded plans: {', '.join(plans_df['plan_name'].tolist())}")
        except:
            print("ℹ️ Plans table not found or empty")
        
        # Load sample customer names
        try:
            customers_df = pd.read_sql("SELECT DISTINCT name FROM customers LIMIT 20", engine)
            if not customers_df.empty:
                value_cache['customers'] = {
                    'name': customers_df['name'].tolist()
                }
                print(f"✅ Loaded {len(customers_df)} customer names")
        except:
            print("ℹ️ Could not load customer names")
            
        cache_initialized = True
        print("🎯 AI cache initialized with your actual data")
        
    except Exception as e:
        print(f"⚠️ Could not initialize AI cache: {e}")

def extract_entities_with_ai(question: str) -> Dict:
    """Extract entities using AI models"""
    if not spacy_available:
        return extract_entities_simple(question)
    
    try:
        doc = nlp(question)
        
        entities = {
            'PERSON': [],
            'ORG': [],
            'GPE': [],  # Geographic/Political entities (regions, countries)
            'LOC': [],  # Locations
            'MONEY': [],
            'DATE': [],
            'CARDINAL': [],  # Numbers
            'ORDINAL': []    # First, second, top, etc.
        }
        
        for ent in doc.ents:
            if ent.label_ in entities:
                entities[ent.label_].append(ent.text.strip())
        
        # Add pattern-based extraction for entities AI might miss
        potential_entities = extract_entities_patterns(question)
        
        return {
            'spacy_entities': entities,
            'potential_entities': potential_entities,
            'has_ai': True
        }
        
    except Exception as e:
        print(f"AI entity extraction failed: {e}")
        return extract_entities_simple(question)

def extract_entities_simple(question: str) -> Dict:
    """Simple pattern-based entity extraction (fallback)"""
    potential_entities = extract_entities_patterns(question)
    
    return {
        'spacy_entities': {'GPE': potential_entities},
        'potential_entities': potential_entities,
        'has_ai': False
    }

def extract_entities_patterns(question: str) -> List[str]:
    """Extract entities using regex patterns"""
    patterns = [
        r'\bin\s+([A-Z][a-zA-Z\s]+?)(?:\s|$|,|\?)',      # "in Europe"
        r'([A-Z][a-zA-Z\s]+?)\s+customers',              # "Europe customers"  
        r'from\s+([A-Z][a-zA-Z\s]+?)(?:\s|$|,|\?)',      # "from Asia"
        r'([A-Z][a-zA-Z\s]+?)\s+region',                 # "Europe region"
        r'([A-Z][a-zA-Z\s]+?)\s+plan',                   # "Premium plan"
        r'with\s+([A-Z][a-zA-Z\s]+?)\s+plan',           # "with Premium plan"
    ]
    
    entities = []
    for pattern in patterns:
        matches = re.findall(pattern, question)
        entities.extend([match.strip() for match in matches if len(match.strip()) > 1])
    
    return list(set(entities))

def find_semantic_matches(entity: str) -> List[Tuple[str, str, float, str]]:
    """Find matches between entities and your actual database values"""
    matches = []
    entity_lower = entity.lower().strip()
    
    if not value_cache:
        return matches
    
    # Check against actual region names from your database
    if 'regions' in value_cache and 'region_name' in value_cache['regions']:
        for region_name in value_cache['regions']['region_name']:
            region_lower = region_name.lower()
            
            # Exact match
            if entity_lower == region_lower:
                matches.append(('regions', 'region_name', 1.0, region_name))
            # Partial match
            elif entity_lower in region_lower or region_lower in entity_lower:
                matches.append(('regions', 'region_name', 0.8, region_name))
    
    # Check against plan names if available
    if 'plans' in value_cache and 'plan_name' in value_cache['plans']:
        for plan_name in value_cache['plans']['plan_name']:
            plan_lower = plan_name.lower()
            
            if entity_lower == plan_lower:
                matches.append(('plans', 'plan_name', 1.0, plan_name))
            elif entity_lower in plan_lower or plan_lower in entity_lower:
                matches.append(('plans', 'plan_name', 0.8, plan_name))
    
    # Use AI semantic matching if available
    if transformers_available and len(matches) == 0:
        try:
            matches.extend(find_ai_semantic_matches(entity))
        except Exception as e:
            print(f"AI semantic matching failed: {e}")
    
    # Sort by confidence
    matches.sort(key=lambda x: x[2], reverse=True)
    return matches[:3]  # Top 3 matches

def find_ai_semantic_matches(entity: str) -> List[Tuple[str, str, float, str]]:
    """Use AI for semantic matching when simple matching fails"""
    matches = []
    entity_embedding = sentence_model.encode([entity.lower()])
    
    for table, columns in value_cache.items():
        for column, values in columns.items():
            if not values:
                continue
                
            try:
                value_embeddings = sentence_model.encode([str(v).lower() for v in values])
                similarities = np.dot(entity_embedding, value_embeddings.T)[0]
                
                for i, similarity in enumerate(similarities):
                    if similarity > 0.7:  # High threshold for AI matches
                        matches.append((table, column, similarity, values[i]))
            except:
                continue
    
    return matches

def create_enhanced_schema(entities: Dict) -> str:
    """Create enhanced schema with entity context from your actual data"""
    schema_text = basic_schema
    
    # Collect all entities
    all_entities = []
    for ent_list in entities['spacy_entities'].values():
        all_entities.extend(ent_list)
    all_entities.extend(entities['potential_entities'])
    
    if all_entities:
        schema_text += "\nDetected Entities and Matches in Your Database:\n"
        
        for entity in set(all_entities):
            matches = find_semantic_matches(entity)
            if matches:
                schema_text += f"'{entity}' matches:\n"
                for table, column, confidence, example in matches:
                    schema_text += f"  - {table}.{column} = '{example}' (confidence: {confidence:.2f})\n"
    
    return schema_text

# Enhanced prompt template
enhanced_prompt_template = PromptTemplate.from_template("""
You are an expert SQL generator working with the user's actual database schema and data.

{schema}

CRITICAL INSTRUCTIONS:
1. Use the entity matches above to write correct JOINs
2. When you see geographic entities (Europe, Asia, etc.), JOIN customers with regions table
3. When you see plan-related entities, JOIN customers with plans table
4. For "top N" queries, ORDER BY appropriate metrics (payments, usage) with LIMIT
5. Use exact matching with the detected entity values
6. Always use proper JOIN syntax
7. For payment totals, consider filtering WHERE status = 'completed'

EXAMPLE PATTERNS:
- "customers in Europe" → JOIN customers c WITH regions r ON c.region_id = r.region_id WHERE r.region_name = 'Europe'
- "top 10 customers" → ORDER BY SUM(payment_amount) DESC LIMIT 10
- "premium customers" → JOIN with plans table WHERE plan_name = 'Premium'

Question: {question}

Generate only the MySQL query:
""")

# Fallback prompt
simple_prompt_template = PromptTemplate.from_template("""
Given the following schema:
{schema}

Important: When geographic terms like "Europe", "Asia" are mentioned, you need to:
1. JOIN customers table with regions table  
2. Match on regions.region_name = 'EntityName'

Question: {question}

SQL:
""")

def generate_sql_from_question(question: str) -> str:
    """
    Generate SQL using your actual database structure and values
    """
    try:
        # Initialize cache with your actual data
        if not cache_initialized:
            initialize_ai_cache()
        
        # Extract entities (with or without AI)
        entities = extract_entities_with_ai(question)
        
        # Create enhanced schema with your actual data
        enhanced_schema = create_enhanced_schema(entities)
        
        # Choose prompt based on available features
        if entities['has_ai'] or any(entities['spacy_entities'].values()) or entities['potential_entities']:
            prompt = enhanced_prompt_template.format(
                schema=enhanced_schema, 
                question=question
            )
            print(f"🎯 Using enhanced generation with entity matches")
        else:
            prompt = simple_prompt_template.format(
                schema=basic_schema,
                question=question
            )
            print(f"📝 Using basic generation")
        
        # Generate SQL
        response = llm.predict(prompt)
        sql_query = response.strip()
        
        # Clean up response
        if sql_query.startswith('```'):
            lines = sql_query.split('\n')
            sql_query = '\n'.join([line for line in lines if not line.strip().startswith('```')])
            sql_query = sql_query.strip()
        
        return sql_query
        
    except Exception as e:
        print(f"Error in SQL generation: {e}")
        return f"-- Error generating SQL: {str(e)}"

# Debug function
def debug_entity_extraction(question: str):
    """Debug what the system detects in your database"""
    print(f"\n🔍 Analyzing: '{question}'")
    print("=" * 50)
    
    if not cache_initialized:
        initialize_ai_cache()
    
    entities = extract_entities_with_ai(question)
    
    print(f"AI Available: {entities['has_ai']}")
    print(f"SpaCy Entities: {entities['spacy_entities']}")
    print(f"Pattern Entities: {entities['potential_entities']}")
    
    # Show what matches we find in your actual database
    all_entities = []
    for ent_list in entities['spacy_entities'].values():
        all_entities.extend(ent_list)
    all_entities.extend(entities['potential_entities'])
    
    for entity in set(all_entities):
        matches = find_semantic_matches(entity)
        if matches:
            print(f"\n🎯 '{entity}' matches in your database:")
            for table, column, score, example in matches:
                print(f"   {table}.{column} = '{example}' (confidence: {score:.2f})")
        else:
            print(f"\n❌ No matches found for '{entity}'")

if __name__ == "__main__":
    # Test with your actual database
    test_questions = [
        "What are top 10 customers?",
        "Top 10 customers in Europe", 
        "How many customers in Asia?",
        "Show me premium customers",
        "Revenue by region"
    ]
    
    print("🧪 Testing with your actual database...")
    
    for question in test_questions:
        debug_entity_extraction(question)
        sql = generate_sql_from_question(question)
        print(f"\n📝 Generated SQL:\n{sql}")
        print("\n" + "="*60)