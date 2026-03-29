# AutoR (Auto Research)

## Overview

AutoR is an AI-assisted research workflow system. A user provides a research goal, the system breaks the work into stages, Claude Code executes each stage, and the user reviews, revises, and approves the output at each checkpoint.

This repository defines the first minimal runnable version. The goal is to validate the full research loop end to end before building a fuller product surface. The current MVP runs in the terminal, but the terminal is only the current interaction surface, not the final product form.

## Architecture

### Core Rules

- Stage order is fixed.
- `refine` means a full rerun of the current stage.
- Workflow state should stay simple and file-based.
- Stages should not exchange complex schemas or custom protocol layers unless there is a proven need later.
- Unnecessary abstraction is forbidden.
- Do not introduce plugin systems, generic orchestration frameworks, or over-designed class hierarchies for the MVP.
- `manager.py` owns workflow control.
- `operator.py` owns Claude execution.
- `utils.py` contains shared helpers only.

### Repository Layout

```text
repo/
├── main.py
├── src/
│   ├── manager.py
│   ├── operator.py
│   ├── utils.py
│   └── prompts/
│       ├── 01_literature_survey.md
│       ├── 02_hypothesis_generation.md
│       ├── 03_study_design.md
│       ├── 04_implementation.md
│       ├── 05_experimentation.md
│       ├── 06_analysis.md
│       ├── 07_writing.md
│       └── 08_dissemination.md
└── runs/
```

### Module Boundaries

- `main.py`
  - bootstrap only
  - reads the initial user goal
  - instantiates the manager and operator
- `src/manager.py`
  - owns the 8-stage loop
  - creates run directories
  - builds prompts
  - handles user choices `1` to `6`
  - decides rerun, approve, next, and abort behavior
  - writes approved memory and logs
  - should use direct control flow, not an event system or workflow framework
- `src/operator.py`
  - calls Claude CLI directly
  - parses `stream-json` output
  - captures stdout, stderr, and exit code
  - validates that the required stage markdown exists
  - should return a minimal execution result only
  - does not decide workflow transitions
- `src/utils.py`
  - stage metadata
  - path helpers
  - prompt assembly helpers
  - markdown parsing helpers
  - file and log helpers
  - should remain a pure helper layer, not a second manager
- `src/prompts/`
  - version-controlled prompt templates only
  - never runtime outputs

### Dependency Direction

```text
main.py -> manager.py -> operator.py
                    \-> utils.py
operator.py -> utils.py
```

## Run Layout

Each execution creates an isolated run directory:

```text
runs/<run_id>/
├── user_input.txt
├── memory.md
├── logs_raw.jsonl
├── stages/
│   ├── 01_literature_survey.md
│   ├── ...
├── workspace/
│   ├── literature/
│   ├── code/
│   ├── data/
│   ├── results/
│   ├── writing/
│   ├── figures/
│   ├── artifacts/
│   ├── notes/
│   └── reviews/
└── logs.txt
```

Recommended `run_id` format:

```text
YYYYMMDD_HHMMSS
```

### Top-Level Boundaries

- `user_input.txt`
  - stores only the original user request for this run
- `memory.md`
  - stores only approved cross-stage context
  - never failed attempts, revision history, or raw logs
- `logs_raw.jsonl`
  - stores the raw Claude `stream-json` event stream for debugging and replay
- `stages/`
  - stores stage summary markdown files
  - is the canonical source of stage output
  - is not a scratch directory
- `workspace/`
  - stores substantive research artifacts
  - is not the workflow control plane
- `logs.txt`
  - stores audit and debug information
  - is not approved memory or user-facing stage output

### Workspace Boundaries

- `workspace/literature/`
  - papers, reading notes, citations, survey material
- `workspace/code/`
  - scripts, notebooks, implementations, runnable logic
- `workspace/data/`
  - raw data references, processed data, metadata, loaders
- `workspace/results/`
  - metrics, evaluations, tables, experiment outputs
- `workspace/writing/`
  - outlines, abstracts, drafts, dissemination text
- `workspace/figures/`
  - plots, diagrams, charts, visual assets
- `workspace/artifacts/`
  - packaged deliverables, reproducibility bundles, export-ready outputs
- `workspace/notes/`
  - temporary notes, TODOs, open questions, scratch thinking
- `workspace/reviews/`
  - critique notes, revision checklists, response drafts

## Stage Model

### Fixed Stage Order

```text
01_literature_survey
02_hypothesis_generation
03_study_design
04_implementation
05_experimentation
06_analysis
07_writing
08_dissemination
```

### Simple Inter-Stage Contract

Each stage consumes:

- the current prompt template from `src/prompts/<stage>.md`
- the original research request from `runs/<run_id>/user_input.txt`
- approved context from `runs/<run_id>/memory.md`
- the current contents of `runs/<run_id>/workspace/`
- optional revision feedback for the current rerun

Each stage produces:

- a required summary file at `runs/<run_id>/stages/<stage>.md`
- any working artifacts inside `runs/<run_id>/workspace/`

That is the contract. Stages should not depend on custom per-stage JSON schemas or complex structured message formats.

### Required Stage Output Format

Every stage must generate markdown in the following structure:

```md
# Stage X: <name>

## Objective
...

## Previously Approved Stage Summaries
...

## What I Did
...

## Key Results
...

## Files Produced
...

## Suggestions for Refinement
1. ...
2. ...
3. ...

## Your Options
1. Use suggestion 1
2. Use suggestion 2
3. Use suggestion 3
4. Refine with your own feedback
5. Approve and continue
6. Abort
```

The `Previously Approved Stage Summaries` section should be a concise readable summary of the relevant approved context from `memory.md`, not a raw dump.

## Execution

### Entry Point

```bash
python main.py
```

### End-to-End Flow

1. `main.py` reads the user goal and starts the manager.
2. The manager creates `runs/<run_id>/` and initializes the run files and workspace directories.
3. The manager enters the fixed 8-stage loop.
4. For each stage attempt, the manager:
   - loads the stage template
   - loads `user_input.txt`
   - loads `memory.md`
   - appends revision feedback if this is a rerun
   - builds the final prompt
5. The manager passes the prompt and run context to the operator.
6. The operator invokes Claude exactly once, captures both parsed output and raw `stream-json`, and checks that `runs/<run_id>/stages/<stage>.md` exists.
7. The manager displays the stage markdown and waits for user choice.
8. The manager reruns the same stage, advances, or aborts.
9. The program exits only when Stage 8 is approved or the user explicitly aborts.

### Prompt Construction

For every stage attempt, the final prompt is assembled in this order:

1. current stage template from `src/prompts/<stage>.md`
2. original user request from `runs/<run_id>/user_input.txt`
3. approved context from `runs/<run_id>/memory.md`
4. revision feedback, only when rerunning the current stage

Prompt assembly should stay simple. Use a small number of clearly delimited text sections, not a complex inter-stage exchange format.

### Claude Invocation Contract

Each stage attempt must use this CLI form:

```bash
claude --dangerously-skip-permissions -p "<PROMPT>" --output-format stream-json --verbose
```

Claude must be instructed to follow these rules:

- all work must happen inside `runs/<run_id>/workspace/`
- the stage summary file must be written to `runs/<run_id>/stages/<stage>.md`
- the summary must follow the required markdown structure exactly
- the summary must include the previously approved stage summaries in readable form
- Claude must not control stage transitions, approvals, retries, or abort behavior

Operator rules:

- call the Claude CLI directly
- parse `stream-json` directly enough to extract useful execution information
- avoid unnecessary abstraction layers around the CLI call
- persist the raw `stream-json` stream to `runs/<run_id>/logs_raw.jsonl`

Suggested minimal operator result:

- `success`
- `exit_code`
- `stdout`
- `stderr`
- `stage_file_path`

### Human Review Loop

After the stage markdown is displayed, the current terminal version prompts:

```text
Enter your choice:
>
```

Supported inputs:

- `1`, `2`, `3`
  - use the corresponding refinement suggestion
  - fully rerun the current stage
- `4`
  - collect custom user feedback
  - fully rerun the current stage
- `5`
  - approve the current stage
  - append the approved stage summary to `memory.md`
  - move to the next stage
- `6`
  - abort the run immediately

Additional rules:

- the workflow must never auto-advance
- `5` is the only action that may advance to the next stage
- `1` through `4` always rerun the same stage
- unapproved attempts must not be written into `memory.md`

## State Rules

- `memory.md`
  - stores only the original user goal and approved stage summaries
- `logs.txt`
  - stores execution and interaction traces only
- `logs_raw.jsonl`
  - stores raw Claude event output only
- these layers must stay distinct:
  - `memory.md` = approved context
  - `stages/<stage>.md` = user-facing stage output
  - `workspace/` = research artifacts
  - `logs.txt` = audit and debug
  - `logs_raw.jsonl` = raw Claude stream output

## MVP v0.1

### Included

- 8 fixed stages
- one Claude invocation per stage attempt
- mandatory human approval after every stage
- AI refine, custom refine, approve, and abort
- isolated run directories under `runs/<run_id>/`
- multi-file Python structure with `manager.py`, `operator.py`, `utils.py`, and `src/prompts/`
- direct-control-flow manager implementation
- thin operator result model
- raw `stream-json` persistence for debugging
- support for a fake operator mode to validate the workflow before wiring real Claude execution

### Out of Scope

- multi-agent execution
- automatic evaluation
- web UI
- database
- concurrent execution

### Acceptance Criteria

- `python main.py` starts the current terminal-based workflow
- each run creates a separate directory under `runs/`
- each stage attempt triggers exactly one Claude CLI invocation
- every stage produces a valid markdown summary with the required sections
- the user can refine the same stage multiple times before approval
- only approved stage summaries are persisted into `memory.md`
- the run ends only when Stage 8 is approved or the user explicitly aborts
