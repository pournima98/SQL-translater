import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

#########
from sqlalchemy import create_engine
import pandas as pd
from utils.charts import generate_chart_base64
from langchain_agent import generate_sql_from_question
from flask import Flask, request, render_template, session, redirect, url_for, flash
from dotenv import load_dotenv
from openai import OpenAI
import openai
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import base64

load_dotenv()  # loads variables from .env into environment

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY")
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour session timeout

openai.api_key = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

engine = create_engine("mysql+pymysql://root:Hemant%40123@localhost:3306/churn_analysis")

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

def clean_session_data():
    """Clean up session data to prevent overflow"""
    keys_to_clean = ['query', 'table_html', 'chart_base64', 'oauth_state', 'rewritten_message']
    for key in keys_to_clean:
        if key in session:
            session.pop(key, None)
    
    # Also compress table data if it exists
    if 'table_html' in session and len(session.get('table_html', '')) > 5000:
        session['table_html'] = session['table_html'][:5000] + "... [truncated]"

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
    
    # Check if user is authenticated
    is_authenticated = 'credentials' in session

    if request.method == "POST":
        question = request.form.get("question")
        if not question:
            return render_template("index.html", result="Please enter a question", query=query, chart_path=chart_data_uri, is_authenticated=is_authenticated)
        
        try:
            # Clean previous session data first
            clean_session_data()
            
            query = generate_sql_from_question(question)
            session['query'] = query

            df = pd.read_sql(query, engine)
            result = df.to_html(classes="table table-bordered", index=False)
            chart_data_uri = generate_chart_base64(query, engine)
            
            # Store only essential data and limit table size
            session['query'] = query
            session['chart_base64'] = chart_data_uri
            
            # Limit table HTML size to prevent session overflow
            if len(result) > 8000:  # Limit table size
                # Truncate table if too large
                session['table_html'] = result[:8000] + "... [Table truncated for email compatibility]"
            else:
                session['table_html'] = result
        except Exception as e:
            result = f"<p style='color:red;'>Error: {str(e)}</p>"

    return render_template("index.html", result=result, query=query, chart_path=chart_data_uri, is_authenticated=is_authenticated)

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
    html_body = f"{body}<br><br>{table_html or ''}"
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

@app.route("/compose_email", methods=["GET", "POST"])
def compose_email():
    # Check if user is authenticated
    if 'credentials' not in session:
        return redirect(url_for('authorize'))

    if request.method == "POST":
        to_email = request.form.get('to_email')
        subject = request.form.get('subject')
        body = request.form.get('body')
        
        if not all([to_email, subject, body]):
            return render_template("compose_email.html", error="Please fill in all required fields")
        
        chart_base64 = session.get('chart_base64')
        table_html = session.get('table_html')

        chart_bytes = None
        if chart_base64:
            try:
                # Remove data URL prefix if present
                if ',' in chart_base64:
                    chart_bytes = base64.b64decode(chart_base64.split(",")[1])
                else:
                    chart_bytes = base64.b64decode(chart_base64)
            except Exception as e:
                print(f"Error processing chart: {str(e)}")

        try:
            result = send_email(subject, body, to_email, chart_bytes, table_html)
            return f"✅ Email sent successfully! Message ID: {result['id']}"
        except Exception as e:
            return f"Error sending email: {str(e)}"

    # Handle GET request
    user_msg = request.args.get("user_message", "Please find attached the churn insights.")
    rewritten = rewrite_message(user_msg)
    return render_template("compose_email.html", rewritten_message=rewritten)

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
        return f"✅ Email sent to {to} — ID: {result['id']}"
    except Exception as e:
        return f"Error sending email: {str(e)}"

# Add a simple route to check auth status
@app.route("/auth_status")
def auth_status():
    if 'credentials' in session:
        return "✅ Authenticated with Gmail"
    else:
        return "❌ Not authenticated. <a href='/authorize'>Click here to authorize</a>"

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)