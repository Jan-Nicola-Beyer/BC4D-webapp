# BC4D Intel — Project Context (auto-read by Claude Code)

## What this app is
Python desktop GUI for survey-based evaluation workflows at ISD Deutschland.
Processes BC4D (Bystander Courage for Democracy) training evaluation data.
Input: Excel files (pre-survey + post-survey). Output: charts, tagged qualitative data, report draft.

## Framework & Style
- **Match existing apps** — ask the user for framework before writing any GUI code
- Colors: primary `#C8175D`, background `#f7f7f5`, text `#0f0f0f`
- Reuse base window class and shared components from existing apps (ask user for paths)

## Critical architecture rules
1. All data flows through a single `AppState` object — never use global variables
2. All Claude API calls go through `ai/claude_client.py` — never call `anthropic` directly from screens
3. All system prompts live in `ai/prompts.py` as constants — never hardcode strings in logic files
4. Session state saves to `sessions/latest.bc4d` (JSON) after every major action

## Model routing — do not deviate without asking
| Task | Model |
|------|-------|
| Bulk free-text tagging | `claude-haiku-4-5-20251001` |
| Report writing | `claude-sonnet-4-6` |
| Column detection, stats, charts | No API — local Python only |

## Panel matching — important
Both Excel files contain a pseudonymisation key: first 4 letters of street + zero-padded birthday day.
These MUST be matched to enable individual-level pre/post analysis. See `core/panel_matcher.py`.

## Build order
Always follow the phases in `CODING_PLAN.md`. Complete and confirm each phase before starting the next.
Do not write logic in Phase 1 — scaffold only.

## Full spec
See `CODING_PLAN.md` for complete screen specs, file structure, component details, and Claude Code prompts.
