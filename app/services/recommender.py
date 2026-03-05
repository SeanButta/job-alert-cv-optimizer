def generate_cv_recommendations(job_title: str, job_desc: str, resume: str) -> str:
    bullets=[]
    jd=job_desc.lower()
    if 'python' in jd and 'python' not in resume.lower():
        bullets.append('- Add a Python project bullet with measurable impact.')
    if 'sql' in jd and 'sql' not in resume.lower():
        bullets.append('- Add SQL/analytics experience and quantified results.')
    if 'communication' in jd:
        bullets.append('- Emphasize stakeholder communication and cross-functional work.')
    if not bullets:
        bullets.append('- Tailor summary to this role and mirror key job phrasing.')
    return f"CV recommendations for {job_title}:\n" + '\n'.join(bullets)
