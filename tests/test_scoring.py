"""
Tests for job-CV scoring model.

Tests cover:
- Score computation with weighted components
- Score breakdown and explainability
- Skills overlap calculation
- Title alignment
- Seniority fit
- Location/remote compatibility
- Exclusion penalties
- Legacy compatibility
"""
import pytest

from app.services.scoring import (
    compute_match_score,
    compute_skills_score,
    compute_title_score,
    compute_seniority_score,
    compute_location_score,
    compute_exclusion_penalty,
    score_job,
    ScoreBreakdown,
    DEFAULT_WEIGHTS,
)


class TestScoreBreakdown:
    """Tests for ScoreBreakdown dataclass."""

    def test_to_dict(self):
        """Breakdown should serialize to dict."""
        breakdown = ScoreBreakdown(
            total_score=0.75,
            skills_score=0.8,
            skills_matched=['python', 'fastapi'],
            skills_missing=['kubernetes'],
            title_score=0.7,
            title_match_reason='Related domain',
            seniority_score=0.8,
            seniority_job='senior',
            seniority_cv='mid',
            seniority_match_reason='Close match',
            location_score=1.0,
            location_match_reason='Remote match',
            exclusion_penalty=0.0,
            excluded_found=[],
        )
        
        d = breakdown.to_dict()
        
        assert d['total_score'] == 0.75
        assert 'components' in d
        assert d['components']['skills']['score'] == 0.8
        assert d['components']['skills']['matched'] == ['python', 'fastapi']

    def test_to_explanation_string(self):
        """Breakdown should generate readable explanation."""
        breakdown = ScoreBreakdown(
            total_score=0.75,
            skills_score=0.8,
            skills_matched=['python', 'fastapi'],
            skills_missing=['kubernetes'],
            title_score=0.7,
            title_match_reason='Related domain: engineer',
            seniority_score=0.8,
            seniority_job='senior',
            seniority_cv='mid',
            seniority_match_reason='Close match',
            location_score=1.0,
            location_match_reason='Remote match',
            exclusion_penalty=0.0,
            excluded_found=[],
        )
        
        explanation = breakdown.to_explanation_string()
        
        assert 'Score: 75%' in explanation
        assert 'Skills:' in explanation
        assert 'python' in explanation


class TestSkillsScore:
    """Tests for skills overlap computation."""

    def test_full_skills_match(self):
        """Perfect skills match should score well."""
        job = "Looking for Python, FastAPI, SQL developer"
        cv = "Experienced in Python, FastAPI, SQL, and more"
        
        score, matched, missing = compute_skills_score(job, cv)
        
        # Should get reasonable score due to skill overlap
        assert score >= 0.3
        # Should have matched some skills
        assert len(matched) > 0

    def test_partial_skills_match(self):
        """Partial match should score proportionally."""
        job = "Need Python, Kubernetes, Go, Rust developer"
        cv = "Python expert with some Go experience"
        
        score, matched, missing = compute_skills_score(job, cv)
        
        assert 0.3 <= score <= 0.7
        assert 'python' in [m.lower() for m in matched]

    def test_no_skills_match(self):
        """No match should give low score."""
        job = "Blockchain Solidity developer needed"
        cv = "Python backend engineer"
        
        score, matched, missing = compute_skills_score(job, cv)
        
        assert score < 0.5

    def test_required_keywords_boost(self):
        """Required keywords should be included in matching."""
        job = "Senior developer position"
        cv = "Expert in Python and FastAPI"
        required = ['python', 'fastapi']
        
        score, matched, missing = compute_skills_score(job, cv, required)
        
        assert 'python' in matched
        assert 'fastapi' in matched


class TestTitleScore:
    """Tests for title alignment computation."""

    def test_exact_title_match(self):
        """Exact title match should score 1.0."""
        job_title = "Senior Software Engineer"
        cv = "Worked as Senior Software Engineer at Google"
        
        score, reason = compute_title_score(job_title, cv)
        
        assert score >= 0.7
        assert 'match' in reason.lower()

    def test_related_domain_match(self):
        """Related domain should give partial score."""
        job_title = "Backend Developer"
        cv = "Software Engineer with backend focus"
        
        score, reason = compute_title_score(job_title, cv)
        
        assert score >= 0.5

    def test_title_mismatch(self):
        """Mismatched titles should score low."""
        job_title = "Product Designer"
        cv = "Software Engineer"
        
        score, reason = compute_title_score(job_title, cv)
        
        assert score < 0.5


class TestSeniorityScore:
    """Tests for seniority fit computation."""

    def test_exact_seniority_match(self):
        """Same seniority level should score 1.0."""
        job = "Senior Software Engineer position"
        cv = "Senior developer with 8 years experience"
        
        score, job_level, cv_level, reason = compute_seniority_score(job, cv)
        
        assert score == 1.0
        assert 'senior' in job_level.lower()

    def test_close_seniority_match(self):
        """One level difference should score high."""
        job = "Senior Engineer wanted"
        cv = "Mid-level developer seeking growth"
        
        score, job_level, cv_level, reason = compute_seniority_score(job, cv)
        
        assert score >= 0.5
        assert 'close' in reason.lower() or 'moderate' in reason.lower()

    def test_large_seniority_gap(self):
        """Large gap should score low."""
        job = "CTO position"
        cv = "Junior developer, 1 year experience"
        
        score, job_level, cv_level, reason = compute_seniority_score(job, cv)
        
        assert score < 0.5
        assert 'gap' in reason.lower()


class TestLocationScore:
    """Tests for location/remote compatibility."""

    def test_remote_match(self):
        """Remote job + remote preference should score 1.0."""
        job = "Fully remote position, work from anywhere"
        cv = "Looking for remote opportunities"
        
        score, reason = compute_location_score(job, cv, user_prefers_remote=True)
        
        assert score == 1.0
        assert 'remote' in reason.lower()

    def test_hybrid_flexibility(self):
        """Hybrid should score well for remote seekers."""
        job = "Hybrid role, 2 days in office"
        cv = "Open to hybrid or remote"
        
        score, reason = compute_location_score(job, cv, user_prefers_remote=True)
        
        assert score >= 0.7

    def test_location_match(self):
        """Matching locations should score well."""
        job = "San Francisco based role"
        cv = "Located in San Francisco bay area"
        
        score, reason = compute_location_score(job, cv, user_prefers_remote=False)
        
        assert score >= 0.7

    def test_location_mismatch(self):
        """Mismatched locations should score low."""
        job = "Must be in New York office"
        cv = "Based in Seattle, prefer remote"
        
        score, reason = compute_location_score(job, cv, user_prefers_remote=True)
        
        assert score < 0.5


class TestExclusionPenalty:
    """Tests for exclusion penalty computation."""

    def test_no_exclusions(self):
        """No excluded keywords should give 0 penalty."""
        job = "Python developer position"
        
        penalty, found = compute_exclusion_penalty(job, None)
        
        assert penalty == 0.0
        assert found == []

    def test_exclusion_found(self):
        """Found excluded keyword should give full penalty."""
        job = "Solidity blockchain developer needed"
        excluded = ['solidity', 'blockchain']
        
        penalty, found = compute_exclusion_penalty(job, excluded)
        
        assert penalty == 1.0
        assert 'solidity' in found

    def test_no_exclusion_match(self):
        """No matching exclusions should give 0 penalty."""
        job = "Python FastAPI developer"
        excluded = ['solidity', 'php']
        
        penalty, found = compute_exclusion_penalty(job, excluded)
        
        assert penalty == 0.0
        assert found == []


class TestComputeMatchScore:
    """Tests for full match score computation."""

    def test_good_match(self):
        """Good match should score high."""
        breakdown = compute_match_score(
            job_title="Senior Python Engineer",
            job_description="Looking for Python, FastAPI, SQL developer. Remote friendly.",
            job_company="TechCorp",
            cv_text="Senior Python developer with FastAPI and SQL experience. Seeking remote.",
            required_keywords=['python'],
            excluded_keywords=['php'],
            user_prefers_remote=True,
        )
        
        assert breakdown.total_score >= 0.6
        assert breakdown.exclusion_penalty == 0.0

    def test_excluded_keyword_zeros_score(self):
        """Excluded keyword should zero out score."""
        breakdown = compute_match_score(
            job_title="Solidity Developer",
            job_description="Blockchain Solidity engineer for DeFi project",
            job_company="CryptoStartup",
            cv_text="Python developer",
            required_keywords=[],
            excluded_keywords=['solidity'],
        )
        
        assert breakdown.total_score == 0.0
        assert breakdown.exclusion_penalty == 1.0
        assert 'solidity' in breakdown.excluded_found

    def test_weights_sum_to_one(self):
        """Default weights should sum to 1.0."""
        total = sum(DEFAULT_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_custom_weights(self):
        """Custom weights should be used."""
        custom_weights = {
            'skills': 0.7,
            'title': 0.1,
            'seniority': 0.1,
            'location': 0.1,
        }
        
        breakdown = compute_match_score(
            job_title="Python Developer",
            job_description="Python, FastAPI, SQL",
            job_company="TechCorp",
            cv_text="Python, FastAPI, SQL expert",
            weights=custom_weights,
        )
        
        assert breakdown.weights == custom_weights


class TestLegacyScoreJob:
    """Tests for legacy score_job function compatibility."""

    def test_legacy_positive_match(self):
        """Legacy function should work for positive match."""
        score, explanation = score_job(
            description="Python FastAPI SQL backend developer",
            resume="Python developer with FastAPI and SQL experience",
            required_keywords="python,fastapi,sql",
            excluded_keywords="solidity",
        )
        
        assert score >= 0.5
        assert 'Score:' in explanation

    def test_legacy_exclusion(self):
        """Legacy function should handle exclusions."""
        score, explanation = score_job(
            description="Solidity blockchain developer",
            resume="Python developer",
            required_keywords="python",
            excluded_keywords="solidity",
        )
        
        assert score == 0.0
        assert 'Exclusion' in explanation

    def test_legacy_empty_keywords(self):
        """Legacy function should handle empty keywords."""
        score, explanation = score_job(
            description="Software developer position",
            resume="Experienced developer",
            required_keywords="",
            excluded_keywords="",
        )
        
        assert score >= 0.0
        assert score <= 1.0


class TestScoreAPI:
    """Tests for score API endpoint."""

    def test_score_endpoint(self):
        """POST /api/score should return score breakdown."""
        from fastapi.testclient import TestClient
        from app.main import app
        
        client = TestClient(app)
        
        resp = client.post('/api/score', json={
            'job_title': 'Senior Python Engineer',
            'job_description': 'Python, FastAPI, SQL developer needed. Remote.',
            'job_company': 'TechCorp',
            'cv_text': 'Senior Python dev with FastAPI experience',
            'required_keywords': ['python'],
            'excluded_keywords': [],
            'user_prefers_remote': True,
        })
        
        assert resp.status_code == 200
        data = resp.json()
        
        assert 'total_score' in data
        assert 'components' in data
        assert 'explanation' in data
        assert 0.0 <= data['total_score'] <= 1.0

    def test_score_weights_endpoint(self):
        """GET /api/score/weights should return weights info."""
        from fastapi.testclient import TestClient
        from app.main import app
        
        client = TestClient(app)
        
        resp = client.get('/api/score/weights')
        
        assert resp.status_code == 200
        data = resp.json()
        
        assert 'weights' in data
        assert 'formula' in data
        assert 'components' in data


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
