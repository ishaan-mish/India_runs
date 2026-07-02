#!/usr/bin/env python3
"""
Redrob FIFA-Polished Recruiter — submission-ready local ranking engine.

This is the core deliverable, not just the dashboard.
It reads candidate JSON/JSONL/GZ, scores every profile against the Redrob
Senior AI Engineer JD, writes a valid ranking CSV, and also emits a rich
JSON payload for the recruiter console.

Constraint design:
- CPU only
- no network calls
- no hosted LLM APIs
- no third-party packages
- deterministic ranking and deterministic reasoning
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

TODAY = date(2026, 7, 2)
TOKEN_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9+.#/-]*")
PROFICIENCY = {"beginner": 0.35, "intermediate": 0.62, "advanced": 0.84, "expert": 1.00}
TIER_WEIGHT = {"tier_1": 1.00, "tier_2": 0.78, "tier_3": 0.56, "tier_4": 0.35, "unknown": 0.45, "": 0.45}
CONSULTING = {"tcs", "infosys", "wipro", "accenture", "cognizant", "capgemini", "mindtree", "ltimindtree", "hcl", "tech mahindra"}
PRODUCTISH = {"product", "saas", "platform", "marketplace", "startup", "ai-native", "software", "internet", "fintech", "healthtech", "edtech"}

# The role asks for ML systems depth + shipping judgment. These groups are scored
# from profile summary, career history and skills; career evidence gets higher weight
# than naked skill keywords to resist keyword stuffing.
GROUPS: Dict[str, Dict[str, Any]] = {
    "retrieval": {
        "label": "Retrieval & Matching",
        "lane": "Retrieval Systems Lead",
        "phrases": [
            "embedding", "embeddings", "semantic search", "information retrieval", "retrieval", "rag",
            "bm25", "hybrid search", "matching system", "candidate matching", "recommendation",
            "recommender", "nearest neighbor", "ann", "search ranking", "query understanding"
        ],
        "skills": ["nlp", "information retrieval", "semantic search", "rag", "recommendation systems", "recommender systems"]
    },
    "vector": {
        "label": "Vector Search Infra",
        "lane": "Vector Infrastructure Builder",
        "phrases": [
            "vector database", "vector db", "faiss", "pinecone", "weaviate", "qdrant", "milvus",
            "opensearch", "elasticsearch", "hnsw", "ivf", "approximate nearest", "index refresh",
            "embedding drift", "retrieval regression", "search infrastructure", "inverted index"
        ],
        "skills": ["faiss", "pinecone", "weaviate", "qdrant", "milvus", "elasticsearch", "opensearch"]
    },
    "ranking": {
        "label": "Ranking & Evaluation",
        "lane": "Ranking Evaluation Lead",
        "phrases": [
            "learning to rank", "lambdamart", "lambda", "xgboost", "lightgbm", "ranker", "re-rank", "rerank",
            "ndcg", "mrr", "map", "precision@", "offline benchmark", "evaluation framework", "ab test",
            "a/b test", "recruiter feedback", "feedback loop", "ranking quality", "offline-to-online"
        ],
        "skills": ["xgboost", "lightgbm", "ranking", "statistics", "statistical modeling", "experiment design"]
    },
    "production": {
        "label": "Production ML",
        "lane": "Production ML Engineer",
        "phrases": [
            "production", "deployed", "real users", "serving", "latency", "monitoring", "on-call", "drift",
            "regression", "feature pipeline", "data quality", "schema drift", "airflow", "spark", "kafka",
            "mlflow", "bentoml", "docker", "kubernetes", "ci/cd", "api", "warehouse", "snowflake",
            "databricks", "batch processing", "streaming", "owned the on-call", "data pipeline"
        ],
        "skills": ["python", "spark", "airflow", "kafka", "mlflow", "bentoml", "docker", "kubernetes", "aws", "gcp", "sql", "databricks"]
    },
    "python": {
        "label": "Python Systems",
        "lane": "Python Systems Engineer",
        "phrases": ["python", "pytorch", "sklearn", "scikit", "fastapi", "flask", "django", "backend", "api", "microservice", "service"],
        "skills": ["python", "pytorch", "scikit-learn", "sklearn", "fastapi", "flask", "django", "sql"]
    },
    "llm": {
        "label": "LLM Systems",
        "lane": "LLM Product Engineer",
        "phrases": [
            "llm", "large language", "transformer", "fine-tuning", "finetuning", "lora", "qlora", "peft",
            "sentence-transformers", "bge", "e5", "openai embeddings", "nlp", "transformers", "prompt evaluation"
        ],
        "skills": ["llm", "fine-tuning llms", "fine-tuning", "lora", "qlora", "peft", "nlp", "transformers"]
    },
    "shipping": {
        "label": "Product Shipping",
        "lane": "Product-Minded Shipper",
        "phrases": [
            "owned", "shipped", "launched", "built", "product", "user", "users", "customer", "metrics",
            "kpi", "stakeholder", "startup", "founding", "0 to 1", "roadmap", "experimentation", "workflow",
            "pm", "scrappy", "first 90 days", "mentor"
        ],
        "skills": ["product management", "project management", "scrum", "agile", "communication"]
    },
}

WEIGHTS = {
    "retrieval": 0.155,
    "vector": 0.105,
    "ranking": 0.155,
    "production": 0.160,
    "python": 0.090,
    "llm": 0.085,
    "shipping": 0.085,
    "lexical_jd": 0.060,
    "experience": 0.045,
    "behavior": 0.060,
}

TEAM_LANES = [
    ("Ranking Core Owner", {"ranking": .34, "retrieval": .24, "python": .14, "production": .18, "shipping": .10}),
    ("Retrieval Infra Owner", {"vector": .32, "retrieval": .30, "production": .20, "python": .12, "shipping": .06}),
    ("ML Platform Owner", {"production": .34, "python": .18, "ranking": .18, "retrieval": .14, "llm": .10, "shipping": .06}),
    ("LLM Product Owner", {"llm": .34, "retrieval": .22, "production": .16, "python": .14, "ranking": .10, "shipping": .04}),
    ("Recruiter Workflow Owner", {"shipping": .34, "ranking": .18, "retrieval": .16, "production": .16, "python": .10, "llm": .06}),
]

@dataclass
class RankedCandidate:
    candidate_id: str
    rank: int
    score: float
    reasoning: str
    name: str
    headline: str
    location: str
    country: str
    years_experience: float
    current_title: str
    current_company: str
    salary_mid_lpa: float
    notice_days: int
    preferred_work_mode: str
    role_lane: str
    potential: int
    chemistry: int
    company_to_candidate: int
    candidate_to_company: int
    group_scores: Dict[str, float]
    behavior_score: float
    lexical_jd_score: float
    experience_score: float
    risk_penalty: float
    risk_flags: List[str]
    strengths: List[str]
    concerns: List[str]
    skills: List[str]
    verified: Dict[str, Any]
    interview_proxy: Dict[str, int]
    team_lane_scores: Dict[str, float]


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def low(x: Any) -> str:
    return str(x or "").lower()


def tokenize(text: str) -> List[str]:
    return [t.lower() for t in TOKEN_RE.findall(text or "")]


def parse_date(s: Any) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def phrase_hits(text: str, phrases: Iterable[str]) -> int:
    t = " " + low(text).replace("_", " ") + " "
    total = 0
    for p in phrases:
        p = p.lower().replace("_", " ")
        if " " + p + " " in t or p in t:
            total += 1
    return total


def load_candidates(path: str | Path) -> List[Dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    if path.suffix.lower() == ".jsonl":
        with path.open("r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("JSON candidates file must contain a list. Use .jsonl or .jsonl.gz for line-delimited input.")
    return data


def profile(c: Dict[str, Any]) -> Dict[str, Any]:
    return c.get("profile", {}) or {}


def career_text(c: Dict[str, Any]) -> str:
    parts = []
    for job in c.get("career_history", []) or []:
        parts += [job.get("title", ""), job.get("company", ""), job.get("industry", ""), job.get("description", "")]
    return "\n".join(str(x) for x in parts if x)


def all_text(c: Dict[str, Any]) -> str:
    p = profile(c)
    parts = [p.get("headline", ""), p.get("summary", ""), p.get("current_title", ""), p.get("current_company", ""), p.get("current_industry", ""), p.get("location", ""), p.get("country", ""), career_text(c)]
    for e in c.get("education", []) or []:
        parts += [e.get("institution", ""), e.get("degree", ""), e.get("field_of_study", ""), e.get("tier", "")]
    for s in c.get("skills", []) or []:
        parts += [s.get("name", ""), s.get("proficiency", "")]
    for cert in c.get("certifications", []) or []:
        parts += [cert.get("name", ""), cert.get("issuer", "")]
    return "\n".join(str(x) for x in parts if x)


def skill_index(c: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {low(s.get("name", "")).strip(): s for s in c.get("skills", []) or [] if s.get("name")}


def skill_score(skills: Dict[str, Dict[str, Any]], terms: List[str]) -> float:
    hits: List[float] = []
    term_l = [t.lower() for t in terms]
    for name, meta in skills.items():
        n = name.replace("_", " ")
        if any(t in n or n in t for t in term_l):
            prof = PROFICIENCY.get(low(meta.get("proficiency")), 0.50)
            dur = min(float(meta.get("duration_months") or 0) / 48.0, 1.0)
            end = min(math.log1p(float(meta.get("endorsements") or 0)) / math.log(80), 1.0)
            hits.append(100 * (0.56 * prof + 0.30 * dur + 0.14 * end))
    if not hits:
        return 0.0
    hits.sort(reverse=True)
    return clamp(0.72 * hits[0] + 0.28 * (sum(hits[:4]) / min(len(hits), 4)))


def assessment_score(c: Dict[str, Any], group: str) -> float:
    assessments = ((c.get("redrob_signals") or {}).get("skill_assessment_scores") or {})
    if not assessments:
        return 0.0
    terms = [*GROUPS[group]["phrases"], *GROUPS[group]["skills"]]
    vals = []
    for k, v in assessments.items():
        key = k.lower()
        if any(t.lower() in key or key in t.lower() for t in terms):
            try:
                vals.append(float(v))
            except Exception:
                pass
    return sum(vals) / len(vals) if vals else 0.0


def group_score(c: Dict[str, Any], group: str) -> float:
    career = career_text(c)
    text = all_text(c)
    skills = skill_index(c)
    career_hits = phrase_hits(career, GROUPS[group]["phrases"])
    all_hits = phrase_hits(text, GROUPS[group]["phrases"])
    text_score = clamp(100 * (1 - math.exp(-(1.10 * career_hits + 0.35 * max(0, all_hits - career_hits)) / 2.4)))
    sk_score = skill_score(skills, GROUPS[group]["skills"])
    ass_score = assessment_score(c, group)
    # Career proof dominates; skills/assessments support but cannot carry a profile alone.
    return clamp(0.62 * text_score + 0.28 * sk_score + 0.10 * ass_score)


class TfidfScorer:
    def __init__(self, jd_text: str, candidates: List[Dict[str, Any]]):
        self.n = len(candidates) + 1
        self.df = Counter()
        self.jd_terms = Counter(self._tokens(jd_text))
        for term in set(self.jd_terms):
            self.df[term] += 1
        for c in candidates:
            toks = set(self._tokens(all_text(c)))
            for t in toks:
                self.df[t] += 1
        self.jd_vec = self._tfidf(self.jd_terms)
        self.jd_norm = math.sqrt(sum(v*v for v in self.jd_vec.values())) or 1.0

    @staticmethod
    def _tokens(text: str) -> List[str]:
        raw = tokenize(text)
        stop = {"the","and","for","with","this","that","you","your","have","has","are","will","from","they","into","role","need","what","we","our","not","but","can","been","was","were","its","it's","their","them","than","then","also","most","more","less","about","where"}
        return [t for t in raw if len(t) > 2 and t not in stop]

    def _idf(self, term: str) -> float:
        return math.log((1 + self.n) / (1 + self.df.get(term, 0))) + 1.0

    def _tfidf(self, counts: Counter) -> Dict[str, float]:
        if not counts:
            return {}
        max_tf = max(counts.values())
        return {t: (0.5 + 0.5 * (tf / max_tf)) * self._idf(t) for t, tf in counts.items()}

    def score(self, c: Dict[str, Any]) -> float:
        counts = Counter(self._tokens(all_text(c)))
        vec = self._tfidf(counts)
        norm = math.sqrt(sum(v*v for v in vec.values())) or 1.0
        dot = sum(v * self.jd_vec.get(t, 0.0) for t, v in vec.items())
        cos = dot / (norm * self.jd_norm)
        return clamp(420 * cos)  # maps normal JD/profile cosine range into readable 0-100


def experience_score(c: Dict[str, Any]) -> float:
    yrs = float(profile(c).get("years_of_experience") or 0)
    if 5 <= yrs <= 9:
        base = 100
    elif 4 <= yrs < 5:
        base = 82 + 18 * (yrs - 4)
    elif 9 < yrs <= 11:
        base = 95 - 7 * (yrs - 9)
    elif 3 <= yrs < 4:
        base = 60 + 22 * (yrs - 3)
    elif 11 < yrs <= 14:
        base = 75 - 7 * (yrs - 11)
    else:
        base = max(15, 55 - abs(yrs - 7) * 5)
    # Institute tier as a small tie-breaker, not a gate.
    tiers = [low(e.get("tier", "unknown")) for e in c.get("education", []) or []]
    edu = max(TIER_WEIGHT.get(t, 0.45) for t in tiers) if tiers else 0.45
    return clamp(0.92 * base + 8 * edu)


def behavior_score(c: Dict[str, Any]) -> float:
    s = c.get("redrob_signals", {}) or {}
    completeness = float(s.get("profile_completeness_score") or 0)
    open_to_work = 100.0 if s.get("open_to_work_flag") else 38.0
    rr = clamp(float(s.get("recruiter_response_rate") or 0) * 100)
    response_hours = float(s.get("avg_response_time_hours") or 999)
    response = clamp(100 - response_hours / 2.4)
    notice = float(s.get("notice_period_days") or 180)
    notice_score = clamp(100 - max(0, notice - 30) * 0.75)
    interview = clamp(float(s.get("interview_completion_rate") or 0) * 100)
    github_raw = float(s.get("github_activity_score", -1) if s.get("github_activity_score", -1) is not None else -1)
    github = 45 if github_raw < 0 else clamp(github_raw)
    linkedin = 100 if s.get("linkedin_connected") else 54
    verified = (50 if s.get("verified_email") else 0) + (50 if s.get("verified_phone") else 0)
    active = 50
    last = parse_date(s.get("last_active_date"))
    if last:
        days = max(0, (TODAY - last).days)
        active = clamp(100 - days / 2.1)
    saved = min(math.log1p(float(s.get("saved_by_recruiters_30d") or 0)) / math.log(25), 1) * 100
    viewed = min(math.log1p(float(s.get("profile_views_received_30d") or 0)) / math.log(100), 1) * 100
    return clamp(
        0.11*completeness + 0.11*open_to_work + 0.13*rr + 0.07*response + 0.12*notice_score +
        0.11*interview + 0.08*github + 0.08*linkedin + 0.08*verified + 0.07*active + 0.02*saved + 0.02*viewed
    )


def salary_mid(c: Dict[str, Any]) -> float:
    rng = ((c.get("redrob_signals") or {}).get("expected_salary_range_inr_lpa") or {})
    mn = float(rng.get("min") or 0)
    mx = float(rng.get("max") or mn or 0)
    if mn <= 0 and mx <= 0:
        return 0.0
    return (mn + mx) / 2


def company_to_candidate_score(c: Dict[str, Any]) -> float:
    s = c.get("redrob_signals", {}) or {}
    mid = salary_mid(c)
    # Senior founding AI engineer budget assumption for demo; final teams can edit in UI.
    budget_ceiling = 55.0
    if mid <= 0:
        salary = 62
    elif mid <= budget_ceiling:
        salary = 100 - max(0, mid - 38) * 1.2
    else:
        salary = clamp(72 - (mid - budget_ceiling) * 4)
    country = low(profile(c).get("country"))
    location = low(profile(c).get("location"))
    relo = bool(s.get("willing_to_relocate"))
    loc = 100 if ("india" in country and ("pune" in location or "noida" in location)) else (88 if "india" in country else (64 if relo else 38))
    work = low(s.get("preferred_work_mode", ""))
    work_mode = 100 if work in {"hybrid", "flexible"} else (78 if work == "onsite" else 60)
    notice = float(s.get("notice_period_days") or 180)
    notice_fit = clamp(100 - max(0, notice - 45) * 0.85)
    return clamp(0.34*salary + 0.27*loc + 0.16*work_mode + 0.23*notice_fit)


def risk_analysis(c: Dict[str, Any], groups: Dict[str, float]) -> Tuple[float, List[str], List[str]]:
    s = c.get("redrob_signals", {}) or {}
    p = profile(c)
    flags: List[str] = []
    concerns: List[str] = []
    penalty = 0.0

    signup = parse_date(s.get("signup_date")); last = parse_date(s.get("last_active_date"))
    if signup and last and last < signup:
        penalty += 8; flags.append("timeline anomaly"); concerns.append("Activity dates need verification before outreach")
    if not s.get("open_to_work_flag"):
        penalty += 4; flags.append("not marked open"); concerns.append("Not currently marked open to work")
    if float(s.get("notice_period_days") or 0) >= 120:
        penalty += 5; flags.append("long notice"); concerns.append(f"Notice period is {int(s.get('notice_period_days') or 0)} days")
    if float(s.get("recruiter_response_rate") or 0) < 0.20:
        penalty += 4; flags.append("low response"); concerns.append("Recruiter response rate is weak")
    if not s.get("verified_email") or not s.get("verified_phone"):
        penalty += 2; flags.append("verification gap")
    yrs = float(p.get("years_of_experience") or 0)
    if yrs < 3:
        penalty += 12; flags.append("too junior"); concerns.append("Experience is materially below the senior range")
    if yrs > 14:
        penalty += 5; flags.append("seniority mismatch")
    # Keyword-stuffing detection: skill names look strong but career evidence does not.
    skill_names = " ".join([low(x.get("name")) for x in c.get("skills", []) or []])
    ai_skill_hits = phrase_hits(skill_names, sum([GROUPS[g]["skills"] for g in GROUPS], []))
    career_hits = phrase_hits(career_text(c), sum([GROUPS[g]["phrases"] for g in GROUPS], []))
    if ai_skill_hits >= 5 and career_hits <= 1:
        penalty += 12; flags.append("keyword-heavy"); concerns.append("Skills list is stronger than career evidence")
    companies = {low(j.get("company")) for j in c.get("career_history", []) or []}
    if companies and companies.issubset(CONSULTING) and groups.get("production", 0) < 45 and groups.get("retrieval", 0) < 35:
        penalty += 6; flags.append("consulting-heavy"); concerns.append("Career evidence may be more services/consulting than product ML")
    title_text = low(p.get("current_title", "") + " " + p.get("headline", ""))
    if any(x in title_text for x in ["marketing", "accountant", "civil", "mechanical", "support", "operations manager"]):
        if groups.get("retrieval", 0) < 30 and groups.get("ranking", 0) < 30:
            penalty += 10; flags.append("role mismatch"); concerns.append("Current role is not close to AI engineering")
    return clamp(penalty, 0, 35), flags[:5], concerns[:5]


def strengths_from_scores(c: Dict[str, Any], groups: Dict[str, float]) -> List[str]:
    items = sorted(groups.items(), key=lambda kv: kv[1], reverse=True)
    out = []
    for g, v in items:
        if v >= 45:
            out.append(f"{GROUPS[g]['label']} evidence")
    s = c.get("redrob_signals", {}) or {}
    if s.get("linkedin_connected"):
        out.append("LinkedIn connected")
    if s.get("verified_email") and s.get("verified_phone"):
        out.append("verified contact channels")
    if s.get("open_to_work_flag"):
        out.append("available/open-to-work signal")
    if not out:
        out.append("some adjacent technical/product evidence")
    return out[:5]


def role_lane(groups: Dict[str, float]) -> str:
    g, v = max(groups.items(), key=lambda kv: kv[1])
    if v < 34:
        return "Adjacent Talent Prospect"
    return GROUPS[g]["lane"]


def team_lane_scores(groups: Dict[str, float]) -> Dict[str, float]:
    out = {}
    for lane, weights in TEAM_LANES:
        out[lane] = round(sum(groups.get(g, 0.0) * w for g, w in weights.items()), 2)
    return out


def reasoning_for(c: Dict[str, Any], score: float, groups: Dict[str, float], behavior: float, c2r: float, r2c: float, concerns: List[str]) -> str:
    p = profile(c)
    yrs = float(p.get("years_of_experience") or 0)
    top = sorted(groups.items(), key=lambda kv: kv[1], reverse=True)[:2]
    names = [GROUPS[g]["label"] for g, v in top if v >= 25]
    skill_names = [s.get("name", "") for s in c.get("skills", []) or []][:8]
    anchor = ", ".join(names) if names else "adjacent AI/data evidence"
    skills = ", ".join([s for s in skill_names if s][:3]) or "listed technical skills"
    first = f"{yrs:.1f} years as {p.get('current_title','candidate')} with strongest evidence in {anchor}; profile also lists {skills}."
    if concerns:
        second = f"Ranked here after balancing fit score {score:.1f}, hireability signal {behavior:.0f}, and concern: {concerns[0].lower()}."
    elif r2c < 65:
        second = f"Strong candidate-to-role fit, but company-to-candidate practicality needs recruiter validation before outreach."
    else:
        second = f"Good Redrob fit because technical evidence, availability signals, and practical outreach fit are aligned."
    return first + " " + second


def score_candidate(c: Dict[str, Any], tfidf: TfidfScorer) -> RankedCandidate:
    p = profile(c)
    groups = {g: group_score(c, g) for g in GROUPS}
    lex = tfidf.score(c)
    exp = experience_score(c)
    beh = behavior_score(c)
    c2r = clamp(sum(groups[g] * WEIGHTS[g] for g in GROUPS) / sum(WEIGHTS[g] for g in GROUPS))
    r2c = company_to_candidate_score(c)
    penalty, flags, concerns = risk_analysis(c, groups)
    base = sum(groups[g] * WEIGHTS[g] for g in GROUPS) + lex*WEIGHTS["lexical_jd"] + exp*WEIGHTS["experience"] + beh*WEIGHTS["behavior"]
    both = 0 if (c2r + r2c) <= 0 else (2 * c2r * r2c) / (c2r + r2c)
    final = clamp(0.76 * base + 0.24 * both - penalty)
    chem = int(round(clamp(0.46*c2r + 0.30*r2c + 0.24*beh - penalty/2)))
    potential = int(round(clamp(final + 0.18*(100 - final)*(groups.get("shipping",0)/100) + 0.10*(100-final)*(exp/100) - penalty/3)))
    skills = [s.get("name", "") for s in c.get("skills", []) or [] if s.get("name")]
    s = c.get("redrob_signals", {}) or {}
    inter = {
        "Communication": int(round(clamp(38 + 0.36*groups.get("shipping",0) + 0.20*beh + min(len(career_text(c))/900, 1)*12))),
        "Technical Depth": int(round(clamp(0.35*groups.get("retrieval",0) + 0.25*groups.get("ranking",0) + 0.25*groups.get("production",0) + 0.15*groups.get("llm",0)))),
        "Role Clarity": int(round(clamp(0.45*c2r + 0.25*lex + 0.30*groups.get("shipping",0)))),
        "Recruiter Readiness": int(round(beh)),
    }
    rc = RankedCandidate(
        candidate_id=str(c.get("candidate_id", "")), rank=0, score=round(final, 6), reasoning="",
        name=str(p.get("anonymized_name", c.get("candidate_id", "Candidate"))),
        headline=str(p.get("headline", "")), location=str(p.get("location", "")), country=str(p.get("country", "")),
        years_experience=float(p.get("years_of_experience") or 0), current_title=str(p.get("current_title", "")), current_company=str(p.get("current_company", "")),
        salary_mid_lpa=round(salary_mid(c), 2), notice_days=int(s.get("notice_period_days") or 0), preferred_work_mode=str(s.get("preferred_work_mode", "")),
        role_lane=role_lane(groups), potential=potential, chemistry=chem, company_to_candidate=int(round(r2c)), candidate_to_company=int(round(c2r)),
        group_scores={k: round(v, 2) for k,v in groups.items()}, behavior_score=round(beh, 2), lexical_jd_score=round(lex, 2), experience_score=round(exp, 2),
        risk_penalty=round(penalty, 2), risk_flags=flags, strengths=strengths_from_scores(c, groups), concerns=concerns, skills=skills[:18],
        verified={"email": bool(s.get("verified_email")), "phone": bool(s.get("verified_phone")), "linkedin": bool(s.get("linkedin_connected")), "github_activity": s.get("github_activity_score", -1), "open_to_work": bool(s.get("open_to_work_flag")), "response_rate": s.get("recruiter_response_rate", 0)},
        interview_proxy=inter, team_lane_scores=team_lane_scores(groups)
    )
    rc.reasoning = reasoning_for(c, rc.score, groups, beh, c2r, r2c, concerns)
    return rc


def rank_candidates(candidates: List[Dict[str, Any]], jd_text: str) -> List[RankedCandidate]:
    tfidf = TfidfScorer(jd_text, candidates)
    ranked = [score_candidate(c, tfidf) for c in candidates]
    ranked.sort(key=lambda r: (-r.score, r.candidate_id))
    for i, r in enumerate(ranked, 1):
        r.rank = i
    return ranked


def write_csv(rows: List[RankedCandidate], path: str | Path, top: int) -> None:
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    selected = rows[:top]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["candidate_id", "rank", "score", "reasoning"])
        writer.writeheader()
        for i, r in enumerate(selected, 1):
            writer.writerow({"candidate_id": r.candidate_id, "rank": i, "score": f"{r.score:.6f}", "reasoning": r.reasoning})


def write_dashboard(rows: List[RankedCandidate], path: str | Path, top: int = 100) -> None:
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "job": {
            "title": "Senior AI Engineer — Founding Team",
            "company": "Redrob AI",
            "location": "Pune/Noida Hybrid",
            "focus": ["embeddings", "retrieval", "ranking", "vector search", "production Python", "evaluation frameworks", "product shipping"]
        },
        "weights": WEIGHTS,
        "groups": {k: {"label": v["label"], "lane": v["lane"]} for k,v in GROUPS.items()},
        "team_lanes": [lane for lane, _ in TEAM_LANES],
        "candidates": [asdict(r) for r in rows[:top]],
        "summary": {
            "candidate_count_ranked": len(rows),
            "dashboard_count": min(top, len(rows)),
            "top_score": rows[0].score if rows else None,
            "average_top10": round(sum(r.score for r in rows[:10]) / max(1, min(10, len(rows))), 4),
        }
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Rank Redrob candidates and emit a submission CSV.")
    ap.add_argument("--candidates", default="data/sample_candidates.json", help="Path to sample_candidates.json, candidates.jsonl, or candidates.jsonl.gz")
    ap.add_argument("--jd", default="data/job_description.txt", help="Path to extracted job description text")
    ap.add_argument("--output", default="outputs/team_redrob_fifa_sample_top50.csv", help="CSV output path")
    ap.add_argument("--dashboard-json", default="outputs/dashboard_payload.json", help="Dashboard JSON output path")
    ap.add_argument("--top", type=int, default=50, help="Number of rows to write. Use 100 for final submission.")
    ap.add_argument("--strict-submission", action="store_true", help="Require exactly 100 output rows for official submission")
    args = ap.parse_args(argv)

    candidates = load_candidates(args.candidates)
    jd_path = Path(args.jd)
    jd_text = jd_path.read_text(encoding="utf-8") if jd_path.exists() else "Senior AI Engineer embeddings retrieval ranking vector search Python production ML evaluation frameworks product shipping"
    if args.strict_submission:
        args.top = 100
        if len(candidates) < 100:
            raise SystemExit(f"strict submission requires at least 100 candidates; found {len(candidates)}")
    top = min(args.top, len(candidates))
    ranked = rank_candidates(candidates, jd_text)
    write_csv(ranked, args.output, top)
    write_dashboard(ranked, args.dashboard_json, top=max(100, top))
    print(json.dumps({"ranked": len(ranked), "csv": args.output, "dashboard_json": args.dashboard_json, "top_score": ranked[0].score if ranked else None}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
