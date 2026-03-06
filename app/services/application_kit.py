from __future__ import annotations

from typing import List


def _clean_points(text: str, limit: int = 8) -> List[str]:
    raw = [x.strip(' -•\t') for x in text.replace('\r', '\n').split('\n') if x.strip()]
    out = []
    seen = set()
    for r in raw:
        if len(r) < 10:
            continue
        k = r.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
        if len(out) >= limit:
            break
    return out


def _job_keywords(job_title: str, job_description: str, top_n: int = 8) -> List[str]:
    text = f"{job_title} {job_description}".lower()
    seeds = [
        'python', 'fastapi', 'sql', 'api', 'product', 'analytics', 'leadership', 'stakeholder',
        'communication', 'ai', 'machine learning', 'growth', 'sales', 'operations', 'strategy',
        'kpi', 'roadmap', 'execution', 'design', 'cloud', 'aws', 'docker', 'kubernetes'
    ]
    found = [s for s in seeds if s in text]
    return found[:top_n]


def generate_tailored_resume(resume_text: str, job_title: str, company: str, job_description: str) -> str:
    highlights = _clean_points(resume_text, limit=10)
    kws = _job_keywords(job_title, job_description)
    core_skills = ', '.join(kws[:8]) if kws else 'Role-relevant technical and cross-functional execution skills'

    selected = highlights[:6] if highlights else [
        'Drove measurable impact across core responsibilities in prior roles',
        'Led cross-functional initiatives with clear business outcomes',
        'Delivered projects from planning through execution and iteration',
    ]

    bullets = '\n'.join([f"- {b}" for b in selected])

    return f"""TAILORED RESUME DRAFT
Target Role: {job_title}
Target Company: {company or 'N/A'}

PROFESSIONAL SUMMARY
Outcome-driven professional aligned to {job_title}, with hands-on experience in delivery, stakeholder collaboration, and measurable impact. Brings a track record of prioritizing high-leverage work and executing with speed and quality.

CORE SKILLS
{core_skills}

SELECTED EXPERIENCE HIGHLIGHTS (truth-preserving from saved resume)
{bullets}

ALIGNMENT NOTES
- This draft prioritizes experience relevant to the role while preserving factual history.
- Suggested emphasis areas from job description: {', '.join(kws[:5]) if kws else 'execution, collaboration, and measurable outcomes'}.
""".strip()


def generate_cover_letter(resume_text: str, job_title: str, company: str, job_description: str) -> str:
    points = _clean_points(resume_text, limit=5)
    top = points[:3]
    fallback = [
        'Delivered high-impact work with measurable outcomes',
        'Collaborated effectively across teams to ship initiatives',
        'Balanced execution speed with quality and reliability',
    ]
    while len(top) < 3:
        top.append(fallback[len(top)])

    return f"""Dear Hiring Team at {company or 'the company'},

I’m excited to apply for the {job_title} role. The position stands out because it blends execution, ownership, and business impact in a way that matches how I work best.

In my prior work, I have consistently focused on outcomes that matter. A few relevant examples include:
- {top[0]}
- {top[1]}
- {top[2]}

What excites me most about this role is the opportunity to contribute quickly, partner cross-functionally, and help the team deliver against its priorities. I’d bring a pragmatic, results-oriented approach and a strong bias toward clear communication and follow-through.

Thank you for your time and consideration. I’d welcome the chance to discuss how my background maps to your goals for this role.

Sincerely,
[Your Name]
""".strip()


def generate_interview_prep(resume_text: str, job_title: str, company: str, job_description: str) -> str:
    kws = _job_keywords(job_title, job_description, top_n=10)
    exp = _clean_points(resume_text, limit=8)

    likely_questions = [
        f"Why are you interested in {company or 'our company'} and this {job_title} role?",
        "Tell me about a high-impact project you led end-to-end.",
        "Describe a time you had to influence stakeholders without direct authority.",
        "How do you prioritize when everything feels urgent?",
        "Walk me through a setback and how you recovered.",
    ]

    ask_them = [
        "What outcomes define success in the first 90 days?",
        "Which cross-functional partnerships are most critical for this role?",
        "What are the biggest risks the team is working through right now?",
        "How does the team measure quality and business impact?",
        "If I join, what problem should I tackle first?",
    ]

    points = exp[:5] if exp else ["Bring concrete examples with metrics, ownership, and outcomes."]
    q_list = '\n'.join([f"- {q}" for q in likely_questions])
    p_list = '\n'.join([f"- {p}" for p in points])
    a_list = '\n'.join([f"- {q}" for q in ask_them])

    return f"""INTERVIEW PREP PACK
Role: {job_title}
Company: {company or 'N/A'}
Priority Themes: {', '.join(kws[:6]) if kws else 'execution, ownership, communication'}

1) LIKELY INTERVIEW QUESTIONS
{q_list}

2) YOUR TALKING POINTS (from saved resume)
{p_list}

3) STRONG QUESTIONS TO ASK INTERVIEWER
{a_list}

4) 30/60/90 DAY VALUE PLAN (DRAFT)
- 30 days: Learn systems, stakeholders, and success metrics; ship one quick-win improvement.
- 60 days: Own a scoped initiative tied to team KPIs; publish progress and risks.
- 90 days: Deliver measurable business impact and propose next-quarter roadmap priorities.

5) RISK AREAS + MITIGATION RESPONSES
- Risk: Ambiguous scope → Mitigation: Align early on goals, owners, and decision cadence.
- Risk: Cross-team dependencies → Mitigation: Create weekly sync + explicit handoffs.
- Risk: Execution drift → Mitigation: Use milestone tracking and proactive escalation.
""".strip()
