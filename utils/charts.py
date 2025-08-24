# utils/charts.py - FIXED VERSION with proper time series handling
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
                r'extract\s*\(\s*month',
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
                r'sum\s*\(',
                r'total_'
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
            'date': [r'date', r'time', r'created', r'updated'],
            'year': [r'^year$', r'yr$'],
            'month': [r'^month$', r'mon$', r'month_num'],
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
            'type': 'comparison',
            'is_time_series': False,
            'is_ranking': False,
            'is_aggregation': False,
            'has_limit': False,
            'groupby_columns': [],
            'select_columns': []
        }
        
        # Check for time series patterns
        for pattern in self.query_patterns['time_series']:
            if re.search(pattern, sql_lower):
                intent['type'] = 'time_series'
                intent['is_time_series'] = True
                print(f"🕒 Detected time series pattern: {pattern}")
                break
        
        # Check for ranking
        for pattern in self.query_patterns['ranking']:
            if re.search(pattern, sql_lower):
                intent['is_ranking'] = True
                if 'limit' in sql_lower:
                    intent['has_limit'] = True
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
            if unique_count <= 20:
                return 'category'
            else:
                return 'name'
        
        return 'unknown'
    
    def preprocess_dataframe(self, df, sql_query):
        """Preprocess dataframe for better visualization"""
        
        # Reset index
        df = df.reset_index(drop=True)
        
        # Handle date columns
        for col in df.columns:
            if df[col].dtype == 'object':
                try:
                    sample = df[col].dropna().head(5)
                    if len(sample) > 0:
                        parsed = pd.to_datetime(sample, errors='coerce')
                        if not parsed.isna().all():
                            df[col] = pd.to_datetime(df[col], errors='coerce')
                except:
                    pass
        
        # Handle numeric columns
        for col in df.columns:
            if pd.api.types.is_numeric_dtype(df[col]):
                try:
                    if df[col].dtype == 'float64':
                        non_null_values = df[col].fillna(0)
                        if (non_null_values % 1 == 0).all():
                            df[col] = df[col].fillna(0).astype('int64')
                except Exception as e:
                    print(f"Warning: Could not convert {col} to integer: {e}")
                    continue
        
        # FIXED: Better sorting for time series data
        intent = self.analyze_sql_query(sql_query)
        
        if intent['is_time_series']:
            # Try to sort by year, then month
            if 'year' in df.columns and 'month' in df.columns:
                df = df.sort_values(['year', 'month'])
                print("✅ Sorted by year and month")
            elif any('year' in str(col).lower() for col in df.columns):
                year_col = [col for col in df.columns if 'year' in str(col).lower()][0]
                month_col = [col for col in df.columns if 'month' in str(col).lower()]
                if month_col:
                    df = df.sort_values([year_col, month_col[0]])
                    print(f"✅ Sorted by {year_col} and {month_col[0]}")
                else:
                    df = df.sort_values(year_col)
                    print(f"✅ Sorted by {year_col}")
            else:
                # Find date column
                date_cols = [col for col in df.columns if 'date' in col.lower()]
                if date_cols:
                    df = df.sort_values(date_cols[0])
                    print(f"✅ Sorted by {date_cols[0]}")
        elif intent['is_ranking']:
            # Sort by numeric columns descending
            numeric_cols = [col for col in df.select_dtypes(include=[np.number]).columns 
                          if self.classify_column_type(col, df[col]) != 'id']
            if len(numeric_cols) > 0:
                df = df.sort_values(numeric_cols[0], ascending=False)
        
        return df
    
    def smart_column_selection(self, df, sql_intent):
        """FIXED: Better column selection for time series"""
        
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
        
        x_col, y_col = None, None
        
        if sql_intent['is_time_series']:
            # For time series, we need to create a proper time axis
            time_cols = []
            
            # Look for year and month columns
            year_cols = [col for col, info in columns_info.items() if info['type'] == 'year' or 'year' in col.lower()]
            month_cols = [col for col, info in columns_info.items() if info['type'] == 'month' or 'month' in col.lower()]
            
            if year_cols and month_cols:
                # We have both year and month - create a combined time axis
                x_col = 'time_period'  # We'll create this
                print(f"🕒 Will create time_period from {year_cols[0]} and {month_cols[0]}")
            elif year_cols:
                x_col = year_cols[0]
            elif month_cols:
                x_col = month_cols[0]
            else:
                # Look for date columns
                date_cols = [col for col, info in columns_info.items() if info['type'] == 'date']
                if date_cols:
                    x_col = date_cols[0]
            
            # Y should be the measure
            measure_cols = [col for col, info in columns_info.items() 
                          if info['is_numeric'] and info['type'] in ['count', 'money', 'measure']]
            if measure_cols:
                y_col = measure_cols[0]
        
        elif sql_intent['is_ranking'] or sql_intent['is_aggregation']:
            # X should be categorical, Y should be measure
            cat_cols = [col for col, info in columns_info.items() 
                       if info['type'] in ['category', 'name'] and info['cardinality'] <= 50]
            measure_cols = [col for col, info in columns_info.items() 
                          if info['is_numeric'] and info['type'] in ['money', 'count', 'measure']]
            
            if cat_cols and measure_cols:
                x_col = cat_cols[0]
                y_col = measure_cols[0]
        
        else:
            # Default selection
            cat_cols = [col for col, info in columns_info.items() 
                       if not info['is_numeric'] or info['type'] == 'category']
            num_cols = [col for col, info in columns_info.items() 
                       if info['is_numeric'] and info['type'] != 'id']
            
            if cat_cols and num_cols:
                x_col = cat_cols[0]
                y_col = num_cols[0]
        
        # Fallback selection
        if not x_col or not y_col:
            cols = list(df.columns)
            
            if not x_col:
                non_numeric_cols = [col for col in cols if not pd.api.types.is_numeric_dtype(df[col])]
                x_col = non_numeric_cols[0] if non_numeric_cols else cols[0]
            
            if not y_col:
                numeric_non_id_cols = [col for col in cols 
                                     if pd.api.types.is_numeric_dtype(df[col]) 
                                     and self.classify_column_type(col, df[col]) != 'id'
                                     and col != x_col]
                if numeric_non_id_cols:
                    y_col = numeric_non_id_cols[0]
                else:
                    y_col = [col for col in cols if col != x_col][0]
        
        print(f"DEBUG - Selected: X={x_col}, Y={y_col}")
        
        return x_col, y_col
    
    def create_time_period_column(self, df):
        """Create a proper time period column for time series charts"""
        try:
            # Look for year and month columns
            year_col = None
            month_col = None
            
            for col in df.columns:
                if 'year' in col.lower():
                    year_col = col
                elif 'month' in col.lower():
                    month_col = col
            
            if year_col and month_col:
                # Create a proper datetime or string representation
                df['time_period'] = df[year_col].astype(str) + '-' + df[month_col].astype(str).str.zfill(2)
                
                # Try to convert to datetime for better sorting and display
                try:
                    df['time_period_dt'] = pd.to_datetime(df['time_period'], format='%Y-%m')
                    df = df.sort_values('time_period_dt')
                    # Use the string version for display but sorted by datetime
                    print("✅ Created time_period column with datetime sorting")
                except:
                    # Fallback to string sorting
                    df = df.sort_values('time_period')
                    print("✅ Created time_period column with string sorting")
                
                return df, 'time_period'
            
        except Exception as e:
            print(f"❌ Error creating time period column: {e}")
        
        return df, None
    
    def determine_chart_type(self, df, x_col, y_col, sql_intent):
        """Determine the best chart type based on data and intent"""
        
        x_info = {
            'type': self.classify_column_type(x_col, df[x_col]) if x_col in df.columns else 'unknown',
            'is_numeric': pd.api.types.is_numeric_dtype(df[x_col]) if x_col in df.columns else False,
            'cardinality': df[x_col].nunique() if x_col in df.columns else 0
        }
        
        y_info = {
            'type': self.classify_column_type(y_col, df[y_col]),
            'is_numeric': pd.api.types.is_numeric_dtype(df[y_col])
        }
        
        print(f"📊 Chart type analysis: X={x_info}, Y={y_info}, Intent={sql_intent['type']}")
        
        # Time series = line chart
        if sql_intent['is_time_series'] or x_col == 'time_period':
            print("📈 Selecting line chart for time series")
            return 'line'
        
        # Regional data = pie chart
        if (not x_info['is_numeric'] and y_info['is_numeric'] and 
            any(keyword in x_col.lower() for keyword in ['region', 'area', 'location']) and
            x_info['cardinality'] <= 8):
            return 'pie'
        
        # Ranking with limit = bar chart
        if sql_intent['is_ranking'] or sql_intent['has_limit']:
            return 'bar'
        
        # Two numeric columns = scatter
        if x_info['is_numeric'] and y_info['is_numeric'] and not sql_intent['is_ranking']:
            if x_info['cardinality'] > 10 and y_info['cardinality'] > 10:
                return 'scatter'
        
        # Categorical vs numeric = bar or pie
        if not x_info['is_numeric'] and y_info['is_numeric']:
            if len(df) <= 5 and x_info['cardinality'] <= 5:
                return 'pie'
            else:
                return 'bar'
        
        return 'bar'
    
    def create_smart_title(self, df, x_col, y_col, sql_intent, chart_type):
        """Generate intelligent titles based on data and intent"""
        
        x_formatted = self.format_column_name(x_col)
        y_formatted = self.format_column_name(y_col)
        
        if sql_intent['is_ranking'] and sql_intent['has_limit']:
            return f"Top {len(df)} {x_formatted} by {y_formatted}"
        elif sql_intent['is_time_series'] or x_col == 'time_period':
            return f"{y_formatted} Over Time"
        elif chart_type == 'pie':
            return f"{y_formatted} Distribution"
        elif chart_type == 'scatter':
            return f"{y_formatted} vs {x_formatted}"
        else:
            return f"{y_formatted} by {x_formatted}"
    
    def format_column_name(self, col_name):
        """Format column names for display"""
        if col_name == 'time_period':
            return 'Time Period'
        
        formatted = col_name.replace('_', ' ').title()
        
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
        
        formatted = re.sub(r'\([^)]*\)', '', formatted).strip()
        
        return formatted
    
    def create_visualization(self, df, x_col, y_col, chart_type, title):
        """Create the actual chart with FIXED time series handling"""
        
        plt.style.use('default')
        fig, ax = plt.subplots(figsize=(12, 8))
        
        # Handle special time period case
        if x_col == 'time_period':
            x_data = df['time_period']
            # Create numeric indices for plotting
            x_positions = range(len(x_data))
        else:
            x_data = df[x_col]
            x_positions = range(len(x_data))
        
        y_data = df[y_col]
        
        print(f"📊 Creating {chart_type} chart with {len(df)} data points")
        
        if chart_type == 'line':
            # FIXED: Line chart with proper time axis
            ax.plot(x_positions, y_data, marker='o', linewidth=3, markersize=8, 
                   color='steelblue', markerfacecolor='white', 
                   markeredgecolor='steelblue', markeredgewidth=2)
            
            # Set custom x-tick labels
            ax.set_xticks(x_positions)
            if x_col == 'time_period':
                # Format time period labels
                labels = [str(label) for label in x_data]
            else:
                labels = [str(label) for label in x_data]
            
            ax.set_xticklabels(labels, rotation=45, ha='right')
            ax.grid(True, alpha=0.3)
            
            print(f"✅ Line chart created with {len(x_positions)} points")
            
        elif chart_type == 'bar':
            colors = plt.cm.Set3(np.linspace(0, 1, len(df))) if len(df) > 1 else ['steelblue']
            bars = ax.bar(x_positions, y_data, color=colors, alpha=0.8, 
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
            ax.set_xticks(x_positions)
            labels = [str(label)[:20] + '...' if len(str(label)) > 20 else str(label) for label in x_data]
            ax.set_xticklabels(labels, rotation=45, ha='right')
            
            # Adjust y-axis
            y_max = max(y_data) if len(y_data) > 0 else 0
            ax.set_ylim(0, y_max * 1.15)
            
        elif chart_type == 'pie':
            colors = plt.cm.Set3(np.linspace(0, 1, len(df)))
            wedges, texts, autotexts = ax.pie(y_data, labels=x_data, autopct='%1.1f%%', 
                                            startangle=90, colors=colors)
            for autotext in autotexts:
                autotext.set_fontweight('bold')
                
        elif chart_type == 'scatter':
            ax.scatter(x_data if pd.api.types.is_numeric_dtype(df[x_col]) else x_positions, 
                      y_data, alpha=0.7, s=100, color='steelblue', 
                      edgecolor='navy', linewidth=1)
            if not pd.api.types.is_numeric_dtype(df[x_col]):
                ax.set_xticks(x_positions)
                ax.set_xticklabels(x_data, rotation=45, ha='right')
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
        print(f"🎯 Detected intent: {sql_intent}")
        
        # Handle time series data specially
        if sql_intent['is_time_series']:
            # Check if we need to create a time period column
            if 'year' in [col.lower() for col in df.columns] and 'month' in [col.lower() for col in df.columns]:
                df, time_col = self.create_time_period_column(df)
                if time_col:
                    print(f"✅ Created time period column: {time_col}")
        
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
    """Backwards-compatible function for app.py"""
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