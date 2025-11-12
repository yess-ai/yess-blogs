import asyncio
import json
from temporalio.client import Client
from temporalio.worker import Worker
from workflow import CRMAnalysisWorkflow, CRMAnalysisParams
from activities import (
    analyze_contacts,
    analyze_opportunities,
    validate_analysis,
    combine_analysis
)

async def main():
    # Connect to Temporal server
    client = await Client.connect("localhost:7233")

    # Run workflow directly (for demo purposes)
    result = await client.execute_workflow(
        CRMAnalysisWorkflow.run,
        CRMAnalysisParams(
            contacts_file="crm_contacts.csv",
            opportunities_file="crm_opportunities.csv"
        ),
        id="crm-analysis-demo",
        task_queue="crm-analysis"
    )

    if result.get("error"):
        print("\n" + "="*60)
        print(f"❌ Error: {result.get('error')}")
        print(f"Reason: {result.get('reason')}")
        print("="*60)
    else:
        print("\n" + "="*60)
        print("✅ Analysis completed successfully!")
        print("="*60)
        print(json.dumps(result, indent=2))
        print("="*60)
    return result

async def run_worker():
    """Run worker in background to execute workflows"""
    client = await Client.connect("localhost:7233")

    worker = Worker(
        client,
        task_queue="crm-analysis",
        workflows=[CRMAnalysisWorkflow],
        activities=[
            analyze_contacts,
            analyze_opportunities,
            validate_analysis,
            combine_analysis
        ]
    )

    print("🔧 Worker started. Listening for workflows...")
    await worker.run()

if __name__ == "__main__":
    # Run worker and workflow in parallel
    async def run_all():
        worker_task = asyncio.create_task(run_worker())
        await asyncio.sleep(2)  # Give worker time to start
        await main()

    asyncio.run(run_all())

