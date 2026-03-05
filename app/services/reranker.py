"""
Optional LLM reranker for candidate matches.

Disabled by default - enable with ENABLE_LLM_RERANKER=true and provide API key.
Falls back to deterministic scoring when disabled or on any error.
"""
import os
import json
import logging
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)


def _is_enabled() -> bool:
    """Check if LLM reranker is enabled via env flag."""
    return os.getenv('ENABLE_LLM_RERANKER', 'false').lower() == 'true'


def _get_openai_key() -> Optional[str]:
    """Get OpenAI API key if available."""
    return os.getenv('OPENAI_API_KEY')


def _get_anthropic_key() -> Optional[str]:
    """Get Anthropic API key if available."""
    return os.getenv('ANTHROPIC_API_KEY')


def _call_openai(prompt: str) -> Optional[str]:
    """Call OpenAI API for reranking."""
    import requests

    api_key = _get_openai_key()
    if not api_key:
        return None

    try:
        response = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json={
                'model': os.getenv('LLM_RERANKER_MODEL', 'gpt-4o-mini'),
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': 0.0,
                'max_tokens': 500,
            },
            timeout=30,
        )
        if response.ok:
            return response.json()['choices'][0]['message']['content']
    except Exception as e:
        logger.warning(f"OpenAI reranker call failed: {e}")

    return None


def _call_anthropic(prompt: str) -> Optional[str]:
    """Call Anthropic API for reranking."""
    import requests

    api_key = _get_anthropic_key()
    if not api_key:
        return None

    try:
        response = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'Content-Type': 'application/json',
            },
            json={
                'model': os.getenv('LLM_RERANKER_MODEL_ANTHROPIC', 'claude-3-haiku-20240307'),
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 500,
            },
            timeout=30,
        )
        if response.ok:
            return response.json()['content'][0]['text']
    except Exception as e:
        logger.warning(f"Anthropic reranker call failed: {e}")

    return None


def _build_rerank_prompt(
    job_title: str,
    job_description: str,
    resume: str,
    base_score: float,
) -> str:
    """Build prompt for LLM reranking."""
    return f"""You are a job-candidate match evaluator. Given a job posting and candidate resume, 
provide a refined match score between 0.0 and 1.0, and a brief explanation.

Job Title: {job_title}

Job Description:
{job_description[:1000]}

Candidate Resume:
{resume[:1000]}

Base algorithmic score: {base_score:.2f}

Evaluate the match considering:
1. Skill alignment (technical and soft skills)
2. Experience level fit
3. Industry/domain relevance
4. Career trajectory alignment

Respond in JSON format only:
{{"score": <float 0.0-1.0>, "explanation": "<brief explanation>"}}"""


def rerank_match(
    job_title: str,
    job_description: str,
    resume: str,
    base_score: float,
    base_explanation: str,
) -> Tuple[float, str, bool]:
    """
    Optionally rerank a match using LLM.

    Returns: (score, explanation, was_reranked)

    Falls back to base score/explanation if:
    - LLM reranker is disabled
    - No API key available
    - LLM call fails
    """
    if not _is_enabled():
        return base_score, base_explanation, False

    # Try OpenAI first, then Anthropic
    prompt = _build_rerank_prompt(job_title, job_description, resume, base_score)

    response = _call_openai(prompt)
    if response is None:
        response = _call_anthropic(prompt)

    if response is None:
        logger.info("LLM reranker unavailable, using base score")
        return base_score, base_explanation, False

    # Parse response
    try:
        # Extract JSON from response (handle markdown code blocks)
        if '```' in response:
            import re
            match = re.search(r'```(?:json)?\s*(.*?)\s*```', response, re.DOTALL)
            if match:
                response = match.group(1)

        data = json.loads(response.strip())
        score = float(data.get('score', base_score))
        explanation = data.get('explanation', base_explanation)

        # Clamp score to valid range
        score = max(0.0, min(1.0, score))

        logger.info(f"LLM reranked: {base_score:.2f} -> {score:.2f}")
        return score, f"[LLM] {explanation}", True

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning(f"Failed to parse LLM response: {e}")
        return base_score, base_explanation, False


def rerank_matches_batch(
    matches: List[dict],
    resume: str,
) -> List[dict]:
    """
    Rerank a batch of matches.

    Each match dict should have: job_title, job_description, base_score, base_explanation
    Returns matches with updated score, explanation, and llm_reranked flag.
    """
    if not _is_enabled():
        for m in matches:
            m['llm_reranked'] = False
        return matches

    reranked = []
    for m in matches:
        score, explanation, was_reranked = rerank_match(
            m['job_title'],
            m['job_description'],
            resume,
            m['base_score'],
            m['base_explanation'],
        )
        reranked.append({
            **m,
            'score': score,
            'explanation': explanation,
            'llm_reranked': was_reranked,
        })

    return reranked
