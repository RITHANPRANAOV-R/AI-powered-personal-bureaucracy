"""Compliance & Validation Agent Rationale and Policy Documentation.

Why deterministic Python code is used instead of a generative LLM:
------------------------------------------------------------------
1. **Safety & Permission Gatekeeping**: Compliance and safety gates must be 100% deterministic,
   auditable, reproducible, and verifiable. A generative LLM must never be allowed to grant
   permission, override safety policies, or hallucinate requirement verification.
2. **Auditability & Traceability**: Automated bureaucracy assistance requires every rule failure
   or approval check to be traceable to explicit line-item code, rule IDs, and evidence IDs.
3. **Repeatability**: Given the exact same inputs (Intent, ProfileContext, RetrievedEvidence,
   WorkflowPlan, Approvals, and Observations), validation results must be identical every time,
   with no probabilistic variance, prompt drift, or temperature fluctuations.
4. **Boundary Control**: Fact verification status (`user_confirmed` vs `document_extracted`/`inferred`)
   and host allowlist matching must be strictly enforced without risk of prompt injection or model evasion.
5. **Clear Distinctions**: Keep LLM-proposed steps or extracted facts strictly distinguishable from
   formally verified evidence and confirmed user data.
"""

SYSTEM_DESIGN_DOCUMENTATION = __doc__
