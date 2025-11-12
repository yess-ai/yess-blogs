# Building Durable Agentic Workflows in Production Without Losing Your Mind

![Difficulty: Intermediate](https://img.shields.io/badge/Difficulty-Intermediate-yellow)
![Time: 45 mins](https://img.shields.io/badge/Time-45%20mins-blue)
![Python](https://img.shields.io/badge/Python-3.8+-green)
![Temporal](https://img.shields.io/badge/Temporal-Required-orange)

**TL;DR:** TBD

---

## **Why Agentic Workflows Fail in Production**

At Yess, we build AI agents that perform actions in your CRM.

A key challenge is understanding each customer's specific CRM structure.Their unique objects, fields, relationships, and business logic - Which we do using agents.


Our CRM agents were a hit from the get go!<br>Then we landed some big clients…


Data volumes exploded. Agentic workflows that took just a few minutes now ran 10, 20, even 45 minutes. More data meant more tool calls - querying CRM APIs, fetching schemas, analyzing records, each one another chance for failure. Each failure meant restarting from scratch, wasting time and money.

>❌ **The Silent Failure**
>
>The workflow completes successfully, but an agent hallucinated something midway through. Everything downstream is poisoned. Restart from scratch.

---

## **What We Needed**

We couldn't keep restarting 45-minute workflows. After testing different approaches, we came up with three requirements that made everything work:

### **1. Durable Execution with Smart Failure Handling**

Infrastructure **will** fail. When it does, minimize lost progress and know when to quit.

**Checkpointing:** Save progress after each step. If something breaks, resume from the last checkpoint instead of restarting from scratch.

**Timeouts & Retries:** Define reasonable completion times and retry limits. When exceeded, fail fast instead of waiting indefinitely.

### **2. Validation Checkpoints (Catch Issues Early)**

An agent finishing isn't enough, we need to verify it did a good job. Validations must be:
- **Fast** - don't slow down the pipeline
- **Early** - catch problems before wasting downstream work
- **Specific** - allow retries on the exact failed step, not the entire workflow
- **Informative** - pass validation failure reasons to retries so agents can fix specific issues

### **3. Stay Optimized**

Minimize time and resource costs wherever possible. Through parallel execution, efficient task sizing, and smart retry strategies.

---

## **The Solution - Task decomposition**

Breaking complex workflows into small steps unlocks all three requirements:
- **Enables durable execution:** Checkpoint after each small step instead of losing hours of work
- **Makes validation practical:** Verify small outputs instead of massive mixed results
- **Reveals optimization:** See which steps are independent and can run in parallel


| Aspect | Before Task Decomposition | After Task Decomposition |
|--------|---------------------------|--------------------------|
| **System Failure Impact** | Lose entire workflow (45 min) | Lose one step (5-10 min) |
| **Validation Failure Impact** | Re-run entire workflow | Re-run only failed step |
| **Validation Scope** | Validate 2000+ lines of mixed output | Validate 200 lines per step |
| **Optimization** | Everything runs sequentially | Independent steps run in parallel |

---

## **Building the Workflow, Step by Step**

This section walks through a simplified version of our CRM Knowledge Extraction Workflow that chains three agents sequentially with validation checkpoints using Temporal.

>ℹ️ About Temporal
>
> [Temporal](https://temporal.io/) is an open-source platform that provides durable execution through event sourcing. Workflows automatically resume from the last completed step after infrastructure failures. It handles retries, timeouts, and state persistence.


---

### **Step 1/5: Define the Workflow Structure**

A Temporal workflow defines your orchestration logic—what steps to run and in what order. Each step is an "activity" that Temporal can checkpoint and retry independently.

<details>
<summary><b>📝 View Workflow Definition Code</b></summary>

```python
from temporalio import workflow
from datetime import timedelta
from temporalio.common import RetryPolicy

@workflow.defn
class KnowledgeBuildingWorkflow:
    """
    Execute agents as temporal activities sequentially with validation checkpoints:
    1. Schema Analyzer Agent - Analyzes CRM schema and data structures
    2. Schema Validation Agent - Validates schema analysis quality
    3. Data Analyzer Agent - Builds analysis based on schema
    4. Data Validation Agent - Validates data analysis quality
    5. Business Summarizer Agent - Creates executive summary
    6. Knowledge Creation - Persists results to database
    """

    @workflow.run
    async def run(self, params: CrmSessionParams):
        # Agent 1: Schema Analyzer
        schema_analyzer_name = "crm-schema-foundation-agent"
        schema_analyzer_session_data = {
            "input": "Analyze CRM schema and data structures",
            "artifacts_mcp_url": f"{params.config['mcp_url']}/artifacts/mcp",
            "crm_mcp_url": f"{params.config['mcp_url']}/crm/mcp",
            "user_id": params.user_id,
            "vendor_id": params.vendor_id,
            "mcp_jwt": params.config["mcp_jwt"],
            "openai_api_key": params.config["openai_api_key"],
            "session_id": workflow.info().workflow_id,
        }

        schema_analysis_result = await workflow.execute_activity(
            CrmKnowledgeActivities.run_crm_agent,
            args=[schema_analyzer_name, schema_analyzer_session_data,
                  params.timeout, params.raise_on_error],
            start_to_close_timeout=timedelta(minutes=15),
            retry_policy=RetryPolicy(maximum_attempts=2)
        )

        # Agent 2: Validate schema analysis
        validator_result = await workflow.execute_activity(
            CrmKnowledgeActivities.run_crm_agent,
            args=["crm-report-validator", {
                "input": f"Validate schema analysis: {schema_analysis_result}",
                "context": {"previous_results": [{"agent_name": schema_analyzer_name,
                                                   "result": schema_analysis_result}]}
            }, params.timeout, params.raise_on_error],
            start_to_close_timeout=timedelta(minutes=15),
            retry_policy=RetryPolicy(maximum_attempts=2)
        )

        # Early termination if validation fails
        validation_passed = validator_result.get("validation_passed", False)
        if not validation_passed:
            return {
                "error": "Schema analysis validation failed",
                "validator_result": validator_result
            }

        # Agent 3: Data Analyzer (receives Agent 1 output as context)
        data_analyzer_session_data = {
            "input": "Build analysis based on schema findings",
            "context": {
                "previous_results": [
                    {"agent_name": schema_analyzer_name, "result": schema_analysis_result}
                ]
            },
        }

        data_result = await workflow.execute_activity(
            CrmKnowledgeActivities.run_crm_agent,
            args=["crm-statistical-analysis-agent", data_analyzer_session_data,
                  params.timeout, params.raise_on_error],
            start_to_close_timeout=timedelta(minutes=15),
            retry_policy=RetryPolicy(maximum_attempts=2)
        )

        # Agent 2: Validate data analysis
        # ... (similar pattern)

        # Agent 3: Business Summarizer (receives context from Agents 1 & 2)
        summary_result = await workflow.execute_activity(
            CrmKnowledgeActivities.run_crm_agent,
            args=["crm-business-summary-agent", {
                "input": "Create business summary",
                "context": {
                    "previous_results": [
                        {"agent_name": schema_analyzer_name, "result": schema_analysis_result},
                        {"agent_name": "crm-statistical-analysis-agent", "result": data_result}
                    ]
                }
            }, params.timeout, params.raise_on_error],
            start_to_close_timeout=timedelta(minutes=12),
            retry_policy=RetryPolicy(maximum_attempts=2)
        )

        # Persist to database
        knowledge_result = await workflow.execute_activity(
            CrmKnowledgeActivities.create_knowledge,
            args=[summary_result, params.user_id, params.vendor_id],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3)
        )

        return knowledge_result
```

</details>

**Key points:**
- Each agent runs as a separate activity with its own checkpoint
- Validation happens between processing steps
- Each step has independent timeout and retry policies

---

### **Step 2/5: Implement Activities**

Activities wrap your actual work (LLM calls, database queries, etc.) in retriable units. When an activity completes, Temporal checkpoints the result.

<details>
<summary><b>📝 View Activity Implementation Code</b></summary>

```python
from temporalio import activity
from eevee import Eevee
from eevee.control.operators.executors import BuildExecutorsParams, ExecutorsOperationContext

@activity.defn
async def run_crm_agent(
    agent_name: str,
    agent_inputs: dict,
    timeout: int = 300,
    raise_on_error: bool = True,
) -> dict:
    """
    Run a Crm agent.

    This is a Temporal Activity (retriable, non-deterministic).
    If this fails due to rate limit or network issue, Temporal
    will automatically retry based on the workflow's RetryPolicy.
    """
    # Build agent executor
    agent_executor = await Eevee.operate(
        context=ExecutorsOperationContext(
            operation=ExecutorsOperationType.BUILD,
            params=BuildExecutorsParams(
                definition_name=agent_name,
                inputs=agent_inputs,
            ),
        )
    )

    # Execute agent (this calls the LLM, uses tools, etc.)
    result = await agent_executor.run(
        stream=False,
        input=agent_inputs["input"]
    )

    return result


@activity.defn
async def create_knowledge(
    summary_data: list[dict],
    user_id: str,
    vendor_id: str
) -> dict:
    """
    Persist analysis results to knowledge database.

    Separate activity with higher retry count (3 vs 2) because
    DB operations have different failure characteristics than LLM calls.
    """
    # Clean output (remove emojis, normalize unicode)
    summary_text = "\n\n".join([
        _remove_emojis(item["result"])
        for item in summary_data
    ])

    cleaned_text = unicodedata.normalize("NFKC", summary_text)
    cleaned_text = (
        cleaned_text
        .replace("-", "-")
        .replace("→", "->")
        # ... more normalization
    )

    # Create knowledge object via Eevee
    knowledge_resource = create_knowledge_object(
        name=f"user-crm-knowledge-{vendor_id}-{user_id}",
        knowledge_content=cleaned_text,
        tags={"vendor_id": vendor_id, "user_id": user_id},
        display_name="User Crm Knowledge",
    )

    # Persist to resource store
    await Eevee.operate(
        ResourcesOperationContext(
            operation=ResourcesOperation.CREATE,
            params=CreateResourceParams(
                resource_type=EeveeResourceType.MEMORY.value,
                resource=knowledge_resource
            ),
        )
    )

    return knowledge_resource
```

</details>

**Key points:**
- Activities are retriable—if they fail, Temporal retries automatically
- Works with any agent framework (we use our own, but LangChain, CrewAI, etc. all work)
- Different activities get different retry policies based on their failure characteristics

---

### **Step 3/5: Configure Timeouts & Retries**

Define reasonable timeouts and retry limits for each activity type. LLM calls need different policies than database operations.

**Example configuration:**

```python
# Agent activities: longer timeouts
start_to_close_timeout=timedelta(minutes=15)
retry_policy=RetryPolicy(maximum_attempts=2)
```

**Why different policies?**
- **LLM calls:** Longer timeouts (analysis takes time), fewer retries (rate limits resolve quickly, hallucinations don't improve with retries)
- **Database calls:** Short timeouts (operations are fast), more retries (failures are usually transient)

One-size-fits-all policies lead to premature timeouts or endless retries on systematic failures. Differentiate based on failure characteristics.

---

### **Step 4/5: Implement Validation**

After each processing step, run a lightweight validator to check output quality. This catches hallucinations and quality issues before they poison downstream work.

<details>
<summary><b>📝 View Validator Implementation</b></summary>

```python
# Validator agent definition (YAML config)
name: 'crm-report-validator'
spec:
  definition:
    name: 'CRM Report Validator'
    model: 'gpt-4o-mini'  # Fast, cheap model for validation
    instructions: |
      You are a quality assurance validator for CRM analysis reports.

      Your task: Validate that the analysis output meets quality standards.

      Validation Criteria:
      1. Completeness: Did the agent analyze the expected scope?
      2. Schema Compliance: Does output match expected structure?
      3. Hallucination Detection: Are there fabricated fields/objects?
      4. Logical Consistency: Do findings make sense given inputs?

      Output Format (JSON):
      {
        "validation_passed": true/false,
        "validation_reason": "Detailed explanation",
        "issues_found": ["issue1", "issue2", ...]
      }

      Examples of validation failures:
      - "Analysis claims 100 objects exist, but only 47 mentioned"
      - "Field 'CustomField__c' doesn't exist in CRM standard objects"
      - "Report says 'no data found' but also shows statistics"

# Validation checkpoint in workflow
validation_result = await workflow.execute_activity(
    run_crm_agent,
    args=["crm-report-validator", {
        "input": f"Validate schema analysis:\n\n{schema_analysis_result}",
        "context": {"previous_results": [schema_analysis_result]}
    }],
    start_to_close_timeout=timedelta(minutes=15),
    retry_policy=RetryPolicy(maximum_attempts=2)
)

# Parse validation result
validation_passed = validation_result.get("validation_passed", False)
if not validation_passed:
    logging.error(f"Validation failed: {validation_result['validation_reason']}")
    return {
        "error": "Schema analysis validation failed",
        "details": validation_result
    }
```

</details>

**Why this matters:**
- Validators use fast, cheap models to check expensive processing outputs
- Catching failures early prevents wasting downstream compute
- Failed validations can trigger targeted retries with specific failure reasons

**When validation fails:**
1. Log the specific issue
2. Either terminate the workflow or retry the failed step with the failure reason as additional context
3. Don't continue processing garbage

---

### **Step 5/5: Monitor with Temporal UI**

Temporal's Web UI shows you everything: workflow history, current state, failures, retries, and full input/output for every activity. All workflow information in one place instead of digging through logs across multiple services.

---

## **Key Takeaways**

**Task decomposition is the foundation.** Breaking workflows into small steps enabled everything: checkpointing (resume, don't restart), validation (catch issues early), and optimization (parallel execution where possible).

**Temporal handles infrastructure, you handle business logic.** Durable execution solves crashes and network failures. Validation gates catch hallucinations and quality issues. You need both.

**Different activities need different policies.** LLM calls need longer timeouts and fewer retries. Database calls need shorter timeouts and more retries. One-size-fits-all policies waste money.

**Use this approach when:**
- Workflows run longer than 10 minutes
- Steps depend on each other
- Failures are expensive (time, compute, or both)
- You need production reliability

---

## **Final Thoughts**

Production-ready agentic workflows aren't about better prompts or bigger models. They're about infrastructure: checkpointing so failures don't mean restarts, validation so hallucinations don't poison outputs, and smart retry policies so you don't waste money.

Temporal handles the hard infrastructure problems (state persistence, automatic recovery, observability). You handle the business logic (validation, task decomposition, domain-specific policies).

The combination works.

---

**Code:** [github.com/yess-ai/yess-agent](https://github.com/yess-ai/yess-agent/tree/main/core/services/agent_api/temporal)

**Tags:** `#Temporal` `#Agentic` `#LLM` `#Production` `#Workflows`

