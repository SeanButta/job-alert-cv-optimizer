"""
API for platform toggles and scoring.

Endpoints:
- GET    /api/platforms              - List all platforms with settings
- GET    /api/platforms/{platform}   - Get single platform info
- POST   /api/platforms/{platform}/enable   - Enable platform
- POST   /api/platforms/{platform}/disable  - Disable platform
- GET    /api/platforms/priority     - Get priority-ranked platform list
- POST   /api/score                  - Score a job against CV
- GET    /api/score/breakdown/{match_id} - Get score breakdown for a match
"""
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.platforms import (
    PLATFORMS, PlatformType, PlatformInfo,
    get_platforms_by_priority, get_platform_priority_list
)
from app.models.platform_settings import PlatformSetting
from app.services.scoring import compute_match_score, ScoreBreakdown


router = APIRouter(prefix="/api", tags=["platforms"])


# --- Pydantic Models ---

class PlatformResponse(BaseModel):
    """Platform info with current settings."""
    type: str
    name: str
    description: str
    priority: int
    enabled: bool
    default_enabled: bool
    adapter_type: str
    requires_auth: bool
    rate_limit_per_hour: int
    last_checked: Optional[str] = None
    last_error: Optional[str] = None
    error_count: int = 0


class PlatformListResponse(BaseModel):
    """List of platforms."""
    platforms: List[PlatformResponse]
    total: int


class PlatformPriorityResponse(BaseModel):
    """Priority-ordered platform list."""
    priority_order: List[str]
    descriptions: dict


class ScoreRequest(BaseModel):
    """Request body for scoring."""
    job_title: str = Field(..., min_length=1)
    job_description: str = Field(..., min_length=1)
    job_company: str = ""
    cv_text: str = Field(..., min_length=1)
    required_keywords: List[str] = Field(default_factory=list)
    excluded_keywords: List[str] = Field(default_factory=list)
    user_prefers_remote: bool = True


class ScoreResponse(BaseModel):
    """Score response with breakdown."""
    total_score: float
    components: dict
    exclusion_penalty: float
    excluded_found: List[str]
    llm_adjustment: float
    llm_explanation: str
    explanation: str


# --- Helper Functions ---

def _get_platform_setting(db, platform: str, user_id: Optional[int] = None) -> Optional[PlatformSetting]:
    """Get platform setting from DB."""
    query = select(PlatformSetting).where(PlatformSetting.platform == platform)
    if user_id is not None:
        query = query.where(PlatformSetting.user_id == user_id)
    else:
        query = query.where(PlatformSetting.user_id == None)
    return db.scalar(query)


def _get_or_create_setting(db, platform: str, user_id: Optional[int] = None) -> PlatformSetting:
    """Get or create platform setting."""
    setting = _get_platform_setting(db, platform, user_id)
    if not setting:
        # Get default from platform info
        platform_info = PLATFORMS.get(PlatformType(platform))
        default_enabled = platform_info.default_enabled if platform_info else True
        
        setting = PlatformSetting(
            platform=platform,
            enabled=default_enabled,
            user_id=user_id,
        )
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting


def _platform_to_response(info: PlatformInfo, setting: Optional[PlatformSetting]) -> PlatformResponse:
    """Convert platform info + settings to response."""
    enabled = setting.enabled if setting else info.default_enabled
    return PlatformResponse(
        type=info.type.value,
        name=info.name,
        description=info.description,
        priority=info.priority,
        enabled=enabled,
        default_enabled=info.default_enabled,
        adapter_type=info.adapter_type,
        requires_auth=info.requires_auth,
        rate_limit_per_hour=info.rate_limit_per_hour,
        last_checked=setting.last_checked.isoformat() if setting and setting.last_checked else None,
        last_error=setting.last_error if setting else None,
        error_count=setting.error_count if setting else 0,
    )


# --- API Endpoints ---

@router.get("/platforms", response_model=PlatformListResponse)
async def list_platforms(
    user_id: Optional[int] = Query(None, description="Filter by user ID for user-specific settings"),
):
    """List all platforms with current enable/disable settings."""
    db = SessionLocal()
    try:
        platforms = []
        for info in get_platforms_by_priority():
            setting = _get_platform_setting(db, info.type.value, user_id)
            platforms.append(_platform_to_response(info, setting))
        
        return PlatformListResponse(
            platforms=platforms,
            total=len(platforms)
        )
    finally:
        db.close()


@router.get("/platforms/priority", response_model=PlatformPriorityResponse)
async def get_platform_priority():
    """Get priority-ordered platform list for polling."""
    priority_order = get_platform_priority_list()
    descriptions = {
        info.type.value: info.description
        for info in PLATFORMS.values()
    }
    
    return PlatformPriorityResponse(
        priority_order=priority_order,
        descriptions=descriptions
    )


@router.get("/platforms/{platform}", response_model=PlatformResponse)
async def get_platform(
    platform: str,
    user_id: Optional[int] = Query(None),
):
    """Get single platform info with settings."""
    try:
        platform_type = PlatformType(platform)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown platform: {platform}")
    
    info = PLATFORMS[platform_type]
    
    db = SessionLocal()
    try:
        setting = _get_platform_setting(db, platform, user_id)
        return _platform_to_response(info, setting)
    finally:
        db.close()


@router.post("/platforms/{platform}/enable", response_model=PlatformResponse)
async def enable_platform(
    platform: str,
    user_id: Optional[int] = Query(None),
):
    """Enable a platform for polling."""
    try:
        platform_type = PlatformType(platform)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown platform: {platform}")
    
    info = PLATFORMS[platform_type]
    
    db = SessionLocal()
    try:
        setting = _get_or_create_setting(db, platform, user_id)
        setting.enabled = True
        setting.error_count = 0  # Reset errors on manual enable
        setting.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(setting)
        
        return _platform_to_response(info, setting)
    finally:
        db.close()


@router.post("/platforms/{platform}/disable", response_model=PlatformResponse)
async def disable_platform(
    platform: str,
    user_id: Optional[int] = Query(None),
):
    """Disable a platform from polling."""
    try:
        platform_type = PlatformType(platform)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown platform: {platform}")
    
    info = PLATFORMS[platform_type]
    
    db = SessionLocal()
    try:
        setting = _get_or_create_setting(db, platform, user_id)
        setting.enabled = False
        setting.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(setting)
        
        return _platform_to_response(info, setting)
    finally:
        db.close()


@router.post("/score", response_model=ScoreResponse)
async def score_job_match(body: ScoreRequest):
    """
    Score a job listing against user CV.
    
    Returns detailed score breakdown with weighted components.
    """
    breakdown = compute_match_score(
        job_title=body.job_title,
        job_description=body.job_description,
        job_company=body.job_company,
        cv_text=body.cv_text,
        required_keywords=body.required_keywords,
        excluded_keywords=body.excluded_keywords,
        user_prefers_remote=body.user_prefers_remote,
    )
    
    breakdown_dict = breakdown.to_dict()
    
    return ScoreResponse(
        total_score=breakdown_dict['total_score'],
        components=breakdown_dict['components'],
        exclusion_penalty=breakdown_dict['exclusion_penalty'],
        excluded_found=breakdown_dict['excluded_found'],
        llm_adjustment=breakdown_dict['llm_adjustment'],
        llm_explanation=breakdown_dict['llm_explanation'],
        explanation=breakdown.to_explanation_string(),
    )


@router.get("/score/weights")
async def get_score_weights():
    """Get current scoring weights configuration."""
    from app.services.scoring import DEFAULT_WEIGHTS
    
    return {
        'weights': DEFAULT_WEIGHTS,
        'formula': (
            "base_score = (skills_weight * skills + title_weight * title + "
            "seniority_weight * seniority + location_weight * location) * "
            "(1 - exclusion_penalty) * llm_adjustment"
        ),
        'components': {
            'skills': 'Overlap between job requirements and CV skills',
            'title': 'Job title alignment with CV experience',
            'seniority': 'Seniority level fit (intern to C-level)',
            'location': 'Location/remote compatibility',
            'exclusion_penalty': 'Penalty for excluded keywords (0 or 1)',
            'llm_adjustment': 'Optional LLM rerank factor (0.5-1.5)',
        }
    }
