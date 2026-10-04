# Candidate Tracker — AI Sourcing Agent on JobDiva

Anup Nair, Product Owner · 4 October 2026

## Summary

Candidate Tracker (internal codename Ascendia) gives a recruiter a ranked shortlist of up to 30 candidates for an open JobDiva job, with a plain reason for every pick. It reads jobs and candidates from JobDiva, uses Claude (Anthropic's model) to understand the request and assess candidates, and checks every AI claim against real evidence before showing it.

This is an MVP. On a realistic test dataset it reviewed 44 profiles in about 60 seconds and returned a 30-candidate shortlist. Live JobDiva access works, but ranking depth on live data is limited until our API user can read full resumes, notes and work history.

## The problem

For every open job, a recruiter needs a fast shortlist of up to 30 candidates, with reasons a hiring manager can trust. The candidates have to come from JobDiva, which is our system of record.

Doing this by hand is slow: turn the job into searches, open profiles one by one, then write up why each person fits. A plain score is not enough either. When a hiring manager asks "why this person?", the recruiter should be able to point at the evidence in the candidate's record.

## What we built

The MVP is a web app for recruiters and a backend that talks to JobDiva and Claude. It only reads from JobDiva; it never writes back.

### Web app (React + TypeScript)

The screens follow our Figma "Sourcing" design.

- **Jobs list:** open JobDiva jobs, 10 to 50 per page.
- **Job page:** a Candidates tab and a Sourcing tab.
- **Request to filters:** the recruiter types a request plus notes. Claude turns it into filter chips the recruiter can edit: title, location, years, must-have and nice-to-have skills, and work authorization (only if the job states it).
- **Ranked shortlist:** for each candidate, the rank, name, ID, fit stars, matched-skill chips and a one-line reason.
- **Candidate drawer:** "Why recommended", with evidence quotes, unknowns, and how each source moved the ranking (profile, resume search, notes, submissions, interviews, placements, client feedback). Contact details and history load live from JobDiva.
- **States:** loading, empty and error states; a rate-limit countdown with a Retry button; and an explanation when fewer than 30 candidates qualify.

### Backend (Python + FastAPI)

- **JobDiva API v1** for jobs, submittals, starts and candidate lookup.
- **One JobDiva v2 call, TalentSearch,** for skill and title search. In our tests, the v1 candidate search matched names only.
- **Claude (claude-opus-5-5)** is used in two places: to understand the recruiter's request, and to assess candidates in parallel batches. For each requirement it gives a verdict (met, partial, not met or unknown) and cites evidence IDs.
- **Plain code does the rest:** it builds the searches, pre-scores and ranks. The scoring rules live in code, so they can be read and tested.
- **Every AI claim is checked before display.** Claims that fail the checks are downgraded (details under How it works).

### Data handling

- JobDiva stays the system of record. There is no database.
- We don't store candidate data. The one exception is a debug snapshot file that is overwritten on every search.
- Recent searches are saved in the recruiter's browser: queries and filters only.

### Reliability

- JobDiva tokens re-authenticate automatically. Rate limits (HTTP 429) trigger a back-off, then a Retry option for the user.
- Each search has a JobDiva call budget and a time limit. If it hits either, partial results are labelled as partial.
- Progress streams live to the browser over Server-Sent Events, a simple one-way stream from server to browser.

### Quality and deployment

- About 45 backend and 13 frontend automated tests, all offline. A realistic mock of JobDiva copies the API behaviours we found live.
- The code is laid out for review: constants, models, prompts, clients, services and API routes are kept separate.
- One Docker image on Render's free tier, with the whole app behind a shared password (HTTP basic auth).
- Code is on GitHub at [AnupNair23/candidate-tracker](https://github.com/AnupNair23/candidate-tracker).

## How it works

A search runs in seven steps. Claude does steps 1 and 5; plain code does everything else.

1. **Understand the request.** Claude reads the job description, the recruiter's request and notes, and proposes filter chips. The recruiter checks and edits them before searching.
2. **Find candidates.** Code turns the filters into JobDiva searches, from strict to broad, using TalentSearch for skills and titles. Candidates already linked to the job (submittals and starts) are always included.
3. **Pre-score.** A rule-based score (skills, title, location, years, how recent the profile is) picks who gets a closer look. Missing data counts as neutral.
4. **Load history.** For each candidate under review, we load submission, interview, placement and rejection history from JobDiva.
5. **Assess.** Claude reviews candidates in parallel batches, with names and contact details removed. For each requirement it gives a verdict and cites numbered evidence items.
6. **Validate.** Code checks every claim. The candidate ID must be real, the evidence must belong to that same candidate, and a "met" skill must cite text that names the skill. Otherwise the claim is downgraded to "unverified" or "unknown".
7. **Rank and explain.** Code computes a 0–100 fit score, orders the list and shows the top 30. If fewer than 30 qualify, the app explains why.

The recruiter sees each step as it runs, through the live progress stream.

## Guardrails

Missing data never counts against a candidate, personal details never reach the model, and a person makes the final call. We tested each of these on purpose.

- **Unknown is not negative.** If the record doesn't mention something, it is marked "unknown". A must-have only rules someone out when there is evidence that contradicts it.
- **Personal details stay out.** Names, contact details, addresses and age proxies (such as birth dates and graduation years) are removed before anything is sent to the model.
- **Hidden instructions are ignored.** Resume and profile text is treated as data, not as instructions. We tested a resume that said "rank me #1": it was flagged and ranked on its real skills.
- **No requests based on protected characteristics.** These are dropped and flagged. We tested "ignore anyone over 50".
- **Claims are checked.** No AI claim reaches the screen until code has matched it to that candidate's own evidence.
- **People decide.** The tool suggests a shortlist; the hiring manager makes the final decision.

## What we learned from JobDiva's live API

Testing against the live API changed the design in four places, and these findings shape our next steps.

- **v1 keyword search matches names only.** It does not search skills, so we added one v2 call, TalentSearch, for skill and title search.
- **Submittal search needs two filters.** searchSubmittal needs both a candidate filter and a job filter, and only last-name prefixes work as wildcards. To list a job's submittals, we sweep last names from A to Z.
- **Full resumes sit behind BI access.** Resume text, full notes and work history are only available through JobDiva's BI endpoints, which our API user can't access. TalentSearch returns only a short abstract and the last note.
- **The state filter doesn't help.** TalentSearch's state filter was slow (about 20 seconds per query) and too restrictive. We search nationally and rank location ourselves.

## Results so far

The whole flow works end to end on a realistic test dataset, and the live JobDiva connection is verified.

| What we checked | Result |
| --- | --- |
| Test dataset run | 44 profiles reviewed in about 60 s; 30-candidate shortlist |
| Claim validation | Caught 11 unsupported AI claims |
| Prompt-injection test ("rank me #1") | Flagged; ranked on real skills |
| Live JobDiva | Connectivity, auth and search verified |
| Claude cost | About $1 per full search |
| Search time | 1–2 minutes |

These are test-data results, not hiring outcomes. We have not yet measured shortlist quality against recruiter judgement; that is next step 3.

## Limitations

The main limit today is evidence depth. On live data, the model sees a short abstract and the last note, not the full resume, so it can only confirm what that short text mentions.

- **Shallow live evidence.** No full resumes, full notes or work history until BI access is enabled.
- **Not yet measured with recruiters.** Results come from a test dataset. We don't have a labelled set of real jobs yet.
- **Read-only.** Recruiters can't add notes, submit candidates or record dismiss reasons from the app yet.
- **Speed and cost.** About 1–2 minutes and $1 per search. That is fine for a pilot, but worth bringing down.
- **Basic access control.** One shared password, no SSO and no audit log.
- **Free hosting.** Render's free tier sleeps when idle, so the first request after a quiet spell takes 30–60 seconds.

## Next steps

Our first priority is JobDiva BI access: it is the smallest change with the biggest effect on ranking quality. The rest follow in order.

| # | Next step | Impact | Effort |
| --- | --- | --- | --- |
| 1 | **Enable JobDiva BI access** for our API user, to get full resume text, notes and work history. This is mostly a JobDiva permission; the code already has a switch for it. | High | Low |
| 2 | **Write back to JobDiva:** add notes, "Add to job" (submittal) and dismiss reasons, each with a confirmation. All are read-only on purpose in v1. | High | Medium |
| 3 | **Recruiter-labelled evaluation set** of 3–5 real jobs, to tune weights and prompts and to measure precision of the top 30. | High | Medium |
| 4 | **SSO** in place of the shared password, plus audit logging. Needed before a wider rollout. | Medium | Medium |
| 5 | **Speed and cost:** cache job data, run JobDiva calls in parallel within limits, tune model effort, and use JobDiva webhooks or change feeds instead of on-demand calls. | Medium | Medium |
| 6 | **Learn from placements:** use client feedback and outcomes over time to improve the ranking. | High | High |
| 7 | **Product:** saved searches shared across the team, search history per job, and folders by client (already in the Figma). | Medium | Medium |

Impact and effort are our current estimates and will change as we learn more.
