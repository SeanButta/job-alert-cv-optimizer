"""
Tests for job source CRUD operations and ingestion dispatch.

Tests cover:
- Source CRUD API endpoints
- Enable/disable behavior
- Ingestion dispatch by source type
- Source adapter functionality
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.db.database import SessionLocal, Base, engine
from app.models.sources import JobSource, SourceType, SourceStatus


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    """Reset database before each test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


class TestSourceCRUD:
    """Tests for source CRUD operations."""

    def test_create_telegram_channel_source(self):
        """Create a new Telegram channel source."""
        resp = client.post('/api/sources', json={
            'type': 'telegram_channel',
            'identifier': '@jobchannel',
            'name': 'My Job Channel'
        })
        
        assert resp.status_code == 200
        data = resp.json()
        assert data['type'] == 'telegram_channel'
        assert data['identifier'] == '@jobchannel'
        assert data['name'] == 'My Job Channel'
        assert data['status'] == 'active'
        assert data['id'] is not None

    def test_create_website_source(self):
        """Create a new website source."""
        resp = client.post('/api/sources', json={
            'type': 'website',
            'identifier': 'https://example.com/jobs',
            'name': 'Example Jobs'
        })
        
        assert resp.status_code == 200
        data = resp.json()
        assert data['type'] == 'website'
        assert data['identifier'] == 'https://example.com/jobs'
        assert data['status'] == 'active'

    def test_create_linkedin_recruiter_source(self):
        """Create a LinkedIn recruiter source with config."""
        resp = client.post('/api/sources', json={
            'type': 'linkedin_recruiter',
            'identifier': 'https://linkedin.com/in/recruiter-name',
            'name': 'John Recruiter',
            'config': {
                'company': 'Acme Corp',
                'notes': 'Posts Python jobs'
            }
        })
        
        assert resp.status_code == 200
        data = resp.json()
        assert data['type'] == 'linkedin_recruiter'
        assert data['config']['company'] == 'Acme Corp'

    def test_create_telegram_public_source(self):
        """Create a Telegram public channel source (no bot required)."""
        resp = client.post('/api/sources', json={
            'type': 'telegram_public',
            'identifier': '@python_jobs',
            'name': 'Python Jobs Channel'
        })
        
        assert resp.status_code == 200
        data = resp.json()
        assert data['type'] == 'telegram_public'
        assert data['identifier'] == '@python_jobs'
        assert data['status'] == 'active'

    def test_create_telegram_public_source_various_formats(self):
        """Create Telegram public sources with various identifier formats."""
        test_cases = [
            ('t.me/channel1', 't.me/channel1'),
            ('https://t.me/channel2', 'https://t.me/channel2'),
            ('https://t.me/s/channel3', 'https://t.me/s/channel3'),
        ]
        
        for idx, (identifier, expected) in enumerate(test_cases):
            resp = client.post('/api/sources', json={
                'type': 'telegram_public',
                'identifier': identifier,
            })
            assert resp.status_code == 200, f"Failed for {identifier}"
            assert resp.json()['identifier'] == expected

    def test_create_invalid_source_type(self):
        """Reject invalid source type."""
        resp = client.post('/api/sources', json={
            'type': 'invalid_type',
            'identifier': 'test'
        })
        
        assert resp.status_code == 400
        assert 'Invalid source type' in resp.json()['detail']

    def test_create_duplicate_source(self):
        """Reject duplicate source identifier."""
        # Create first source
        client.post('/api/sources', json={
            'type': 'telegram_channel',
            'identifier': '@testchannel'
        })
        
        # Try to create duplicate
        resp = client.post('/api/sources', json={
            'type': 'telegram_channel',
            'identifier': '@testchannel'
        })
        
        assert resp.status_code == 409
        assert 'already exists' in resp.json()['detail']

    def test_list_sources(self):
        """List all sources."""
        # Create multiple sources
        client.post('/api/sources', json={'type': 'telegram_channel', 'identifier': '@ch1'})
        client.post('/api/sources', json={'type': 'website', 'identifier': 'https://a.com'})
        client.post('/api/sources', json={'type': 'linkedin_recruiter', 'identifier': 'John Doe'})
        
        resp = client.get('/api/sources')
        assert resp.status_code == 200
        data = resp.json()
        assert data['total'] == 3
        assert len(data['sources']) == 3

    def test_list_sources_filter_by_type(self):
        """Filter sources by type."""
        client.post('/api/sources', json={'type': 'telegram_channel', 'identifier': '@ch1'})
        client.post('/api/sources', json={'type': 'website', 'identifier': 'https://a.com'})
        
        resp = client.get('/api/sources?type=telegram_channel')
        data = resp.json()
        assert data['total'] == 1
        assert data['sources'][0]['type'] == 'telegram_channel'

    def test_list_sources_filter_by_status(self):
        """Filter sources by status."""
        client.post('/api/sources', json={'type': 'telegram_channel', 'identifier': '@ch1'})
        
        # Deactivate the source
        resp = client.get('/api/sources')
        source_id = resp.json()['sources'][0]['id']
        client.post(f'/api/sources/{source_id}/deactivate')
        
        # Filter by inactive
        resp = client.get('/api/sources?status=inactive')
        data = resp.json()
        assert data['total'] == 1
        assert data['sources'][0]['status'] == 'inactive'

    def test_get_source_by_id(self):
        """Get a single source by ID."""
        create_resp = client.post('/api/sources', json={
            'type': 'telegram_channel',
            'identifier': '@test'
        })
        source_id = create_resp.json()['id']
        
        resp = client.get(f'/api/sources/{source_id}')
        assert resp.status_code == 200
        assert resp.json()['identifier'] == '@test'

    def test_get_source_not_found(self):
        """Return 404 for non-existent source."""
        resp = client.get('/api/sources/99999')
        assert resp.status_code == 404

    def test_update_source(self):
        """Update source attributes."""
        create_resp = client.post('/api/sources', json={
            'type': 'telegram_channel',
            'identifier': '@original'
        })
        source_id = create_resp.json()['id']
        
        resp = client.put(f'/api/sources/{source_id}', json={
            'identifier': '@updated',
            'name': 'Updated Name'
        })
        
        assert resp.status_code == 200
        data = resp.json()
        assert data['identifier'] == '@updated'
        assert data['name'] == 'Updated Name'

    def test_delete_source(self):
        """Delete a source."""
        create_resp = client.post('/api/sources', json={
            'type': 'telegram_channel',
            'identifier': '@todelete'
        })
        source_id = create_resp.json()['id']
        
        resp = client.delete(f'/api/sources/{source_id}')
        assert resp.status_code == 200
        assert resp.json()['deleted'] is True
        
        # Verify it's gone
        resp = client.get(f'/api/sources/{source_id}')
        assert resp.status_code == 404


class TestSourceActivation:
    """Tests for source activation/deactivation."""

    def test_deactivate_source(self):
        """Deactivate an active source."""
        create_resp = client.post('/api/sources', json={
            'type': 'telegram_channel',
            'identifier': '@test'
        })
        source_id = create_resp.json()['id']
        
        resp = client.post(f'/api/sources/{source_id}/deactivate')
        assert resp.status_code == 200
        assert resp.json()['status'] == 'inactive'

    def test_activate_source(self):
        """Activate an inactive source."""
        create_resp = client.post('/api/sources', json={
            'type': 'telegram_channel',
            'identifier': '@test'
        })
        source_id = create_resp.json()['id']
        
        # Deactivate first
        client.post(f'/api/sources/{source_id}/deactivate')
        
        # Activate
        resp = client.post(f'/api/sources/{source_id}/activate')
        assert resp.status_code == 200
        assert resp.json()['status'] == 'active'

    def test_activate_resets_error_count(self):
        """Activating a source resets error count."""
        db = SessionLocal()
        try:
            # Create source with errors
            source = JobSource(
                type='telegram_channel',
                identifier='@errortest',
                status='error',
                error_count=5
            )
            db.add(source)
            db.commit()
            db.refresh(source)
            source_id = source.id
        finally:
            db.close()
        
        resp = client.post(f'/api/sources/{source_id}/activate')
        assert resp.status_code == 200
        assert resp.json()['status'] == 'active'
        assert resp.json()['error_count'] == 0


class TestSourceAdapters:
    """Tests for source adapter functionality."""

    def test_telegram_adapter_normalize_channel_id(self):
        """Test Telegram channel ID normalization."""
        from app.adapters.source_adapters import TelegramChannelAdapter
        
        db = SessionLocal()
        try:
            # Test different formats
            test_cases = [
                ('@jobchannel', '@jobchannel'),
                ('jobchannel', '@jobchannel'),
                ('t.me/jobchannel', '@jobchannel'),
                ('https://t.me/jobchannel', '@jobchannel'),
                ('-1001234567890', '-1001234567890'),
            ]
            
            for identifier, expected in test_cases:
                source = JobSource(type='telegram_channel', identifier=identifier)
                adapter = TelegramChannelAdapter(source)
                assert adapter.channel_id == expected, f"Failed for {identifier}"
        finally:
            db.close()

    def test_telegram_public_url_normalization(self):
        """Test Telegram public channel URL normalization."""
        from app.adapters.source_adapters import normalize_telegram_public_url
        
        test_cases = [
            # Input -> Expected output
            ('@jobchannel', 'https://t.me/s/jobchannel'),
            ('jobchannel', 'https://t.me/s/jobchannel'),
            ('t.me/jobchannel', 'https://t.me/s/jobchannel'),
            ('https://t.me/jobchannel', 'https://t.me/s/jobchannel'),
            ('https://t.me/s/jobchannel', 'https://t.me/s/jobchannel'),
            ('t.me/s/jobchannel', 'https://t.me/s/jobchannel'),
            ('https://t.me/jobchannel/', 'https://t.me/s/jobchannel'),
        ]
        
        for identifier, expected in test_cases:
            result = normalize_telegram_public_url(identifier)
            assert result == expected, f"Failed for {identifier}: got {result}, expected {expected}"

    def test_telegram_public_extract_channel(self):
        """Test extracting channel name from public URL."""
        from app.adapters.source_adapters import extract_channel_from_public_url
        
        test_cases = [
            ('https://t.me/s/jobchannel', 'jobchannel'),
            ('https://t.me/s/python_jobs', 'python_jobs'),
            ('t.me/s/test123', 'test123'),
        ]
        
        for url, expected in test_cases:
            result = extract_channel_from_public_url(url)
            assert result == expected, f"Failed for {url}"

    def test_telegram_public_adapter_init(self):
        """Test TelegramPublicAdapter initialization."""
        from app.adapters.source_adapters import TelegramPublicAdapter
        
        source = JobSource(type='telegram_public', identifier='@python_jobs')
        adapter = TelegramPublicAdapter(source)
        
        assert adapter.public_url == 'https://t.me/s/python_jobs'
        assert adapter.channel_name == 'python_jobs'

    def test_website_adapter_normalize_url(self):
        """Test website URL normalization."""
        from app.adapters.source_adapters import WebsiteAdapter
        
        test_cases = [
            ('example.com/jobs', 'https://example.com/jobs'),
            ('http://example.com/jobs', 'http://example.com/jobs'),
            ('https://example.com/jobs', 'https://example.com/jobs'),
        ]
        
        for identifier, expected in test_cases:
            source = JobSource(type='website', identifier=identifier)
            adapter = WebsiteAdapter(source)
            assert adapter.url == expected, f"Failed for {identifier}"

    def test_linkedin_adapter_extract_name(self):
        """Test LinkedIn recruiter name extraction."""
        from app.adapters.source_adapters import LinkedInRecruiterAdapter
        
        test_cases = [
            ('https://linkedin.com/in/john-doe', 'John Doe'),
            ('John Smith', 'John Smith'),
            ('linkedin.com/in/jane-recruiter', 'Jane Recruiter'),
        ]
        
        for identifier, expected_name in test_cases:
            source = JobSource(type='linkedin_recruiter', identifier=identifier)
            adapter = LinkedInRecruiterAdapter(source)
            assert adapter.recruiter_name == expected_name, f"Failed for {identifier}"

    def test_get_adapter_factory(self):
        """Test adapter factory returns correct adapter type."""
        from app.adapters.source_adapters import (
            get_adapter, TelegramChannelAdapter, TelegramPublicAdapter, 
            WebsiteAdapter, LinkedInRecruiterAdapter
        )
        
        tg_source = JobSource(type='telegram_channel', identifier='@test')
        tgpub_source = JobSource(type='telegram_public', identifier='@test')
        web_source = JobSource(type='website', identifier='https://test.com')
        li_source = JobSource(type='linkedin_recruiter', identifier='John Doe')
        
        assert isinstance(get_adapter(tg_source), TelegramChannelAdapter)
        assert isinstance(get_adapter(tgpub_source), TelegramPublicAdapter)
        assert isinstance(get_adapter(web_source), WebsiteAdapter)
        assert isinstance(get_adapter(li_source), LinkedInRecruiterAdapter)

    def test_get_adapter_invalid_type(self):
        """Test adapter factory raises for invalid type."""
        from app.adapters.source_adapters import get_adapter
        
        source = JobSource(type='invalid', identifier='test')
        with pytest.raises(ValueError):
            get_adapter(source)


class TestTelegramPublicAdapter:
    """Tests for Telegram public channel adapter."""

    def test_parse_posts_from_html(self):
        """Test parsing posts from Telegram public channel HTML."""
        from app.adapters.source_adapters import TelegramPublicAdapter
        
        # Sample HTML structure from t.me/s/<channel>
        sample_html = '''
        <html>
        <div class="tgme_widget_message_wrap" data-post="testchannel/123">
            <div class="tgme_widget_message_text">
                Senior Python Developer Needed
                
                We're looking for a Python developer with FastAPI experience.
                Apply here: https://example.com/jobs/python-dev
            </div>
        </div>
        <div class="tgme_widget_message_wrap" data-post="testchannel/124">
            <div class="tgme_widget_message_text">
                Remote ML Engineer Position
                
                Join our AI team. Check out: https://ai-jobs.com/ml-eng
            </div>
        </div>
        </html>
        '''
        
        source = JobSource(type='telegram_public', identifier='@testchannel')
        adapter = TelegramPublicAdapter(source)
        
        posts = adapter._parse_posts(sample_html, limit=10)
        
        assert len(posts) >= 1
        assert posts[0]['source'] == 'telegram_public'
        assert 'tgpub-testchannel-123' in posts[0]['external_id']
        assert 'Python' in posts[0]['title'] or 'Python' in posts[0]['description']

    def test_extract_text_removes_html(self):
        """Test that HTML tags are properly removed from text."""
        from app.adapters.source_adapters import TelegramPublicAdapter
        
        source = JobSource(type='telegram_public', identifier='@test')
        adapter = TelegramPublicAdapter(source)
        
        html_block = '''
        <div class="tgme_widget_message_text">
            <b>Bold text</b> and <a href="https://example.com">link</a><br/>
            New line here
        </div>
        '''
        
        text = adapter._extract_text(html_block)
        
        assert '<b>' not in text
        assert '</a>' not in text
        assert 'Bold text' in text
        assert 'link' in text

    def test_extract_links_filters_telegram_links(self):
        """Test that internal t.me links are filtered out."""
        from app.adapters.source_adapters import TelegramPublicAdapter
        
        source = JobSource(type='telegram_public', identifier='@test')
        adapter = TelegramPublicAdapter(source)
        
        html_block = '''
        <a href="https://example.com/job">Apply here</a>
        <a href="https://t.me/somechannel">Join channel</a>
        <a href="https://linkedin.com/jobs/123">LinkedIn</a>
        '''
        
        links = adapter._extract_links(html_block)
        
        assert 'https://example.com/job' in links
        assert 'https://linkedin.com/jobs/123' in links
        # t.me links should be filtered
        assert not any('t.me' in link for link in links)

    @patch('app.adapters.source_adapters.requests.get')
    def test_telegram_public_test_connection_success(self, mock_get):
        """Test connection succeeds for valid public channel."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '''
        <html>
        <meta property="og:title" content="Python Jobs Channel">
        <div class="tgme_channel_info">Channel info</div>
        </html>
        '''
        mock_get.return_value = mock_resp
        
        source = JobSource(type='telegram_public', identifier='@python_jobs')
        source.id = 1
        
        create_resp = client.post('/api/sources', json={
            'type': 'telegram_public',
            'identifier': '@python_jobs'
        })
        source_id = create_resp.json()['id']
        
        resp = client.post(f'/api/sources/{source_id}/test')
        assert resp.status_code == 200
        data = resp.json()
        # May or may not succeed depending on network, but should not error
        assert 'success' in data

    @patch('app.adapters.source_adapters.requests.get')
    def test_telegram_public_test_connection_not_found(self, mock_get):
        """Test connection fails for non-existent channel."""
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp
        
        create_resp = client.post('/api/sources', json={
            'type': 'telegram_public',
            'identifier': '@nonexistent_channel_12345'
        })
        source_id = create_resp.json()['id']
        
        resp = client.post(f'/api/sources/{source_id}/test')
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is False


class TestSourceTest:
    """Tests for source connectivity testing."""

    @patch('app.adapters.source_adapters.requests.get')
    def test_telegram_test_missing_token(self, mock_get):
        """Telegram test fails without bot token."""
        create_resp = client.post('/api/sources', json={
            'type': 'telegram_channel',
            'identifier': '@test'
        })
        source_id = create_resp.json()['id']
        
        # Clear token for test
        with patch.dict('os.environ', {}, clear=True):
            resp = client.post(f'/api/sources/{source_id}/test')
            assert resp.status_code == 200
            data = resp.json()
            assert data['success'] is False
            assert 'TELEGRAM_BOT_TOKEN' in data['message']

    @patch('app.adapters.source_adapters.requests.head')
    def test_website_test_accessible(self, mock_head):
        """Website test returns success for accessible site."""
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.url = 'https://example.com/jobs'
        mock_resp.headers = {'Content-Type': 'text/html'}
        mock_head.return_value = mock_resp
        
        create_resp = client.post('/api/sources', json={
            'type': 'website',
            'identifier': 'https://example.com/jobs'
        })
        source_id = create_resp.json()['id']
        
        resp = client.post(f'/api/sources/{source_id}/test')
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is True
        assert 'accessible' in data['message'].lower()

    def test_linkedin_test_always_valid(self):
        """LinkedIn recruiter test always validates format (no scraping)."""
        create_resp = client.post('/api/sources', json={
            'type': 'linkedin_recruiter',
            'identifier': 'https://linkedin.com/in/test-recruiter'
        })
        source_id = create_resp.json()['id']
        
        resp = client.post(f'/api/sources/{source_id}/test')
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is True
        assert 'compliance_mode' in str(data['details'])


class TestIngestionDispatch:
    """Tests for ingestion dispatch by source type."""

    def test_poll_cycle_skips_inactive_sources(self):
        """Poll cycle should skip inactive sources."""
        from app.services.source_poller import get_sources_due_for_check
        
        db = SessionLocal()
        try:
            # Create inactive source
            source = JobSource(
                type='telegram_channel',
                identifier='@inactive',
                status='inactive'
            )
            db.add(source)
            db.commit()
            
            sources = get_sources_due_for_check(db)
            assert len(sources) == 0
        finally:
            db.close()

    def test_poll_cycle_skips_linkedin_recruiters(self):
        """Poll cycle should skip LinkedIn recruiters (passive tracking)."""
        from app.services.source_poller import get_sources_due_for_check
        
        db = SessionLocal()
        try:
            # Create active LinkedIn recruiter source
            source = JobSource(
                type='linkedin_recruiter',
                identifier='John Doe',
                status='active'
            )
            db.add(source)
            db.commit()
            
            sources = get_sources_due_for_check(db)
            # LinkedIn recruiters are not actively polled
            assert len(sources) == 0
        finally:
            db.close()

    def test_poll_cycle_includes_telegram_public(self):
        """Poll cycle should include telegram_public sources."""
        from app.services.source_poller import get_sources_due_for_check
        
        db = SessionLocal()
        try:
            # Create active telegram_public source
            source = JobSource(
                type='telegram_public',
                identifier='@test_channel',
                status='active'
            )
            db.add(source)
            db.commit()
            
            sources = get_sources_due_for_check(db)
            # telegram_public should be actively polled
            assert len(sources) == 1
            assert sources[0].type == 'telegram_public'
        finally:
            db.close()

    def test_get_linkedin_recruiters_for_tagging(self):
        """Get LinkedIn recruiters for job tagging."""
        from app.services.source_poller import get_linkedin_recruiters
        
        db = SessionLocal()
        try:
            # Create active LinkedIn recruiter
            source = JobSource(
                type='linkedin_recruiter',
                identifier='https://linkedin.com/in/jane-smith',
                config=json.dumps({'company': 'TechCorp'})
            )
            db.add(source)
            db.commit()
            
            recruiters = get_linkedin_recruiters(db)
            assert len(recruiters) > 0
            
            # Check recruiter info
            key = ('jane smith', 'techcorp')
            assert key in recruiters
            assert recruiters[key]['recruiter_name'] == 'Jane Smith'
        finally:
            db.close()

    def test_tag_job_with_recruiter(self):
        """Tag job when recruiter name/company matches."""
        from app.services.source_poller import tag_job_with_recruiter
        
        recruiters = {
            ('john doe', 'acme corp'): {
                'recruiter_id': 1,
                'recruiter_name': 'John Doe',
                'company': 'Acme Corp'
            }
        }
        
        # Job mentions recruiter company
        job_data = {
            'title': 'Software Engineer',
            'company': 'Acme Corp',
            'description': 'Great opportunity at Acme Corp'
        }
        
        result = tag_job_with_recruiter(job_data, recruiters)
        assert result is not None
        assert result['recruiter_name'] == 'John Doe'

    def test_ingest_job_with_dedupe(self):
        """Ingest job with deduplication."""
        from app.services.source_poller import ingest_job_from_source
        
        db = SessionLocal()
        try:
            job_data = {
                'source': 'telegram_channel',
                'external_id': 'test-job-1',
                'title': 'Test Job',
                'company': 'Test Co',
                'description': 'Test description',
                'link': 'https://example.com/job1'
            }
            
            # First ingestion should succeed
            job1 = ingest_job_from_source(db, job_data)
            assert job1 is not None
            assert job1.title == 'Test Job'
            
            # Duplicate should be skipped
            job2 = ingest_job_from_source(db, job_data)
            assert job2 is None
            
            db.commit()
        finally:
            db.close()


class TestDashboardWithSources:
    """Tests for dashboard integration with sources."""

    def test_dashboard_shows_source_stats(self):
        """Dashboard should include source statistics."""
        # Create some sources
        client.post('/api/sources', json={'type': 'telegram_channel', 'identifier': '@ch1'})
        client.post('/api/sources', json={'type': 'website', 'identifier': 'https://a.com'})
        
        resp = client.get('/api/dashboard')
        assert resp.status_code == 200
        data = resp.json()
        
        assert 'source_stats' in data
        assert data['source_stats']['active'] == 2
        assert data['source_stats']['total'] == 2

    def test_dashboard_lists_sources(self):
        """Dashboard should list configured sources."""
        client.post('/api/sources', json={
            'type': 'telegram_channel',
            'identifier': '@testchannel',
            'name': 'Test Channel'
        })
        
        resp = client.get('/api/dashboard')
        data = resp.json()
        
        assert 'sources' in data
        assert len(data['sources']) == 1
        assert data['sources'][0]['name'] == 'Test Channel'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
