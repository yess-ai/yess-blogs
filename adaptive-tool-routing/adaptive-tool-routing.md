# Adaptive Tool Routing: Solving Tool Overload in the MCP Era

<p align="center">
  <img src="images/confused_llm.png" width="100%" alt="Confused LLM" />
</p>

**TL;DR:** More MCP tools = worse agent performance. Adaptive Tool Routing (ATR) filters tools per query before they hit the system prompt. We open-sourced it - check out [`adaptive-tools`](https://github.com/yess-ai/atr).

## Your Agent Has Too Many Tools

MCP is the standard interface between AI agents and external capabilities. Bloomberg, YFinance, trading platforms, risk systems, portfolio managers - everything speaks MCP now. Teams are racing to connect their agents to every service they might need.

Great for interoperability. Terrible for performance.

A typical enterprise agent might connect to 5 MCP servers - YFinance, Bloomberg, Portfolio Management, Risk Analytics, Trading Execution - totaling **45+ tools before the user says hello.**

This creates two failure modes:

**Context explosion** - Every tool definition lives in the system prompt. At ~250 tokens per tool, 50 tools burn 12,000-15,000 tokens before a single message is exchanged. That's 10-15% of your context window gone - less room for conversation history, retrieved documents, and actual reasoning.

**Tool selection degradation** - More tools doesn't mean more capable. It means more confused. Research backs this up:

- [LongFuncEval (2025)](https://arxiv.org/abs/2505.10570) found **7-85% accuracy degradation** as tool catalog size increases
- [Context Rot (Chroma, 2025)](https://research.trychroma.com/context-rot) showed performance degrades non-uniformly as context grows - even for simple tasks
- [EMNLP 2025](https://arxiv.org/abs/2510.05381) demonstrated **13.9-85% performance drops** even with perfect retrieval - length itself causes degradation

The result: wrong tool selection, hallucinated tool names, coordination failures across multi-step tasks, and wasted tokens reasoning about which tool to use.

## What If Your Agent Only Saw What It Needed?

> Giving an agent access to 50 tools when it only needs 3 is like handing someone a 200-page manual when they asked how to turn on the TV.

The fix is simple in concept: **filter tools per query before they reach the system prompt.**

Adaptive Tool Routing (ATR) is a lightweight routing step injected into the agent's existing initialization flow. Before the agent builds its system prompt, ATR analyzes the user's query and selects only the tools that are actually relevant.

The result:

| | Tools in prompt | Token cost |
|---|---|---|
| **Before ATR** | 50 | ~12,500 |
| **After ATR** | 5 | ~1,250 |
| **Savings** | 90% fewer tools | **~90% token reduction** |

Fewer tools in context means better tool selection, lower latency, reduced cost, and more room for what actually matters - the conversation and the reasoning.

We packaged this pattern into [`adaptive-tools`](https://github.com/yess-ai/atr) - an open-source Python library with zero core dependencies, pluggable LLM providers, and adapters for LangGraph, Agno, OpenAI Agents SDK, and raw MCP. Drop it into your existing stack, no rewrites needed.

## Under the Hood: How ATR Routes Tools

ATR isn't a separate orchestration layer - it's a lightweight routing step that ensures your agent only sees the tools relevant to each query. How it plugs in depends on your framework, but the pattern is the same everywhere - route first, then act.

<table>
  <tr>
    <td align="center"><b>Standard Flow</b></td>
    <td align="center"><b>Flow With ATR</b></td>
  </tr>
  <tr>
    <td><img src="images/standard-init-flow.svg" alt="Standard Agent Flow" width="360" /></td>
    <td><img src="images/atr-init-flow.svg" alt="Flow with ATR" width="360" /></td>
  </tr>
</table>

The architecture has three phases, all happening before the agent is created:

**Gather** - All tools from connected MCPs and toolkits are collected into a flat list - the same collection step you'd normally do before passing tools to your agent. Nothing changes here.

**Route** - This is where ATR steps in. A lightweight LLM call (fast/cheap model like GPT-4o-mini or Claude Haiku) receives the user query alongside compact tool summaries - just names and descriptions, no parameter schemas. It returns the names of the tools relevant to the query. The overhead is minimal: ~100ms and ~200-400 tokens.

**Filter** - The original tool list is filtered down to only the tools the routing model selected. This filtered subset is what gets passed to the agent at initialization. The agent never sees the tools it doesn't need.

The routing model uses conservative selection with overlap tolerance - when it's unsure between similar tools, it includes both. A configurable max-tools cap prevents runaway selection. For multi-step queries ("Show me Tesla's historical prices and technical indicators"), the router simply returns multiple relevant tools.

The key insight: the routing model doesn't need full parameter schemas to understand tool capabilities. A name and a one-line description is enough to match intent to capability.

**Want to try it?** Check out the repo: [`adaptive-tools`](https://github.com/yess-ai/atr)
