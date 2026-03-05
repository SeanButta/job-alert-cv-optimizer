"""
Job platform definitions with metadata, descriptions, and priority ranking.

Platforms are ranked by data quality, freshness, and relevance for job alerts.
Priority 1 = best/most trusted, higher numbers = lower priority.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class PlatformType(str, Enum):
    """Supported job platform types."""
    WELLFOUND = "wellfound"
    YC_WORK_AT_STARTUP = "yc_work_at_startup"
    OTTA = "otta"
    BUILT_IN = "built_in"
    A16Z_TALENT = "a16z_talent"
    VC_PORTFOLIO_BOARDS = "vc_portfolio_boards"
    LINKEDIN_JOBS = "linkedin_jobs"
    INDEED = "indeed"
    ZIPRECRUITER = "ziprecruiter"
    GLASSDOOR = "glassdoor"
    GOOGLE_JOBS = "google_jobs"
    REMOTE_OK = "remote_ok"
    WE_WORK_REMOTELY = "we_work_remotely"
    FLEXJOBS = "flexjobs"
    REMOTIVE = "remotive"
    WORKING_NOMADS = "working_nomads"


@dataclass
class PlatformInfo:
    """Platform metadata and configuration."""
    type: PlatformType
    name: str
    description: str
    priority: int  # 1 = highest priority (poll first)
    default_enabled: bool
    adapter_type: str  # 'api', 'scraper', 'feed', 'aggregator', 'manual'
    requires_auth: bool
    rate_limit_per_hour: int
    notes: str = ""


# Platform definitions with ranked priority (1 = best sources, higher = lower priority)
PLATFORMS: Dict[PlatformType, PlatformInfo] = {
    # --- Tier 1: Startup/VC focused, high signal-to-noise ---
    PlatformType.YC_WORK_AT_STARTUP: PlatformInfo(
        type=PlatformType.YC_WORK_AT_STARTUP,
        name="Y Combinator Work at a Startup",
        description="Curated jobs from YC-backed startups with strong growth potential.",
        priority=1,
        default_enabled=True,
        adapter_type="scraper",
        requires_auth=False,
        rate_limit_per_hour=30,
        notes="High-quality startup jobs, excellent signal-to-noise ratio"
    ),
    PlatformType.WELLFOUND: PlatformInfo(
        type=PlatformType.WELLFOUND,
        name="Wellfound (AngelList Talent)",
        description="Startup jobs with salary transparency and equity details upfront.",
        priority=2,
        default_enabled=True,
        adapter_type="api",
        requires_auth=False,
        rate_limit_per_hour=60,
        notes="Formerly AngelList, excellent for startup roles"
    ),
    PlatformType.A16Z_TALENT: PlatformInfo(
        type=PlatformType.A16Z_TALENT,
        name="a16z Talent",
        description="Jobs from Andreessen Horowitz portfolio companies.",
        priority=3,
        default_enabled=True,
        adapter_type="scraper",
        requires_auth=False,
        rate_limit_per_hour=20,
        notes="High-growth companies backed by top-tier VC"
    ),
    PlatformType.VC_PORTFOLIO_BOARDS: PlatformInfo(
        type=PlatformType.VC_PORTFOLIO_BOARDS,
        name="VC Portfolio Boards",
        description="Aggregated jobs from Sequoia, Greylock, and other top VC portfolios.",
        priority=4,
        default_enabled=True,
        adapter_type="scraper",
        requires_auth=False,
        rate_limit_per_hour=15,
        notes="Generic adapter for various VC portfolio job boards"
    ),
    PlatformType.OTTA: PlatformInfo(
        type=PlatformType.OTTA,
        name="Otta",
        description="Personalized startup job matches with company culture insights.",
        priority=5,
        default_enabled=True,
        adapter_type="api",
        requires_auth=True,
        rate_limit_per_hour=30,
        notes="Strong for tech roles, requires account for full access"
    ),
    PlatformType.BUILT_IN: PlatformInfo(
        type=PlatformType.BUILT_IN,
        name="Built In",
        description="Tech jobs with detailed company profiles and local market focus.",
        priority=6,
        default_enabled=True,
        adapter_type="scraper",
        requires_auth=False,
        rate_limit_per_hour=40,
        notes="Good for location-specific tech hubs (NYC, SF, etc.)"
    ),
    
    # --- Tier 2: Remote-focused boards ---
    PlatformType.REMOTE_OK: PlatformInfo(
        type=PlatformType.REMOTE_OK,
        name="Remote OK",
        description="Verified remote jobs with salary data and company remote-work culture.",
        priority=7,
        default_enabled=True,
        adapter_type="feed",
        requires_auth=False,
        rate_limit_per_hour=60,
        notes="RSS feed available, good for remote-first roles"
    ),
    PlatformType.WE_WORK_REMOTELY: PlatformInfo(
        type=PlatformType.WE_WORK_REMOTELY,
        name="We Work Remotely",
        description="Largest remote work community with quality-vetted listings.",
        priority=8,
        default_enabled=True,
        adapter_type="feed",
        requires_auth=False,
        rate_limit_per_hour=60,
        notes="Long-running remote job board with good reputation"
    ),
    PlatformType.REMOTIVE: PlatformInfo(
        type=PlatformType.REMOTIVE,
        name="Remotive",
        description="Hand-picked remote jobs in tech, marketing, and customer support.",
        priority=9,
        default_enabled=True,
        adapter_type="feed",
        requires_auth=False,
        rate_limit_per_hour=40,
        notes="Curated remote jobs, good quality"
    ),
    PlatformType.WORKING_NOMADS: PlatformInfo(
        type=PlatformType.WORKING_NOMADS,
        name="Working Nomads",
        description="Remote jobs curated for digital nomads and location-independent workers.",
        priority=10,
        default_enabled=False,
        adapter_type="feed",
        requires_auth=False,
        rate_limit_per_hour=30,
        notes="Good for fully remote, location-flexible roles"
    ),
    PlatformType.FLEXJOBS: PlatformInfo(
        type=PlatformType.FLEXJOBS,
        name="FlexJobs",
        description="Vetted remote and flexible jobs, subscription-based with manual feed mode.",
        priority=11,
        default_enabled=False,
        adapter_type="manual",
        requires_auth=True,
        rate_limit_per_hour=20,
        notes="Paid service, manual import or feed mode supported"
    ),
    
    # --- Tier 3: Large aggregators (higher volume, more noise) ---
    PlatformType.LINKEDIN_JOBS: PlatformInfo(
        type=PlatformType.LINKEDIN_JOBS,
        name="LinkedIn Jobs",
        description="Massive job marketplace with company insights and easy apply options.",
        priority=12,
        default_enabled=False,
        adapter_type="scraper",
        requires_auth=True,
        rate_limit_per_hour=20,
        notes="High volume but compliance-sensitive; use carefully"
    ),
    PlatformType.GLASSDOOR: PlatformInfo(
        type=PlatformType.GLASSDOOR,
        name="Glassdoor",
        description="Job listings paired with company reviews and salary reports.",
        priority=13,
        default_enabled=False,
        adapter_type="scraper",
        requires_auth=True,
        rate_limit_per_hour=20,
        notes="Requires account for full access"
    ),
    PlatformType.INDEED: PlatformInfo(
        type=PlatformType.INDEED,
        name="Indeed",
        description="World's largest job aggregator with broad coverage across industries.",
        priority=14,
        default_enabled=False,
        adapter_type="scraper",
        requires_auth=False,
        rate_limit_per_hour=30,
        notes="Very high volume, needs strong filtering"
    ),
    PlatformType.ZIPRECRUITER: PlatformInfo(
        type=PlatformType.ZIPRECRUITER,
        name="ZipRecruiter",
        description="AI-powered job matching with one-click apply across multiple boards.",
        priority=15,
        default_enabled=False,
        adapter_type="api",
        requires_auth=True,
        rate_limit_per_hour=30,
        notes="Good matching but high noise ratio"
    ),
    PlatformType.GOOGLE_JOBS: PlatformInfo(
        type=PlatformType.GOOGLE_JOBS,
        name="Google Jobs",
        description="Aggregated job search across multiple sources via Google's index.",
        priority=16,
        default_enabled=False,
        adapter_type="aggregator",
        requires_auth=False,
        rate_limit_per_hour=60,
        notes="Aggregator input mode - good for coverage, may duplicate"
    ),
}


def get_platform_info(platform_type: PlatformType) -> PlatformInfo:
    """Get platform info by type."""
    return PLATFORMS[platform_type]


def get_platforms_by_priority() -> List[PlatformInfo]:
    """Get all platforms sorted by priority (best first)."""
    return sorted(PLATFORMS.values(), key=lambda p: p.priority)


def get_default_enabled_platforms() -> List[PlatformInfo]:
    """Get platforms enabled by default."""
    return [p for p in PLATFORMS.values() if p.default_enabled]


def get_platform_priority_list() -> List[str]:
    """Get platform type names in priority order (for polling)."""
    return [p.type.value for p in get_platforms_by_priority()]


def get_platform_descriptions() -> Dict[str, str]:
    """Get platform descriptions keyed by type."""
    return {p.type.value: p.description for p in PLATFORMS.values()}


# Export priority list for easy access
PLATFORM_PRIORITY_ORDER = get_platform_priority_list()
