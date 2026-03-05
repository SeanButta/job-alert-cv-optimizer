from app.services.matching import score_job

def test_matching_score_positive():
    """Test that matching jobs with required keywords get a positive score."""
    s, e = score_job('python fastapi sql role', 'python dev', 'python,fastapi,sql', 'solidity')
    # New scoring model uses weighted components, score will be reasonable but not as high
    assert s >= 0.4
    assert 'Score:' in e or 'Skills' in e

def test_matching_excluded():
    """Test that excluded keywords result in 0 score."""
    s, e = score_job('solidity engineer', 'python dev', 'python', 'solidity')
    assert s == 0
