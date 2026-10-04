# Ascendia — JobDiva sourcing agent

An internal tool for recruiters. Pick a JobDiva job, describe the candidate you want, and get up to **30 ranked candidates**. Each candidate comes with:
- the skills that matched, backed by evidence;
- a short reason for the ranking;
- how each data source affected the recommendation: profile, resume, submissions, interviews, placements, client feedback.

If fewer than 30 candidates qualify, the app explains why. The hiring manager makes the final decision.

- **Backend:** Python 3.12, FastAPI, and Claude (`claude-opus-5-5`) through the Anthropic SDK.
- **Frontend:** React, Vite and TypeScript, following the Figma "Sourcing" screen.
- **Data source:** JobDiva **API v1**, `/api/jobdiva/*` endpoints only by default. JobDiva remains the system of record: the app is read-only and stores no candidate data.

## Quick start

```bash
# 1. Configure: fill in ANTHROPIC_API_KEY and JOBDIVA_CLIENT_ID / USERNAME / PASSWORD
$EDITOR .env                      # template: .env.example

# 2. Backend (http://127.0.0.1:8000)
cd backend && uv sync && uv run uvicorn app.main:app --reload --port 8000

# 3. Frontend (http://localhost:5173, proxies /api → :8000)
cd frontend && npm install && npm run dev
```

To run with no credentials, start the backend with `JOBDIVA_MOCK=true` for a synthetic JobDiva dataset, `LLM_MODE=stub` for a keyword matcher instead of Claude, or both. The UI shows a "Dev mode" badge whenever either is on.

Tests: `cd backend && uv run pytest` (45 tests) and `cd frontend && npm test` (13 tests). Neither calls JobDiva or Claude.

## Project structure

```
backend/app/
  main.py            FastAPI app: lifespan deps, CORS, /api router, upstream-error handlers
  core/              settings (config.py), logging + query-string redaction, domain error → HTTP mapping
  constants/         every tunable value: jobdiva (endpoints, params), ranking, search, assessment, intent, llm, pii, api
  models/            pydantic models and internal dataclasses: intent, assessment (Claude output), results, requests, jobdiva DTOs, pipeline
  prompts/           Claude system prompts (intent.py, assess.py), verbatim
  clients/           external services only: jobdiva/ (client, errors, mappers, mock) and claude.py (+ claude_errors.py)
  services/          business logic: intent → retrieval → prescore → hydrate → assess → validation → scoring → shortfall,
                     orchestrated by pipeline.py; plus jobs, candidates, snapshot, geo
  utils/text.py      escaping, PII scrubbing, term matching
  api/               deps.py, sse.py and thin route modules in routes/ (health, jobs, candidates, search)
backend/tests/       pytest suite (offline: mock JobDiva transport, fake Claude client)
frontend/src/
  constants/         page sizes, search steps, source labels, storage keys, API base path, avatar palette
  models/            zod schemas + inferred types by domain (job, intent, search, candidate, health, errors), client state types
  api/               fetch client, ApiError, SSE search stream
  hooks/             useCountdown, useSearchRun / useSearchStore
  state/             SearchRunStore + provider, recent-search history (localStorage)
  utils/format.ts    location and date formatting
  components/        shared presentational components (Layout, Stars, Avatar, SkillChip, Skeleton, EmptyState, ErrorState)
  features/          pages and tabs: jobs, job, sourcing, candidates, drawer
  styles/index.css   global styles
  test/              vitest suite
```

## How a search works

1. **Analyze** (`POST /api/jobs/{id}/intent`). Claude reads the job description, the recruiter's query and the recruiter notes, and produces a structured `SearchIntent`:
   - titles and their synonyms;
   - location and radius;
   - years of experience;
   - requirements, each marked must-have or nice-to-have, with aliases;
   - preferences and exclusions;
   - ambiguities for the recruiter to confirm.

   Requests based on protected characteristics (for example age) are dropped and flagged. The recruiter can edit the result as filter chips.
2. **Retrieve.** No LLM is involved. Code builds escaped keyword queries and runs them from strict to broad through `universalSearchByPermission`, paged 30 at a time, then searches by location. Candidates already linked to the job (`searchSubmittal` and `searchStart`) are always included.
3. **Pre-score.** A deterministic score ranks the pool, and the top `STAGE2_TOP_N` plus every job-linked candidate are reviewed in depth.
4. **Hydrate.** For each candidate under review, the app loads submittal, interview, placement and rejection history.
5. **Assess.** Claude receives the candidates in batches of 8, 5 batches at a time.
   - Each candidate is identified only by a handle, with numbered evidence items. Names, contact details, addresses and age proxies are removed.
   - Text from profiles is treated as untrusted data. Any instructions it contains are ignored and flagged.
   - Claude returns a verdict per requirement (met, partial, not_met or unknown) citing evidence IDs, plus a per-source contribution assessed on content.
6. **Validate.** Code checks every claim before anything is shown:
   - each handle must be real and each evidence ID must belong to that same candidate;
   - a `met` verdict must cite text that names the skill, or it becomes `unverified`;
   - a `not_met` verdict without contradicting evidence becomes `unknown`.
7. **Rank.** Code computes the scores. If the shortlist has fewer than 30, a funnel explains why.

## Ranking parameters

**Pre-score** (values in [constants/ranking.py](backend/app/constants/ranking.py), logic in [prescore.py](backend/app/services/prescore.py)). It decides who gets reviewed in depth and later breaks ties.

| Signal | Weight | How it is computed (unknown = 0.5, neutral) |
|---|---|---|
| Skill coverage | 0.45 | Requirement or alias found in the title, skills, search text or resume. Must-haves count 2, nice-to-haves 1. |
| Title similarity | 0.20 | 1.0 if a target title appears in the candidate's title; otherwise token Jaccard overlap. |
| Location | 0.15 | Remote OK = 1. Within the radius (default 50 mi) = 1, falling linearly to 0 at 3× the radius. With no distance: same state 0.7, different state 0.2. |
| Years | 0.10 | In range = 1. Below the minimum = 1 − gap/min. Above the maximum = 0.8. |
| Recency | 0.10 | Profile updated within 1 year = 1.0, within 3 years = 0.6, older = 0.3. |

**Hard filters.** These apply only when the recruiter ticks *Required*. A candidate is excluded only when their profile shows a conflicting value: a known distance outside the radius, or known years below the minimum. An unknown value never excludes anyone.

**Fit score, 0–100** (values in [constants/ranking.py](backend/app/constants/ranking.py), logic in [scoring.py](backend/app/services/scoring.py)):
- Each requirement scores 1.0 if met and 0.5 if partial. Unknown, unverified and not_met score 0. Must-haves weigh 2, nice-to-haves 1.
- The minimum-years requirement is assessed by Claude from the evidence, and is a must-have only if the recruiter marked it Required.
- Interaction adjustment: +0.03 for each positive and −0.03 for each negative validated contribution from submissions, interviews, placements, client feedback or recorded conversations, capped at ±0.06.
- A candidate is excluded as **not a fit** only when a must-have is `not_met` and Claude cited evidence that contradicts it.
- A candidate is excluded as **insufficient evidence** when nothing is met or partial, there is no positive contribution, and they are not already on the job.
- The shortlist is ordered by fit, then pre-score, then candidate ID. The top `SHORTLIST_SIZE` (30) are shown.
- Stars: 85+ = 5, 70+ = 4, 55+ = 3, 35+ = 2, otherwise 1. Tier: 75+ strong, 55+ good, otherwise possible.

**Settings in `.env`:**
- `STAGE2_TOP_N` (40): candidates reviewed in depth.
- `POOL_TARGET` (200): candidate pool size.
- `ASSESS_BATCH_SIZE` (8) and `ASSESS_CONCURRENCY` (5): Claude batching.
- `CLAUDE_EFFORT_ASSESS` and `CLAUDE_EFFORT_INTENT` (both `low`): Claude reasoning effort.
- `SEARCH_CALL_BUDGET` (300): maximum JobDiva calls per search.
- `SEARCH_DEADLINE_S` (120): time limit per search.
- `SHORTLIST_SIZE` (30): candidates shown.

## JobDiva integration (v1, plus one v2 call)

| Need | Endpoint |
|---|---|
| Auth | `GET /api/authenticate`. Any auth-header failure triggers one re-authentication, then one retry; tokens can be rotated anytime. |
| Open jobs (page size 30) | `GET /api/jobdiva/SearchJob?status=0&showAllOpenJobs=true&offset&maxReturned` |
| Job detail | `GET /api/jobdiva/SearchJob?jobId=` (the returned ID must match exactly) |
| Candidates on a job | `GET /api/jobdiva/searchSubmittal?jobid&candidatelastname=a%` … `z%` (A–Z sweep, cached 2 min), plus `GET /api/jobdiva/searchStart?jobId&offset&maxreturned` |
| **Candidate search (the only v2 call)** | `POST /apiv2/jobdiva/TalentSearch` with one skill (`skills`) or a title (`titleSearch`) per query, national, `resumeCount` 40 |
| Candidate lookup for the drawer | `GET /api/jobdiva/us/quickCandidateProfileSearch?criteria=<id>` (exact ID match), then `POST /api/jobdiva/searchCandidateProfile` by name for contact details |
| History | `GET /api/jobdiva/searchStart?candidateid=` (all jobs), plus submittals to the current job from the A–Z sweep |

**What I verified live, and why the design looks like this:**
- **v1 can't search candidates by skill or title.** `universalSearchByPermission` matches candidates by name only. Skill and title search therefore uses v2 `TalentSearch`, the only v2 call in the app.
- **Searches run one skill at a time, nationally.**
  - `TalentSearch` ANDs its skills, and multi-skill queries took 20–30 s for almost no results. Single-skill and title queries return in under 1 s.
  - Each candidate collects every skill JobDiva matched them on. That match is evidence, which Claude treats as "mentioned" (partial unless confirmed elsewhere).
  - The `states` filter took about 20 s per query and returned nothing for smaller states, so location is ranked locally instead.
- **`searchSubmittal` needs both a candidate filter and a job filter.** `%` is not a wildcard, but `a%` is, so a job's submittals are listed with an A–Z last-name sweep. Cross-job history comes from `searchStart`.
- **What a search actually returns.** `TalentSearch` returns only a short `ABSTRACT` (about 50 characters) and the `LASTNOTE`. Full resume text, notes and work history exist only under `/api/bi/*`, which this API user can't access. The UI marks them unavailable rather than missing. If BI access is granted, set `JOBDIVA_USE_BI=true`.
- **429 responses.** The client honours `Retry-After` or backs off exponentially, up to 3 times. If the limit persists, the search ends with a `rate_limited` error and the UI shows a countdown and a **Retry search** button.

## Data handling

- No database. Candidate data exists only in memory during a request, plus `backend/.cache/search_snapshot.json`. That file is overwritten on every search, is gitignored, and exists for debugging. `SNAPSHOT_REPLAY=true` re-runs ranking on it without calling JobDiva.
- Browser `localStorage` keeps recent searches (query and filters only, no candidate data), stored per job.
- Logs record IDs, counts and timings. Query strings, which carry JobDiva credentials, are redacted.
- The deployed app sits behind HTTP basic auth (see Deploy). Replace it with company SSO before wider rollout.

## Deploy (Render)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/AnupNair23/candidate-tracker)

One Docker web service (see [Dockerfile](Dockerfile) and [render.yaml](render.yaml)). FastAPI serves both the API and the built UI from the same origin.

- **Secrets Render asks for:** `ANTHROPIC_API_KEY`, `JOBDIVA_CLIENT_ID`, `JOBDIVA_USERNAME`, `JOBDIVA_PASSWORD`, `BASIC_AUTH_USER`, `BASIC_AUTH_PASSWORD`. Nothing secret is baked into the image.
- **Basic auth:** the whole app (UI, API and the search stream) sits behind HTTP basic auth. The browser prompts once and then reuses the credentials. Only `GET /healthz` (Render's health check, returns `{"ok": true}`) is open. If either auth variable is unset, auth is off and the server logs a warning.
- **Free-tier cold start:** the service sleeps after 15 minutes idle, so the first request after that takes ~30–60 s.
- **JobDiva IP allow-listing:** if JobDiva restricts API access by IP, allow-list the service's outbound IPs (Render dashboard → service → *Connect* → *Outbound*).
- **Run the image locally** (mock data, no secrets):

  ```bash
  docker build -t candidate-tracker . && docker run -p 8000:8000 -e JOBDIVA_MOCK=true -e LLM_MODE=stub -e BASIC_AUTH_USER=demo -e BASIC_AUTH_PASSWORD=demo candidate-tracker
  ```

  Then open http://localhost:8000 and log in as `demo` / `demo`.
