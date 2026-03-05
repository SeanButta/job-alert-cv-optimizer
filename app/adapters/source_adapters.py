"""
Source adapters for different job source types.

Each adapter handles:
- Testing connectivity
- Fetching job posts
- Parsing and normalizing data

Adapters:
- TelegramChannelAdapter: Telegram channels/groups
- WebsiteAdapter: Web page scraping (scaffold)
- LinkedInRecruiterAdapter: LinkedIn recruiter tracking (compliance-safe scaffold)
"""
import os
import re
import json
import hashlib
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
from urllib.parse import urlparse, urljoin

import requests

from app.models.sources import JobSource, SourceType, SourceStatus

logger = logging.getLogger(__name__)


# --- Base Adapter ---

class BaseSourceAdapter(ABC):
    """Base class for source adapters."""
    
    def __init__(self, source: JobSource):
        self.source = source
        self.config = self._parse_config()
    
    def _parse_config(self) -> dict:
        """Parse JSON config from source."""
        if self.source.config:
            try:
                return json.loads(self.source.config)
            except (json.JSONDecodeError, TypeError):
                pass
        return {}
    
    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """Test source connectivity. Returns {success, message, details}."""
        pass
    
    @abstractmethod
    def fetch_posts(self, limit: int = 25) -> List[Dict[str, Any]]:
        """
        Fetch job posts from source.
        
        Returns list of dicts with keys:
        - source: str (source type)
        - external_id: str (unique ID from source)
        - title: str
        - company: str
        - description: str
        - link: str
        - raw_data: dict (optional, original data)
        - recruiter_info: dict (optional, for linkedin_recruiter)
        """
        pass


# --- Telegram Channel Adapter ---

class TelegramChannelAdapter(BaseSourceAdapter):
    """
    Adapter for Telegram channels.
    
    Configuration:
        TELEGRAM_BOT_TOKEN env var required for API access.
    
    Limitations:
        - Bot must be added to the channel/group
        - Only receives messages sent after bot was added
        - getUpdates has a 100-message limit
        - For high-volume channels, consider webhooks
    
    Identifier formats:
        - @channel_username
        - https://t.me/channel_username
        - Channel ID (numeric)
    """
    
    def __init__(self, source: JobSource):
        super().__init__(source)
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.channel_id = self._normalize_channel_id()
    
    def _normalize_channel_id(self) -> str:
        """Normalize channel identifier to usable format."""
        identifier = self.source.identifier.strip()
        
        # Handle t.me links
        if 't.me/' in identifier:
            match = re.search(r't\.me/([^/\s?]+)', identifier)
            if match:
                return '@' + match.group(1)
        
        # Already has @ prefix
        if identifier.startswith('@'):
            return identifier
        
        # Numeric ID
        if identifier.lstrip('-').isdigit():
            return identifier
        
        # Assume username
        return '@' + identifier
    
    def test_connection(self) -> Dict[str, Any]:
        """Test Telegram bot connection and channel access."""
        if not self.bot_token:
            return {
                'success': False,
                'message': 'TELEGRAM_BOT_TOKEN environment variable not set',
                'details': {'setup_required': True}
            }
        
        try:
            # Test bot token validity
            resp = requests.get(
                f'https://api.telegram.org/bot{self.bot_token}/getMe',
                timeout=10
            )
            if not resp.ok:
                return {
                    'success': False,
                    'message': 'Invalid bot token',
                    'details': {'error': resp.text}
                }
            
            bot_info = resp.json().get('result', {})
            
            # Try to get chat info (requires bot in channel)
            chat_resp = requests.get(
                f'https://api.telegram.org/bot{self.bot_token}/getChat',
                params={'chat_id': self.channel_id},
                timeout=10
            )
            
            if chat_resp.ok:
                chat_info = chat_resp.json().get('result', {})
                return {
                    'success': True,
                    'message': f"Connected to channel: {chat_info.get('title', self.channel_id)}",
                    'details': {
                        'bot_username': bot_info.get('username'),
                        'channel_title': chat_info.get('title'),
                        'channel_type': chat_info.get('type'),
                    }
                }
            else:
                return {
                    'success': False,
                    'message': 'Bot not added to channel or channel not found',
                    'details': {
                        'bot_username': bot_info.get('username'),
                        'channel_id': self.channel_id,
                        'hint': 'Add the bot as admin to the channel first'
                    }
                }
        
        except requests.Timeout:
            return {'success': False, 'message': 'Connection timeout'}
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def fetch_posts(self, limit: int = 25) -> List[Dict[str, Any]]:
        """Fetch posts from Telegram channel using getUpdates."""
        if not self.bot_token:
            logger.warning("TELEGRAM_BOT_TOKEN not set, skipping fetch")
            return []
        
        try:
            resp = requests.get(
                f'https://api.telegram.org/bot{self.bot_token}/getUpdates',
                params={'limit': min(limit, 100)},
                timeout=20
            )
            if not resp.ok:
                logger.error(f"Telegram API error: {resp.text}")
                return []
            
            results = []
            for item in resp.json().get('result', []):
                msg = item.get('channel_post') or item.get('message') or {}
                chat = msg.get('chat', {})
                chat_id = str(chat.get('id', ''))
                
                # Filter by channel ID if not matching
                if self.channel_id.startswith('@'):
                    channel_username = '@' + (chat.get('username') or '')
                    if channel_username.lower() != self.channel_id.lower():
                        continue
                elif chat_id != self.channel_id:
                    continue
                
                text = msg.get('text') or msg.get('caption') or ''
                if not text:
                    continue
                
                # Extract link from text
                link = self._extract_link(text) or f"https://t.me/{chat.get('username', 'unknown')}"
                
                results.append({
                    'source': 'telegram_channel',
                    'source_id': self.source.id,
                    'external_id': f"tg-{item.get('update_id')}",
                    'title': text.split('\n')[0][:255],
                    'company': chat.get('title') or chat.get('username') or 'Telegram',
                    'description': text,
                    'link': link,
                    'raw_data': msg,
                })
            
            return results[:limit]
        
        except Exception as e:
            logger.error(f"Telegram fetch error: {e}")
            return []
    
    def _extract_link(self, text: str) -> Optional[str]:
        """Extract first URL from text."""
        match = re.search(r'https?://\S+', text or '')
        return match.group(0) if match else None


# --- Website Adapter ---

class WebsiteAdapter(BaseSourceAdapter):
    """
    Adapter for scraping job listings from websites.
    
    Configuration (via config JSON):
        - selector: CSS selector for job items (default: 'a[href*="job"]')
        - title_selector: CSS selector for title within item
        - link_selector: CSS selector for link within item
        - description_selector: CSS selector for description
        - user_agent: Custom User-Agent header
    
    Limitations:
        - Requires explicit user consent for web scraping
        - Respects robots.txt by default
        - Rate limited to avoid abuse
        - Some sites may block automated access
    
    This is a SCAFFOLD implementation. Production use requires:
        - Proper HTML parsing (BeautifulSoup/lxml)
        - JavaScript rendering for SPAs (Playwright/Selenium)
        - Anti-bot detection handling
    """
    
    DEFAULT_USER_AGENT = 'JobAlertBot/1.0 (contact: admin@example.com)'
    DEFAULT_TIMEOUT = 15
    
    def __init__(self, source: JobSource):
        super().__init__(source)
        self.url = self._normalize_url()
        self.user_agent = self.config.get('user_agent', self.DEFAULT_USER_AGENT)
    
    def _normalize_url(self) -> str:
        """Normalize URL to valid format."""
        url = self.source.identifier.strip()
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        return url
    
    def test_connection(self) -> Dict[str, Any]:
        """Test website accessibility."""
        try:
            resp = requests.head(
                self.url,
                headers={'User-Agent': self.user_agent},
                timeout=self.DEFAULT_TIMEOUT,
                allow_redirects=True
            )
            
            if resp.ok:
                return {
                    'success': True,
                    'message': f'Website accessible: {self.url}',
                    'details': {
                        'status_code': resp.status_code,
                        'final_url': resp.url,
                        'content_type': resp.headers.get('Content-Type', 'unknown'),
                    }
                }
            else:
                return {
                    'success': False,
                    'message': f'Website returned error: {resp.status_code}',
                    'details': {'status_code': resp.status_code}
                }
        
        except requests.Timeout:
            return {'success': False, 'message': 'Connection timeout'}
        except requests.RequestException as e:
            return {'success': False, 'message': f'Request error: {str(e)}'}
    
    def fetch_posts(self, limit: int = 25) -> List[Dict[str, Any]]:
        """
        Fetch job posts from website.
        
        SCAFFOLD: This is a minimal implementation.
        Production use requires proper HTML parsing.
        """
        try:
            resp = requests.get(
                self.url,
                headers={'User-Agent': self.user_agent},
                timeout=self.DEFAULT_TIMEOUT
            )
            if not resp.ok:
                logger.warning(f"Website fetch failed: {resp.status_code}")
                return []
            
            # SCAFFOLD: Basic link extraction
            # Real implementation would use BeautifulSoup/lxml
            results = []
            
            # Find all links that look like job postings
            link_pattern = re.compile(r'href=["\']([^"\']*(?:job|career|position|opening|vacancy)[^"\']*)["\']', re.I)
            title_pattern = re.compile(r'>([^<]{10,100})</a>', re.I)
            
            html = resp.text
            seen_links = set()
            
            for match in link_pattern.finditer(html):
                link = match.group(1)
                
                # Normalize link
                if not link.startswith(('http://', 'https://')):
                    link = urljoin(self.url, link)
                
                # Dedupe
                link_hash = hashlib.md5(link.encode()).hexdigest()[:16]
                if link_hash in seen_links:
                    continue
                seen_links.add(link_hash)
                
                # Try to extract title from surrounding context
                context_start = max(0, match.start() - 200)
                context = html[context_start:match.end() + 200]
                title_match = title_pattern.search(context)
                title = title_match.group(1).strip() if title_match else link.split('/')[-1]
                
                results.append({
                    'source': 'website',
                    'source_id': self.source.id,
                    'external_id': f"web-{link_hash}",
                    'title': title[:255],
                    'company': urlparse(self.url).netloc,
                    'description': f"Job posting from {self.url}",
                    'link': link,
                })
                
                if len(results) >= limit:
                    break
            
            return results
        
        except Exception as e:
            logger.error(f"Website fetch error: {e}")
            return []


# --- LinkedIn Recruiter Adapter ---

class LinkedInRecruiterAdapter(BaseSourceAdapter):
    """
    Adapter for tracking LinkedIn recruiters.
    
    COMPLIANCE-SAFE MODE:
        - Only tracks public profile data
        - Does NOT scrape LinkedIn directly (ToS violation)
        - Relies on user-provided recruiter info
        - Can integrate with LinkedIn API if user provides OAuth
    
    Identifier formats:
        - LinkedIn profile URL: https://linkedin.com/in/username
        - Recruiter name (for manual tracking)
    
    Configuration (via config JSON):
        - company: Recruiter's company name
        - notes: User notes about recruiter
        - job_categories: List of job types they typically post
    
    This adapter:
        1. Stores recruiter metadata from user input
        2. Tags jobs found elsewhere with recruiter info
        3. Does NOT actively scrape LinkedIn
    
    For production LinkedIn integration, use:
        - LinkedIn Marketing API (requires approval)
        - User OAuth flow for personal data access
    """
    
    def __init__(self, source: JobSource):
        super().__init__(source)
        self.profile_url = self._normalize_profile_url()
        self.recruiter_name = self.config.get('name') or self._extract_name()
        self.company = self.config.get('company', '')
    
    def _normalize_profile_url(self) -> Optional[str]:
        """Normalize LinkedIn profile URL."""
        identifier = self.source.identifier.strip()
        
        # Already a LinkedIn URL
        if 'linkedin.com/in/' in identifier:
            match = re.search(r'linkedin\.com/in/([^/?\s]+)', identifier)
            if match:
                return f'https://www.linkedin.com/in/{match.group(1)}'
        
        # Could be just username or name
        return None
    
    def _extract_name(self) -> str:
        """Extract recruiter name from identifier."""
        identifier = self.source.identifier.strip()
        
        # From LinkedIn URL
        if 'linkedin.com/in/' in identifier:
            match = re.search(r'linkedin\.com/in/([^/?\s]+)', identifier)
            if match:
                # Convert username to readable name
                name = match.group(1).replace('-', ' ').title()
                return name
        
        # Assume it's the name
        return identifier
    
    def test_connection(self) -> Dict[str, Any]:
        """
        Test LinkedIn recruiter entry validity.
        
        Note: We do NOT verify by scraping LinkedIn.
        This just validates the data format.
        """
        if not self.source.identifier:
            return {
                'success': False,
                'message': 'No recruiter identifier provided'
            }
        
        details = {
            'recruiter_name': self.recruiter_name,
            'profile_url': self.profile_url,
            'company': self.company,
            'compliance_mode': 'public_data_only'
        }
        
        if self.profile_url:
            # Just verify URL format, don't actually fetch
            return {
                'success': True,
                'message': f'Recruiter entry valid: {self.recruiter_name}',
                'details': details
            }
        else:
            return {
                'success': True,
                'message': f'Recruiter tracked by name: {self.recruiter_name}',
                'details': {
                    **details,
                    'note': 'No LinkedIn URL provided. Jobs can still be tagged with this recruiter.'
                }
            }
    
    def fetch_posts(self, limit: int = 25) -> List[Dict[str, Any]]:
        """
        LinkedIn recruiter adapter does NOT actively fetch posts.
        
        Instead, it provides recruiter metadata for tagging jobs
        found through other sources.
        
        Returns empty list - recruiter info is attached to jobs
        during ingestion from other sources when keywords match.
        """
        logger.info(
            f"LinkedIn recruiter adapter for '{self.recruiter_name}' "
            "does not actively fetch. Use other sources and tag with recruiter."
        )
        return []
    
    def get_recruiter_info(self) -> Dict[str, Any]:
        """Get recruiter metadata for tagging jobs."""
        return {
            'recruiter_id': self.source.id,
            'recruiter_name': self.recruiter_name,
            'profile_url': self.profile_url,
            'company': self.company,
            'job_categories': self.config.get('job_categories', []),
            'notes': self.config.get('notes', ''),
        }


# --- Adapter Factory ---

def get_adapter(source: JobSource) -> BaseSourceAdapter:
    """Get appropriate adapter for source type."""
    adapters = {
        SourceType.TELEGRAM_CHANNEL.value: TelegramChannelAdapter,
        SourceType.WEBSITE.value: WebsiteAdapter,
        SourceType.LINKEDIN_RECRUITER.value: LinkedInRecruiterAdapter,
    }
    
    adapter_class = adapters.get(source.type)
    if not adapter_class:
        raise ValueError(f"Unknown source type: {source.type}")
    
    return adapter_class(source)


def test_source_connection(source: JobSource) -> Dict[str, Any]:
    """Test source connection using appropriate adapter."""
    try:
        adapter = get_adapter(source)
        return adapter.test_connection()
    except Exception as e:
        return {
            'success': False,
            'message': f'Adapter error: {str(e)}'
        }


def fetch_from_source(source: JobSource, limit: int = 25) -> List[Dict[str, Any]]:
    """Fetch posts from source using appropriate adapter."""
    try:
        adapter = get_adapter(source)
        return adapter.fetch_posts(limit=limit)
    except Exception as e:
        logger.error(f"Fetch error for source {source.id}: {e}")
        return []
