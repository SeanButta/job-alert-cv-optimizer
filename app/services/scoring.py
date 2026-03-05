"""
Job-CV scoring model with weighted components and explainability.

Provides deterministic base scoring with optional LLM rerank adjustment.
All scores are in [0.0, 1.0] range.

Score Components:
- skills_overlap: Overlap between job requirements and CV skills
- title_alignment: Job title match to CV experience/target titles
- seniority_fit: Seniority level alignment
- location_fit: Location/remote compatibility
- exclusion_penalty: Penalty for excluded keywords

Formula:
    base_score = (
        skills_weight * skills_overlap +
        title_weight * title_alignment +
        seniority_weight * seniority_fit +
        location_weight * location_fit
    ) * (1 - exclusion_penalty)

    final_score = base_score * llm_adjustment (if enabled)
"""
import re
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# Default weights (must sum to 1.0)
DEFAULT_WEIGHTS = {
    'skills': 0.40,
    'title': 0.25,
    'seniority': 0.20,
    'location': 0.15,
}

# Seniority keywords
SENIORITY_LEVELS = {
    'intern': 1,
    'junior': 2,
    'associate': 2,
    'entry': 2,
    'mid': 3,
    'senior': 4,
    'staff': 5,
    'principal': 6,
    'lead': 5,
    'manager': 5,
    'director': 6,
    'vp': 7,
    'head': 6,
    'chief': 8,
    'c-level': 8,
    'cto': 8,
    'ceo': 8,
    'founder': 7,
}

# Location keywords
REMOTE_KEYWORDS = {'remote', 'distributed', 'anywhere', 'work from home', 'wfh', 'fully remote'}
HYBRID_KEYWORDS = {'hybrid', 'flexible', 'partial remote'}


@dataclass
class ScoreBreakdown:
    """Detailed breakdown of match score components."""
    total_score: float
    skills_score: float
    skills_matched: List[str]
    skills_missing: List[str]
    title_score: float
    title_match_reason: str
    seniority_score: float
    seniority_job: str
    seniority_cv: str
    seniority_match_reason: str
    location_score: float
    location_match_reason: str
    exclusion_penalty: float
    excluded_found: List[str]
    llm_adjustment: float = 1.0
    llm_explanation: str = ""
    weights: Dict[str, float] = field(default_factory=lambda: DEFAULT_WEIGHTS.copy())

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            'total_score': round(self.total_score, 4),
            'components': {
                'skills': {
                    'score': round(self.skills_score, 4),
                    'weight': self.weights['skills'],
                    'matched': self.skills_matched,
                    'missing': self.skills_missing,
                },
                'title': {
                    'score': round(self.title_score, 4),
                    'weight': self.weights['title'],
                    'reason': self.title_match_reason,
                },
                'seniority': {
                    'score': round(self.seniority_score, 4),
                    'weight': self.weights['seniority'],
                    'job_level': self.seniority_job,
                    'cv_level': self.seniority_cv,
                    'reason': self.seniority_match_reason,
                },
                'location': {
                    'score': round(self.location_score, 4),
                    'weight': self.weights['location'],
                    'reason': self.location_match_reason,
                },
            },
            'exclusion_penalty': round(self.exclusion_penalty, 4),
            'excluded_found': self.excluded_found,
            'llm_adjustment': round(self.llm_adjustment, 4),
            'llm_explanation': self.llm_explanation,
        }

    def to_explanation_string(self) -> str:
        """Generate human-readable explanation."""
        parts = [f"Score: {self.total_score:.0%}"]

        # Skills
        if self.skills_matched:
            parts.append(f"Skills: {len(self.skills_matched)}/{len(self.skills_matched)+len(self.skills_missing)} matched ({', '.join(self.skills_matched[:3])})")

        # Title
        parts.append(f"Title: {self.title_match_reason}")

        # Seniority
        if self.seniority_match_reason:
            parts.append(f"Seniority: {self.seniority_match_reason}")

        # Location
        parts.append(f"Location: {self.location_match_reason}")

        # Exclusions
        if self.excluded_found:
            parts.append(f"⚠️ Exclusions found: {', '.join(self.excluded_found)}")

        # LLM
        if self.llm_explanation:
            parts.append(f"LLM: {self.llm_explanation}")

        return " | ".join(parts)


def _normalize_text(text: str) -> str:
    """Normalize text for matching."""
    return re.sub(r'[^\w\s]', ' ', text.lower()).strip()


def _extract_skills(text: str) -> set:
    """Extract skill keywords from text."""
    normalized = _normalize_text(text)
    # Common tech skills patterns
    skill_patterns = [
        r'\b(python|javascript|typescript|java|c\+\+|rust|go|ruby|php|swift|kotlin)\b',
        r'\b(react|angular|vue|nextjs|nodejs|django|flask|fastapi|rails|spring)\b',
        r'\b(aws|gcp|azure|docker|kubernetes|terraform|jenkins|ci/cd)\b',
        r'\b(sql|postgresql|mysql|mongodb|redis|elasticsearch|kafka)\b',
        r'\b(machine learning|ml|ai|deep learning|nlp|computer vision)\b',
        r'\b(api|rest|graphql|grpc|microservices)\b',
        r'\b(git|agile|scrum|devops|sre)\b',
    ]
    skills = set()
    for pattern in skill_patterns:
        skills.update(re.findall(pattern, normalized))
    # Also extract standalone words as potential skills
    words = set(normalized.split())
    return skills | words


def _extract_titles(text: str) -> List[str]:
    """Extract job title keywords from text."""
    normalized = _normalize_text(text)
    title_keywords = []

    # Common title patterns
    patterns = [
        r'(software engineer|developer|programmer)',
        r'(data scientist|data engineer|data analyst)',
        r'(product manager|project manager|program manager)',
        r'(designer|ux|ui)',
        r'(devops|sre|platform|infrastructure)',
        r'(frontend|backend|fullstack|full stack)',
        r'(machine learning|ml engineer|ai engineer)',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, normalized)
        title_keywords.extend(matches)

    return title_keywords


def _extract_seniority(text: str) -> Tuple[str, int]:
    """Extract seniority level from text. Returns (label, level)."""
    normalized = _normalize_text(text)

    for keyword, level in sorted(SENIORITY_LEVELS.items(), key=lambda x: -x[1]):
        if keyword in normalized:
            return keyword, level

    return "mid", 3  # Default to mid-level


def _extract_location_preference(text: str) -> Tuple[str, bool, bool]:
    """Extract location info. Returns (location_str, is_remote, is_hybrid)."""
    normalized = _normalize_text(text)

    is_remote = any(kw in normalized for kw in REMOTE_KEYWORDS)
    is_hybrid = any(kw in normalized for kw in HYBRID_KEYWORDS)

    # Try to extract city/country
    location = ""
    location_patterns = [
        r'(san francisco|sf|bay area|nyc|new york|seattle|austin|boston|los angeles|la)',
        r'(london|berlin|amsterdam|paris|toronto|vancouver)',
        r'(usa|us|uk|eu|europe|canada)',
    ]
    for pattern in location_patterns:
        match = re.search(pattern, normalized)
        if match:
            location = match.group(1)
            break

    return location, is_remote, is_hybrid


def compute_skills_score(
    job_text: str,
    cv_text: str,
    required_keywords: Optional[List[str]] = None
) -> Tuple[float, List[str], List[str]]:
    """
    Compute skills overlap score.

    Returns: (score, matched_skills, missing_skills)
    """
    job_skills = _extract_skills(job_text)
    cv_skills = _extract_skills(cv_text)

    # Add explicit required keywords
    if required_keywords:
        required = set(k.lower().strip() for k in required_keywords if k.strip())
    else:
        required = set()

    # Find matches
    matched = job_skills & cv_skills
    if required:
        matched |= (required & cv_skills)

    # Find missing required skills
    all_required = job_skills | required
    missing = all_required - cv_skills

    if not all_required:
        return 0.6, list(matched), []  # No requirements = neutral score

    score = len(matched) / len(all_required) if all_required else 0.6
    return min(1.0, score), sorted(matched)[:10], sorted(missing)[:10]


def compute_title_score(job_title: str, cv_text: str) -> Tuple[float, str]:
    """
    Compute title alignment score.

    Returns: (score, reason)
    """
    job_titles = _extract_titles(job_title)
    cv_titles = _extract_titles(cv_text)

    if not job_titles:
        return 0.5, "No clear title match criteria"

    # Check for exact matches
    matches = set(job_titles) & set(cv_titles)
    if matches:
        return 1.0, f"Title match: {', '.join(matches)}"

    # Check for partial matches (same domain)
    job_normalized = _normalize_text(job_title)
    cv_normalized = _normalize_text(cv_text)

    # Domain keywords
    domains = [
        ('engineer', ['developer', 'programmer', 'engineer']),
        ('data', ['data', 'analytics', 'ml', 'ai']),
        ('product', ['product', 'pm']),
        ('design', ['design', 'ux', 'ui']),
    ]

    for domain, keywords in domains:
        job_has = any(kw in job_normalized for kw in keywords)
        cv_has = any(kw in cv_normalized for kw in keywords)
        if job_has and cv_has:
            return 0.7, f"Related domain: {domain}"

    return 0.3, "Title mismatch"


def compute_seniority_score(job_text: str, cv_text: str) -> Tuple[float, str, str, str]:
    """
    Compute seniority fit score.

    Returns: (score, job_level, cv_level, reason)
    """
    job_level_label, job_level = _extract_seniority(job_text)
    cv_level_label, cv_level = _extract_seniority(cv_text)

    diff = abs(job_level - cv_level)

    if diff == 0:
        return 1.0, job_level_label, cv_level_label, "Exact seniority match"
    elif diff == 1:
        return 0.8, job_level_label, cv_level_label, "Close seniority match"
    elif diff == 2:
        return 0.5, job_level_label, cv_level_label, "Moderate seniority gap"
    else:
        return 0.2, job_level_label, cv_level_label, f"Large seniority gap ({job_level_label} vs {cv_level_label})"


def compute_location_score(
    job_text: str,
    cv_text: str,
    user_prefers_remote: bool = True,
    remote_only: bool = False,
    preferred_locations: Optional[List[str]] = None,
) -> Tuple[float, str]:
    """
    Compute location/remote fit score.

    Returns: (score, reason)
    """
    job_location, job_remote, job_hybrid = _extract_location_preference(job_text)
    cv_location, cv_remote, cv_hybrid = _extract_location_preference(cv_text)

    preferred_locations = [p.strip().lower() for p in (preferred_locations or []) if p and p.strip()]

    # Hard preference transformed into scoring floor
    if remote_only and not job_remote:
        return 0.0, "Remote-only preference not satisfied"

    # Preferred location signal
    if preferred_locations:
        if job_location:
            jl = job_location.lower()
            if any(p in jl for p in preferred_locations):
                # strong positive location alignment
                return 1.0, f"Preferred location match: {job_location}"
            # non-match: keep partial score so other components can still win if excellent
            if job_remote:
                return 0.6, f"Remote role outside preferred locations ({job_location})"
            return 0.2, f"Outside preferred locations: {job_location}"
        # unknown location but remote can still be viable
        if job_remote:
            return 0.7, "Remote role; location unspecified"

    # Perfect match: both want remote
    if job_remote and (cv_remote or user_prefers_remote):
        return 1.0, "Remote role matches preference"

    # Hybrid flexibility
    if job_hybrid and (cv_remote or cv_hybrid or user_prefers_remote):
        return 0.8, "Hybrid role, flexible"

    # Location match
    if job_location and cv_location:
        if job_location.lower() == cv_location.lower():
            return 1.0, f"Location match: {job_location}"
        else:
            return 0.4, f"Location mismatch: {job_location} vs {cv_location}"

    # No location specified
    if not job_location and not job_remote:
        return 0.5, "Location unclear in job posting"

    # Job requires location, CV prefers remote
    if job_location and (cv_remote or user_prefers_remote):
        return 0.3, f"Requires {job_location}, prefers remote"

    return 0.5, "Neutral location fit"


def compute_exclusion_penalty(
    job_text: str,
    excluded_keywords: Optional[List[str]] = None
) -> Tuple[float, List[str]]:
    """
    Compute exclusion penalty for unwanted keywords.

    Returns: (penalty, found_excluded)
    Penalty is in [0, 1] where 1 = fully excluded
    """
    if not excluded_keywords:
        return 0.0, []

    normalized = _normalize_text(job_text)
    found = []

    for keyword in excluded_keywords:
        kw = keyword.lower().strip()
        if kw and kw in normalized:
            found.append(kw)

    if found:
        # Full exclusion if any excluded keyword found
        return 1.0, found

    return 0.0, []


def compute_match_score(
    job_title: str,
    job_description: str,
    job_company: str,
    cv_text: str,
    required_keywords: Optional[List[str]] = None,
    excluded_keywords: Optional[List[str]] = None,
    user_prefers_remote: bool = True,
    remote_only: bool = False,
    preferred_locations: Optional[List[str]] = None,
    weights: Optional[Dict[str, float]] = None,
    llm_adjustment: float = 1.0,
    llm_explanation: str = ""
) -> ScoreBreakdown:
    """
    Compute comprehensive match score with breakdown.

    Args:
        job_title: Job posting title
        job_description: Full job description
        job_company: Company name
        cv_text: User's CV/resume text
        required_keywords: User's required skill keywords
        excluded_keywords: User's excluded keywords
        user_prefers_remote: Whether user generally prefers remote work
        remote_only: Strict remote-only preference from user settings
        preferred_locations: Preferred locations from user settings
        weights: Custom weights for score components
        llm_adjustment: LLM rerank adjustment factor (0.5-1.5)
        llm_explanation: LLM explanation for adjustment

    Returns:
        ScoreBreakdown with detailed score information
    """
    weights = weights or DEFAULT_WEIGHTS.copy()
    job_text = f"{job_title} {job_description} {job_company}"

    # Compute components
    skills_score, matched, missing = compute_skills_score(
        job_text, cv_text, required_keywords
    )
    title_score, title_reason = compute_title_score(job_title, cv_text)
    seniority_score, job_sen, cv_sen, sen_reason = compute_seniority_score(
        job_text, cv_text
    )
    location_score, location_reason = compute_location_score(
        job_text,
        cv_text,
        user_prefers_remote=user_prefers_remote,
        remote_only=remote_only,
        preferred_locations=preferred_locations,
    )
    exclusion_penalty, excluded_found = compute_exclusion_penalty(
        job_text, excluded_keywords
    )

    # Compute weighted base score
    base_score = (
        weights['skills'] * skills_score +
        weights['title'] * title_score +
        weights['seniority'] * seniority_score +
        weights['location'] * location_score
    )

    # Apply exclusion penalty (full penalty = 0 score)
    if exclusion_penalty >= 1.0:
        total_score = 0.0
    else:
        total_score = base_score * (1 - exclusion_penalty)

    # Apply LLM adjustment
    total_score = min(1.0, max(0.0, total_score * llm_adjustment))

    return ScoreBreakdown(
        total_score=total_score,
        skills_score=skills_score,
        skills_matched=matched,
        skills_missing=missing,
        title_score=title_score,
        title_match_reason=title_reason,
        seniority_score=seniority_score,
        seniority_job=job_sen,
        seniority_cv=cv_sen,
        seniority_match_reason=sen_reason,
        location_score=location_score,
        location_match_reason=location_reason,
        exclusion_penalty=exclusion_penalty,
        excluded_found=excluded_found,
        llm_adjustment=llm_adjustment,
        llm_explanation=llm_explanation,
        weights=weights,
    )


def score_job(
    description: str,
    resume: str,
    required_keywords: str,
    excluded_keywords: str
) -> Tuple[float, str]:
    """
    Legacy-compatible scoring function.

    Maintains backward compatibility with existing matching.py interface.

    Args:
        description: Job description text
        resume: User's resume text
        required_keywords: Comma-separated required keywords
        excluded_keywords: Comma-separated excluded keywords

    Returns:
        (score, explanation) tuple
    """
    required = [k.strip() for k in required_keywords.split(',') if k.strip()]
    excluded = [k.strip() for k in excluded_keywords.split(',') if k.strip()]

    breakdown = compute_match_score(
        job_title="",
        job_description=description,
        job_company="",
        cv_text=resume,
        required_keywords=required,
        excluded_keywords=excluded,
    )

    return breakdown.total_score, breakdown.to_explanation_string()


# Enable LLM reranking via environment variable
ENABLE_LLM_RERANK = os.getenv('ENABLE_LLM_RERANKER', 'false').lower() == 'true'


async def apply_llm_rerank(
    breakdown: ScoreBreakdown,
    job_text: str,
    cv_text: str
) -> ScoreBreakdown:
    """
    Apply optional LLM reranking adjustment.

    Only runs if ENABLE_LLM_RERANKER=true.
    Adjusts score by 0.5-1.5x based on LLM assessment.
    """
    if not ENABLE_LLM_RERANK:
        return breakdown

    try:
        from app.services.reranker import rerank_with_llm

        adjustment, explanation = await rerank_with_llm(
            job_text=job_text,
            cv_text=cv_text,
            base_score=breakdown.total_score,
        )

        # Apply adjustment
        breakdown.llm_adjustment = adjustment
        breakdown.llm_explanation = explanation
        breakdown.total_score = min(1.0, max(0.0, breakdown.total_score * adjustment))

    except Exception as e:
        breakdown.llm_explanation = f"LLM rerank failed: {str(e)}"

    return breakdown
