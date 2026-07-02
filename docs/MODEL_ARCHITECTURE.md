# Model Architecture

## A → B pipeline

**Raw candidate file**
→ `load_candidates()` accepts `.json`, `.jsonl`, and `.jsonl.gz`.

**Candidate object**
→ profile, career history, education, skills, certifications, languages, and `redrob_signals` are parsed.

**JD file**
→ extracted `job_description.txt` becomes the target query for the local ranker.

**Feature layer**
→ group scores are computed for retrieval, vector infrastructure, ranking evaluation, production ML, Python systems, LLM systems, and product shipping.

**TF-IDF layer**
→ the JD is compared against every candidate with a local CPU-only TF-IDF cosine model.

**Behavior layer**
→ availability, response behavior, notice period, salary fit, work mode, relocation, verification, LinkedIn, GitHub, and interview-completion signals are scored.

**Risk layer**
→ suspicious timelines, weak availability, keyword stuffing, low response, long notice, role mismatch, and verification gaps are penalized.

**Final rank**
→ score is sorted descending, ties break by `candidate_id`, and CSV reasoning is generated from actual candidate facts.

## Current scoring blocks

```text
Technical evidence
→ retrieval / vector / ranking / production / Python / LLM / shipping

JD similarity
→ local TF-IDF cosine score

Experience fit
→ strongest near the JD's senior range, flexible for exceptional signals

Behavioral hireability
→ Redrob platform signals

Both-ways fit
→ candidate-to-company + company-to-candidate practicality

Risk penalty
→ reduces fragile or suspicious profiles
```

## Current stack

```text
Python standard library
→ ranker.py
→ app.py
→ CSV output
→ JSON dashboard payload

HTML / CSS / JavaScript
→ polished Scout Arena dashboard
→ candidate card
→ dossier
→ budget team builder
→ model room
```

## Aspirational production stack

```text
DuckDB / Polars
→ fast candidate feature table

BM25 + dense embeddings
→ high-recall retrieval stage

FAISS / Qdrant / OpenSearch
→ vector + hybrid search infrastructure

LightGBM LambdaMART / XGBoost ranker
→ supervised learning-to-rank once labeled feedback exists

Calibration layer
→ monotonic, explainable score bands

Evaluation harness
→ NDCG@10, NDCG@50, MAP, P@10

Human feedback loop
→ recruiter saves, rejects, outreach responses, interview completions
```

## Design principle

**Skill keyword count**
→ weak signal by itself.

**Career evidence + behavioral hireability + JD fit**
→ stronger ranking signal.
