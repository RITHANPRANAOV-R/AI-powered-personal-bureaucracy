"""Monitoring & Update Agent Rationale and Policy Documentation.

Why 100% Deterministic Python Code is used instead of a Generative LLM:
----------------------------------------------------------------------
1. **Auditable & Repeatable State Tracking**: Tracking workflow status transitions, comparing step
   statuses across upstream agent outputs, recording event histories, and computing deltas must be
   100% auditable, deterministic, and reproducible. A generative LLM must never be allowed to guess,
   hallucinate, or silently alter workflow statuses or reminder dates.
2. **Provenance Preservation**: Status events must maintain verifiable provenance labels:
   - `OFFICIAL_PORTAL_VISIBLE`: Only when directly observed by the Execution Agent on an allowlisted page.
   - `USER_REPORTED`: Explicitly user-entered status. User reports update `user_reported_status`,
     but CANNOT silently overwrite `portal_observed_status`.
3. **Preserving Uncertainty & Preventing Auto-Retry**: Statuses such as `submission_attempted` or `uncertain`
   must NEVER be promoted to `confirmed` without direct, current official evidence. The Monitoring Agent
   does not poll government portals in the background or trigger automatic resubmission attempts.
4. **Local CLI Reminders Only**: Reminders are calculated strictly from explicitly provided user deadlines
   or verified official evidence dates. No background daemons, cron jobs, network polling, push notifications,
   emails, or SMS are sent.
"""

SYSTEM_DESIGN_DOCUMENTATION = __doc__
