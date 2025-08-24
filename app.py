#########

#####3

import os
from dotenv import load_dotenv

from core.mysql_engine import get_db_connection

load_dotenv()
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'




#########
from sqlalchemy import create_engine
import pandas as pd
from utils.charts import generate_chart_base64
from langchain_agent import generate_sql_from_question
from flask import Flask, request, render_template, session, redirect, url_for, flash
from openai import OpenAI
import openai
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import base64
from flask import jsonify
from flask import send_file, make_response
from datetime import datetime
import tempfile
import os
import io 

# Add this to your app.py temporarily for debugging
print("GCP_CLOUD_SQL_CONNECTION_NAME:", os.getenv('GCP_CLOUD_SQL_CONNECTION_NAME'))
print("GOOGLE_APPLICATION_CREDENTIALS:", os.getenv('GOOGLE_APPLICATION_CREDENTIALS'))
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY")
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour session timeout

openai.api_key = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

#engine = create_engine("mysql+pymysql://root:Hemant%40123@localhost:3306/churn_analysis")

db_url = os.getenv("DB_URL")
engine = get_db_connection()

# Google OAuth configuration
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI")

# Create credentials.json content programmatically
CREDENTIALS_INFO = {
    "web": {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [GOOGLE_REDIRECT_URI]
    }
}



# JavaScript helper functions for CSV export (add to your template)
def get_csv_export_js():
    return """
    <script>
    // CSV Export Functions
    
    function exportToCSV() {
        // Show loading state
        const exportBtn = document.querySelector('.btn-export-csv');
        if (exportBtn) {
            const originalText = exportBtn.innerHTML;
            exportBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Exporting...';
            exportBtn.disabled = true;
            
            // Create a temporary link to trigger download
            window.location.href = '/export_csv';
            
            // Reset button after delay
            setTimeout(() => {
                exportBtn.innerHTML = originalText;
                exportBtn.disabled = false;
                showSuccessAlert('📊 CSV export completed!');
            }, 2000);
        }
    }
    
    function showExportModal() {
        // You can implement a modal for advanced export options
        const modal = document.getElementById('exportModal');
        if (modal) {
            const bootstrap_modal = new bootstrap.Modal(modal);
            bootstrap_modal.show();
        }
    }
    
    // Handle export button clicks
    document.addEventListener('DOMContentLoaded', function() {
        const exportBtn = document.querySelector('.btn-export-csv');
        if (exportBtn) {
            exportBtn.addEventListener('click', function(e) {
                e.preventDefault();
                exportToCSV();
            });
        }
    });
    </script>
    """


def clean_session_data():
    """Clean up session data to prevent overflow"""
    keys_to_clean = ['query', 'table_html', 'chart_base64', 'oauth_state', 'rewritten_message']
    for key in keys_to_clean:
        if key in session:
            session.pop(key, None)
    
    # Also compress table data if it exists
    if 'table_html' in session and len(session.get('table_html', '')) > 5000:
        session['table_html'] = session['table_html'][:5000] + "... [truncated]"


def get_session_size():
    """Calculate current session size in bytes"""
    try:
        import pickle
        return len(pickle.dumps(dict(session)))
    except:
        return 0

def clean_session_data():
    """Aggressively clean session to prevent overflow"""
    # Remove ALL large data items
    large_keys = ['table_html', 'chart_base64', 'rewritten_message', 'oauth_state']
    for key in large_keys:
        session.pop(key, None)
    
    # Keep only essential data
    essential_keys = ['credentials', 'query']
    current_session = dict(session)
    session.clear()
    
    # Restore only essential data
    for key in essential_keys:
        if key in current_session:
            session[key] = current_session[key]
    
    print(f"Session cleaned. New size: {get_session_size()} bytes")


@app.route("/session_info")
def session_info():
    """Debug route to check session size"""
    size = get_session_size()
    keys = list(session.keys())
    
    info = {
        'size_bytes': size,
        'size_kb': round(size / 1024, 2),
        'keys': keys,
        'status': 'OK' if size < 3000 else 'WARNING' if size < 4000 else 'CRITICAL'
    }
    
    return jsonify(info)



def rewrite_message(user_input):
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You're a helpful assistant rewriting professional emails."},
                {"role": "user", "content": f"Rewrite this: {user_input}"}
            ],
            temperature=0.4
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error rewriting message: {str(e)}")
        return user_input  # Return original if rewriting fails

@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    query = None
    chart_data_uri = None
    export_available = False
    
    is_authenticated = 'credentials' in session

    if request.method == "POST":
        question = request.form.get("question")
        if not question:
            flash("Please enter a question", "warning")
            return render_template("index.html", result="Please enter a question", 
                                 query=query, chart_path=chart_data_uri, 
                                 is_authenticated=is_authenticated,
                                 export_available=export_available)
        
        try:
            clean_session_data()
            
            # Generate query with validation
            query_result = generate_sql_from_question(question)
            
            # Check if it's an error message (not SQL)
            if query_result.startswith('❌') or 'not available' in query_result.lower():
                # Return the validation error message
                result = f"<div class='alert alert-warning'>{query_result.replace(chr(10), '<br>')}</div>"
                query = None
                chart_data_uri = None
                flash("Query validation failed", "warning")
                
            else:
                # It's valid SQL - proceed normally
                query = query_result
                df = pd.read_sql(query, engine)
                
                if not df.empty:
                    result = df.to_html(classes="table table-bordered table-striped", index=False)
                    export_available = True
                    flash(f"✅ Query executed successfully! Found {len(df)} rows.", "success")
                else:
                    result = "<div class='alert alert-info'>Query executed but returned no results.</div>"
                    flash("Query returned no results", "info")
                
                # Generate chart
                try:
                    chart_data_uri = generate_chart_base64(query, engine)
                    print("✅ Chart generated successfully")
                except Exception as e:
                    print(f"❌ Chart generation failed: {str(e)}")
                    chart_data_uri = None
                
                session['query'] = query
                session['has_chart'] = chart_data_uri is not None
                session['export_available'] = export_available
            
        except Exception as e:
            result = f"<div class='alert alert-danger'>Error: {str(e)}</div>"
            flash(f"❌ Error executing query: {str(e)}", "error")
    
    else:
        # For GET requests, check if export is available from session
        export_available = session.get('export_available', False)

    return render_template("index.html", 
                         result=result, 
                         query=query, 
                         chart_path=chart_data_uri, 
                         is_authenticated=is_authenticated,
                         export_available=export_available)


def send_email(subject, body, to_email, chart_image_bytes=None, table_html=None):
    if 'credentials' not in session:
        raise Exception("No credentials in session. Please authorize first.")

    # Recreate credentials from session
    creds = Credentials(
        token=session['credentials']['token'],
        refresh_token=session['credentials']['refresh_token'],
        token_uri=session['credentials']['token_uri'],
        client_id=session['credentials']['client_id'],
        client_secret=session['credentials']['client_secret'],
        scopes=session['credentials']['scopes']
    )

    service = build("gmail", "v1", credentials=creds)

    # Create multipart message
    msg = MIMEMultipart()
    msg['to'] = to_email
    msg['subject'] = subject

    # Add body with table
    #html_body = f"{body}<br><br>{table_html or ''}"
    #msg.attach(MIMEText(html_body, "html"))
    html_body = body
    msg.attach(MIMEText(html_body, "html"))
    # Add chart as attachment if available
    if chart_image_bytes:
        chart_attachment = MIMEImage(chart_image_bytes)
        chart_attachment.add_header('Content-Disposition', 'attachment', filename='chart.png')
        msg.attach(chart_attachment)

    # Encode and send
    raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    message_body = {"raw": raw_message}
    
    try:
        message = service.users().messages().send(userId="me", body=message_body).execute()
        return message
    except Exception as e:
        raise Exception(f"Failed to send email: {str(e)}")

# Fix 1: Make sure chart is actually attached


# Add a simple test route for the rewriter
@app.route("/test_rewrite")
def test_rewrite():
    """Simple test page for the rewriter"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test AI Rewrite</title>
        <script>
            async function testRewrite() {
                const message = document.getElementById('testMessage').value;
                const response = await fetch('/rewrite_message', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: message, tone: 'professional', length: 'concise'})
                });
                const data = await response.json();
                document.getElementById('result').innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
            }
        </script>
    </head>
    <body>
        <h2>Test AI Rewrite</h2>
        <textarea id="testMessage" placeholder="Enter message to rewrite">find churn data</textarea><br><br>
        <button onclick="testRewrite()">Test Rewrite</button>
        <div id="result"></div>
    </body>
    </html>
    '''

@app.route("/authorize")
def authorize():
    try:
        flow = Flow.from_client_config(
            CREDENTIALS_INFO,
            scopes=[
                'https://www.googleapis.com/auth/userinfo.email',
                'https://www.googleapis.com/auth/gmail.send',
                'openid'
            ]
        )
        flow.redirect_uri = GOOGLE_REDIRECT_URI
        
        auth_url, state = flow.authorization_url(
            prompt='consent',
            access_type='offline',
            include_granted_scopes='true'
        )
        
        # Store only the state, not the entire flow
        session['oauth_state'] = state
        return redirect(auth_url)
    except Exception as e:
        return f"Authorization error: {str(e)}"

@app.route("/oauth2callback")
def oauth2callback():
    try:
        # Verify state parameter
        if 'oauth_state' not in session:
            return "Error: No OAuth state found in session"
            
        flow = Flow.from_client_config(
            CREDENTIALS_INFO,
            scopes=[
                'https://www.googleapis.com/auth/userinfo.email',
                'https://www.googleapis.com/auth/gmail.send',
                'openid'
            ],
            state=session['oauth_state']
        )
        flow.redirect_uri = GOOGLE_REDIRECT_URI
        
        # Get the authorization response
        authorization_response = request.url
        flow.fetch_token(authorization_response=authorization_response)

        credentials = flow.credentials
        
        # Store only essential credential data to reduce session size
        session['credentials'] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        
        # Clear OAuth state to save space
        session.pop('oauth_state', None)
        
        return redirect(url_for('index'))
    except Exception as e:
        return f"OAuth callback error: {str(e)}"

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('index'))


@app.route("/export_csv")
def export_csv():
    """Export current query results to CSV - clean data only"""
    
    # Check if user has query results
    if 'query' not in session:
        flash('No query results to export. Please run a query first.', 'error')
        return redirect(url_for('index'))
    
    try:
        query = session.get('query')
        if not query:
            flash('No valid query found to export.', 'error')
            return redirect(url_for('index'))
        
        # Execute the query to get fresh results
        df = pd.read_sql(query, engine)
        
        if df.empty:
            flash('Query returned no results to export.', 'warning')
            return redirect(url_for('index'))
        
        # Create CSV content - CLEAN VERSION (no metadata)
        output = io.StringIO()
        df.to_csv(output, index=False)  # Just the data, no extra headers
        output.seek(0)
        
        # Create filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"data_export_{timestamp}.csv"
        
        # Create response with proper headers
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.headers['Content-Length'] = len(output.getvalue())
        
        return response
        
    except Exception as e:
        flash(f'Error exporting CSV: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route("/export_csv_advanced", methods=["POST"])
def export_csv_advanced():
    """Advanced CSV export with custom options"""
    
    if 'query' not in session:
        return jsonify({
            'success': False,
            'error': 'No query results available for export'
        })
    
    try:
        # Get export options from form
        include_metadata = request.form.get('include_metadata', 'true') == 'true'
        custom_filename = request.form.get('filename', '').strip()
        date_format = request.form.get('date_format', '%Y-%m-%d')
        
        query = session.get('query')
        df = pd.read_sql(query, engine)
        
        if df.empty:
            return jsonify({
                'success': False,
                'error': 'No data to export'
            })
        
        # Format dates if any datetime columns exist
        for col in df.columns:
            if df[col].dtype == 'datetime64[ns]':
                df[col] = df[col].dt.strftime(date_format)
        
        # Create filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if custom_filename:
            filename = f"{custom_filename}_{timestamp}.csv"
        else:
            filename = f"analysis_export_{timestamp}.csv"
        
        # Create CSV content
        output = io.StringIO()
        
        if include_metadata:
            output.write(f"# Analysis Export\n")
            output.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            output.write(f"# Rows: {len(df)}, Columns: {len(df.columns)}\n")
            output.write(f"# Query: {query}\n")
            output.write("#\n")
        
        df.to_csv(output, index=False)
        
        # Create temporary file for download
        temp_file = tempfile.NamedTemporaryFile(mode='w+', suffix='.csv', delete=False)
        temp_file.write(output.getvalue())
        temp_file.close()
        
        # Return file download
        return send_file(
            temp_file.name,
            as_attachment=True,
            download_name=filename,
            mimetype='text/csv'
        )
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Export failed: {str(e)}'
        })

# Add a simple route to check auth status
@app.route("/auth_status")
def auth_status():
    if 'credentials' in session:
        return "✅ Authenticated with Gmail"
    else:
        return "❌ Not authenticated. <a href='/authorize'>Click here to authorize</a>"

def rewrite_message_advanced(user_input, tone="professional", length="concise"):
    """Advanced message rewriting with tone and length control"""
    
    tone_prompts = {
        "professional": "professional and business-appropriate",
        "friendly": "friendly and warm while maintaining professionalism",
        "formal": "formal and respectful",
        "casual": "casual and conversational",
        "urgent": "urgent and action-oriented",
        "apologetic": "apologetic and understanding"
    }
    
    length_prompts = {
        "brief": "Keep it brief and to the point (1-2 sentences)",
        "concise": "Make it concise but complete (2-4 sentences)",
        "detailed": "Provide a detailed and comprehensive message (4-6 sentences)"
    }
    
    tone_instruction = tone_prompts.get(tone, "professional and business-appropriate")
    length_instruction = length_prompts.get(length, "Make it concise but complete")
    
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {
                    "role": "system", 
                    "content": f"""You are an expert email writing assistant. Your job is to rewrite messages to be {tone_instruction}. 
                    
                    Guidelines:
                    - {length_instruction}
                    - Use proper email etiquette
                    - Make the message clear and actionable
                    - Maintain the original intent
                    - Use appropriate greetings and closings
                    - Be specific about data analysis context when relevant
                    
                    Also identify 2-3 key improvements you made (like "Added professional greeting", "Clarified request", "Improved tone")."""
                },
                {
                    "role": "user", 
                    "content": f"Rewrite this message: '{user_input}'\n\nPlease provide:\n1. The rewritten message\n2. A list of key improvements made"
                }
            ],
            temperature=0.7
        )
        
        full_response = response.choices[0].message.content.strip()
        
        # Try to parse the response to extract improvements
        if "improvements" in full_response.lower() or "improved" in full_response.lower():
            lines = full_response.split('\n')
            rewritten_lines = []
            improvement_lines = []
            in_improvements = False
            
            for line in lines:
                if any(word in line.lower() for word in ['improvement', 'change', 'enhanced', 'added', 'clarified']):
                    in_improvements = True
                    improvement_lines.append(line.strip('- ').strip())
                elif not in_improvements and line.strip():
                    rewritten_lines.append(line)
            
            rewritten_message = '\n'.join(rewritten_lines).strip()
            improvements = improvement_lines if improvement_lines else ["Enhanced professionalism", "Improved clarity", "Better structure"]
        else:
            rewritten_message = full_response
            improvements = ["Enhanced professionalism", "Improved clarity", "Better tone"]
        
        return rewritten_message, improvements
        
    except Exception as e:
        print(f"Error rewriting message: {str(e)}")
        # Fallback rewriting
        fallback_message = f"Dear Recipient,\n\nI hope this email finds you well. {user_input}\n\nPlease let me know if you need any additional information.\n\nBest regards"
        return fallback_message, ["Added professional greeting", "Improved structure", "Added courteous closing"]



@app.route("/rewrite_message", methods=["POST"])
def rewrite_message_api():
    """API endpoint for message rewriting"""
    try:
        data = request.get_json()
        
        if not data or 'message' not in data:
            return jsonify({
                'success': False,
                'error': 'No message provided'
            })
        
        message = data['message']
        tone = data.get('tone', 'professional')
        length = data.get('length', 'concise')
        
        if not message.strip():
            return jsonify({
                'success': False,
                'error': 'Message cannot be empty'
            })
        
        # Rewrite the message
        rewritten_message, improvements = rewrite_message_advanced(message, tone, length)
        
        return jsonify({
            'success': True,
            'rewritten_message': rewritten_message,
            'improvements': improvements,
            'original_message': message,
            'tone': tone,
            'length': length
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })    
    

# Replace your existing /compose_email route with this updated version

@app.route("/compose_email", methods=["GET", "POST"])
def compose_email():
    if 'credentials' not in session:
        return redirect(url_for('authorize'))

    if request.method == "POST":
        to_email = request.form.get('to_email')
        subject = request.form.get('subject')
        body = request.form.get('body')
        include_chart = request.form.get('include_chart') == 'on'
        
        if not all([to_email, subject, body]):
            return render_template("compose_email.html", error="Please fill in all required fields")
        
        try:
            query = session.get('query', '')
            
            # Build email content
            email_content_parts = [body.replace('\n', '<br>')]
            
            # Create HTML email
            simple_html = f'''<!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; }}
                    .content {{ padding: 20px; }}
                    .signature {{ margin-top: 30px; padding-top: 20px; border-top: 2px solid #f0f0f0; color: #666; }}
                    code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }}
                </style>
            </head>
            <body>
                <div class="content">
                    {''.join(email_content_parts)}
                </div>
            </body>
            </html>'''
            
            # Create email message
            creds = Credentials(
                token=session['credentials']['token'],
                refresh_token=session['credentials']['refresh_token'],
                token_uri=session['credentials']['token_uri'],
                client_id=session['credentials']['client_id'],
                client_secret=session['credentials']['client_secret'],
                scopes=session['credentials']['scopes']
            )

            service = build("gmail", "v1", credentials=creds)
            msg = MIMEMultipart()
            msg['to'] = to_email
            msg['subject'] = subject
            msg.attach(MIMEText(simple_html, "html"))
            
            chart_attached = False
            
            # Generate and attach chart if requested
            if include_chart and query:
                try:
                    print(f"🔄 Generating fresh chart for query: {query}")
                    chart_base64 = generate_chart_base64(query, engine)
                    
                    if chart_base64:
                        print("✅ Chart generated, attaching to email...")
                        
                        # Handle data URL format
                        if chart_base64.startswith('data:image'):
                            chart_bytes = base64.b64decode(chart_base64.split(",")[1])
                        else:
                            chart_bytes = base64.b64decode(chart_base64)
                        
                        chart_attachment = MIMEImage(chart_bytes)
                        chart_attachment.add_header('Content-Disposition', 'attachment', 
                                                filename='analysis_chart.png')
                        msg.attach(chart_attachment)
                        chart_attached = True
                        print("📎 Chart successfully attached!")
                    else:
                        print("❌ No chart data generated")
                        
                except Exception as e:
                    print(f"❌ Error generating/attaching chart: {str(e)}")

            # Send email
            raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            message_body = {"raw": raw_message}
            
            result = service.users().messages().send(userId="me", body=message_body).execute()
            
            # Instead of returning success message, use flash and redirect
            success_message = f"✅ Email sent successfully to {to_email}!"
            if chart_attached:
                success_message += " 📊 Chart was attached."
            elif include_chart:
                success_message += " ⚠️ Chart was requested but could not be generated."
                
            flash(success_message, 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            flash(f"❌ Error sending email: {str(e)}", 'error')
            return render_template("compose_email.html", error=f"Error sending email: {str(e)}")

    # Handle GET request (existing code remains the same)
    query = session.get('query', '')
    has_chart = session.get('has_chart', False)
    
    has_analysis_data = bool(query)
    
    if has_analysis_data:
        default_message = "Please find the data analysis results attached."
        analysis_summary = "Your chart is ready — attach it to share instantly." if has_chart else "Query ready"
    else:
        default_message = "Please run a data analysis query first."
        analysis_summary = None
    
    return render_template("compose_email.html", 
                         rewritten_message=default_message,
                         analysis_summary=analysis_summary,
                         chart_available=has_chart,
                         table_available=False,
                         has_analysis_data=has_analysis_data,
                         query=query)


# Also update the confirm_and_send_email route
@app.route('/confirm_and_send_email', methods=['GET', 'POST'])
def confirm_and_send_email():
    if 'credentials' not in session:
        return redirect(url_for('authorize'))
        
    if request.method == 'GET':
        rewritten_message = session.get('rewritten_message', '')
        return render_template("confirm_email.html", message=rewritten_message)

    to = request.form.get('to')
    subject = request.form.get('subject')
    message = request.form.get('message')
    
    if not all([to, subject, message]):
        return render_template("confirm_email.html", error="Please fill in all required fields")
    
    try:
        chart_base64 = session.get('chart_base64')
        table_html = session.get('table_html')
        
        chart_bytes = None
        if chart_base64:
            try:
                if ',' in chart_base64:
                    chart_bytes = base64.b64decode(chart_base64.split(",")[1])
                else:
                    chart_bytes = base64.b64decode(chart_base64)
            except Exception as e:
                print(f"Error processing chart: {str(e)}")
        
        result = send_email(subject, message, to, chart_bytes, table_html)
        
        # Use flash message and redirect instead of returning success text
        flash(f"✅ Email sent successfully to {to}! Message ID: {result['id']}", 'success')
        return redirect(url_for('index'))
        
    except Exception as e:
        flash(f"❌ Error sending email: {str(e)}", 'error')
        return render_template("confirm_email.html", error=f"Error sending email: {str(e)}")    

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)