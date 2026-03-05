"""
Job-CV matching service.

This module provides backward compatibility with the legacy API.
The actual scoring logic is in scoring.py.
"""
from app.services.scoring import score_job

# Re-export for backward compatibility
__all__ = ['score_job']
