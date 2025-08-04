import smtplib, ssl
from email.message import EmailMessage

def send_email(subject, body, to_email, chart_base64, table_html):
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = "your.email@gmail.com"
    msg['To'] = to_email
    msg.set_content("This email contains an HTML part and an image.")
    msg.add_alternative(body, subtype='html')

    # Attach chart
    msg.add_attachment(chart_base64, maintype='image', subtype='png', filename='chart.png')

    # Attach table as HTML
    msg.add_attachment(table_html.encode('utf-8'), maintype='text', subtype='html', filename='table.html')

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as smtp:
        smtp.login("your.email@gmail.com", "your_app_password")  # Use Gmail App Password
        smtp.send_message(msg)
