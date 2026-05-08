---
name: session-index
description: Search, analyze, and synthesize across all your Claude Code sessions. Ask "what did I try last time?" and get answers with resume links.
license: MIT
compatibility: Requires Python 3.11+ and Claude Code
metadata:
  authors:
    - Lee Fuhr
    - Syrunekai
  version: "0.4.0"
  fork-of: lee-fuhr/claude-session-index
  tags:
    - session-search
    - session-history
    - analytics
    - memory
    - productivity
---

# Session index skill

You have access to a session index — a SQLite database with FTS5 full-text search across all Claude Code sessions. Use it whenever the user asks about past sessions, previous conversations, or wants to know what they've tried before.

**The user's interface is this conversation.** They ask naturally ("Didn't we discuss browser control recently?"), you translate to CLI commands, and present results conversationally. They should never need to know the CLI syntax.

## How to handle session queries

### 1. Extract keywords from the question

The user says: "Didn't we discuss browser control recently?"
You search: `sessions "browser control"`

The user says: "What approaches have I tried for form automation?"
You search: `sessions "form automation"`

The user says: "How much time did I spend on Acme this week?"
You run: `sessions analytics --client "Acme" --week`

### 2. Run the right command via Bash

**Search** — find sessions by topic:
```bash
sessions "relevant keywords"
sessions "relevant keywords" --context    # includes conversation excerpts
```

**Context** — read the actual conversation from a session:
```bash
sessions context <session_id> "search term"   # exchanges matching a term
sessions context <session_id>                 # all exchanges
```

**Analytics** — effort, time, tool usage:
```bash
sessions analytics                    # overall
sessions analytics --client "Acme"    # per client
sessions analytics --week             # this week
sessions analytics --month            # this month
```

**Filter** — find sessions by metadata:
```bash
sessions find --client "Acme"              # by client
sessions find --tool Task --week           # by tool + date
sessions find --project myapp              # by project
sessions recent 20                         # last N sessions
```

### 3. For synthesis ("what worked?", "what have I tried?")

This is the most valuable capability. When the user asks a question that spans multiple sessions:

1. Search: `sessions "topic" -n 10`
2. For the top 3-5 results, extract context: `sessions context <id> "topic" -n 3`
3. Spawn a Task with `model="haiku"` to synthesize:
   - What approaches were tried?
   - What worked / what failed?
   - Recurring patterns?
   - Current state?
4. Present the synthesis conversationally with `claude --resume <id>` links for each source session

This uses an in-session Haiku subagent — no external API key needed.

### 4. Fallback — extracting full message content

`sessions context <id>` defaults are tuned for quick scanning: only the **first 10 exchanges** are shown, each message **truncated at ~1000 chars**. When the user asks for the *contents* of a past message — long structured assistant outputs (memory dumps, briefs, self-summaries, full code), or content that lives past exchange #10 — those defaults will hide what they actually want.

**Reach for `--full` first.** It removes both limits at once.

#### Standard fallback pattern

```bash
sessions context <session_id> --full
```

Dumps every exchange in the session, untruncated, in the same bordered display as `sessions context` — assistant text complete, tool calls summarized as one-liners (`[Read: path]`, `[Bash: cmd]`, `[Task: "desc" → agent]`).

#### Filter by topic when the session is large

```bash
sessions context <session_id> --full "topic keywords"
```

Returns only exchanges where the user message or assistant message matches the filter — still untruncated. Use this when the user is asking about a specific subject within a long session.

#### Look only at the end of a long session

```bash
sessions context <session_id> --full --tail 20
```

Last 20 exchanges, untruncated. Useful when the user wants "what did we finish with?" rather than the whole conversation.

#### Look at a specific count from the start

```bash
sessions context <session_id> --full -n 30
```

First 30 exchanges, untruncated. `-n` and `--tail` are mutually exclusive.

**Zero-touch.** All `sessions context` invocations read JSONL only — they never modify the source session, never update timestamps, never write back. Use freely.

### 5. Present results conversationally

Don't dump raw CLI output. Summarize:
- "You discussed browser control in 3 sessions last week..."
- "The main approach that worked was..."
- Include `claude --resume <session_id>` links so they can jump back in
- If context is relevant, quote key exchanges

## Installation

```bash
uv tool install git+https://github.com/Syrunekai/claude-session-index
sessions install-skill            # copies this file to ~/.claude/skills/
sessions configure-permissions    # allows DB writes inside Claude sandbox
```

First run of any command auto-indexes all existing sessions.

## Data location

- **Database:** `$XDG_CACHE_HOME/claude-session-index/sessions.db` (default `~/.cache/...`)
- **Config:** `$XDG_CONFIG_HOME/claude-session-index/config.toml` (default `~/.config/...`)
- **Topics:** `~/.claude/session-topics/` (Claude's namespace, not ours)
