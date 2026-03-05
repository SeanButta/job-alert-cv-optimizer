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
            get_adapter, TelegramChannelAdapter, WebsiteAdapter, LinkedInRecruiterAdapter
        )
        
        tg_source = JobSource(type='telegram_channel', identifier='@test')
        web_source = JobSource(type='website', identifier='https://test.com')
        li_source = JobSource(type='linkedin_recruiter', identifier='John Doe')
        
        assert isinstance(get_adapter(tg_source), TelegramChannelAdapter)
        assert isinstance(get_adapter(web_source), WebsiteAdapter)
        assert isinstance(get_adapter(li_source), LinkedInRecruiterAdapter)

    def test_get_adapter_invalid_type(self):
        """Test adapter factory raises for invalid type."""
        from app.adapters.source_adapters import get_adapter
        
        source = JobSource(type='invalid', identifier='test')
        with pytest.raises(ValueError):
            get_adapter(source)


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
