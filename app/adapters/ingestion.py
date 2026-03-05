import os
import re
import requests


def sample_telegram_posts():
    return [
        {
            'source': 'telegram', 'external_id': 'tg-1', 'title': 'Backend Python Engineer', 'company': 'Acme',
            'description': 'Looking for Python, FastAPI, SQL, communication skills',
            'link': 'https://example.com/jobs/1'
        },
        {
            'source': 'telegram', 'external_id': 'tg-2', 'title': 'Solidity Engineer', 'company': 'ChainCo',
            'description': 'Smart contracts, solidity, web3',
            'link': 'https://example.com/jobs/2'
        }
    ]


def _extract_link(text: str) -> str:
    m = re.search(r'https?://\S+', text or '')
    return m.group(0) if m else 'https://t.me'


def fetch_telegram_posts_real(limit: int = 25):
    """
    Uses Telegram Bot API getUpdates. For channel monitoring, bot must be in channel and receive post updates.
    Env:
      TELEGRAM_BOT_TOKEN
      TELEGRAM_SOURCE_CHAT_ID (optional filter)
    """
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        return []

    source_filter = os.getenv('TELEGRAM_SOURCE_CHAT_ID')
    resp = requests.get(f'https://api.telegram.org/bot{bot_token}/getUpdates', timeout=20)
    if not resp.ok:
        return []

    results = []
    for item in resp.json().get('result', [])[-limit:]:
        msg = item.get('channel_post') or item.get('message') or {}
        chat = msg.get('chat', {})
        chat_id = str(chat.get('id', ''))
        if source_filter and chat_id != str(source_filter):
            continue
        text = msg.get('text') or msg.get('caption') or ''
        if not text:
            continue
        results.append({
            'source': 'telegram',
            'external_id': f"tg-{item.get('update_id')}",
            'title': text.split('\n')[0][:255],
            'company': chat.get('title') or chat.get('username') or 'telegram',
            'description': text,
            'link': _extract_link(text),
        })
    return results
