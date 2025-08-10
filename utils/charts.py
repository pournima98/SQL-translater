###########
####


# utils/charts.py
# utils/charts.py
import io
import base64
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.cluster import KMeans
from sklearn.preprocessing import LabelEncoder
import re
from collections import Counter

class UniversalChartGenerator:
    def __init__(self):
        self.setup_ml_models()
        
    def setup_ml_models(self):
        """Setup ML models for universal intent recognition"""
        
        # Universal intent patterns (not database-specific)
        self.intent_patterns = {
            'ranking': [
                "top", "best", "highest", "most", "largest", "maximum", "rank", "leading",
                "bottom", "worst", "lowest", "least", "smallest", "minimum"
            ],
            'comparison': [
                "vs", "versus", "compare", "comparison", "against", "difference", "between"
            ],
            'distribution': [
                "by", "across", "distribution", "breakdown", "split", "group", "category"
            ],
            'trend': [
                "over time", "trend", "timeline", "monthly", "daily", "yearly", "quarterly",
                "progression", "change", "growth", "decline"
            ],
            'correlation': [
                "relationship", "correlation", "impact", "effect", "influence", "vs"
            ]
        }
        
        # Create vectorizer for semantic similarity
        self.semantic_vectorizer = TfidfVectorizer(
            stop_words='english', 
            ngram_range=(1, 2),
            max_features=1000
        )
        
    def analyze_dataframe_structure(self, df):
        """Dynamically analyze ANY dataframe to understand its structure"""
        
        analysis = {
            'columns': {},
            'relationships': {},
            'data_types': {},
            'cardinality': {},
            'patterns': {}
        }
        
        for col in df.columns:
            col_analysis = self.analyze_column(df, col)
            analysis['columns'][col] = col_analysis
            
        return analysis
    
    def analyze_column(self, df, col):
        """Universal column analysis that works with any data"""
        
        analysis = {
            'data_type': str(df[col].dtype),
            'is_numeric': pd.api.types.is_numeric_dtype(df[col]),
            'cardinality': df[col].nunique(),
            'cardinality_ratio': df[col].nunique() / len(df),
            'has_nulls': df[col].isnull().sum() > 0,
            'null_ratio': df[col].isnull().sum() / len(df),
            'column_type_prediction': self.predict_column_type(df, col),
            'semantic_meaning': self.extract_semantic_meaning(col)
        }
        
        # Analyze actual values for additional insights
        if analysis['is_numeric']:
            analysis.update(self.analyze_numeric_column(df, col))
        else:
            analysis.update(self.analyze_categorical_column(df, col))
            
        return analysis
    
    def predict_column_type(self, df, col):
        """ML-based prediction of column purpose (works universally)"""
        
        col_lower = col.lower()
        data = df[col]
        
        # Pattern-based classification
        scores = {
            'identifier': 0,
            'categorical': 0, 
            'measure': 0,
            'temporal': 0,
            'descriptive': 0
        }
        
        # Identifier patterns (universal)
        if any(pattern in col_lower for pattern in ['id', 'key', 'code', 'number', 'ref']):
            scores['identifier'] += 5
        
        if data.nunique() == len(data):  # Unique values suggest identifier
            scores['identifier'] += 5
            
        # Categorical patterns (universal)
        if data.dtype == 'object' and data.nunique() < len(data) * 0.5:
            scores['categorical'] += 5
            
        if any(pattern in col_lower for pattern in ['name', 'type', 'category', 'group', 'class', 'status', 'region', 'country']):
            scores['categorical'] += 10
            
        # Measure patterns (universal)
        if pd.api.types.is_numeric_dtype(data):
            scores['measure'] += 5
            
        if any(pattern in col_lower for pattern in ['amount', 'total', 'sum', 'count', 'avg', 'mean', 'sales', 'revenue', 'price', 'cost', 'value', 'score']):
            scores['measure'] += 10
            
        # Temporal patterns (universal)  
        if any(pattern in col_lower for pattern in ['date', 'time', 'year', 'month', 'day', 'created', 'updated']):
            scores['temporal'] += 10
            
        if data.dtype == 'object':
            # Try parsing as datetime
            try:
                pd.to_datetime(data.head(10))
                scores['temporal'] += 8
            except:
                pass
                
        # Descriptive patterns (universal)
        if data.dtype == 'object' and data.nunique() > len(data) * 0.8:
            scores['descriptive'] += 5
            
        return max(scores, key=scores.get)
    
    def analyze_numeric_column(self, df, col):
        """Analyze numeric columns for additional insights"""
        data = df[col]
        
        return {
            'min_value': data.min(),
            'max_value': data.max(),
            'mean_value': data.mean(),
            'std_value': data.std(),
            'is_integer': data.dtype in ['int64', 'int32'],
            'is_positive': (data >= 0).all(),
            'has_outliers': self.detect_outliers(data),
            'distribution_type': self.classify_distribution(data)
        }
    
    def analyze_categorical_column(self, df, col):
        """Analyze categorical columns for patterns"""
        data = df[col]
        
        value_counts = data.value_counts()
        
        return {
            'top_values': value_counts.head(5).to_dict(),
            'is_binary': data.nunique() == 2,
            'is_high_cardinality': data.nunique() > len(data) * 0.7,
            'most_frequent': value_counts.index[0] if len(value_counts) > 0 else None,
            'frequency_distribution': 'uniform' if value_counts.std() < value_counts.mean() * 0.1 else 'skewed'
        }
    
    def detect_outliers(self, data):
        """Simple outlier detection"""
        Q1 = data.quantile(0.25)
        Q3 = data.quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR
        return ((data < lower_bound) | (data > upper_bound)).any()
    
    def classify_distribution(self, data):
        """Classify the distribution type of numeric data"""
        try:
            skewness = data.skew()
            if abs(skewness) < 0.5:
                return 'normal'
            elif skewness > 0.5:
                return 'right_skewed'
            else:
                return 'left_skewed'
        except:
            return 'unknown'
    
    def extract_semantic_meaning(self, col_name):
        """Extract semantic meaning from column names using NLP"""
        
        semantic_categories = {
            'person': ['name', 'customer', 'client', 'user', 'employee', 'staff'],
            'location': ['region', 'country', 'state', 'city', 'address', 'location'],
            'time': ['date', 'time', 'year', 'month', 'day', 'created', 'updated'],
            'financial': ['amount', 'price', 'cost', 'revenue', 'sales', 'payment'],
            'quantity': ['count', 'total', 'sum', 'number', 'quantity'],
            'quality': ['rating', 'score', 'grade', 'rank', 'level'],
            'category': ['type', 'category', 'class', 'group', 'status']
        }
        
        col_lower = col_name.lower()
        
        for category, keywords in semantic_categories.items():
            if any(keyword in col_lower for keyword in keywords):
                return category
                
        return 'general'
    
    def smart_column_selection(self, df, question):
        """Universal smart column selection based on ML analysis"""
        
        df_analysis = self.analyze_dataframe_structure(df)
        question_intent = self.analyze_question_intent(question)
        
        # Score each column for X and Y axis suitability
        x_candidates = []
        y_candidates = []
        
        for col, analysis in df_analysis['columns'].items():
            x_score = self.calculate_x_axis_score(col, analysis, question_intent)
            y_score = self.calculate_y_axis_score(col, analysis, question_intent)
            
            x_candidates.append((col, x_score))
            y_candidates.append((col, y_score))
        
        # Sort by scores
        x_candidates.sort(key=lambda x: x[1], reverse=True)
        y_candidates.sort(key=lambda x: x[1], reverse=True)
        
        # Select best X (avoid identifiers unless no choice)
        best_x = None
        for col, score in x_candidates:
            col_type = df_analysis['columns'][col]['column_type_prediction']
            if col_type != 'identifier' or score > 5:
                best_x = col
                break
        
        if not best_x:
            best_x = x_candidates[0][0]  # Fallback
            
        # Select best Y (different from X)
        best_y = None
        for col, score in y_candidates:
            if col != best_x:
                best_y = col
                break
                
        if not best_y:
            best_y = y_candidates[0][0] if y_candidates[0][0] != best_x else y_candidates[1][0]
        
        return best_x, best_y
    
    def calculate_x_axis_score(self, col, analysis, question_intent):
        """Calculate X-axis suitability score"""
        score = 0
        
        # Categorical data is good for X-axis
        if analysis['column_type_prediction'] == 'categorical':
            score += 10
            
        # Names are excellent for X-axis
        if analysis['semantic_meaning'] in ['person', 'location', 'category']:
            score += 15
            
        # Temporal data good for trends
        if analysis['semantic_meaning'] == 'time' and 'trend' in question_intent['type']:
            score += 15
            
        # Penalize identifiers heavily
        if analysis['column_type_prediction'] == 'identifier':
            score -= 20
            
        # Medium cardinality is good (not too many, not too few categories)
        if 2 <= analysis['cardinality'] <= 50:
            score += 5
        elif analysis['cardinality'] > 100:
            score -= 5
            
        return score
    
    def calculate_y_axis_score(self, col, analysis, question_intent):
        """Calculate Y-axis suitability score"""
        score = 0
        
        # Numeric measures are excellent for Y-axis
        if analysis['column_type_prediction'] == 'measure':
            score += 20
            
        # Financial and quantity semantics
        if analysis['semantic_meaning'] in ['financial', 'quantity', 'quality']:
            score += 15
            
        # Numeric data in general
        if analysis['is_numeric']:
            score += 10
            
        # Question-specific boosts
        if any(keyword in col.lower() for keyword in question_intent['measure_keywords']):
            score += 10
            
        return score
    
    def analyze_question_intent(self, question):
        """Analyze question to understand visualization intent"""
        
        question_lower = question.lower()
        
        intent = {
            'type': 'general',
            'measure_keywords': [],
            'category_keywords': [],
            'temporal_keywords': []
        }
        
        # Extract measure-related keywords
        measure_words = ['sales', 'revenue', 'amount', 'total', 'count', 'sum', 'average', 'price', 'cost', 'value']
        intent['measure_keywords'] = [word for word in measure_words if word in question_lower]
        
        # Extract category keywords  
        category_words = ['customer', 'region', 'product', 'category', 'type', 'group']
        intent['category_keywords'] = [word for word in category_words if word in question_lower]
        
        # Determine intent type
        if any(word in question_lower for word in ['top', 'best', 'highest', 'most']):
            intent['type'] = 'ranking'
        elif any(word in question_lower for word in ['trend', 'over time', 'monthly', 'yearly']):
            intent['type'] = 'trend'  
        elif 'by' in question_lower:
            intent['type'] = 'distribution'
            
        return intent
    
    def determine_chart_type(self, df, x_col, y_col, question_intent):
        """Universal chart type determination"""
        
        x_analysis = self.analyze_column(df, x_col)
        y_analysis = self.analyze_column(df, y_col)
        
        # Time series
        if x_analysis['semantic_meaning'] == 'time' or question_intent['type'] == 'trend':
            return 'line'
            
        # For ranking/top results, always use bar chart regardless of data size
        if question_intent['type'] == 'ranking':
            return 'bar'
            
        # Categorical X-axis - prefer bar charts over pie for better readability
        if x_analysis['column_type_prediction'] in ['categorical', 'descriptive']:
            # Only use pie chart for very specific cases (not ranking/top results)
            if len(df) == 2 and question_intent['type'] not in ['ranking', 'distribution']:
                return 'pie'
            else:
                return 'bar'
                
        # Numeric vs Numeric
        if x_analysis['is_numeric'] and y_analysis['is_numeric']:
            return 'scatter'
            
        return 'bar'  # Safe default
    
    def generate_universal_chart(self, df, question):
        """Main method: Generate chart from any dataframe and question"""
        
        if df.empty:
            raise ValueError("DataFrame is empty")
            
        if len(df.columns) < 2:
            raise ValueError("Need at least 2 columns for visualization")
        
        # Universal ML-based column selection
        x_col, y_col = self.smart_column_selection(df, question)
        
        # Analyze question intent
        question_intent = self.analyze_question_intent(question)
        
        # Determine chart type
        chart_type = self.determine_chart_type(df, x_col, y_col, question_intent)
        
        # Generate title
        title = self.generate_universal_title(x_col, y_col, question, question_intent)
        
        # Create the chart
        return self.create_chart(df, x_col, y_col, chart_type, title)
    
    def create_chart(self, df, x_col, y_col, chart_type, title):
        """Create the actual visualization"""
        
        fig, ax = plt.subplots(figsize=(12, 8))
        
        x = df[x_col]
        y = df[y_col]
        
        if chart_type == 'bar':
            # Always create proper bar chart with single bar for one result
            if len(df) == 1:
                # For single result, create a clean bar chart with proper spacing
                bars = ax.bar([0], y, width=0.6, color='steelblue', alpha=0.8, edgecolor='navy', linewidth=2)
                ax.set_xticks([0])
                ax.set_xticklabels([str(x.iloc[0])], fontsize=11, fontweight='bold')
                ax.set_xlim(-0.8, 0.8)  # Center the single bar
            else:
                bars = ax.bar(range(len(x)), y, color='steelblue', alpha=0.8, edgecolor='navy', linewidth=0.5)
                ax.set_xticks(range(len(x)))
                ax.set_xticklabels(x, rotation=45, ha='right')
            
            # Smart value labeling
            for i, (bar, value) in enumerate(zip(bars, y)):
                height = bar.get_height()
                if pd.api.types.is_numeric_dtype(df[y_col]):
                    label = f'{value:,.0f}' if value >= 1 else f'{value:.2f}'
                else:
                    label = str(value)
                ax.text(bar.get_x() + bar.get_width()/2., height + height*0.01,
                       label, ha='center', va='bottom', fontweight='bold', fontsize=10)
            
            # Better y-axis range for single bars
            if len(df) == 1:
                y_val = y.iloc[0]
                ax.set_ylim(0, y_val * 1.2)  # Give some headroom above the bar
        
        elif chart_type == 'line':
            ax.plot(x, y, marker='o', linewidth=3, markersize=8, color='steelblue', markeredgecolor='navy')
            plt.xticks(rotation=45, ha='right')
            
        elif chart_type == 'pie':
            colors = plt.cm.Set3(np.linspace(0, 1, len(y)))
            ax.pie(y, labels=x, autopct='%1.1f%%', startangle=90, colors=colors)
            
        elif chart_type == 'scatter':
            ax.scatter(x, y, alpha=0.7, s=100, color='steelblue', edgecolor='navy')
        
        # Universal formatting
        if chart_type != 'pie':
            ax.set_xlabel(self.format_column_name(x_col), fontsize=12, fontweight='bold')
            ax.set_ylabel(self.format_column_name(y_col), fontsize=12, fontweight='bold')
            ax.grid(True, alpha=0.3)
            
            # Smart axis formatting
            if pd.api.types.is_numeric_dtype(df[y_col]):
                y_analysis = self.analyze_column(df, y_col)
                if y_analysis['semantic_meaning'] == 'financial':
                    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
        
        ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
        plt.tight_layout()
        
        # Convert to base64
        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=300, bbox_inches='tight', 
                    facecolor='white', edgecolor='none')
        buf.seek(0)
        chart_uri = "data:image/png;base64," + base64.b64encode(buf.read()).decode("utf-8")
        buf.close()
        plt.close(fig)
        
        return chart_uri
    
    def format_column_name(self, col_name):
        """Universal column name formatting"""
        # Remove common prefixes/suffixes
        formatted = re.sub(r'_(id|key|code)$', '', col_name, flags=re.IGNORECASE)
        
        # Replace underscores and capitalize
        formatted = formatted.replace('_', ' ').title()
        
        # Common replacements
        replacements = {
            'Id': 'ID', 'Url': 'URL', 'Api': 'API', 'Avg': 'Average',
            'Min': 'Minimum', 'Max': 'Maximum', 'Std': 'Standard Deviation'
        }
        
        for old, new in replacements.items():
            formatted = formatted.replace(old, new)
            
        return formatted
    
    def generate_universal_title(self, x_col, y_col, question, intent):
        """Generate title based on universal patterns"""
        
        x_formatted = self.format_column_name(x_col)
        y_formatted = self.format_column_name(y_col)
        
        # Intent-based titles
        if intent['type'] == 'ranking':
            if any(word in question.lower() for word in ['top', 'best', 'highest', 'most']):
                return f"Top {x_formatted} by {y_formatted}"
            else:
                return f"Bottom {x_formatted} by {y_formatted}"
        elif intent['type'] == 'trend':
            return f"{y_formatted} Trend Over Time"
        elif intent['type'] == 'distribution':
            return f"{y_formatted} by {x_formatted}"
        
        # Generic fallback
        return f"{y_formatted} by {x_formatted}"


# CRITICAL: Create the backwards-compatible function that app.py expects
def generate_chart_base64(query, engine):
    """
    Backwards-compatible function that your app.py expects.
    This function extracts the question intent from SQL and generates a chart.
    """
    try:
        # Execute the SQL query to get data
        df = pd.read_sql(query, engine)
        
        if df.empty:
            print("❌ No data returned from query")
            return None
            
        print(f"✅ Data loaded: {len(df)} rows, {len(df.columns)} columns")
        
        # Extract a generic "question" from the SQL query for chart generation
        # This is a simple heuristic - you might want to store the original question differently
        question = extract_question_from_sql(query)
        
        # Initialize the chart generator
        chart_gen = UniversalChartGenerator()
        
        # Generate the chart
        chart_uri = chart_gen.generate_universal_chart(df, question)
        
        print("✅ Chart generated successfully")
        return chart_uri
        
    except Exception as e:
        print(f"❌ Error generating chart: {str(e)}")
        return None


def extract_question_from_sql(sql_query):
    """
    Extract intent from SQL query to create a pseudo-question.
    This helps the chart generator understand what kind of visualization to create.
    """
    sql_lower = sql_query.lower()
    
    # Look for common patterns in SQL to infer intent
    if any(word in sql_lower for word in ['top', 'limit']) and any(word in sql_lower for word in ['order by', 'desc']):
        return "Show top ranking results"  # This will trigger ranking intent
    elif 'group by' in sql_lower:
        return "Show breakdown by category"
    elif any(word in sql_lower for word in ['sum', 'count', 'avg', 'average']):
        return "Show aggregated values"
    elif 'where' in sql_lower and any(word in sql_lower for word in ['date', 'time', 'year', 'month']):
        return "Show trends over time"
    else:
        return "Show data analysis results"


# Global instance for reuse (optional optimization)
_chart_generator = None

def get_chart_generator():
    """Get a singleton instance of the chart generator"""
    global _chart_generator
    if _chart_generator is None:
        _chart_generator = UniversalChartGenerator()
    return _chart_generator