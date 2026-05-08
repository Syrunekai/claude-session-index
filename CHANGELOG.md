# Changelog

## v0.4.1 — Auto-reindex on staleness

The index now refreshes itself in the background when it gets stale, so search results stop drifting behind the conversation you're currently in. No new flags to remember; the next `sessions` command after the threshold quietly does the right thing.

- **Auto-reindex on staleness** — `ensure_indexed()` now also triggers an *incremental* refresh (not a full backfill) when the database hasn't been updated in `auto_reindex_time` minutes. The cheap-path sweep is hash-skip only, so untouched sessions cost ~ms each — only currently-active sessions actually re-parse.
- **`auto_reindex_time` config key** — defaults to 60 minutes. Set to `0` in your config to disable auto-reindex entirely (back to manual `sessions index` only). Tune up if you have thousands of sessions on slower hardware and the sweep cost is noticeable; tune down if you ask "what did I just try?" and want fresher results.
- **`metadata` table in the SQLite schema** — stores `last_indexed_at` as the freshness marker. Cross-platform robust where filesystem mtime isn't (WAL-mode SQLite doesn't reliably bump the main DB file's mtime on every commit, so an in-DB row is the right signal). Pre-v0.4.1 databases without this table or row are treated as stale and refreshed on first contact, populating the metadata going forward.
- **Schema version bumped to 2** — old `schema_version = 1` configs keep working unchanged; defaults silently fill in `auto_reindex_time = 60` and the existing one-time advisory warning points at `config.example.toml`.
- **11 new tests** — `MetadataTableTests` (table created, timestamp written by both backfill and incremental) and `EnsureIndexedStalenessTests` (fresh skip, stale trigger, `auto_reindex_time = 0` disables, missing-row treated-as-stale) plus `AutoReindexConfigTests` for the new key resolution. Also added `VersionConsistencyTests` — a drift check that fails if `pyproject.toml`'s `project.version` and `session_index.__version__` disagree, since that drift bit us in the v0.4.0 cycle (`__init__.py` stuck at 0.3.0 while pyproject had moved on). Suite total: 80.

## v0.4.0 — Fork divergence: XDG paths, hardened defaults, admin subcommands

First release of the [Syrunekai fork](https://github.com/Syrunekai/claude-session-index) — divergence point from upstream [`lee-fuhr/claude-session-index@v0.3.1`](https://github.com/lee-fuhr/claude-session-index). Focused on resilience, security defaults, and self-contained setup so the tool is usable inside Claude Code's sandbox without external scaffolding.

If you're upgrading from upstream: your old DB at `~/.session-index/sessions.db` keeps working (legacy notice on first run tells you where the new XDG-compliant location is). Re-indexing at the new location is fast and offline.

- **WAL fallback for sandboxed environments** — `PRAGMA journal_mode=WAL` requires creating `-wal` and `-shm` sidecar files, which the Claude Code sandbox blocks by default. The indexer now tries WAL, falls back to default journaling on `OperationalError`, and emits a one-time-per-invocation warning pointing at the fix. Default mode is correct, just slightly slower for concurrent access — irrelevant for a single-user CLI.
- **XDG-compliant paths** — DB moved from `~/.session-index/sessions.db` to `$XDG_CACHE_HOME/claude-session-index/sessions.db` (regenerable cache). Config moved from `~/.session-index/config.json` to `$XDG_CONFIG_HOME/claude-session-index/config.toml` (hand-edited, sync-friendly). Topics directory unchanged at `~/.claude/session-topics/` (Claude's namespace).
- **Permission hardening (`0o700` / `0o600`)** — DB and config directories created owner-only; DB and config files created owner-only. Permissions are *self-healing* — old loose-perm files get tightened on the next CLI invocation. Addresses upstream issue [#1](https://github.com/lee-fuhr/claude-session-index/issues/1) by [@miclivne](https://github.com/miclivne).
- **`sessions install-skill`** — first-class skill installation that doesn't need npm or npx. Defaults to copy (snapshot, supply-chain-safe); `--link` opts into a symlink that tracks the package. The `npx skills add` workflow still works for users who want skill-marketplace integration.
- **`sessions configure-permissions`** — adds a `Write($XDG_CACHE_HOME/claude-session-index/**)` rule to `~/.claude/settings.json` so WAL works inside the Claude Code sandbox without manual settings editing. Backs up settings.json before writing; `--dry-run` previews; `--remove` for clean uninstall.
- **`sessions init-config`** — exposes the previously-unreachable bootstrap that writes a default config file. Supports `--force` to overwrite. The generated TOML is fully commented inline.
- **TOML config + schema versioning** — config format switched from JSON to TOML. Reading via stdlib `tomllib`; writing from a hardcoded `CONFIG_TEMPLATE` constant in `config.py` (zero runtime deps added). Each config carries a `schema_version`; mismatch produces a one-time advisory warning, defaults still apply silently for missing keys.
- **`config.example.toml` at repo root** — generated from the same `CONFIG_TEMPLATE` constant. Browse the full config reference on GitHub without cloning. Regenerated via `scripts/sync-config-example.py`; a test enforces drift detection.
- **Cross-platform skill file** — instead of a symlink that only worked on Linux/macOS, `skills/session-index/SKILL.md` is now a real file kept in sync with `session_index/_skill/SKILL.md` via `scripts/sync-skill.py`. A test in the suite catches forgotten syncs. Restores Windows compatibility.
- **Test suite** — upstream had no tests. This fork ships with 51 stdlib `unittest` tests covering XDG path resolution, legacy detection, perm helpers, WAL fallback, TOML loading, schema versioning, all three new admin subcommands, and the sync-script drift detection. Run with `python -m unittest discover -s tests`.
- **Min Python bumped to 3.11** — required for stdlib `tomllib`. 3.10 has been EOL or near-EOL on most distros; the cleaner zero-deps story is worth the cut.
- **`.env.example` removed** — the file existed in upstream but no code path loaded it, so anyone copying it to `.env` got nothing. Env vars are documented inline in the README's Configuration > Priority order section.

## v0.3.1 — Stop titling everything "## Curation Data"

- **Smarter title auto-generation** — skips markdown headers, agent system prompts, and system caveats when picking a title from user messages. Tries up to 5 messages before giving up.
- Previously, 84+ sessions were titled "## Curation Data" and 20+ were titled "You are QA testing...". Now those get proper titles or null instead of garbage.

## v0.3.0 — Sessions have names now

The biggest annoyance is fixed: most sessions showed "(unnamed)" because only manually-titled sessions had display names. Now titles are auto-generated from compaction summaries or the first user message. Re-index with `sessions index --backfill` to see the difference.

- **Auto-generated session titles** — compaction summaries get parsed (including JSON blobs), and untitled sessions fall back to the first user message. No more walls of "(unnamed)".
- **`--days N` filter** — `sessions find --days 14` for arbitrary date ranges, not just `--week`
- **`--exclude-project` filter** — `sessions find --exclude-project "share memory"` to cut the noise
- **FTS5 crash fixes** — queries with periods (`CLAUDE.md`), hyphens (`session-index`), and reserved words (`index`) no longer crash. All search terms get quoted for safe literal matching.
- **CLI flag parsing fix** — `sessions "query" -n 5` now works correctly (the flag value was getting split from the flag)
- **`npx skills add` support** — skill moved to `skills/session-index/SKILL.md` to match the skills.sh registry convention. Install with `npx skills add lee-fuhr/claude-session-index`.
- **Conversational interface as primary UX** — README and skill rewritten to emphasize the natural language experience in Claude Code. The CLI is still there for power users.

## v0.2.0 — It looks good now

The output got a proper makeover. Conversations read like conversations. Analytics have visual hierarchy. And you don't have to set anything up anymore.

- **One command to rule them all** — `sessions` replaces the old `session-search` / `session-analyze` / `session-index` trio. Plain text defaults to search: `sessions "webhook debugging"` just works.
- Chat-like conversation display with 🧑/🤖 markers — you can actually tell who said what
- Box-drawing characters for session cards and exchange blocks
- Section headers with emoji in analytics (📊 📈 🔧 💬) for scannable output
- Cleaner search results with ◆ bullets and → resume commands
- Auto-indexing on first use — no more separate `--backfill` step, just run any command and it handles the rest
- Better stats display with visual structure instead of raw JSON
- The old commands still work if you prefer them

## v0.1.0 — Initial release

- Full-text search across all Claude Code sessions (SQLite + FTS5)
- Filter by client, project, tool, agent, tag, date
- Conversation context retrieval from session JSONL files
- Analytics: time per client, tool trends, session frequency, topic analysis
- Cross-session synthesis via Anthropic API (optional dependency)
- Live topic capture via Claude Code hooks (UserPromptSubmit, PreCompact, SessionEnd)
- Background indexing via macOS LaunchAgent
- Claude Code skill for natural language session queries
- Configurable paths via CLI flags, env vars, or config file
