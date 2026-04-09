"""Tests for bounded automatic recovery (Issue #35).

Validates that:
- MAX_STAGE_ATTEMPTS is enforced on all retry loops.
- Recovery context is injected into continuation prompts after repeated failures.
- Normal first-attempt prompts do not include recovery context.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from src.manager import ResearchManager
from src.operator import ClaudeOperator
from src.terminal_ui import TerminalUI
from src.utils import (
    MAX_STAGE_ATTEMPTS,
    STAGES,
    StageSpec,
    build_continuation_prompt,
    build_run_paths,
    create_run_root,
    ensure_run_layout,
    format_stage_template,
    initialize_memory,
    initialize_run_config,
    load_prompt_template,
    write_text,
)


class TestMaxStageAttemptsConstant(unittest.TestCase):
    def test_max_stage_attempts_is_positive_integer(self):
        self.assertIsInstance(MAX_STAGE_ATTEMPTS, int)
        self.assertGreater(MAX_STAGE_ATTEMPTS, 0)

    def test_default_value_is_five(self):
        self.assertEqual(MAX_STAGE_ATTEMPTS, 5)


class TestRecoveryContextInContinuationPrompt(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.runs_dir = Path(self.tmp) / "runs"
        self.runs_dir.mkdir()
        self.run_root = create_run_root(self.runs_dir)
        self.paths = build_run_paths(self.run_root)
        ensure_run_layout(self.paths)
        initialize_run_config(self.paths, model="sonnet", venue="neurips_2025")
        initialize_memory(self.paths, "Test goal")
        write_text(self.paths.user_input, "Test goal")

        self.stage = STAGES[0]
        repo_root = Path(__file__).resolve().parent.parent
        prompt_dir = repo_root / "src" / "prompts"
        template = load_prompt_template(prompt_dir, self.stage)
        self.stage_template = format_stage_template(template, self.stage, self.paths)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_recovery_context_on_first_attempt(self):
        prompt = build_continuation_prompt(
            self.stage, self.stage_template, self.paths,
            handoff_context="", revision_feedback=None,
            attempt_no=1,
            previous_validation_errors=["missing ## Key Results"],
        )
        self.assertNotIn("# Recovery Context", prompt)

    def test_no_recovery_context_on_second_attempt(self):
        prompt = build_continuation_prompt(
            self.stage, self.stage_template, self.paths,
            handoff_context="", revision_feedback=None,
            attempt_no=2,
            previous_validation_errors=["missing ## Key Results"],
        )
        self.assertNotIn("# Recovery Context", prompt)

    def test_recovery_context_on_third_attempt(self):
        errors = ["missing ## Key Results", "missing ## Files Produced"]
        prompt = build_continuation_prompt(
            self.stage, self.stage_template, self.paths,
            handoff_context="", revision_feedback=None,
            attempt_no=3,
            previous_validation_errors=errors,
        )
        self.assertIn("# Recovery Context", prompt)
        self.assertIn("attempt 3", prompt)
        self.assertIn("missing ## Key Results", prompt)
        self.assertIn("missing ## Files Produced", prompt)

    def test_recovery_context_mentions_human_reviewer(self):
        prompt = build_continuation_prompt(
            self.stage, self.stage_template, self.paths,
            handoff_context="", revision_feedback=None,
            attempt_no=4,
            previous_validation_errors=["missing section"],
        )
        self.assertIn("human reviewer", prompt)

    def test_no_recovery_context_without_errors(self):
        prompt = build_continuation_prompt(
            self.stage, self.stage_template, self.paths,
            handoff_context="", revision_feedback=None,
            attempt_no=5,
            previous_validation_errors=None,
        )
        self.assertNotIn("# Recovery Context", prompt)

    def test_no_recovery_context_with_empty_errors(self):
        prompt = build_continuation_prompt(
            self.stage, self.stage_template, self.paths,
            handoff_context="", revision_feedback=None,
            attempt_no=5,
            previous_validation_errors=[],
        )
        self.assertNotIn("# Recovery Context", prompt)


class TestRunStageMaxAttempts(unittest.TestCase):
    """Test that _run_stage stops after MAX_STAGE_ATTEMPTS."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.runs_dir = Path(self.tmp) / "runs"
        self.runs_dir.mkdir()
        self.run_root = create_run_root(self.runs_dir)
        self.paths = build_run_paths(self.run_root)
        ensure_run_layout(self.paths)
        initialize_run_config(self.paths, model="sonnet", venue="neurips_2025")
        initialize_memory(self.paths, "Test goal")
        write_text(self.paths.user_input, "Test goal")

        self.repo_root = Path(__file__).resolve().parent.parent
        self.ui = TerminalUI()
        self.operator = ClaudeOperator(
            model="sonnet", fake_mode=True, ui=self.ui,
        )
        self.manager = ResearchManager(
            project_root=self.repo_root,
            runs_dir=self.runs_dir,
            operator=self.operator,
            ui=self.ui,
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_run_stage_returns_false_after_max_attempts(self):
        """Simulate a stage that always produces invalid output.

        We patch the attempt counter to start just below the limit so the
        loop hits the ceiling quickly without running MAX_STAGE_ATTEMPTS
        real fake-operator calls.
        """
        from src.utils import write_attempt_count
        stage = STAGES[0]
        # Set attempt counter so next attempt_no = MAX_STAGE_ATTEMPTS + 1
        write_attempt_count(self.paths, stage, MAX_STAGE_ATTEMPTS)

        result = self.manager._run_stage(self.paths, stage)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
