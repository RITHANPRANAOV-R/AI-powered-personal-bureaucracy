from __future__ import annotations

import os
from typing import Any, Optional

from .schema import CitizenResponse, ExecutionResult


class ProductionResponseGenerator:
    """
    Generates high quality, citizen-friendly structured responses and markdown dashboards.
    Falls back gracefully to deterministic templates when Gemini ADK is unconfigured or offline.
    """

    def generate(self, result: ExecutionResult) -> CitizenResponse:
        headline = self._generate_headline(result)
        summary = self._generate_summary(result)
        citizen_next_step = result.action_required or (
            result.pending_steps[0] if result.pending_steps else "No further action is required at this time."
        )

        formatted_md = self._format_markdown(
            headline=headline,
            summary=summary,
            result=result,
            citizen_next_step=citizen_next_step,
        )

        return CitizenResponse(
            headline=headline,
            summary=summary,
            completed_actions=list(result.completed_steps),
            pending_actions=list(result.pending_steps),
            citizen_next_step=citizen_next_step,
            key_details=dict(result.important_details or {}),
            missing_items=list(result.missing_information or []),
            official_links=list(result.official_references or ["https://myaadhaar.uidai.gov.in/"]),
            formatted_markdown=formatted_md,
        )

    def _generate_headline(self, result: ExecutionResult) -> str:
        status_map = {
            "COMPLETED": f"{result.service_name} Completed Successfully",
            "IN_PROGRESS": f"{result.service_name} In Progress",
            "ACTION_REQUIRED": f"Action Required for {result.service_name}",
            "BLOCKED": f"{result.service_name} Blocked",
            "FAILED": f"{result.service_name} Could Not Be Completed",
        }
        return status_map.get(result.overall_status.upper(), f"{result.service_name} Status Update")

    def _generate_summary(self, result: ExecutionResult) -> str:
        status = result.overall_status.upper()
        if status == "COMPLETED":
            return f"Your {result.service_name} has been processed and submitted successfully."
        if status == "ACTION_REQUIRED":
            action = result.action_required or "Please provide the required details to continue."
            return f"Action is required to proceed: {action}"
        if status == "BLOCKED":
            reason = result.action_required or "Process is blocked due to compliance or missing requirements."
            return f"Your {result.service_name} could not proceed: {reason}"
        if status == "FAILED":
            return f"An error occurred during {result.service_name}. Please review the details below."
        return f"Your {result.service_name} is currently progressing through the official workflow."

    def _format_markdown(
        self,
        headline: str,
        summary: str,
        result: ExecutionResult,
        citizen_next_step: Optional[str],
    ) -> str:
        lines = [
            f"### {headline}",
            "",
            summary,
            "",
        ]

        if result.completed_steps:
            lines.append("#### Completed Steps")
            for step in result.completed_steps:
                lines.append(f"- [x] {step}")
            lines.append("")

        if result.pending_steps:
            lines.append("#### Next / Pending Steps")
            for step in result.pending_steps:
                lines.append(f"- [ ] {step}")
            lines.append("")

        if result.missing_information:
            lines.append("#### Missing Information / Documents")
            for item in result.missing_information:
                lines.append(f"- :warning: **{item}**")
            lines.append("")

        if citizen_next_step:
            lines.append(f"**Immediate Citizen Action**: {citizen_next_step}")
            lines.append("")

        if result.official_references:
            lines.append("#### Official Resources & Tracking")
            for ref in result.official_references:
                lines.append(f"- [{ref}]({ref})")

        return "\n".join(lines)
