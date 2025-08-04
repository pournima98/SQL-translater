import os
import base64
from email.mime.text import MIMEText
from flask import session, redirect, url_for, request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv

load_dotenv()

SCOPES = os.getenv("GMAIL_SCOPES").split(",")
REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")


def get_flow():
    return Flow(
        client_type="web",
        client_config={
            "web": {
                "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [REDIRECT_URI],
            }
        },
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )


def authorize():
    flow = get_flow()
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline', include_granted_scopes='true')
    return redirect(auth_url)


def oauth2callback():
    flow = get_flow()
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials

    session['credentials'] = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': creds.scopes
    }
    return redirect(url_for('confirm_and_send_email'))


def send_email(to, subject, message):
    creds = Credentials(**session['credentials'])
    service = build('gmail', 'v1', credentials=creds)

    mime_msg = MIMEText(message)
    mime_msg['to'] = to
    mime_msg['subject'] = subject
    raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode()

    result = service.users().messages().send(userId='me', body={'raw': raw}).execute()
    return result
