"""
Platform adapters for job platforms.

Each adapter handles:
- Testing connectivity
- Fetching job posts
- Rate limiting
- Error handling

These are scaffold implementations. Production adapters should:
- Handle authentication where required
- Implement proper rate limiting
- Handle pagination
- Parse platform-specific job formats
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

from app.models.platforms import PlatformType, PlatformInfo, PLATFORMS

logger = logging.getLogger(__name__)


class BasePlatformAdapter(ABC):
    """Base class for platform adapters."""
    
    DEFAULT_TIMEOUT = 15
    DEFAULT_USER_AGENT = 'JobAlertBot/1.0 (automated job search)'
    
    def __init__(self, platform_type: PlatformType, config: Optional[dict] = None):
        self.platform_type = platform_type
        self.platform_info = PLATFORMS[platform_type]
        self.config = config or {}
    
    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """Test platform connectivity. Returns {success, message, details}."""
        pass
    
    @abstractmethod
    def fetch_jobs(self, limit: int = 25, filters: Optional[dict] = None) -> List[Dict[str, Any]]:
        """
        Fetch job listings from platform.
        
        Returns list of dicts with keys:
        - platform: str (platform type)
        - external_id: str (unique ID from platform)
        - title: str
        - company: str
        - description: str
        - link: str
        - location: str
        - remote: bool
        - salary_min: int (optional)
        - salary_max: int (optional)
        - posted_at: datetime (optional)
        - raw_data: dict (optional, original data)
        """
        pass
    
    def _make_request(
        self,
        url: str,
        method: str = 'GET',
        **kwargs
    ) -> requests.Response:
        """Make HTTP request with default headers and timeout."""
        headers = kwargs.pop('headers', {})
        headers.setdefault('User-Agent', self.DEFAULT_USER_AGENT)
        
        timeout = kwargs.pop('timeout', self.DEFAULT_TIMEOUT)
        
        return requests.request(
            method,
            url,
            headers=headers,
            timeout=timeout,
            **kwargs
        )


# --- Wellfound Adapter ---

class WellfoundAdapter(BasePlatformAdapter):
    """
    Adapter for Wellfound (formerly AngelList Talent).
    
    SCAFFOLD: Uses public job search page.
    Production: Use Wellfound API with authentication.
    """
    
    BASE_URL = 'https://wellfound.com'
    
    def __init__(self, config: Optional[dict] = None):
        super().__init__(PlatformType.WELLFOUND, config)
    
    def test_connection(self) -> Dict[str, Any]:
        try:
            resp = self._make_request(f'{self.BASE_URL}/jobs')
            if resp.ok:
                return {
                    'success': True,
                    'message': 'Wellfound accessible',
                    'details': {'status_code': resp.status_code}
                }
            return {
                'success': False,
                'message': f'HTTP {resp.status_code}',
                'details': {'status_code': resp.status_code}
            }
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def fetch_jobs(self, limit: int = 25, filters: Optional[dict] = None) -> List[Dict[str, Any]]:
        """SCAFFOLD: Returns empty list. Production: implement scraping or API."""
        logger.info("Wellfound adapter is a scaffold - returning empty list")
        return []


# --- YC Work at a Startup Adapter ---

class YCWorkAtStartupAdapter(BasePlatformAdapter):
    """
    Adapter for Y Combinator Work at a Startup.
    
    SCAFFOLD: Basic implementation.
    """
    
    BASE_URL = 'https://www.workatastartup.com'
    
    def __init__(self, config: Optional[dict] = None):
        super().__init__(PlatformType.YC_WORK_AT_STARTUP, config)
    
    def test_connection(self) -> Dict[str, Any]:
        try:
            resp = self._make_request(f'{self.BASE_URL}/jobs')
            if resp.ok:
                return {
                    'success': True,
                    'message': 'YC Work at a Startup accessible',
                    'details': {'status_code': resp.status_code}
                }
            return {'success': False, 'message': f'HTTP {resp.status_code}'}
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def fetch_jobs(self, limit: int = 25, filters: Optional[dict] = None) -> List[Dict[str, Any]]:
        logger.info("YC Work at a Startup adapter is a scaffold - returning empty list")
        return []


# --- Otta Adapter ---

class OttaAdapter(BasePlatformAdapter):
    """
    Adapter for Otta.
    
    SCAFFOLD: Requires account for API access.
    """
    
    BASE_URL = 'https://otta.com'
    
    def __init__(self, config: Optional[dict] = None):
        super().__init__(PlatformType.OTTA, config)
    
    def test_connection(self) -> Dict[str, Any]:
        return {
            'success': True,
            'message': 'Otta requires authentication for full access',
            'details': {'requires_auth': True}
        }
    
    def fetch_jobs(self, limit: int = 25, filters: Optional[dict] = None) -> List[Dict[str, Any]]:
        logger.info("Otta adapter requires auth - returning empty list")
        return []


# --- Built In Adapter ---

class BuiltInAdapter(BasePlatformAdapter):
    """Adapter for Built In."""
    
    BASE_URL = 'https://builtin.com'
    
    def __init__(self, config: Optional[dict] = None):
        super().__init__(PlatformType.BUILT_IN, config)
    
    def test_connection(self) -> Dict[str, Any]:
        try:
            resp = self._make_request(f'{self.BASE_URL}/jobs')
            return {
                'success': resp.ok,
                'message': 'Built In accessible' if resp.ok else f'HTTP {resp.status_code}'
            }
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def fetch_jobs(self, limit: int = 25, filters: Optional[dict] = None) -> List[Dict[str, Any]]:
        logger.info("Built In adapter is a scaffold - returning empty list")
        return []


# --- a16z Talent Adapter ---

class A16ZTalentAdapter(BasePlatformAdapter):
    """Adapter for a16z portfolio jobs."""
    
    BASE_URL = 'https://jobs.a16z.com'
    
    def __init__(self, config: Optional[dict] = None):
        super().__init__(PlatformType.A16Z_TALENT, config)
    
    def test_connection(self) -> Dict[str, Any]:
        try:
            resp = self._make_request(self.BASE_URL)
            return {
                'success': resp.ok,
                'message': 'a16z Talent accessible' if resp.ok else f'HTTP {resp.status_code}'
            }
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def fetch_jobs(self, limit: int = 25, filters: Optional[dict] = None) -> List[Dict[str, Any]]:
        logger.info("a16z Talent adapter is a scaffold - returning empty list")
        return []


# --- VC Portfolio Boards Adapter ---

class VCPortfolioBoardsAdapter(BasePlatformAdapter):
    """Generic adapter for VC portfolio job boards."""
    
    def __init__(self, config: Optional[dict] = None):
        super().__init__(PlatformType.VC_PORTFOLIO_BOARDS, config)
        self.vc_urls = config.get('vc_urls', []) if config else []
    
    def test_connection(self) -> Dict[str, Any]:
        return {
            'success': True,
            'message': 'VC Portfolio Boards adapter configured',
            'details': {'vc_count': len(self.vc_urls)}
        }
    
    def fetch_jobs(self, limit: int = 25, filters: Optional[dict] = None) -> List[Dict[str, Any]]:
        logger.info("VC Portfolio Boards adapter is a scaffold - returning empty list")
        return []


# --- Remote Job Board Adapters ---

class RemoteOKAdapter(BasePlatformAdapter):
    """Adapter for Remote OK (RSS feed)."""
    
    RSS_URL = 'https://remoteok.com/remote-jobs.rss'
    
    def __init__(self, config: Optional[dict] = None):
        super().__init__(PlatformType.REMOTE_OK, config)
    
    def test_connection(self) -> Dict[str, Any]:
        try:
            resp = self._make_request(self.RSS_URL)
            return {
                'success': resp.ok and 'xml' in resp.headers.get('content-type', '').lower(),
                'message': 'Remote OK RSS accessible' if resp.ok else f'HTTP {resp.status_code}'
            }
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def fetch_jobs(self, limit: int = 25, filters: Optional[dict] = None) -> List[Dict[str, Any]]:
        logger.info("Remote OK adapter is a scaffold - returning empty list")
        # Production: parse RSS feed
        return []


class WeWorkRemotelyAdapter(BasePlatformAdapter):
    """Adapter for We Work Remotely."""
    
    BASE_URL = 'https://weworkremotely.com'
    
    def __init__(self, config: Optional[dict] = None):
        super().__init__(PlatformType.WE_WORK_REMOTELY, config)
    
    def test_connection(self) -> Dict[str, Any]:
        try:
            resp = self._make_request(self.BASE_URL)
            return {
                'success': resp.ok,
                'message': 'We Work Remotely accessible' if resp.ok else f'HTTP {resp.status_code}'
            }
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def fetch_jobs(self, limit: int = 25, filters: Optional[dict] = None) -> List[Dict[str, Any]]:
        logger.info("We Work Remotely adapter is a scaffold - returning empty list")
        return []


class RemotiveAdapter(BasePlatformAdapter):
    """Adapter for Remotive."""
    
    BASE_URL = 'https://remotive.com'
    
    def __init__(self, config: Optional[dict] = None):
        super().__init__(PlatformType.REMOTIVE, config)
    
    def test_connection(self) -> Dict[str, Any]:
        try:
            resp = self._make_request(f'{self.BASE_URL}/remote-jobs')
            return {
                'success': resp.ok,
                'message': 'Remotive accessible' if resp.ok else f'HTTP {resp.status_code}'
            }
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def fetch_jobs(self, limit: int = 25, filters: Optional[dict] = None) -> List[Dict[str, Any]]:
        logger.info("Remotive adapter is a scaffold - returning empty list")
        return []


class WorkingNomadsAdapter(BasePlatformAdapter):
    """Adapter for Working Nomads."""
    
    BASE_URL = 'https://www.workingnomads.com'
    
    def __init__(self, config: Optional[dict] = None):
        super().__init__(PlatformType.WORKING_NOMADS, config)
    
    def test_connection(self) -> Dict[str, Any]:
        try:
            resp = self._make_request(f'{self.BASE_URL}/jobs')
            return {
                'success': resp.ok,
                'message': 'Working Nomads accessible' if resp.ok else f'HTTP {resp.status_code}'
            }
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def fetch_jobs(self, limit: int = 25, filters: Optional[dict] = None) -> List[Dict[str, Any]]:
        logger.info("Working Nomads adapter is a scaffold - returning empty list")
        return []


class FlexJobsAdapter(BasePlatformAdapter):
    """Adapter for FlexJobs (manual/feed mode)."""
    
    def __init__(self, config: Optional[dict] = None):
        super().__init__(PlatformType.FLEXJOBS, config)
    
    def test_connection(self) -> Dict[str, Any]:
        return {
            'success': True,
            'message': 'FlexJobs requires subscription - manual/feed mode',
            'details': {'requires_auth': True, 'mode': 'manual'}
        }
    
    def fetch_jobs(self, limit: int = 25, filters: Optional[dict] = None) -> List[Dict[str, Any]]:
        logger.info("FlexJobs adapter is manual mode - returning empty list")
        return []


# --- Large Aggregator Adapters ---

class LinkedInJobsAdapter(BasePlatformAdapter):
    """Adapter for LinkedIn Jobs (compliance-sensitive)."""
    
    def __init__(self, config: Optional[dict] = None):
        super().__init__(PlatformType.LINKEDIN_JOBS, config)
    
    def test_connection(self) -> Dict[str, Any]:
        return {
            'success': True,
            'message': 'LinkedIn Jobs requires authentication and careful compliance',
            'details': {'requires_auth': True, 'compliance_sensitive': True}
        }
    
    def fetch_jobs(self, limit: int = 25, filters: Optional[dict] = None) -> List[Dict[str, Any]]:
        logger.info("LinkedIn Jobs adapter disabled by default - compliance concerns")
        return []


class IndeedAdapter(BasePlatformAdapter):
    """Adapter for Indeed."""
    
    def __init__(self, config: Optional[dict] = None):
        super().__init__(PlatformType.INDEED, config)
    
    def test_connection(self) -> Dict[str, Any]:
        return {
            'success': True,
            'message': 'Indeed adapter scaffold ready',
            'details': {'note': 'High volume, needs strong filtering'}
        }
    
    def fetch_jobs(self, limit: int = 25, filters: Optional[dict] = None) -> List[Dict[str, Any]]:
        logger.info("Indeed adapter is a scaffold - returning empty list")
        return []


class ZipRecruiterAdapter(BasePlatformAdapter):
    """Adapter for ZipRecruiter."""
    
    def __init__(self, config: Optional[dict] = None):
        super().__init__(PlatformType.ZIPRECRUITER, config)
    
    def test_connection(self) -> Dict[str, Any]:
        return {
            'success': True,
            'message': 'ZipRecruiter adapter scaffold ready',
            'details': {'requires_auth': True}
        }
    
    def fetch_jobs(self, limit: int = 25, filters: Optional[dict] = None) -> List[Dict[str, Any]]:
        logger.info("ZipRecruiter adapter is a scaffold - returning empty list")
        return []


class GlassdoorAdapter(BasePlatformAdapter):
    """Adapter for Glassdoor."""
    
    def __init__(self, config: Optional[dict] = None):
        super().__init__(PlatformType.GLASSDOOR, config)
    
    def test_connection(self) -> Dict[str, Any]:
        return {
            'success': True,
            'message': 'Glassdoor adapter scaffold ready',
            'details': {'requires_auth': True}
        }
    
    def fetch_jobs(self, limit: int = 25, filters: Optional[dict] = None) -> List[Dict[str, Any]]:
        logger.info("Glassdoor adapter is a scaffold - returning empty list")
        return []


class GoogleJobsAdapter(BasePlatformAdapter):
    """Adapter for Google Jobs (aggregator input mode)."""
    
    def __init__(self, config: Optional[dict] = None):
        super().__init__(PlatformType.GOOGLE_JOBS, config)
    
    def test_connection(self) -> Dict[str, Any]:
        return {
            'success': True,
            'message': 'Google Jobs aggregator mode ready',
            'details': {'mode': 'aggregator', 'note': 'May duplicate from other sources'}
        }
    
    def fetch_jobs(self, limit: int = 25, filters: Optional[dict] = None) -> List[Dict[str, Any]]:
        logger.info("Google Jobs adapter is a scaffold - returning empty list")
        return []


# --- Adapter Factory ---

PLATFORM_ADAPTERS = {
    PlatformType.WELLFOUND: WellfoundAdapter,
    PlatformType.YC_WORK_AT_STARTUP: YCWorkAtStartupAdapter,
    PlatformType.OTTA: OttaAdapter,
    PlatformType.BUILT_IN: BuiltInAdapter,
    PlatformType.A16Z_TALENT: A16ZTalentAdapter,
    PlatformType.VC_PORTFOLIO_BOARDS: VCPortfolioBoardsAdapter,
    PlatformType.LINKEDIN_JOBS: LinkedInJobsAdapter,
    PlatformType.INDEED: IndeedAdapter,
    PlatformType.ZIPRECRUITER: ZipRecruiterAdapter,
    PlatformType.GLASSDOOR: GlassdoorAdapter,
    PlatformType.GOOGLE_JOBS: GoogleJobsAdapter,
    PlatformType.REMOTE_OK: RemoteOKAdapter,
    PlatformType.WE_WORK_REMOTELY: WeWorkRemotelyAdapter,
    PlatformType.FLEXJOBS: FlexJobsAdapter,
    PlatformType.REMOTIVE: RemotiveAdapter,
    PlatformType.WORKING_NOMADS: WorkingNomadsAdapter,
}


def get_platform_adapter(
    platform_type: PlatformType,
    config: Optional[dict] = None
) -> BasePlatformAdapter:
    """Get adapter for platform type."""
    adapter_class = PLATFORM_ADAPTERS.get(platform_type)
    if not adapter_class:
        raise ValueError(f"No adapter for platform: {platform_type}")
    return adapter_class(config)


def test_platform_connection(platform_type: PlatformType) -> Dict[str, Any]:
    """Test platform connection."""
    try:
        adapter = get_platform_adapter(platform_type)
        return adapter.test_connection()
    except Exception as e:
        return {'success': False, 'message': str(e)}
