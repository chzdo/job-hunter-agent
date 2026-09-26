import re
from typing import Dict, Any, Tuple

def evaluate_job_match(job: Dict[str, Any], config: Dict[str, Any]) -> Tuple[bool, float, str]:
    """
    Score job against candidate profile and target roles.
    Returns: (is_match, score_percentage, reason)
    """
    title = job.get("title", "").lower()
    description = job.get("description", "").lower()
    target_roles = [r.lower() for r in config.get("search", {}).get("roles", [])]

    # Quick role title check
    matched_role = None
    for role in target_roles:
        if role in title or all(w in title for w in role.split()):
            matched_role = role
            break

    if not matched_role:
        # Check description as fallback
        for role in target_roles:
            if role in description:
                matched_role = role
                break

    if not matched_role:
        return False, 0.0, "Title does not match target roles"

    # Score based on presence of key terms
    score = 70.0  # Base match for matching title
    positive_signals = ["remote", "flexible", "full-time", "benefits", "growth"]
    for signal in positive_signals:
        if signal in description:
            score += 4.0

    score = min(score, 100.0)
    return True, score, f"Matched role: {matched_role}"

def resolve_screening_question(question_text: str, config: Dict[str, Any], job_role: str = "") -> str:
    """
    Match typical ATS screening questions to standard answers configured in config.yaml.
    """
    q = question_text.lower().strip()
    answers = config.get("screening_answers", {})
    candidate = config.get("candidate", {})

    # Authorization / Sponsorship
    if any(k in q for k in ["authorized to work", "legally authorized", "work authorization", "right to work"]):
        return str(answers.get("authorized_to_work", "Yes"))

    if any(k in q for k in ["sponsorship", "visa", "require sponsorship"]):
        return str(answers.get("require_sponsorship", "No"))

    # Years of experience
    if "how many years" in q or "years of experience" in q:
        exp_dict = answers.get("years_of_experience", {})
        for key, val in exp_dict.items():
            if key != "default" and key in q:
                return str(val)
        return str(exp_dict.get("default", 3))

    # Salary expectations
    if any(k in q for k in ["salary", "compensation", "pay expectation", "desired salary"]):
        return str(answers.get("salary_expectation", "Negotiable"))

    # Notice period
    if any(k in q for k in ["notice period", "start date", "how soon", "when can you start"]):
        return str(answers.get("notice_period", "Immediate / 2 weeks"))

    # Education
    if any(k in q for k in ["education", "degree", "highest level of education"]):
        return str(answers.get("education_level", "Bachelor's Degree"))

    # Contact / Links
    if "linkedin" in q:
        return str(candidate.get("linkedin_url", ""))
    if "github" in q or "portfolio" in q or "website" in q:
        return str(candidate.get("portfolio_url") or candidate.get("github_url", ""))

    return ""
