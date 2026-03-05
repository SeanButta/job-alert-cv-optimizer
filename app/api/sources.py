"""
CRUD API for job sources management.

Endpoints:
- GET    /api/sources          - List all sources (filterable by type/status)
- POST   /api/sources          - Create new source
- GET    /api/sources/{id}     - Get source by ID
- PUT    /api/sources/{id}     - Update source
- DELETE /api/sources/{id}     - Delete source
- POST   /api/sources/{id}/activate   - Activate source
- POST   /api/sources/{id}/deactivate - Deactivate source
- POST   /api/sources/{id}/test       - Test source connectivity
"""
import json
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.sources import JobSource, SourceType, SourceStatus


router = APIRouter(prefix="/api/sources", tags=["sources"])


# --- Pydantic Models ---

class SourceCreate(BaseModel):
    """Request body for creating a source."""
    type: str = Field(..., description="Source type: telegram_channel, website, linkedin_recruiter")
    identifier: str = Field(..., min_length=1, max_length=500, description="Channel username, URL, or profile identifier")
    name: Optional[str] = Field(None, max_length=255, description="Display name (optional)")
    user_id: Optional[int] = Field(None, description="Owner user ID (optional, NULL = global)")
    config: Optional[dict] = Field(None, description="Source-specific configuration")


class SourceUpdate(BaseModel):
    """Request body for updating a source."""
    identifier: Optional[str] = Field(None, min_length=1, max_length=500)
    name: Optional[str] = Field(None, max_length=255)
    config: Optional[dict] = None
    status: Optional[str] = None


class SourceResponse(BaseModel):
    """Response model for source."""
    id: int
    type: str
    identifier: str
    name: Optional[str]
    status: str
    user_id: Optional[int]
    config: Optional[dict]
    last_checked: Optional[str]
    last_error: Optional[str]
    error_count: int
    created_at: Optional[str]
    updated_at: Optional[str]

    class Config:
        from_attributes = True


class SourceListResponse(BaseModel):
    """Response model for list of sources."""
    sources: List[SourceResponse]
    total: int


class SourceTestResult(BaseModel):
    """Response model for source test."""
    success: bool
    message: str
    details: Optional[dict] = None


# --- Helper Functions ---

def _validate_source_type(source_type: str) -> None:
    """Validate source type."""
    valid_types = [t.value for t in SourceType]
    if source_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source type. Must be one of: {valid_types}"
        )


def _get_source_or_404(db, source_id: int) -> JobSource:
    """Get source by ID or raise 404."""
    source = db.get(JobSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


def _source_to_response(source: JobSource) -> dict:
    """Convert JobSource to response dict."""
    data = source.to_dict()
    # Parse JSON config if present
    if data.get('config'):
        try:
            data['config'] = json.loads(data['config'])
        except (json.JSONDecodeError, TypeError):
            pass
    return data


# --- API Endpoints ---

@router.get("", response_model=SourceListResponse)
async def list_sources(
    type: Optional[str] = Query(None, description="Filter by source type"),
    status: Optional[str] = Query(None, description="Filter by status (active/inactive/error)"),
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
):
    """List all sources with optional filtering."""
    db = SessionLocal()
    try:
        query = select(JobSource)
        
        if type:
            _validate_source_type(type)
            query = query.where(JobSource.type == type)
        
        if status:
            query = query.where(JobSource.status == status)
        
        if user_id is not None:
            query = query.where(JobSource.user_id == user_id)
        
        query = query.order_by(JobSource.created_at.desc())
        sources = list(db.scalars(query).all())
        
        return SourceListResponse(
            sources=[_source_to_response(s) for s in sources],
            total=len(sources)
        )
    finally:
        db.close()


@router.post("", response_model=SourceResponse)
async def create_source(body: SourceCreate):
    """Create a new job source."""
    _validate_source_type(body.type)
    
    db = SessionLocal()
    try:
        # Check for duplicate identifier within same type
        existing = db.scalar(
            select(JobSource).where(
                JobSource.type == body.type,
                JobSource.identifier == body.identifier
            )
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Source with identifier '{body.identifier}' already exists for type '{body.type}'"
            )
        
        source = JobSource(
            type=body.type,
            identifier=body.identifier,
            name=body.name or body.identifier,
            user_id=body.user_id,
            config=json.dumps(body.config) if body.config else None,
            status=SourceStatus.ACTIVE.value,
        )
        db.add(source)
        db.commit()
        db.refresh(source)
        
        return _source_to_response(source)
    finally:
        db.close()


@router.get("/{source_id}", response_model=SourceResponse)
async def get_source(source_id: int):
    """Get a source by ID."""
    db = SessionLocal()
    try:
        source = _get_source_or_404(db, source_id)
        return _source_to_response(source)
    finally:
        db.close()


@router.put("/{source_id}", response_model=SourceResponse)
async def update_source(source_id: int, body: SourceUpdate):
    """Update a source."""
    db = SessionLocal()
    try:
        source = _get_source_or_404(db, source_id)
        
        if body.identifier is not None:
            # Check for duplicate
            existing = db.scalar(
                select(JobSource).where(
                    JobSource.type == source.type,
                    JobSource.identifier == body.identifier,
                    JobSource.id != source_id
                )
            )
            if existing:
                raise HTTPException(
                    status_code=409,
                    detail=f"Source with identifier '{body.identifier}' already exists"
                )
            source.identifier = body.identifier
        
        if body.name is not None:
            source.name = body.name
        
        if body.config is not None:
            source.config = json.dumps(body.config)
        
        if body.status is not None:
            if body.status not in [s.value for s in SourceStatus]:
                raise HTTPException(status_code=400, detail="Invalid status")
            source.status = body.status
        
        source.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(source)
        
        return _source_to_response(source)
    finally:
        db.close()


@router.delete("/{source_id}")
async def delete_source(source_id: int):
    """Delete a source."""
    db = SessionLocal()
    try:
        source = _get_source_or_404(db, source_id)
        db.delete(source)
        db.commit()
        return {"deleted": True, "id": source_id}
    finally:
        db.close()


@router.post("/{source_id}/activate", response_model=SourceResponse)
async def activate_source(source_id: int):
    """Activate a source."""
    db = SessionLocal()
    try:
        source = _get_source_or_404(db, source_id)
        source.status = SourceStatus.ACTIVE.value
        source.error_count = 0  # Reset error count on manual activation
        source.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(source)
        return _source_to_response(source)
    finally:
        db.close()


@router.post("/{source_id}/deactivate", response_model=SourceResponse)
async def deactivate_source(source_id: int):
    """Deactivate a source."""
    db = SessionLocal()
    try:
        source = _get_source_or_404(db, source_id)
        source.status = SourceStatus.INACTIVE.value
        source.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(source)
        return _source_to_response(source)
    finally:
        db.close()


@router.post("/{source_id}/test", response_model=SourceTestResult)
async def test_source(source_id: int):
    """Test source connectivity/validity."""
    from app.adapters.source_adapters import test_source_connection
    
    db = SessionLocal()
    try:
        source = _get_source_or_404(db, source_id)
        result = test_source_connection(source)
        return result
    finally:
        db.close()
