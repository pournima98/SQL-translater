# utils/charts.py - FIXED VERSION with corrected column selection
import io
import base64
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
import re
from collections import Counter
from datetime import datetime

class EnhancedChartGenerator:
    def __init__(self):
        self.setup_chart_patterns()
        
    def setup_chart_patterns(self):
        """Setup patterns for intelligent chart generation"""
        
        # SQL query patterns to understand data intent
        self.query_patterns = {
            'time_series': [
                r'group\s+by\s+year',
                r'group\s+by\s+month',
                r'group\s+by\s+date',
                r'order\s+by\s+.*date',
                r'extract\s*\(\s*year',
                r'date_format\s*\(',
                r'year\s*\(',
                r'month\s*\('
            ],
            'ranking': [
                r'order\s+by\s+.*\s+desc\s+limit',
                r'top\s+\d+',
                r'limit\s+\d+',
                r'order\s+by.*desc.*limit',
                r'max\s*\(',
                r'greatest\s*\(',
                r'sum\s*\(',  # Often indicates ranking by totals
                r'total_'     # Common pattern for ranking queries
            ],
            'comparison': [
                r'group\s+by\s+(?!.*date)(?!.*year)(?!.*month)',
                r'by\s+region',
                r'by\s+category',
                r'by\s+type',
                r'by\s+plan'
            ],
            'aggregation': [
                r'sum\s*\(',
                r'count\s*\(',
                r'avg\s*\(',
                r'average\s*\(',
                r'total'
            ]
        }
        
        # Column type inference patterns - IMPROVED
        self.column_patterns = {
            'date': [r'date', r'time', r'year', r'month', r'created', r'updated'],
            'money': [r'amount', r'revenue', r'sales', r'price', r'cost', r'payment', r'total_sales', r'total_amount'],
            'count': [r'count', r'total_count', r'number', r'quantity', r'^total$'],
            'name': [r'name', r'title', r'label', r'description'],
            'category': [r'region', r'type', r'category', r'status', r'plan', r'group'],
            'id': [r'_id$', r'^id', r'key$', r'code$', r'customer_id$', r'payment_id$']
        }
    
    def analyze_sql_query(self, sql_query):
        """Analyze SQL query to understand visualization intent"""
        sql_lower = sql_query.lower()
        
        intent = {
            'type': 'comparison',  # default
            'is_time_series': False,
            'is_ranking': False,
            'is_aggregation': False,
            'has_limit': False,
            'groupby_columns': [],
            'select_columns': []
        }
        
        # Check for time series
        for pattern in self.query_patterns['time_series']:
            if re.search(pattern, sql_lower):
                intent['type'] = 'time_series'
                intent['is_time_series'] = True
                break
        
        # Check for ranking
        for pattern in self.query_patterns['ranking']:
            if re.search(pattern, sql_lower):
                intent['is_ranking'] = True
                if 'limit' in sql_lower:
                    intent['has_limit'] = True
                # If it's not time series but has ranking, make it comparison
                if not intent['is_time_series']:
                    intent['type'] = 'ranking'
                break
        
        # Check for aggregation
        for pattern in self.query_patterns['aggregation']:
            if re.search(pattern, sql_lower):
                intent['is_aggregation'] = True
                break
        
        # Extract GROUP BY columns
        group_by_match = re.search(r'group\s+by\s+([^having|^order|^limit]+)', sql_lower)
        if group_by_match:
            group_cols = group_by_match.group(1).strip().split(',')
            intent['groupby_columns'] = [col.strip() for col in group_cols]
        
        return intent
    
    def classify_column_type(self, column_name, data_series):
        """Classify column type based on name and data - IMPROVED"""
        col_lower = column_name.lower()
        
        # Check patterns first
        for col_type, patterns in self.column_patterns.items():
            if any(re.search(pattern, col_lower) for pattern in patterns):
                return col_type
        
        # Check data characteristics
        if pd.api.types.is_numeric_dtype(data_series):
            unique_ratio = data_series.nunique() / len(data_series)
            
            # Check if it's likely an ID (high uniqueness)
            if unique_ratio > 0.95:
                return 'id'
            # Check if it contains typical money values
            elif any(keyword in col_lower for keyword in ['sales', 'amount', 'revenue', 'payment', 'total']):
                return 'money'
            # Check if it's count-like (integers >= 0)
            elif data_series.dtype in ['int64', 'int32'] and data_series.min() >= 0:
                return 'count'
            else:
                return 'measure'
        
        # For text data
        if data_series.dtype == 'object':
            unique_count = data_series.nunique()
            if unique_count <= 20:  # Limited categories
                return 'category'
            else:
                return 'name'
        
        return 'unknown'
    
    def preprocess_dataframe(self, df, sql_query):
        """Preprocess dataframe for better visualization"""
        
        # Remove any columns that are just row indices
        df = df.reset_index(drop=True)
        
        # Handle date columns
        for col in df.columns:
            if df[col].dtype == 'object':
                # Try to parse as datetime
                try:
                    # Check if it looks like a date
                    sample = df[col].dropna().head(5)
                    if len(sample) > 0:
                        parsed = pd.to_datetime(sample, errors='coerce')
                        if not parsed.isna().all():
                            df[col] = pd.to_datetime(df[col], errors='coerce')
                except:
                    pass
        
        # Handle numeric columns that should be integers
        for col in df.columns:
            if pd.api.types.is_numeric_dtype(df[col]):
                try:
                    # Check if it's a float column with integer-like values
                    if df[col].dtype == 'float64':
                        # Use .all() to check if ALL values are integers when modulo 1 equals 0
                        non_null_values = df[col].fillna(0)
                        if (non_null_values % 1 == 0).all():
                            df[col] = df[col].fillna(0).astype('int64')
                except Exception as e:
                    # If conversion fails, skip this column
                    print(f"Warning: Could not convert {col} to integer: {e}")
                    continue
        
        # Sort data logically
        intent = self.analyze_sql_query(sql_query)
        
        if intent['is_time_series']:
            # Find date column and sort by it
            date_cols = [col for col in df.columns if 'date' in col.lower() or 'year' in col.lower() or 'month' in col.lower()]
            if date_cols:
                df = df.sort_values(date_cols[0])
        elif intent['is_ranking']:
            # Sort by numeric columns descending (but not ID columns)
            numeric_cols = [col for col in df.select_dtypes(include=[np.number]).columns 
                          if self.classify_column_type(col, df[col]) != 'id']
            if len(numeric_cols) > 0:
                df = df.sort_values(numeric_cols[0], ascending=False)
        
        return df
    
    def smart_column_selection(self, df, sql_intent):
        """FIXED: Intelligently select X and Y columns based on data and query intent"""
        
        if len(df.columns) < 2:
            raise ValueError("Need at least 2 columns for visualization")
        
        columns_info = {}
        for col in df.columns:
            col_type = self.classify_column_type(col, df[col])
            columns_info[col] = {
                'type': col_type,
                'is_numeric': pd.api.types.is_numeric_dtype(df[col]),
                'cardinality': df[col].nunique(),
                'has_nulls': df[col].isna().sum() > 0
            }
        
        print(f"DEBUG - Column types: {[(col, info['type']) for col, info in columns_info.items()]}")
        
        # Smart selection based on query intent
        x_col, y_col = None, None
        
        if sql_intent['is_time_series']:
            # X should be time, Y should be measure
            time_cols = [col for col, info in columns_info.items() 
                        if info['type'] in ['date'] or 'year' in col.lower() or 'month' in col.lower()]
            measure_cols = [col for col, info in columns_info.items() 
                          if info['is_numeric'] and info['type'] in ['count', 'money', 'measure']]
            
            if time_cols:
                x_col = time_cols[0]
            if measure_cols:
                y_col = measure_cols[0]
        
        elif sql_intent['is_ranking'] or sql_intent['is_aggregation']:
            # X should be categorical/name, Y should be the measure we're ranking by
            # FIXED: Prioritize non-ID columns for categorical axis
            cat_cols = [col for col, info in columns_info.items() 
                       if info['type'] in ['category', 'name'] and info['cardinality'] <= 50]
            # FIXED: Prioritize money/measure columns over IDs for Y-axis
            measure_cols = [col for col, info in columns_info.items() 
                          if info['is_numeric'] and info['type'] in ['money', 'count', 'measure']]
            
            if cat_cols and measure_cols:
                x_col = cat_cols[0]
                y_col = measure_cols[0]
        
        else:
            # Default: categorical for X, numeric for Y (but avoid IDs)
            cat_cols = [col for col, info in columns_info.items() 
                       if not info['is_numeric'] or info['type'] == 'category']
            num_cols = [col for col, info in columns_info.items() 
                       if info['is_numeric'] and info['type'] != 'id']
            
            if cat_cols and num_cols:
                x_col = cat_cols[0]
                y_col = num_cols[0]
        
        # Fallback: pick smartly from available columns, avoiding IDs when possible
        if not x_col or not y_col:
            cols = list(df.columns)
            
            # For X-axis, prefer non-numeric or categorical
            if not x_col:
                non_numeric_cols = [col for col in cols if not pd.api.types.is_numeric_dtype(df[col])]
                x_col = non_numeric_cols[0] if non_numeric_cols else cols[0]
            
            # For Y-axis, prefer numeric non-ID columns
            if not y_col:
                numeric_non_id_cols = [col for col in cols 
                                     if pd.api.types.is_numeric_dtype(df[col]) 
                                     and self.classify_column_type(col, df[col]) != 'id'
                                     and col != x_col]
                if numeric_non_id_cols:
                    y_col = numeric_non_id_cols[0]
                else:
                    # Last resort: pick any column that's not x_col
                    y_col = [col for col in cols if col != x_col][0]
        
        print(f"DEBUG - Selected: X={x_col} (type: {columns_info[x_col]['type']}), Y={y_col} (type: {columns_info[y_col]['type']})")
        
        return x_col, y_col
    
    def determine_chart_type(self, df, x_col, y_col, sql_intent):
        """Determine the best chart type based on data and intent"""
        
        x_info = {
            'type': self.classify_column_type(x_col, df[x_col]),
            'is_numeric': pd.api.types.is_numeric_dtype(df[x_col]),
            'cardinality': df[x_col].nunique()
        }
        
        y_info = {
            'type': self.classify_column_type(y_col, df[y_col]),
            'is_numeric': pd.api.types.is_numeric_dtype(df[y_col])
        }
        
        # Time series = line chart
        if sql_intent['is_time_series'] or x_info['type'] == 'date':
            return 'line'
        
        # SPECIFIC: Regional data = pie chart
        if (not x_info['is_numeric'] and y_info['is_numeric'] and 
            any(keyword in x_col.lower() for keyword in ['region', 'area', 'location']) and
            x_info['cardinality'] <= 8):  # Reasonable limit for regions
            return 'pie'
        
        # Ranking with limit = bar chart
        if sql_intent['is_ranking'] or sql_intent['has_limit']:
            return 'bar'
        
        # Two numeric columns = scatter (but only if makes sense)
        if x_info['is_numeric'] and y_info['is_numeric'] and not sql_intent['is_ranking']:
            # Avoid scatter for obvious categorical data
            if x_info['cardinality'] > 10 and y_info['cardinality'] > 10:
                return 'scatter'
        
        # Categorical vs numeric = bar or pie
        if not x_info['is_numeric'] and y_info['is_numeric']:
            # Pie chart only for very small datasets (original logic)
            if len(df) <= 5 and x_info['cardinality'] <= 5:
                return 'pie'
            else:
                return 'bar'
        
        # Default to bar chart
        return 'bar'
    
    def create_smart_title(self, df, x_col, y_col, sql_intent, chart_type):
        """Generate intelligent titles based on data and intent"""
        
        x_formatted = self.format_column_name(x_col)
        y_formatted = self.format_column_name(y_col)
        
        if sql_intent['is_ranking'] and sql_intent['has_limit']:
            return f"Top {len(df)} {x_formatted} by {y_formatted}"
        elif sql_intent['is_time_series']:
            return f"{y_formatted} Over Time"
        elif chart_type == 'pie':
            return f"{y_formatted} Distribution"
        elif chart_type == 'scatter':
            return f"{y_formatted} vs {x_formatted}"
        else:
            return f"{y_formatted} by {x_formatted}"
    
    def format_column_name(self, col_name):
        """Format column names for display"""
        # Handle common SQL aliases
        formatted = col_name.replace('_', ' ').title()
        
        # Handle common patterns
        replacements = {
            'Id': 'ID',
            'Url': 'URL', 
            'Api': 'API',
            'Sum(': 'Total ',
            'Count(': 'Count of ',
            'Avg(': 'Average ',
            'Max(': 'Maximum ',
            'Min(': 'Minimum ',
            'Total Sales': 'Total Sales',
            'Customer Id': 'Customer ID'
        }
        
        for old, new in replacements.items():
            formatted = formatted.replace(old, new)
        
        # Clean up parentheses
        formatted = re.sub(r'\([^)]*\)', '', formatted).strip()
        
        return formatted
    
    def create_visualization(self, df, x_col, y_col, chart_type, title):
        """Create the actual chart"""
        
        # Set up the plot
        plt.style.use('default')
        fig, ax = plt.subplots(figsize=(12, 8))
        
        # Get data
        x_data = df[x_col]
        y_data = df[y_col]
        
        if chart_type == 'line':
            # Handle datetime x-axis
            if pd.api.types.is_datetime64_any_dtype(x_data):
                ax.plot(x_data, y_data, marker='o', linewidth=3, markersize=8, 
                       color='steelblue', markerfacecolor='white', 
                       markeredgecolor='steelblue', markeredgewidth=2)
            else:
                ax.plot(range(len(x_data)), y_data, marker='o', linewidth=3, markersize=8,
                       color='steelblue', markerfacecolor='white', 
                       markeredgecolor='steelblue', markeredgewidth=2)
                ax.set_xticks(range(len(x_data)))
                ax.set_xticklabels(x_data, rotation=45, ha='right')
            
            ax.grid(True, alpha=0.3)
            
        elif chart_type == 'bar':
            colors = plt.cm.Set3(np.linspace(0, 1, len(df))) if len(df) > 1 else ['steelblue']
            bars = ax.bar(range(len(x_data)), y_data, color=colors, alpha=0.8, 
                         edgecolor='navy', linewidth=0.5)
            
            # Add value labels on bars
            for bar, value in zip(bars, y_data):
                height = bar.get_height()
                if pd.api.types.is_numeric_dtype(df[y_col]):
                    if abs(value) >= 1000:
                        label = f'{value:,.0f}'
                    elif abs(value) >= 1:
                        label = f'{value:.1f}'
                    else:
                        label = f'{value:.2f}'
                else:
                    label = str(value)
                    
                ax.text(bar.get_x() + bar.get_width()/2., height + abs(height)*0.01,
                       label, ha='center', va='bottom', fontweight='bold', fontsize=10)
            
            # Set x-tick labels
            ax.set_xticks(range(len(x_data)))
            # Truncate long labels
            labels = [str(label)[:20] + '...' if len(str(label)) > 20 else str(label) for label in x_data]
            ax.set_xticklabels(labels, rotation=45, ha='right')
            
            # Adjust y-axis to give space for labels
            y_max = max(y_data) if len(y_data) > 0 else 0
            ax.set_ylim(0, y_max * 1.15)
            
        elif chart_type == 'pie':
            colors = plt.cm.Set3(np.linspace(0, 1, len(df)))
            wedges, texts, autotexts = ax.pie(y_data, labels=x_data, autopct='%1.1f%%', 
                                            startangle=90, colors=colors)
            # Make percentage text bold
            for autotext in autotexts:
                autotext.set_fontweight('bold')
                
        elif chart_type == 'scatter':
            ax.scatter(x_data, y_data, alpha=0.7, s=100, color='steelblue', 
                      edgecolor='navy', linewidth=1)
            ax.grid(True, alpha=0.3)
        
        # Formatting
        if chart_type != 'pie':
            ax.set_xlabel(self.format_column_name(x_col), fontsize=12, fontweight='bold')
            ax.set_ylabel(self.format_column_name(y_col), fontsize=12, fontweight='bold')
            
            # Smart Y-axis formatting
            if pd.api.types.is_numeric_dtype(df[y_col]):
                y_type = self.classify_column_type(y_col, df[y_col])
                if y_type == 'money':
                    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}' if abs(x) >= 1 else f'${x:.2f}'))
                elif y_type == 'count' and df[y_col].dtype in ['int64', 'int32']:
                    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x):,}'))
        
        # Title and layout
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
    
    def generate_chart_from_query(self, df, sql_query, user_question=None):
        """Main method: Generate chart from dataframe and SQL query"""
        
        if df is None or df.empty:
            raise ValueError("DataFrame is empty or None")
        
        print(f"📊 Generating chart for {len(df)} rows, {len(df.columns)} columns")
        print(f"Columns: {list(df.columns)}")
        
        # Preprocess data
        df = self.preprocess_dataframe(df, sql_query)
        
        # Analyze SQL intent
        sql_intent = self.analyze_sql_query(sql_query)
        print(f"🎯 Detected intent: {sql_intent['type']}")
        
        # Smart column selection
        x_col, y_col = self.smart_column_selection(df, sql_intent)
        print(f"📈 Selected columns: X={x_col}, Y={y_col}")
        
        # Determine chart type
        chart_type = self.determine_chart_type(df, x_col, y_col, sql_intent)
        print(f"📊 Chart type: {chart_type}")
        
        # Create title
        title = self.create_smart_title(df, x_col, y_col, sql_intent, chart_type)
        
        # Generate visualization
        return self.create_visualization(df, x_col, y_col, chart_type, title)


def generate_chart_base64(query, engine):
    """
    FIXED backwards-compatible function for app.py
    """
    try:
        print(f"🔍 Executing SQL: {query[:100]}...")
        
        # Execute query
        df = pd.read_sql(query, engine)
        
        if df.empty:
            print("❌ Query returned no data")
            return None
            
        print(f"✅ Data loaded: {len(df)} rows, {len(df.columns)} columns")
        print(f"Sample data:\n{df.head()}")
        
        # Initialize enhanced chart generator
        chart_gen = EnhancedChartGenerator()
        
        # Generate chart
        chart_uri = chart_gen.generate_chart_from_query(df, query)
        
        print("✅ Chart generated successfully")
        return chart_uri
        
    except Exception as e:
        print(f"❌ Chart generation failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return None