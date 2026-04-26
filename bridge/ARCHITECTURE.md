# Bridge Architecture - Not Reinventing the Wheel

## Philosophy: Open Bridge

We are **NOT** reinventing the wheel. We are a **thin bridge** that connects the UI to the core Hermes engine.

## What We Use From Core

### 1. AIAgent (run_agent.py)
- **Core class**: `from run_agent import AIAgent`
- **What it does**: Handles all agent logic, tool execution, LLM calls, memory
- **We use it**: Create instances, call `run_conversation()`, wire callbacks

### 2. SessionDB (hermes_state.py)
- **Core class**: `from hermes_state import SessionDB`
- **What it does**: Persistent conversation storage, session management
- **We use it**: Load history, save messages, manage sessions

### 3. Agent Caching Pattern (gateway/run.py:9790-9850)
- **Core pattern**: Cache `(agent, signature)` tuples per session
- **Why**: Preserves prompt caching, avoids rebuilding system prompt every turn
- **We use it**: Exact same pattern in `agent_pool.py`

## What We DON'T Use

### GatewayRunner (gateway/run.py)
- **What it is**: Messaging platform gateway (Telegram, Discord, WhatsApp)
- **Why we don't use it**: 
  - Designed for long-running platform adapters
  - Handles platform-specific auth, delivery, voice channels
  - We're HTTP/SSE, not a messaging platform
- **What we do instead**: Use the same **core components** it uses (AIAgent, SessionDB)

## Bridge Responsibilities

### What We Do
1. **HTTP/SSE Server** - FastAPI endpoints for UI
2. **Event Streaming** - SSE for real-time agent output
3. **Callback Wiring** - Connect agent callbacks to SSE streams
4. **Profile Management** - Switch between user profiles
5. **Model Selection** - UI for choosing models/providers

### What We DON'T Do (Core Does It)
1. ❌ Agent logic - `AIAgent` handles this
2. ❌ Tool execution - `AIAgent` handles this
3. ❌ Memory management - `AIAgent` + `SessionDB` handle this
4. ❌ LLM API calls - `AIAgent` handles this
5. ❌ Context compression - `AIAgent` handles this

## Code Flow

```
UI (Next.js)
    ↓ HTTP POST /chat
Bridge (FastAPI)
    ↓ get_agent(session_id)
agent_pool.py
    ↓ AIAgent() or cached
Core (run_agent.py)
    ↓ run_conversation()
    ↓ tool execution
    ↓ LLM calls
    ↓ callbacks
    ↑ response
Bridge
    ↑ SSE stream
UI
```

## Key Insight

The Gateway (gateway/run.py) is **one way** to use the core components.
The Bridge (bridge/) is **another way** to use the same core components.

Both use:
- `AIAgent` for agent logic
- `SessionDB` for persistence
- Same caching pattern
- Same callback system

But:
- Gateway = Messaging platforms (Telegram, Discord)
- Bridge = HTTP/SSE for web UI

## References

- Core agent: `hermes-agent/run_agent.py`
- Core session: `hermes-agent/hermes_state.py`
- Gateway pattern: `hermes-agent/gateway/run.py:9790-9850`
- Bridge implementation: `hermes/bridge/Chat/agent_pool.py`

## Summary

✅ **We use the wheel** (AIAgent, SessionDB, caching pattern)
❌ **We don't reinvent the wheel** (no custom agent logic)
✅ **We're a bridge** (HTTP/SSE to UI, not a messaging gateway)
