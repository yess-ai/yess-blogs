from temporalio import activity
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from pydantic import BaseModel
import csv
import json
import os

# Define Pydantic models for structured outputs
class TopCompany(BaseModel):
    name: str
    count: int

class ContactAnalysis(BaseModel):
    total_contacts: int
    unique_companies: int
    top_company: TopCompany
    companies_distribution: dict[str, int]
    unique_titles: int

class OpportunityAnalysis(BaseModel):
    total_opportunities: int
    total_pipeline_value: float
    won_value: float
    stages_breakdown: dict[str, int]
    win_rate: float

class ValidationResult(BaseModel):
    passed: bool
    reason: str

@activity.defn
async def analyze_contacts(file_path: str) -> dict:
    """Analyze CRM contacts using Agno AI agent"""
    activity.logger.info(f"Analyzing contacts from {file_path}")

    # Load CSV data
    with open(file_path) as f:
        contacts = list(csv.DictReader(f))

    # Compute unique_titles deterministically from data (avoid AI counting errors)
    unique_titles = len(set(row.get("title", "") for row in contacts if row.get("title")))

    # Create Agno agent with structured output
    agent = Agent(
        model=OpenAIChat(id="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY")),
        description="You are a CRM data analyst. Analyze contact data and extract key insights.",
        output_schema=ContactAnalysis,
        structured_outputs=True
    )

    # Build prompt with data
    data_str = json.dumps(contacts, indent=2)
    prompt = f"""Analyze this CRM contacts data:

{data_str}

Extract:
- total_contacts: total number of contacts (count all rows)
- unique_companies: number of unique companies (count distinct company values)
- top_company: company with most contacts (name and count)
- companies_distribution: all companies with their contact counts (dict of company_name: count)
- unique_titles: number of unique job titles (count distinct title values - be careful to count each unique title exactly once)

IMPORTANT: Count unique_titles by examining each distinct title value in the data. Do not skip any titles."""

    # Run agent - returns Pydantic model
    response = agent.run(prompt)

    # Convert Pydantic model to dict
    result = response.content.model_dump()

    # Override unique_titles with deterministic computation to ensure accuracy
    result["unique_titles"] = unique_titles

    return result

@activity.defn
async def analyze_opportunities(file_path: str) -> dict:
    """Analyze CRM opportunities using Agno AI agent"""
    activity.logger.info(f"Analyzing opportunities from {file_path}")

    # Load CSV data
    with open(file_path) as f:
        opps = list(csv.DictReader(f))

    # Create Agno agent with structured output
    agent = Agent(
        model=OpenAIChat(id="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY")),
        description="You are a sales pipeline analyst. Analyze opportunity data and extract revenue insights.",
        output_schema=OpportunityAnalysis,
        structured_outputs=True
    )

    # Build prompt with data
    data_str = json.dumps(opps, indent=2)
    prompt = f"""Analyze this CRM opportunities data:

{data_str}

Extract:
- total_opportunities: total number of opportunities
- total_pipeline_value: sum of all amounts
- won_value: sum of amounts where stage is "Closed Won"
- stages_breakdown: all stages with their opportunity counts
- win_rate: won_value / total_pipeline_value (between 0 and 1)"""

    # Run agent - returns Pydantic model
    response = agent.run(prompt)

    # Convert Pydantic model to dict
    return response.content.model_dump()

def deterministic_validate(analysis_type: str, analysis: dict, schema: dict, source_data: list = None) -> dict:
    """Fast deterministic validation - check fields, types, and ranges"""

    # Check for missing required fields
    missing = [f for f in schema["required_fields"] if f not in analysis]
    if missing:
        return {"passed": False, "reason": f"Missing fields: {', '.join(missing)}"}

    # Check for negative values
    for key, value in analysis.items():
        if isinstance(value, (int, float)) and "rate" not in key.lower():
            if value < 0:
                return {"passed": False, "reason": f"Negative value for {key}: {value}"}

    # Check rate/percentage fields are between 0 and 1
    for key, value in analysis.items():
        if isinstance(value, (int, float)) and "rate" in key.lower():
            if not (0 <= value <= 1):
                return {"passed": False, "reason": f"Invalid rate {key}: {value}"}

    # Logical consistency checks
    if analysis_type == "contacts":
        if analysis.get("total_contacts", 0) < analysis.get("unique_companies", 0):
            return {"passed": False, "reason": "total_contacts < unique_companies"}

        # Cross-reference with actual data if available
        if source_data:
            actual_total = len(source_data)
            actual_unique_companies = len(set(row.get("company", "") for row in source_data if row.get("company")))
            actual_unique_titles = len(set(row.get("title", "") for row in source_data if row.get("title")))

            if analysis.get("total_contacts") != actual_total:
                return {"passed": False, "reason": f"total_contacts mismatch: reported {analysis.get('total_contacts')}, actual {actual_total}"}

            if analysis.get("unique_companies") != actual_unique_companies:
                return {"passed": False, "reason": f"unique_companies mismatch: reported {analysis.get('unique_companies')}, actual {actual_unique_companies}"}

            if analysis.get("unique_titles") != actual_unique_titles:
                return {"passed": False, "reason": f"unique_titles mismatch: reported {analysis.get('unique_titles')}, actual {actual_unique_titles}"}

            # Verify companies_distribution sums to total_contacts
            dist_sum = sum(analysis.get("companies_distribution", {}).values())
            if dist_sum != actual_total:
                return {"passed": False, "reason": f"companies_distribution sum ({dist_sum}) doesn't match total_contacts ({actual_total})"}
    elif analysis_type == "opportunities":
        if analysis.get("won_value", 0) > analysis.get("total_pipeline_value", 0):
            return {"passed": False, "reason": "won_value > total_pipeline_value"}

    return {"passed": True, "reason": "Deterministic checks passed"}

@activity.defn
async def validate_analysis(analysis_type: str, analysis: dict, source_file: str = None) -> dict:
    """Hybrid validation: fast deterministic checks, then AI semantic analysis"""
    activity.logger.info(f"Validating {analysis_type} analysis")

    # Define expected schema
    if analysis_type == "contacts":
        schema = {
            "required_fields": ["total_contacts", "unique_companies", "top_company", "companies_distribution", "unique_titles"]
        }
    else:
        schema = {
            "required_fields": ["total_opportunities", "total_pipeline_value", "won_value", "stages_breakdown", "win_rate"]
        }

    # Load source data for cross-validation
    source_data = None
    if source_file and os.path.exists(source_file):
        with open(source_file) as f:
            source_data = list(csv.DictReader(f))

    # STEP 1: Fast deterministic validation (catches 90% of issues)
    deterministic_result = deterministic_validate(analysis_type, analysis, schema, source_data)
    if not deterministic_result["passed"]:
        return deterministic_result  # Fail fast, save AI costs

    # For contacts, deterministic validation with source data cross-reference is sufficient
    # Skip AI validation since we've already verified all counts against source data
    if analysis_type == "contacts":
        return {"passed": True, "reason": "Deterministic validation passed - all counts verified against source data"}

    # STEP 2: AI semantic validation (hallucination detection, deeper analysis)
    # Only needed for opportunities to verify win_rate calculation
    agent = Agent(
        model=OpenAIChat(id="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY")),
        description="You are a data quality validator. Check for semantic issues and hallucinations.",
        output_schema=ValidationResult,
        structured_outputs=True
    )

    # Build validation prompt with type-specific context
    if analysis_type == "opportunities":
        prompt = f"""Validate this {analysis_type} analysis for semantic correctness.

Data: {json.dumps(analysis, indent=2)}

IMPORTANT CONTEXT:
- win_rate is calculated as VALUE-BASED, not count-based: win_rate = won_value / total_pipeline_value
- This means win_rate represents the percentage of revenue won, not the percentage of opportunities won
- For example: if won_value=$80,000 and total_pipeline_value=$130,000, then win_rate=0.6154 (61.54%)
- Do NOT expect win_rate to equal (number of Closed Won opportunities) / (total opportunities)

Check for:
1. Hallucinated or nonsensical values (e.g., impossible company names, weird numbers)
2. Semantic inconsistencies (e.g., distributions don't match totals)
3. win_rate should equal won_value / total_pipeline_value (value-based calculation)

The data already passed basic checks (fields exist, no negatives, rates are 0-1).
Focus ONLY on semantic/logical issues an LLM might introduce.

Return passed=true if semantically valid, passed=false if you detect hallucinations."""
    else:
        prompt = f"""Validate this {analysis_type} analysis for semantic correctness.

Data: {json.dumps(analysis, indent=2)}

IMPORTANT CONTEXT:
- The data has already passed deterministic validation that cross-referenced the source data
- If total_contacts matches the sum of companies_distribution values, that is CORRECT (e.g., 3+1+1=5 is valid)
- If unique_titles equals total_contacts, that is VALID (it means each contact has a different title)
- unique_titles can be equal to or less than total_contacts (multiple contacts can share the same title)
- The deterministic validation already verified counts match the source data

Check for:
1. Hallucinated or nonsensical values (e.g., impossible company names, weird numbers)
2. Semantic inconsistencies that weren't caught by deterministic checks

The data already passed basic checks (fields exist, no negatives, rates are 0-1, counts verified against source).
Focus ONLY on semantic/logical issues an LLM might introduce that deterministic checks can't catch.

Return passed=true if semantically valid, passed=false if you detect hallucinations."""

    response = agent.run(prompt)
    return response.content.model_dump()

@activity.defn
async def combine_analysis(contact_analysis: dict, opp_analysis: dict) -> dict:
    """Combine analyses into final CRM analysis report"""
    activity.logger.info("Combining analyses into final report")

    return {
        "crm_summary": {
            "contacts": contact_analysis,
            "opportunities": opp_analysis
        },
        "key_insights": [
            f"Managing {contact_analysis['total_contacts']} contacts across {contact_analysis['unique_companies']} companies",
            f"Top customer: {contact_analysis['top_company']['name']} ({contact_analysis['top_company']['count']} contacts)",
            f"Pipeline value: ${opp_analysis['total_pipeline_value']:,.0f} across {opp_analysis['total_opportunities']} opportunities",
            f"Closed revenue: ${opp_analysis['won_value']:,.0f} (Win rate: {opp_analysis['win_rate']:.1%})"
        ],
        "status": "analysis_completed_successfully"
    }

