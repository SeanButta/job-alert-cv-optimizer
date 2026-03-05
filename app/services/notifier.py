import os
import requests
from typing import Any, Dict


def build_alert(job_title: str, link: str, score: float, doc_url: str) -> str:
    return f"Match found: {job_title} (score={score:.2f})\nJob link: {link}\nCV doc: {doc_url}"


def _enabled() -> bool:
    return os.getenv('ENABLE_REAL_NOTIFICATIONS', 'false').lower() == 'true'


def send_email(target_email: str, message: str) -> Dict[str, Any]:
    if not _enabled():
        return {'channel': 'email', 'target': target_email, 'status': 'mock_sent', 'message': message}

    api_key = os.getenv('SENDGRID_API_KEY')
    sender = os.getenv('ALERT_FROM_EMAIL', 'alerts@example.com')
    if not api_key:
        return {'channel': 'email', 'target': target_email, 'status': 'failed', 'error': 'SENDGRID_API_KEY missing'}

    resp = requests.post(
        'https://api.sendgrid.com/v3/mail/send',
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json={
            'personalizations': [{'to': [{'email': target_email}]}],
            'from': {'email': sender},
            'subject': 'Job Match Alert',
            'content': [{'type': 'text/plain', 'value': message}],
        },
        timeout=15,
    )
    return {'channel': 'email', 'target': target_email, 'status': 'sent' if resp.ok else 'failed', 'http_status': resp.status_code}


def send_sms(target_phone: str, message: str) -> Dict[str, Any]:
    if not _enabled():
        return {'channel': 'sms', 'target': target_phone, 'status': 'mock_sent', 'message': message}

    sid = os.getenv('TWILIO_ACCOUNT_SID')
    token = os.getenv('TWILIO_AUTH_TOKEN')
    from_number = os.getenv('TWILIO_FROM_NUMBER')
    if not (sid and token and from_number):
        return {'channel': 'sms', 'target': target_phone, 'status': 'failed', 'error': 'Twilio env vars missing'}

    resp = requests.post(
        f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json',
        auth=(sid, token),
        data={'To': target_phone, 'From': from_number, 'Body': message},
        timeout=15,
    )
    return {'channel': 'sms', 'target': target_phone, 'status': 'sent' if resp.ok else 'failed', 'http_status': resp.status_code}


def send_telegram(target_chat_id: str, message: str) -> Dict[str, Any]:
    if not _enabled():
        return {'channel': 'telegram', 'target': target_chat_id, 'status': 'mock_sent', 'message': message}

    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        return {'channel': 'telegram', 'target': target_chat_id, 'status': 'failed', 'error': 'TELEGRAM_BOT_TOKEN missing'}

    resp = requests.post(
        f'https://api.telegram.org/bot{bot_token}/sendMessage',
        json={'chat_id': target_chat_id, 'text': message},
        timeout=15,
    )
    return {'channel': 'telegram', 'target': target_chat_id, 'status': 'sent' if resp.ok else 'failed', 'http_status': resp.status_code}


def send_whatsapp(target_phone: str, message: str) -> Dict[str, Any]:
    if not _enabled():
        return {'channel': 'whatsapp', 'target': target_phone, 'status': 'mock_sent', 'message': message}

    token = os.getenv('WHATSAPP_TOKEN')
    phone_number_id = os.getenv('WHATSAPP_PHONE_NUMBER_ID')
    if not (token and phone_number_id):
        return {'channel': 'whatsapp', 'target': target_phone, 'status': 'failed', 'error': 'WhatsApp env vars missing'}

    resp = requests.post(
        f'https://graph.facebook.com/v20.0/{phone_number_id}/messages',
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
        json={
            'messaging_product': 'whatsapp',
            'to': target_phone,
            'type': 'text',
            'text': {'body': message},
        },
        timeout=15,
    )
    return {'channel': 'whatsapp', 'target': target_phone, 'status': 'sent' if resp.ok else 'failed', 'http_status': resp.status_code}


def dispatch_all(user: Dict[str, str], message: str):
    out = []
    if user.get('email'):
        out.append(send_email(user['email'], message))
    if user.get('phone'):
        out.append(send_sms(user['phone'], message))
        out.append(send_whatsapp(user['phone'], message))
    if user.get('telegram_chat_id'):
        out.append(send_telegram(user['telegram_chat_id'], message))
    return out
