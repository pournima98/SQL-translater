# Simple OAuth test to debug the issue
from flask import Flask, request, session, redirect, url_for
from google_auth_oauthlib.flow import Flow
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY")

# Google OAuth configuration
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = "http://localhost:5000/oauth2callback"

# Create credentials configuration
CREDENTIALS_INFO = {
    "web": {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [GOOGLE_REDIRECT_URI]
    }
}

@app.route("/")
def index():
    is_authenticated = 'credentials' in session
    return f"""
    <h1>OAuth Test</h1>
    <p>Status: {'✅ Authenticated' if is_authenticated else '❌ Not authenticated'}</p>
    <a href="/authorize">Authorize Gmail</a> | 
    <a href="/logout">Logout</a> | 
    <a href="/debug">Debug Info</a>
    """

@app.route("/authorize")
def authorize():
    try:
        print("Starting authorization flow...")
        
        flow = Flow.from_client_config(
            CREDENTIALS_INFO,
            scopes=[
                'https://www.googleapis.com/auth/userinfo.email',
                'https://www.googleapis.com/auth/gmail.send'
            ]
        )
        flow.redirect_uri = GOOGLE_REDIRECT_URI
        
        print(f"Redirect URI: {flow.redirect_uri}")
        print(f"Client ID: {GOOGLE_CLIENT_ID}")
        
        auth_url, state = flow.authorization_url(
            prompt='consent',
            access_type='offline'
        )
        
        session['oauth_state'] = state
        print(f"Generated state: {state}")
        print(f"Auth URL: {auth_url}")
        
        return redirect(auth_url)
        
    except Exception as e:
        print(f"Authorization error: {str(e)}")
        import traceback
        traceback.print_exc()
        return f"Authorization error: {str(e)}"

@app.route("/oauth2callback")
def oauth2callback():
    try:
        print("OAuth callback received")
        print(f"Request URL: {request.url}")
        print(f"Request args: {request.args}")
        
        if 'oauth_state' not in session:
            return "Error: No OAuth state found in session"
            
        state = session['oauth_state']
        print(f"Session state: {state}")
        
        flow = Flow.from_client_config(
            CREDENTIALS_INFO,
            scopes=[
                'https://www.googleapis.com/auth/userinfo.email',
                'https://www.googleapis.com/auth/gmail.send'
            ],
            state=state
        )
        flow.redirect_uri = GOOGLE_REDIRECT_URI
        
        flow.fetch_token(authorization_response=request.url)
        
        credentials = flow.credentials
        session['credentials'] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret
        }
        
        session.pop('oauth_state', None)
        
        return redirect(url_for('index'))
        
    except Exception as e:
        print(f"OAuth callback error: {str(e)}")
        import traceback
        traceback.print_exc()
        return f"OAuth callback error: {str(e)}"

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route("/debug")
def debug():
    return f"""
    <h2>Debug Info</h2>
    <p><strong>Client ID:</strong> {GOOGLE_CLIENT_ID}</p>
    <p><strong>Redirect URI:</strong> {GOOGLE_REDIRECT_URI}</p>
    <p><strong>Session keys:</strong> {list(session.keys())}</p>
    <p><strong>Is authenticated:</strong> {'credentials' in session}</p>
    <a href="/">Back to home</a>
    """

if __name__ == "__main__":
    print(f"Client ID: {GOOGLE_CLIENT_ID}")
    print(f"Client Secret: {'***' + GOOGLE_CLIENT_SECRET[-4:] if GOOGLE_CLIENT_SECRET else 'None'}")
    print(f"Redirect URI: {GOOGLE_REDIRECT_URI}")
    app.run(debug=True, host="localhost", port=5000)