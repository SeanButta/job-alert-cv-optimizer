from app.services.matching import score_job

def test_matching_score_positive():
    s,e=score_job('python fastapi sql role','python dev','python,fastapi,sql','solidity')
    assert s >= 0.66
    assert 'required keywords' in e

def test_matching_excluded():
    s,e=score_job('solidity engineer','python dev','python','solidity')
    assert s == 0
