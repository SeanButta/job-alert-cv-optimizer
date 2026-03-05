def _split_csv(s: str):
    return [x.strip().lower() for x in s.split(',') if x.strip()]

def score_job(description: str, resume: str, required_keywords: str, excluded_keywords: str):
    text=(description+' '+resume).lower()
    req=_split_csv(required_keywords)
    exc=_split_csv(excluded_keywords)
    if any(k in text for k in exc):
        return 0.0, 'Excluded keyword found'
    hits=sum(1 for k in req if k in text)
    score=(hits/len(req)) if req else 0.6
    return score, f'{hits}/{len(req) if req else 0} required keywords matched'
