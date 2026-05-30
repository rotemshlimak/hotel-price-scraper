import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json

CONFIG_PATH = 'config.json'

def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def send_email(subject, body, config):
    email_cfg = config['email']
    msg = MIMEMultipart()
    msg['From'] = email_cfg['username']
    msg['To'] = email_cfg['recipient']
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    with smtplib.SMTP(email_cfg['smtp_server'], email_cfg['smtp_port']) as server:
        server.starttls()
        server.login(email_cfg['username'], email_cfg['password'])
        server.send_message(msg)

def main():
    config = load_config()
    send_email('Test Subject', 'This is a test email from Marriott scraper.', config)

if __name__ == '__main__':
    main()
