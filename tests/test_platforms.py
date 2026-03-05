"""
Tests for platform toggles and priority ranking.

Tests cover:
- Platform toggle enable/disable API
- Toggle persistence in database
- Platform priority order usage
- Platform adapter factory
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.db.database import SessionLocal, Base, engine
from app.models.platform_settings import PlatformSetting
from app.models.platforms import (
    PlatformType, PLATFORMS, get_platforms_by_priority,
    get_platform_priority_list, get_default_enabled_platforms
)


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    """Reset database before each test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


class TestPlatformDefinitions:
    """Tests for platform definitions."""

    def test_all_platforms_defined(self):
        """All 16 platforms should be defined."""
        assert len(PLATFORMS) == 16

    def test_platform_types_match_definitions(self):
        """All PlatformType values should have matching definitions."""
        for platform_type in PlatformType:
            assert platform_type in PLATFORMS
            assert PLATFORMS[platform_type].type == platform_type

    def test_platforms_have_required_fields(self):
        """Each platform should have all required fields."""
        for platform_type, info in PLATFORMS.items():
            assert info.name
            assert info.description
            assert info.priority >= 1
            assert info.adapter_type in ('api', 'scraper', 'feed', 'aggregator', 'manual')
            assert info.rate_limit_per_hour > 0

    def test_priorities_are_unique(self):
        """Each platform should have a unique priority."""
        priorities = [info.priority for info in PLATFORMS.values()]
        assert len(priorities) == len(set(priorities))

    def test_priorities_are_sequential(self):
        """Priorities should be 1 through N."""
        priorities = sorted(info.priority for info in PLATFORMS.values())
        assert priorities == list(range(1, len(PLATFORMS) + 1))


class TestPlatformPriority:
    """Tests for platform priority ordering."""

    def test_get_platforms_by_priority_returns_sorted(self):
        """Platforms should be returned in priority order."""
        platforms = get_platforms_by_priority()
        priorities = [p.priority for p in platforms]
        assert priorities == sorted(priorities)

    def test_yc_is_highest_priority(self):
        """YC Work at a Startup should be priority 1."""
        platforms = get_platforms_by_priority()
        assert platforms[0].type == PlatformType.YC_WORK_AT_STARTUP
        assert platforms[0].priority == 1

    def test_google_jobs_is_lowest_priority(self):
        """Google Jobs should be lowest priority (aggregator)."""
        platforms = get_platforms_by_priority()
        assert platforms[-1].type == PlatformType.GOOGLE_JOBS
        assert platforms[-1].priority == 16

    def test_get_platform_priority_list(self):
        """Priority list should be platform type values in order."""
        priority_list = get_platform_priority_list()
        assert len(priority_list) == 16
        assert priority_list[0] == 'yc_work_at_startup'
        assert priority_list[-1] == 'google_jobs'

    def test_startup_boards_before_aggregators(self):
        """Startup boards should come before large aggregators."""
        priority_list = get_platform_priority_list()
        yc_idx = priority_list.index('yc_work_at_startup')
        wellfound_idx = priority_list.index('wellfound')
        linkedin_idx = priority_list.index('linkedin_jobs')
        indeed_idx = priority_list.index('indeed')
        
        assert yc_idx < linkedin_idx
        assert wellfound_idx < indeed_idx


class TestDefaultEnabled:
    """Tests for default enabled platforms."""

    def test_get_default_enabled_platforms(self):
        """Should return platforms that are enabled by default."""
        defaults = get_default_enabled_platforms()
        assert len(defaults) > 0
        
        for p in defaults:
            assert p.default_enabled is True

    def test_high_quality_platforms_enabled_by_default(self):
        """High-quality startup boards should be enabled by default."""
        defaults = {p.type for p in get_default_enabled_platforms()}
        
        assert PlatformType.YC_WORK_AT_STARTUP in defaults
        assert PlatformType.WELLFOUND in defaults
        assert PlatformType.A16Z_TALENT in defaults

    def test_large_aggregators_disabled_by_default(self):
        """Large aggregators should be disabled by default."""
        defaults = {p.type for p in get_default_enabled_platforms()}
        
        assert PlatformType.LINKEDIN_JOBS not in defaults
        assert PlatformType.INDEED not in defaults
        assert PlatformType.ZIPRECRUITER not in defaults


class TestPlatformToggleAPI:
    """Tests for platform toggle API endpoints."""

    def test_list_platforms(self):
        """GET /api/platforms should return all platforms."""
        resp = client.get('/api/platforms')
        
        assert resp.status_code == 200
        data = resp.json()
        assert data['total'] == 16
        assert len(data['platforms']) == 16

    def test_list_platforms_sorted_by_priority(self):
        """Platforms should be returned in priority order."""
        resp = client.get('/api/platforms')
        data = resp.json()
        
        priorities = [p['priority'] for p in data['platforms']]
        assert priorities == sorted(priorities)

    def test_get_single_platform(self):
        """GET /api/platforms/{platform} should return platform info."""
        resp = client.get('/api/platforms/wellfound')
        
        assert resp.status_code == 200
        data = resp.json()
        assert data['type'] == 'wellfound'
        assert data['name'] == 'Wellfound (AngelList Talent)'
        assert 'description' in data

    def test_get_unknown_platform_returns_404(self):
        """Unknown platform should return 404."""
        resp = client.get('/api/platforms/nonexistent')
        assert resp.status_code == 404

    def test_enable_platform(self):
        """POST /api/platforms/{platform}/enable should enable."""
        # First disable
        client.post('/api/platforms/wellfound/disable')
        
        # Then enable
        resp = client.post('/api/platforms/wellfound/enable')
        
        assert resp.status_code == 200
        data = resp.json()
        assert data['enabled'] is True

    def test_disable_platform(self):
        """POST /api/platforms/{platform}/disable should disable."""
        resp = client.post('/api/platforms/wellfound/disable')
        
        assert resp.status_code == 200
        data = resp.json()
        assert data['enabled'] is False

    def test_toggle_persists_in_database(self):
        """Toggle changes should persist to database."""
        # Disable platform
        client.post('/api/platforms/wellfound/disable')
        
        # Check database
        db = SessionLocal()
        try:
            setting = db.scalar(
                select(PlatformSetting).where(
                    PlatformSetting.platform == 'wellfound'
                )
            )
            assert setting is not None
            assert setting.enabled is False
        finally:
            db.close()
        
        # Enable platform
        client.post('/api/platforms/wellfound/enable')
        
        # Check database again
        db = SessionLocal()
        try:
            setting = db.scalar(
                select(PlatformSetting).where(
                    PlatformSetting.platform == 'wellfound'
                )
            )
            assert setting.enabled is True
        finally:
            db.close()

    def test_enable_resets_error_count(self):
        """Enabling a platform should reset error count."""
        db = SessionLocal()
        try:
            # Create setting with errors
            setting = PlatformSetting(
                platform='wellfound',
                enabled=False,
                error_count=5
            )
            db.add(setting)
            db.commit()
        finally:
            db.close()
        
        # Enable platform
        resp = client.post('/api/platforms/wellfound/enable')
        
        assert resp.status_code == 200
        data = resp.json()
        assert data['enabled'] is True
        assert data['error_count'] == 0

    def test_get_priority_endpoint(self):
        """GET /api/platforms/priority should return priority order."""
        resp = client.get('/api/platforms/priority')
        
        assert resp.status_code == 200
        data = resp.json()
        assert 'priority_order' in data
        assert len(data['priority_order']) == 16
        assert data['priority_order'][0] == 'yc_work_at_startup'


class TestPlatformAdapters:
    """Tests for platform adapter factory."""

    def test_get_adapter_for_each_platform(self):
        """Should be able to get adapter for each platform type."""
        from app.adapters.platform_adapters import get_platform_adapter
        
        for platform_type in PlatformType:
            adapter = get_platform_adapter(platform_type)
            assert adapter is not None
            assert adapter.platform_type == platform_type

    def test_adapter_test_connection(self):
        """Each adapter should have test_connection method."""
        from app.adapters.platform_adapters import get_platform_adapter
        
        for platform_type in PlatformType:
            adapter = get_platform_adapter(platform_type)
            result = adapter.test_connection()
            
            assert 'success' in result
            assert 'message' in result

    def test_adapter_fetch_jobs_returns_list(self):
        """Each adapter should return a list from fetch_jobs."""
        from app.adapters.platform_adapters import get_platform_adapter
        
        for platform_type in PlatformType:
            adapter = get_platform_adapter(platform_type)
            jobs = adapter.fetch_jobs(limit=5)
            
            assert isinstance(jobs, list)


class TestSourcePollerPriority:
    """Tests for source poller using platform priority."""

    def test_get_enabled_platforms(self):
        """Should return enabled platforms correctly."""
        from app.services.source_poller import get_enabled_platforms
        
        db = SessionLocal()
        try:
            # Create some settings
            db.add(PlatformSetting(platform='wellfound', enabled=True))
            db.add(PlatformSetting(platform='linkedin_jobs', enabled=False))
            db.commit()
            
            enabled = get_enabled_platforms(db)
            
            assert 'wellfound' in enabled
            assert 'linkedin_jobs' not in enabled
        finally:
            db.close()

    def test_default_enabled_used_without_explicit_setting(self):
        """Default-enabled platforms should be enabled without explicit setting."""
        from app.services.source_poller import get_enabled_platforms
        
        db = SessionLocal()
        try:
            enabled = get_enabled_platforms(db)
            
            # YC is default enabled
            assert 'yc_work_at_startup' in enabled
        finally:
            db.close()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
