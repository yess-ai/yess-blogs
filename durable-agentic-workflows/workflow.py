from temporalio import workflow
from datetime import timedelta
from temporalio.common import RetryPolicy
from dataclasses import dataclass
import asyncio

@dataclass
class CRMAnalysisParams:
    contacts_file: str
    opportunities_file: str

@workflow.defn
class CRMAnalysisWorkflow:
    @workflow.run
    async def run(self, params: CRMAnalysisParams) -> dict:
        # PARALLEL EXECUTION: Analyze contacts and opportunities concurrently
        contact_task = workflow.execute_activity(
            "analyze_contacts",
            args=[params.contacts_file],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=2)
        )

        opportunity_task = workflow.execute_activity(
            "analyze_opportunities",
            args=[params.opportunities_file],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=2)
        )

        # Wait for both parallel tasks to complete
        contact_analysis, opportunity_analysis = await asyncio.gather(
            contact_task, opportunity_task
        )

        # CHECKPOINT: Both analyses complete, state persisted

        # VALIDATION: Check contact analysis for issues
        contact_validation = await workflow.execute_activity(
            "validate_analysis",
            args=["contacts", contact_analysis, params.contacts_file],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=2)
        )

        if not contact_validation["passed"]:
            return {
                "error": "Contact analysis validation failed",
                "reason": contact_validation["reason"]
            }

        # VALIDATION: Check opportunity analysis for issues
        opp_validation = await workflow.execute_activity(
            "validate_analysis",
            args=["opportunities", opportunity_analysis, params.opportunities_file],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=2)
        )

        if not opp_validation["passed"]:
            return {
                "error": "Opportunity analysis validation failed",
                "reason": opp_validation["reason"]
            }

        # CHECKPOINT: Validations passed, state persisted

        # FINAL STEP: Combine analyses into final report
        analysis_report = await workflow.execute_activity(
            "combine_analysis",
            args=[contact_analysis, opportunity_analysis],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3)
        )

        return analysis_report

