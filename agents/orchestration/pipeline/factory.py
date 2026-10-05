from __future__ import annotations

from typing import Optional

from agents.knowledge_based.compliance_validation.agent import ComplianceValidationAgent
from agents.knowledge_based.information_retrieval.agent import InformationRetrievalAgent
from agents.orchestration.integration import (
    ComplianceAgentAdapter,
    ExecutionIntegrationService,
)
from agents.orchestration.intent_understanding import IntentUnderstandingService
from agents.orchestration.monitoring import MonitoringService
from agents.orchestration.workflow_planning import create_workflow_plan
from agents.response_generation import ProductionResponseGenerator
from agents.utility_based.execution_assistance import (
    ExecutionCoordinator,
    UIDAIExecutionAdapter,
)

from .service import TopLevelOrchestrator


def create_uidai_orchestrator(
    require_otp: bool = True,
    retrieval_agent: Optional[InformationRetrievalAgent] = None,
    compliance_agent: Optional[ComplianceValidationAgent] = None,
    execution_adapter: Optional[UIDAIExecutionAdapter] = None,
) -> TopLevelOrchestrator:
    """
    Constructs a fully-integrated TopLevelOrchestrator configured for real UIDAI workflows.
    Integrates Intent Understanding, Information Retrieval, Evidence-Grounded Workflow Planning,
    Compliance Validation, UIDAI Execution Assistance (SSUP/OTP), Monitoring, and Citizen Response Generation.
    """
    ir_agent = retrieval_agent or InformationRetrievalAgent()
    comp_agent = compliance_agent or ComplianceValidationAgent()
    exec_adapter = execution_adapter or UIDAIExecutionAdapter(require_otp=require_otp)

    compliance_adapter = ComplianceAgentAdapter(
        agent=comp_agent,
        policy_version="uidai-compliance-v2",
    )

    execution_integration = ExecutionIntegrationService(
        executor=ExecutionCoordinator(adapter=exec_adapter),
        compliance_validator=compliance_adapter,
    )

    return TopLevelOrchestrator(
        intent_service=IntentUnderstandingService(),
        retrieval_agent=ir_agent,
        workflow_planner=create_workflow_plan,
        execution_integration=execution_integration,
        monitoring_service=MonitoringService(),
        response_generator=ProductionResponseGenerator(),
    )
