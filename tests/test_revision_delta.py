"""Tests for Revision Delta extraction, stripping, prompt inclusion, and UI display."""
from __future__ import annotations

import io
import unittest

from src.terminal_ui import TerminalUI
from src.utils import (
    build_continuation_prompt,
    build_run_paths,
    ensure_run_layout,
    extract_revision_delta,
    strip_revision_delta,
    StageSpec,
)


SAMPLE_STAGE = StageSpec(number=1, slug="01_literature_survey", display_name="Literature Survey")

SAMPLE_MARKDOWN_WITH_DELTA = """\
# Stage 01: Literature Survey

## Revision Delta
- Modified **Key Results** section: added 3 new references
- New file: `workspace/literature/survey.bib`
- Overall: expanded coverage of multi-agent frameworks

## Objective
Survey the relevant literature.

## Previously Approved Stage Summaries
_None yet._

## What I Did
Searched for papers on multi-agent systems.

## Key Results
Found 12 relevant papers.

## Files Produced
- `workspace/literature/survey.bib` - bibliography

## Suggestions for Refinement
1. Add more recent 2025 papers
2. Include survey papers on LLM reasoning
3. Expand coverage of tool-use literature

## Your Options
1. Use suggestion 1
2. Use suggestion 2
3. Use suggestion 3
4. Refine with your own feedback
5. Approve and continue
6. Abort
"""

SAMPLE_MARKDOWN_WITHOUT_DELTA = """\
# Stage 01: Literature Survey

## Objective
Survey the relevant literature.

## Previously Approved Stage Summaries
_None yet._

## What I Did
Searched for papers on multi-agent systems.

## Key Results
Found 12 relevant papers.

## Files Produced
- `workspace/literature/survey.bib` - bibliography

## Suggestions for Refinement
1. Add more recent 2025 papers
2. Include survey papers on LLM reasoning
3. Expand coverage of tool-use literature

## Your Options
1. Use suggestion 1
2. Use suggestion 2
3. Use suggestion 3
4. Refine with your own feedback
5. Approve and continue
6. Abort
"""


class TestExtractRevisionDelta(unittest.TestCase):
    def test_extracts_delta_when_present(self) -> None:
        delta = extract_revision_delta(SAMPLE_MARKDOWN_WITH_DELTA)
        self.assertIsNotNone(delta)
        self.assertIn("Modified **Key Results** section", delta)
        self.assertIn("New file:", delta)
        self.assertIn("Overall:", delta)

    def test_returns_none_when_absent(self) -> None:
        delta = extract_revision_delta(SAMPLE_MARKDOWN_WITHOUT_DELTA)
        self.assertIsNone(delta)

    def test_returns_none_for_empty_delta(self) -> None:
        md = "# Stage 01: Literature Survey\n\n## Revision Delta\n\n## Objective\nDo stuff.\n"
        delta = extract_revision_delta(md)
        self.assertIsNone(delta)


class TestStripRevisionDelta(unittest.TestCase):
    def test_strips_delta_section(self) -> None:
        stripped = strip_revision_delta(SAMPLE_MARKDOWN_WITH_DELTA)
        self.assertNotIn("## Revision Delta", stripped)
        self.assertNotIn("Modified **Key Results** section", stripped)
        # All other sections must survive
        self.assertIn("## Objective", stripped)
        self.assertIn("## Key Results", stripped)
        self.assertIn("## Files Produced", stripped)
        self.assertIn("## Suggestions for Refinement", stripped)

    def test_no_op_when_absent(self) -> None:
        stripped = strip_revision_delta(SAMPLE_MARKDOWN_WITHOUT_DELTA)
        self.assertEqual(stripped, SAMPLE_MARKDOWN_WITHOUT_DELTA)

    def test_no_triple_blank_lines(self) -> None:
        stripped = strip_revision_delta(SAMPLE_MARKDOWN_WITH_DELTA)
        self.assertNotIn("\n\n\n", stripped)

    def test_roundtrip_preserves_stage_title(self) -> None:
        stripped = strip_revision_delta(SAMPLE_MARKDOWN_WITH_DELTA)
        self.assertTrue(stripped.startswith("# Stage 01: Literature Survey"))


class TestContinuationPromptIncludesDeltaInstruction(unittest.TestCase):
    def test_prompt_mentions_revision_delta(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            paths = build_run_paths(run_root)
            ensure_run_layout(paths)
            paths.memory.write_text("# Memory\n")
            paths.user_input.write_text("Test goal.\n")

            prompt = build_continuation_prompt(
                stage=SAMPLE_STAGE,
                stage_template="Do literature survey.",
                paths=paths,
                handoff_context="",
                revision_feedback="Fix the references.",
            )
            self.assertIn("Revision Delta", prompt)
            self.assertIn("what you changed", prompt.lower())


class TestShowRevisionDelta(unittest.TestCase):
    def test_displays_panel_with_delta(self) -> None:
        output = io.StringIO()
        ui = TerminalUI(output_stream=output, input_stream=io.StringIO())
        ui.show_revision_delta("- Changed section A\n- Added file B", 2)
        rendered = output.getvalue()
        self.assertIn("What Changed", rendered)
        self.assertIn("Attempt 2", rendered)
        self.assertIn("Changed section A", rendered)
        self.assertIn("Added file B", rendered)

    def test_attempt_number_shown(self) -> None:
        output = io.StringIO()
        ui = TerminalUI(output_stream=output, input_stream=io.StringIO())
        ui.show_revision_delta("- Minor fix", 5)
        self.assertIn("Attempt 5", output.getvalue())


if __name__ == "__main__":
    unittest.main()
