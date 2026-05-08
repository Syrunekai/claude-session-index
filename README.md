# Claude session index

**Every Claude Code session you've ever had, searchable in under a second.**

You've built things across hundreds of sessions. Solved problems, hit walls, found workarounds. But sessions disappear into `~/.claude/projects/` as unlabeled JSONL files — thousands of them, unsearchable, forgettable. This tool indexes them all into a fast SQLite database with full-text search, conversation retrieval, analytics, and cross-session synthesis.

Ask "what did I try last time I debugged webhooks?" and get an actual answer.

---

## Quick start

This project installs via [**uv**](https://docs.astral.sh/uv/) — Astral's Rust-based Python package manager. If you don't have it yet:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

(Windows users: see the [uv installation docs](https://docs.astral.sh/uv/getting-started/installation/) for the PowerShell command.)

Then:

```bash
uv tool install git+https://github.com/Syrunekai/claude-session-index
sessions install-skill            # copy SKILL.md into ~/.claude/skills/
sessions configure-permissions    # allow DB writes inside Claude sandbox
```

That's it. The first time you ask a question, it auto-indexes all your existing sessions. After that, queries return in milliseconds.

### Updating

To pull the latest commits into your install:

```bash
uv tool install --reinstall git+https://github.com/Syrunekai/claude-session-index
sessions install-skill --force
```

The first command rebuilds the `sessions` binary from the latest source. The second overwrites your installed `~/.claude/skills/session-index/SKILL.md` with the updated copy from the package — important after any change to skill guidance, since the install-time copy is static (unless you originally installed it with `--link`).

If you originally installed the skill via `npx skills add ... --copy`, re-run that command with `--force` instead of `sessions install-skill --force`.

### Skill install — alternative via npx

If you'd rather use the [skills marketplace](https://github.com/anthropics/claude-skills) and its supply-chain risk checker, you can install the skill via npx instead:

```bash
npx skills add Syrunekai/claude-session-index --copy
```

The `--copy` flag is recommended — it creates a static local file rather than symlinking back to the upstream repo, which closes a small supply-chain attack vector.

Either method (`sessions install-skill` or `npx skills add`) results in the same SKILL.md landing in `~/.claude/skills/session-index/`.

---

## How it works (for you)

The interface is your Claude Code conversation. You ask questions naturally, Claude translates them into searches, and gives you conversational answers.

### "Didn't we discuss browser control recently?"

Claude searches your sessions, finds the matches, and tells you:

> You discussed browser control in 3 sessions last week. The most relevant was on Jan 18 where you figured out that synthetic MouseEvent dispatch bypasses the framework's event handling. The key insight was that the submit button was a `<div>`, not a `<button>`.
>
> → `claude --resume a5b111c6-dca0-4ee9-b237-74b75baf13cd`

### "What have I tried for form automation? What actually worked?"

Claude searches across sessions, extracts the relevant conversations, and synthesizes:

> **Approaches tried:** element.click() → failed (framework intercepts). Coordinate-based clicking → failed (dynamic elements). Synthetic MouseEvent dispatch → success.
>
> **What worked:** Native OS-level clicking for all button interaction. Persistent browser profiles for session continuity.
>
> **What failed:** All JavaScript-based clicking — the framework intercepts and blocks it.
>
> Sources: 5 sessions spanning Jan 10–Feb 1
> → `claude --resume abc123...`
> → `claude --resume def456...`

### "How did I spend my week?"

> 89 sessions this week. 302 hours total.
>
> Windmill Labs: 2 sessions, 47h
> GridSync: 2 sessions, 17h
> NovaTech: 4 sessions, 7h
>
> Top tools: Bash (3,214), Read (2,126), Edit (1,718)
> Task agent usage up 142% from last week.

Every answer includes `claude --resume` links so you can jump straight back into any session.

---

## What it does under the hood

1. **Indexes** all your Claude Code sessions into SQLite with FTS5 full-text search
2. **Searches** by content, client, project, tool, agent, tag, or date — results in milliseconds
3. **Retrieves context** — actual conversation exchanges (user + assistant), not just metadata
4. **Analyzes** your usage — time per client, tool trends, session frequency, topic patterns
5. **Synthesizes** across sessions — "What approaches have I tried for X?" via in-session Haiku subagent (no extra API cost)
6. **Tracks topics** live during sessions via Claude Code hooks

---

## The CLI

The skill handles the conversational interface. But if you want direct access from a terminal, everything goes through `sessions`:

```bash
# Search — just type what you're looking for
sessions "webhook debugging"
sessions "webhook" --context              # with conversation excerpts

# Browse a conversation
sessions context <id> "term"              # exchanges matching a term (first 10, truncated at 1000 chars)
sessions context <id>                     # first 10 exchanges, truncated at 1000 chars
sessions context <id> --full              # all exchanges, untruncated (zero-touch read)
sessions context <id> --full --tail 20    # last 20 exchanges, untruncated
sessions context <id> --full -n 30        # first 30 exchanges, untruncated

# Analytics
sessions analytics                        # overall stats
sessions analytics --client "Acme"        # per-client
sessions analytics --week                 # this week
sessions analytics --month                # this month

# Synthesis (requires anthropic package + API key for standalone use)
sessions synthesize "topic"               # cross-session intelligence

# Browse & filter
sessions recent 20                        # last N sessions
sessions find --client "Acme"             # filter by client
sessions find --tool Task --week          # filter by tool + date
sessions topics <session_id>              # topic timeline
sessions tools                            # top tools across sessions
sessions stats                            # database overview

# Indexing
sessions index                            # index new/modified sessions
sessions index --backfill                 # re-index everything

# Setup / admin
sessions install-skill                    # copy SKILL.md to ~/.claude/skills/
sessions install-skill --link             # symlink instead (live updates)
sessions configure-permissions            # add DB write rule to ~/.claude/settings.json
sessions configure-permissions --dry-run  # preview the change
sessions configure-permissions --remove   # back out cleanly
sessions init-config                      # write a default config.toml
sessions init-config --force              # overwrite existing
```

Plain text defaults to search — `sessions "webhook debugging"` just works, no subcommand needed.

### Search tips

The search uses SQLite FTS5 — fast, but it expects keyword-style queries, not natural language. For direct CLI use:

- **Use keywords, not sentences.** `sessions "webhook signature verification"` works. `sessions "what did I figure out about webhook signatures"` requires every word — including `what`, `did`, `I`, `figure` — to appear in the indexed text, so it usually returns nothing.
- **Stop words count.** Common filler words (`the`, `of`, `and`, `what`, `did`, `is`) are not filtered by the index — they become required terms. Drop them from your queries.
- **Quote multi-word phrases** for exact sequences: `sessions '"silent failure"'` matches the literal phrase, not just both words anywhere.
- **In Claude Code conversation, the skill handles all of this for you.** The tips above only matter when typing `sessions` directly into a terminal — Claude extracts keywords from your natural-language question before invoking the CLI.

### CLI output

Search results look like this:

```
🔍 3 results for "silent failure"

  ◆ a5b111c6 · (unnamed)
    2026-01-18 · my-project · 51 exchanges
    "...This was a silent failure - appeared to work but didn't..."
    → claude --resume a5b111c6-dca0-4ee9-b237-74b75baf13cd

  ◆ 7b22239e · (unnamed)
    2026-01-18 · my-project · 50 exchanges
    "...The phrase 'silent failure, which is the ultimate sin'
    captures the core requirement: systems must fail loudly..."
    → claude --resume 7b22239e-9f90-466f-ad92-849840b2a6fd
```

Conversation context shows the actual chat:

```
╭─── Build automation debugging ─────────────────
│ 2026-01-20 · my-project · 96 exchanges · 7min
│ → claude --resume a5b111c6-dca0-4ee9-b237-74b75baf13cd
╰────────────────────────────────────────────────

  ┌─ Jan 20, 19:14 ──────────────────────────────
  │
  │  🧑 Breakthrough session. Successfully submitted forms #32 and #33
  │     using synthetic MouseEvent dispatch to bypass the framework's
  │     event handling.
  │
  │  🤖 I'll process these findings. Let me search for existing patterns...
  │     [Grep: framework|zone\.js|MouseEvent|click]
  │     [Read: /path/to/automation/docs.md]
  │
  └────────────────────────────────────────────────
```

Tool calls get collapsed into readable one-liners — `[Read: path]`, `[Edit: path]`, `[Bash: command]`, `[Task: "description" → agent]` — so you can follow the conversation without drowning in JSON.

---

## Live topic tracking

Capture what you're working on during sessions via Claude Code hooks. Topics get indexed for search.

Add to `~/.claude/settings.json` (or merge with your existing hooks):

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "session-topic-capture UserPromptSubmit"
          }
        ]
      }
    ],
    "PreCompact": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "session-topic-capture PreCompact"
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "session-topic-capture SessionEnd"
          }
        ]
      }
    ]
  }
}
```

Topics are captured every 10 exchanges, before compaction, and at session end.

### Background indexing (macOS)

Keep the index fresh automatically:

```bash
cp launchagent/com.session-indexer.plist ~/Library/LaunchAgents/
# Edit the plist to point to your Python path
launchctl load ~/Library/LaunchAgents/com.session-indexer.plist
```

Runs `session-index --incremental` every 30 minutes. Only processes new or modified sessions.

---

## Configuration

Works out of the box. Everything is configurable; nothing has to be.

### Priority order

1. CLI flags (`--db-path`)
2. Environment variables (`SESSION_INDEX_DB`, `SESSION_INDEX_PROJECTS`, `SESSION_INDEX_TOPICS`)
3. Config file (`$XDG_CONFIG_HOME/claude-session-index/config.toml`)
4. Sensible defaults

### Default paths (XDG-compliant)

| What | Default location | Notes |
|------|------------------|-------|
| Database | `$XDG_CACHE_HOME/claude-session-index/sessions.db` | regenerable cache; default `~/.cache/...` |
| Config | `$XDG_CONFIG_HOME/claude-session-index/config.toml` | hand-edited; default `~/.config/...` |
| Sessions (read) | `~/.claude/projects/` | Claude Code's location |
| Topics | `~/.claude/session-topics/` | Claude Code's namespace, hooks reference it |

### Bootstrap a config file

```bash
sessions init-config        # writes a documented default at $XDG_CONFIG_HOME/...
sessions init-config --force # overwrite an existing config
```

The generated file is fully commented — every key has a short explanation inline.

A reference is also tracked at the repo root as [`config.example.toml`](config.example.toml). Anything you can put in your local config you can see there.

### Schema versioning

Each config file declares a `schema_version`. If you keep an old config after upgrading, defaults silently fill in any new keys, and a one-time warning at startup tells you the schema has moved on:

```
warning: config schema is v1, latest is v2. Defaults apply for any
missing keys. See config.example.toml.
```

The config keeps working — the warning is informational. Refresh by copying any new keys you want from `config.example.toml`, or run `sessions init-config --force` to rebuild from scratch (you'll lose any custom values).

### Configurable keys

| Key | Purpose |
|-----|---------|
| `projects_dir` | Where Claude Code session JSONL files live |
| `db_path` | SQLite index database location |
| `topics_dir` | Hook-captured topic timeline directory |
| `clients` | Optional. List of client names; sessions whose prompts mention any get auto-tagged |
| `project_names` | Optional. Map raw project directory slugs to friendly display names |

### Migrating from upstream `~/.session-index/`

If you previously installed the upstream tool (`lee-fuhr/claude-session-index`), your old DB and config still sit in `~/.session-index/`. This fork won't touch that directory — it just notices it on startup and tells you once:

```
notice: legacy ~/.session-index/ paths detected:
  - /home/you/.session-index/sessions.db
This fork uses XDG-compliant paths. A fresh index will be built at
/home/you/.cache/claude-session-index/sessions.db.
After verifying things work, remove the legacy directory: rm -rf /home/you/.session-index
```

Re-indexing at the new location is fast — purely local, no API calls, runs once.

---

## Security considerations

The SQLite index database is plaintext and contains the full content of your Claude Code sessions — your prompts, Claude's responses, file paths, code, and anything else you've ever discussed. Treat it as you would any private notebook.

**Defaults this fork applies for you:**

- DB and config directories created with mode `0o700` (owner-only)
- DB and config files created with mode `0o600` (owner-only)
- Permissions are *self-healing* — if you upgraded from upstream and your old files have looser permissions, they get tightened on the next CLI invocation

> **Windows note:** POSIX permission modes (`0o700` / `0o600`) are POSIX-only.
> Python's `os.chmod` on Windows only toggles the read-only flag — it does
> *not* enforce owner-only access, because Windows uses NTFS ACLs instead of
> POSIX modes. The owner-only defaults above apply on Linux and macOS;
> Windows users should rely on per-user accounts plus full-disk encryption
> (BitLocker) to achieve the same protection.

**Things you should consider yourself:**

- **Full-disk encryption** — FileVault (macOS), BitLocker (Windows), LUKS (Linux). Filesystem perms don't help if the disk is offline or stolen.
- **Backups** — verify that anything backing up `$XDG_CACHE_HOME` (some agents do) is treating the contents as sensitive. Cloud sync to Dropbox/iCloud unencrypted is a no.
- **Shared machines** — on a multi-user box, the `0o700`/`0o600` defaults block other local users, but root can still read everything. If that matters, consider per-user encrypted home directories.

This fork's security defaults follow suggestions from upstream issue [#1](https://github.com/lee-fuhr/claude-session-index/issues/1) by [@miclivne](https://github.com/miclivne).

---

## Troubleshooting

### "warning: WAL journal mode unavailable; using default journaling."

This shows up when the SQLite write-ahead log can't create its sidecar files (`sessions.db-wal` and `sessions.db-shm`) next to the main DB. Most commonly it means you're running inside Claude Code's sandbox, which blocks writes outside the project working directory.

The tool keeps working in the slower default journal mode — *correctness is unaffected*, just slightly worse concurrency. To enable WAL properly:

```bash
sessions configure-permissions
```

This adds a `Write($XDG_CACHE_HOME/claude-session-index/**)` rule to `~/.claude/settings.json`, granting Claude Code's sandbox the write permission needed for WAL sidecars. Run once; the change is persistent. To undo: `sessions configure-permissions --remove`.

If you're seeing this warning *outside* of Claude Code (cron job, manual CLI), the cause is likely a read-only mount or NFS without locking. The tool still works in fallback mode in those cases.

### Legacy `~/.session-index/` directory

If you upgraded from upstream, the migration notice prints once telling you the old data is no longer used and how to clean up. See [Migrating from upstream](#migrating-from-upstream-session-index) above.

---

## How it works (technically)

```
~/.claude/projects/          session-index              Your conversation
  ├── -project-a/              ┌──────────┐
  │   ├── abc123.jsonl ──────▶│ SQLite   │◀──── "Didn't we discuss X?"
  │   └── def456.jsonl ──────▶│ + FTS5   │◀──── "How'd I spend my week?"
  ├── -project-b/              └──────────┘◀──── "What worked for Y?"
  │   └── ghi789.jsonl ──────▶     │
  └── ...                          │
                                   ▼
                            sessions.db
                          ┌─────────────────┐
                          │ sessions        │  metadata, timestamps, tools
                          │ session_content │  FTS5 full-text index
                          │ session_topics  │  live topic timeline
                          │ session_tools   │  tool usage per session
                          │ session_agents  │  agent invocations
                          └─────────────────┘
```

The indexer parses JSONL files once, extracts metadata (timestamps, tools, agents, topics), and stores everything in SQLite. FTS5 handles the full-text search. Context retrieval reads JSONL on-demand — only the files you ask about.

## Tech stack

- **Python 3.11+** — stdlib only for core features (no runtime dependencies); `tomllib` for config reading
- **SQLite + FTS5** — fast full-text search, no server needed
- **Anthropic SDK** — optional, only for standalone `synthesize` command

---

## Requirements

- Python 3.11+
- Claude Code (the sessions to index)
- That's it. No server, no database setup, no API keys for core features.

---

## Credits

- Originally built by [Lee Fuhr](https://leefuhr.com) — [`lee-fuhr/claude-session-index`](https://github.com/lee-fuhr/claude-session-index).
- Security hardening defaults (issue [#1](https://github.com/lee-fuhr/claude-session-index/issues/1)) suggested by [@miclivne](https://github.com/miclivne).
- This fork maintained by [Syrunekai](https://github.com/Syrunekai).

---

## Contributing

### Editing the skill

`SKILL.md` exists in two places by necessity:

- **Source of truth:** `session_index/_skill/SKILL.md` — ships inside the
  package wheel so `sessions install-skill` can find it post-install.
- **Derived copy:** `skills/session-index/SKILL.md` — the conventional path
  that `npx skills add` reads.

Edit the source. Then regenerate the derived copy:

```bash
python scripts/sync-skill.py
```

A test (`tests/test_installer.py::SkillSyncTests`) fails if the two ever drift,
so you cannot accidentally land an out-of-sync change. Use `--check` mode in
pre-commit hooks or CI:

```bash
python scripts/sync-skill.py --check
```

The two-file split (rather than a symlink) keeps the project usable on Windows,
where git does not materialize symlinks by default.

### Editing the config template

The default config schema lives as `CONFIG_TEMPLATE` in `session_index/config.py`.
The repo-root [`config.example.toml`](config.example.toml) is generated from it
for browsable reference on GitHub. Same pattern as the skill:

```bash
python scripts/sync-config-example.py            # regenerate from CONFIG_TEMPLATE
python scripts/sync-config-example.py --check    # CI-friendly drift detection
```

When you add new keys, also bump `CURRENT_SCHEMA_VERSION` in `config.py` so
existing users see a migration nudge on their next invocation.

### Running tests

```bash
python -m unittest discover -s tests
```

Pure stdlib, no test dependencies.

### Pre-push checks

The repo ships a git pre-push hook that runs the sync checks plus the test
suite before any push, aborting if anything is red. Wire it up once after
cloning:

```bash
python scripts/install-hooks.py
```

That sets git's `core.hooksPath` to `scripts/git-hooks/` for this clone.
From then on, `git push` automatically runs `scripts/preflight.py` first
and aborts on any failure — no network round-trip wasted on a bad push.

You can also run the preflight manually any time:

```bash
python scripts/preflight.py
```

The hook is Python, not bash, so it works the same on Linux, macOS, and
Windows (git-for-windows). No external tooling beyond Python itself.
