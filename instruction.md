# Loom

A personal AI-native automation workflow engine, powered by Claude.

Loom lets you compose modular workflows from triggers, steps, and actions.
Resume tailoring, codebase analysis, and email processing are built-in
workflows — but the engine itself is domain-agnostic.

---

## Philosophy

**AI-native, not AI-assisted**
Claude is the execution core, not a helper. Every step that involves
reasoning, extraction, or generation is delegated to Claude.
The framework handles orchestration, state, and I/O.

**Modular by design**
Triggers, Steps, and Actions are independent units.
A Step does not know where its input came from or where its output goes.
A Workflow is just a composition of these units.

**Local-first, cloud-optional**
Loom runs entirely on your machine by default.
AWS integrations (SES, S3, Lambda) are optional providers,
not hard dependencies.

**Single user, no compromise**
Loom is built for one person. No multi-tenancy, no auth,
no SaaS complexity — until explicitly needed.
Schema is pre-structured for future migration (user_id preserved),
but the current runtime assumes local context.

---

## Architecture

```
Trigger Layer    — what starts a workflow
                   (email received / manual / scheduled / git hook)

Step Layer       — what happens in the middle
                   (parse / match / analyze / generate)

Action Layer     — what happens at the end
                   (store / send / export / notify)

Context          — shared state passed through the pipeline
Storage          — persistent data (profiles, bullets, workflows)
Claude Core      — reasoning engine behind every Step
```

---

## Tech Stack

| Layer       | Technology                        |
|-------------|-----------------------------------|
| Backend     | Python 3.11+, FastAPI             |
| Frontend    | Next.js (Chat interface only)     |
| Database    | PostgreSQL                        |
| AI          | Claude API (Sonnet for reasoning, |
|             | Haiku for extraction/matching)    |
| Agent       | Claude Code + MCP                 |
| Cloud       | AWS SES / S3 / Lambda (optional)  |
| Validation  | Pydantic v2                       |

---

## Core Abstractions

Every component implements one of three interfaces:

**Trigger** — emits a PipelineContext to start a workflow
**Step** — receives Context, runs logic, returns updated Context
**Action** — receives final Context, produces side effects

```python
# All steps follow this contract
class Step:
    async def run(self, context: PipelineContext) -> PipelineContext:
        ...
```

Context carries user_id, workflow state, and inter-step data.
Steps are stateless. All persistence goes through Storage.

---

## Built-in Workflows

**resume-tailor**
```
Trigger: manual / email-received
Steps:   parse-jd → match-profile → select-bullets → generate-resume
Actions: export-pdf → store-s3 / send-email
```

**codebase-scan**
```
Trigger: manual / git-hook
Steps:   analyze-repo → extract-stack → update-profile
Actions: notify-chat
```

---

## Design Principles

**One Step, one responsibility**
A Step that parses JD should not also do matching.
If you find yourself writing "and" in a Step's description, split it.

**Claude handles reasoning, Python handles flow**
Don't write rule-based logic for things Claude can reason about.
Don't call Claude for things a simple function can handle.

**Prompt is code**
Prompts live in versioned files, not inline strings.
Every prompt has a defined input schema and expected output schema.

**Fail loudly, recover gracefully**
Steps should raise typed exceptions.
Workflows should define retry and fallback behavior explicitly.

---

## Project Structure

```
loom/
├── core/
│   ├── pipeline.py       # Workflow orchestration
│   ├── context.py        # PipelineContext definition
│   ├── step.py           # Base Step interface
│   ├── trigger.py        # Base Trigger interface
│   └── action.py         # Base Action interface
├── steps/                # Built-in steps
├── triggers/             # Built-in triggers
├── actions/              # Built-in actions
├── workflows/            # Workflow definitions
├── prompts/              # All Claude prompts
├── storage/              # DB models and queries
├── chat/                 # Next.js Chat interface
└── mcp/                  # MCP server definitions
```

---

## Development Notes

- New workflows go in `workflows/` as YAML or Python config
- New steps go in `steps/`, must implement `Step` base class
- Prompts are files in `prompts/`, named by step and version
- Storage models always include `user_id` and `created_at`
- Use Haiku for high-frequency low-reasoning calls (matching, extraction)
- Use Sonnet for generation, reasoning, and conversation
