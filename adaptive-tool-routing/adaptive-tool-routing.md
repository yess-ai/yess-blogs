# Adaptive Tool Routing: Dynamic Tool Selection for MCP-Heavy Agents

![Difficulty: Advanced](https://img.shields.io/badge/Difficulty-Advanced-red)
![Time: 10 mins](https://img.shields.io/badge/Time-10%20mins-blue)
![Pattern: Conceptual](https://img.shields.io/badge/Pattern-Conceptual-purple)

<p align="center">
  <img src="images/confused_llm.png" width="100%" alt="Confused LLM" />
</p>

**TL;DR:** As agents accumulate MCP connections, they drown in tool definitions - burning context tokens and confusing themselves about which tools to use. Adaptive Tool Routing (ATR) fixes this by integrating a routing step into the agent's initialization flow, filtering tools based on the user query before they reach the system prompt.
<br clear="all" />

---

## Section I: The Problem  -  Tool Overload in the MCP Era

MCP (Model Context Protocol) is becoming the standard interface between AI agents and external capabilities. Bloomberg, YFinance, trading platforms, risk systems, portfolio managers - everything speaks MCP now. Teams are connecting their agents to every service they might need.

This is great for interoperability. It's terrible for your agent's performance.

### The Pattern We're Seeing

A typical enterprise agent might connect to:

- YFinance MCP (9 tools: stock prices, fundamentals, analyst recommendations, news, technical indicators)
- Bloomberg MCP (12 tools)
- Portfolio Management MCP (8 tools)
- Risk Analytics MCP (10 tools)
- Trading Execution MCP (6 tools)

**Total: 45 tools before the user says hello.**

This creates two catastrophic failure modes:

### 1. Context Explosion

Every tool comes with a schema definition that lives in the system prompt:

| Component | Tokens |
|-----------|--------|
| Average tool definition (name, description, parameters) | 200-300 |
| 5 MCPs × 10 tools each = 50 tools | **10,000-15,000** |
| Your actual system prompt instructions | 2,000-5,000 |
| **Total before conversation starts** | **12,000-20,000** |

You're burning 10-15% of your context window on tools the user probably won't need for this specific query. That's less room for conversation history, retrieved documents, and actual reasoning.

### 2. Tool Selection Degradation

More tools doesn't mean more capable. It means more confused.

Recent research quantifies this problem:

- **LongFuncEval (2025)** found **7-85% accuracy degradation** as tool catalog size increases, with 13-40% drops in multi-turn conversations ([arxiv](https://arxiv.org/abs/2505.10570))
- **Context Rot (Chroma, 2025)** tested 18 LLMs and found performance degrades non-uniformly as context length increases - even for simple tasks ([research.trychroma.com](https://research.trychroma.com/context-rot))
- **"Context Length Alone Hurts" (EMNLP 2025)** showed **13.9-85% performance drops** even with perfect retrieval - the length itself causes degradation ([arxiv](https://arxiv.org/abs/2510.05381))

**Common failure modes with large tool catalogs:**

- **Wrong tool selection:** Agent picks `get_stock_fundamentals` when it needed `get_key_financial_ratios`
- **Tool hallucination:** Agent invents tool names or parameters that don't exist
- **Coordination failures:** Multi-step tasks require tools from different MCPs, agent loses track
- **Analysis paralysis:** Agent wastes tokens reasoning about which tool to use

---

## Section II: The Core Insight

> Giving an agent access to 50 tools when it only needs 3 for the current task is like handing someone a 200-page manual when they asked how to turn on the TV.

Most agentic frameworks follow a standard initialization flow:

1. Connect to MCPs and toolkits
2. List/gather all available tools
3. Flatten tools into a single list
4. Build system prompt with tool definitions
5. Execute with user query

**The ATR intervention point:** Insert a routing step between steps 3 and 4. Before tools are added to the system prompt, analyze the user query and filter to only relevant tools.

**Token math:**

| Approach | Calculation | Tokens |
|----------|-------------|--------|
| Before ATR | 50 tools × 250 tokens | 12,500 |
| After ATR | 5 filtered tools × 250 tokens | 1,250 |
| **Savings** | | **90%** |

---

## Section III: The ATR Architecture

ATR isn't a separate orchestration layer - it's a step integrated into the agent's existing initialization flow.

<div style="display: flex; gap: 20px; flex-wrap: wrap; justify-content: center; margin: 30px 0;">
  <div style="flex: 1; min-width: 300px; max-width: 450px;">
    <h4 style="text-align: center; margin-bottom: 10px;">Standard Agent Initialization (Before ATR)</h4>
    <img src="images/standard-init-flow.svg" alt="Standard Agent Initialization Flow" style="width: 100%;" />
  </div>
  <div style="flex: 1; min-width: 300px; max-width: 450px;">
    <h4 style="text-align: center; margin-bottom: 10px;">Agent Initialization With ATR</h4>
    <img src="images/atr-init-flow.svg" alt="Agent Initialization with ATR Flow" style="width: 100%;" />
  </div>
</div>

### The Integration Point

The key is modifying `determine_tools_for_model()` (or equivalent in your framework) to include a routing step.

**The Pattern:**

1. **Gather phase** - Collect all tools from MCPs, toolkits, and direct tool definitions into a flat list (standard framework behavior)
2. **Route phase** - Pass the user query + full tool list to a routing function that returns only relevant tools
3. **Return phase** - Return the filtered subset instead of the full list

The routing function receives the query and tool definitions (IDs, names, capability tags), analyzes what capabilities are needed, and returns a filtered subset. This filtered list is what gets serialized into the system prompt.

---

## Section IV: The Routing Logic - Intent-Based Tool Selection

The routing function uses a lightweight LLM call to classify which tools are relevant to the user's query.


1. **Input preparation** - Format tools as lightweight summaries: `{name, description}`. Skip parameter schemas to minimize tokens. Truncate long descriptions.

2. **LLM routing call** - Single prompt asking a small model to select relevant tools:
   - The user query
   - Tool summaries (name + truncated description)
   - Instruction to return only tool names, one per line
   - Use a fast/cheap model (e.g., GPT-4o-mini, Claude Haiku)

3. **Filter and return** - Parse the tool names from the response, filter the original tool list to only those names.

**Example prompt structure:**

```
User query: "What is the current price of AAPL?"

Available tools:
- get_current_stock_price: Get the current stock price for a ticker
- get_company_info: Get company information and description
- get_stock_fundamentals: Get fundamental data like market cap...
- get_analyst_recommendations: Get analyst recommendations...
- get_company_news: Get recent news articles for a company
- get_technical_indicators: Get technical indicators like RSI...
- get_historical_stock_prices: Get historical price data...

Select the tools needed for this query. Return only tool names, one per line.
```

**Expected output:**

```
get_current_stock_price
```

**Overhead:** ~100ms, ~200-400 tokens

**Why lightweight summaries work:** The filter model doesn't need parameter schemas to understand capability. `get_current_stock_price: Get the current stock price for a ticker` is enough context to match against "What is the current price of AAPL?"

**Handling multi-step queries:** Even for queries like "Show me Tesla's historical prices and technical indicators", the same pattern works - the filter model simply returns multiple tool names:

```
get_historical_stock_prices
get_technical_indicators
```

The key is conservative selection with overlap tolerance - if the model is unsure between similar tools, it includes both. A `max_tools` cap prevents runaway selection.

### Implementation: Subclassing Your Agent

The cleanest approach is to subclass your framework's agent and override the tool resolution method. Here's how it works with [Agno](https://github.com/agno-agi/agno):

**Step 1: Create a FilteredAgent subclass**

```python
from agno.agent import Agent
from agno.tools.function import Function

class FilteredAgent(Agent):
    """Agent that filters tools based on user input using a small LLM."""

    def __init__(
        self,
        filter_model: str = "gpt-4o-mini",  # Small/fast model for filtering
        filter_enabled: bool = True,
        max_tools: int = 5,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.filter_model_id = filter_model
        self.filter_enabled = filter_enabled
        self.max_tools = max_tools
        self._filter_agent: Optional[Agent] = None
```

**Step 2: Override `_determine_tools_for_model`**

This is the key integration point - intercept tool resolution before tools reach the system prompt:

```python
def _determine_tools_for_model(
    self,
    model: Model,
    processed_tools: List[Union[Toolkit, callable, Function, dict]],
    run_response: RunOutput,
    run_context: RunContext,
    session: AgentSession,
) -> List[Union[Function, dict]]:
    """Override to filter tools before they're sent to the model."""
    
    # 1. Get all functions from parent (flattens Toolkits into Functions)
    all_functions = super()._determine_tools_for_model(
        model, processed_tools, run_response, run_context, session
    )

    if not self.filter_enabled or not all_functions:
        return all_functions

    # 2. Extract user input from the run response
    input_text = self._extract_input_text(run_response)
    if not input_text:
        return all_functions

    # 3. Filter tools using the lightweight LLM
    filtered = self._filter_tools_sync(input_text, all_functions)

    return filtered  # Only filtered tools get added to system prompt
```

**Step 3: Build the routing prompt**

Format tools as lightweight summaries - no parameter schemas needed:

```python
def _build_tools_prompt(self, input_text: str, functions: List[Function]) -> str:
    """Build the prompt for the tool filter agent."""
    tool_descriptions = []
    for f in functions:
        desc = f.description or "No description"
        if len(desc) > 150:  # Truncate long descriptions
            desc = desc[:147] + "..."
        tool_descriptions.append(f"- {f.name}: {desc}")

    tools_list = "\n".join(tool_descriptions)

    return f"""User query: "{input_text}"

Available tools:
{tools_list}

Select the tools needed for this query. Return only tool names, one per line."""
```

**Step 4: Create the filter agent and execute routing**

```python
def _get_filter_agent(self) -> Agent:
    """Lazily create the tool filter agent."""
    if self._filter_agent is None:
        self._filter_agent = Agent(
            model=OpenAIChat(id=self.filter_model_id),
            instructions=[
                "You are a tool selector assistant.",
                "Given a user query and a list of available tools, select ONLY the tools directly relevant to answering the query.",
                "Be conservative - select only tools that will definitely be needed.",
                "Return ONLY the tool names, one per line, no explanations.",
                "If unsure between similar tools, include both.",
            ],
            markdown=False,
        )
    return self._filter_agent

def _filter_tools_sync(self, input_text: str, functions: List[Function]) -> List[Function]:
    """Filter tools using the filter agent."""
    prompt = self._build_tools_prompt(input_text, functions)
    
    filter_agent = self._get_filter_agent()
    response = filter_agent.run(prompt)

    # Parse selected tool names from response
    selected_names = set(
        line.strip().lstrip("- ").strip()
        for line in response.content.strip().split("\n")
        if line.strip()
    )

    # Filter to only valid, selected tools
    all_tool_names = {f.name for f in functions}
    valid_selected = selected_names & all_tool_names

    filtered = [f for f in functions if f.name in valid_selected]
    
    # Apply max_tools limit
    if len(filtered) > self.max_tools:
        filtered = filtered[:self.max_tools]

    return filtered if filtered else functions  # Fallback to all if none selected
```

**Step 5: Use it like a regular agent**

```python
from agno.models.openai import OpenAIChat
from agno.tools.yfinance import YFinanceTools

agent = FilteredAgent(
    model=OpenAIChat(id="gpt-4o"),      # Main model for responses
    filter_model="gpt-4o-mini",          # Small model for tool filtering
    filter_enabled=True,
    max_tools=5,
    tools=[YFinanceTools()],             # 9 YFinance tools
)

# Query runs through filtering automatically
response = agent.run("What is the current price of AAPL?")
# Only get_current_stock_price reaches the system prompt
```

---

## Section V: Advanced Technique - Feedback Loop for Missing Tools

The router won't always get it right on the first try. Complex queries might need tools the router didn't anticipate.

Consider this scenario: A user asks "Get Tesla's stock performance and calculate if it's a good buy based on technicals." The router selects price-fetching tools, the agent retrieves the data, and then realizes it needs technical indicator tools to actually assess the buy signal.

Instead of failing, the agent can signal what's missing. The system catches this signal, re-routes with enriched context (now explicitly asking for "technical indicators"), expands the toolset, and lets the agent continue.

The key insight: the re-routing query isn't just the original user request - it includes what the agent has learned it needs. "Get TSLA performance" might not surface technical indicator tools, but "need technical indicators to assess buy signal" directly matches them.

This creates a self-healing system where incomplete initial routing gets corrected through execution feedback, with appropriate guards to prevent infinite loops.

---

## Section VI: Scaling ATR with RAG-Based Tool Discovery

### The Scaling Challenge

ATR works well with 50 tools. But what about 500? Or 5,000?

Passing hundreds of tool definitions to even a lightweight routing model becomes expensive and slow. The context window fills up, latency increases, and costs multiply.

### The Solution: Treat Tools as Searchable Documents

The same RAG pattern that works for document retrieval works for tool discovery. Instead of searching documents to answer questions, search tool definitions to find capabilities.

**The approach:**

1. **Index tools semantically** - Store tool definitions (name, description, capability tags, and crucially - synthetic example queries) in a vector database
2. **Retrieve candidates** - When a request arrives, embed it and find the top-k most similar tools
3. **Refine with LLM** - Pass only those candidates to the routing model for final selection

This turns a 500-tool problem into a 15-tool problem. The semantic search does the heavy lifting cheaply, and the LLM makes the final call on a manageable set.

**Key insight:** Include synthetic example queries in your tool index. "Is AAPL overbought?" matches poorly against "Calculate RSI and Bollinger Bands" but matches strongly against "Check if a stock is overbought" - a synthetic query you generate for that tool.

### When to Consider This

| Tool Count | Approach |
|------------|----------|
| Under 50 | Standard ATR routing |
| 50-200 | RAG can reduce costs |
| 200+ | RAG becomes essential |

This is an extension of ATR, not a replacement. The core pattern remains the same - you're just adding a retrieval layer before the routing decision.

---

## Section VII: When to Use ATR

### Use ATR When:

| Condition | Why It Helps |
|-----------|--------------|
| **15+ tools configured** | Context savings become significant |
| **Diverse tool domains** | Pricing + Fundamentals + Technicals + News - users rarely need all |
| **Cost/latency sensitive** | Every token saved compounds at scale |
| **Unpredictable user queries** | Can't pre-determine which tools are needed |

### Skip ATR When:

| Condition | Why ATR Is Overkill |
|-----------|---------------------|
| **Under 10 focused tools** | Context overhead is manageable |
| **Homogeneous tasks** | Same tools always needed |
| **Ultra-low latency (<100ms)** | Routing adds 100-300ms overhead |
| **All tools always relevant** | No filtering benefit |

### The Break-Even Calculation

```
Routing overhead:  ~100-300ms + ~500 tokens (routing LLM call)
Context savings:   ~10,000-15,000 tokens (avoided tool definitions)

Break-even at:     ~15-20 tools
Clear win at:      30+ tools
```

---

## Section VIII: Key Takeaways

1. **Tool sprawl kills agent performance**  -  Research shows 7-85% accuracy degradation with large tool catalogs. More tools ≠ more capable.

2. **Integrate routing into agent init**  -  ATR isn't a separate orchestrator. It's a filtering step inside `determine_tools_for_model()` that fits naturally into existing framework patterns.

3. **Keep routing lightweight**  -  A single intent classification call with a small model (~100ms, ~200-400 tokens) handles both simple and multi-step queries effectively.

4. **Build in recovery**  -  Feedback loops let the agent signal missing capabilities and re-route. Don't fail on first miss.

5. **Scale with RAG**  -  When tool counts explode, index them in a vector DB. Semantic search finds candidates, LLM refines.

6. **Framework-friendly**  -  ATR requires minimal changes to existing agentic architectures. Hook into the tool resolution pipeline, filter before building the system prompt.

---

## What's Next

ATR is a pattern, not a library. To implement it:

1. **Identify your framework's tool resolution point**  -  Find where tools get flattened into the system prompt
2. **Add the routing step**  -  Insert query analysis before tools are added
3. **Start simple**  -  Basic intent classification works for most cases
4. **Add feedback loops**  -  Let the agent request more tools when needed
5. **Scale with RAG**  -  Add vector indexing when tool counts grow

The pattern applies whether you're using LangChain, CrewAI, Agno, or building custom agents.

---

## References

- [LongFuncEval: Function Calling in Long Contexts (2025)](https://arxiv.org/abs/2505.10570)  -  Quantifies tool selection degradation
- [Context Rot: How Input Tokens Impact LLM Performance (Chroma, 2025)](https://research.trychroma.com/context-rot)  -  Context length degradation research
- [Context Length Alone Hurts LLM Performance (EMNLP 2025)](https://arxiv.org/abs/2510.05381)  -  Even perfect retrieval can't overcome length penalties
- [MCP Tool Overload (lunar.dev)](https://www.lunar.dev/post/why-is-there-mcp-tool-overload-and-how-to-solve-it-for-your-ai-agents)  -  Practical MCP scaling challenges
- [Tool Filtering for MCP Performance (tetrate.io)](https://tetrate.io/learn/ai/mcp/tool-filtering-performance)  -  MCP optimization strategies
