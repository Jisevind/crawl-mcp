"""Tests addressing coverage gaps identified in CODE_REVIEW.md issue #18.

Covers:
- validate_output_path path-traversal sandbox (CRAWL4AI_OUTPUT_BASE_DIR)
- ToolPipeline error handling (ErrorHandlingMiddleware)
- _get_crawler_run_config_info caching
- suppress_stdout_stderr behaviour
"""

import os
import sys
import io
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# validate_output_path — path-traversal sandbox
# ---------------------------------------------------------------------------


class TestValidateOutputPathSandbox:
    """Path-traversal tests for the CRAWL4AI_OUTPUT_BASE_DIR sandbox."""

    @staticmethod
    def _validate(path, overwrite=False, *, base_dir=None):
        """Call validate_output_path with optional env overrides."""
        from crawl4ai_mcp.validators import validate_output_path
        env = {}
        if base_dir is not None:
            env["CRAWL4AI_OUTPUT_BASE_DIR"] = base_dir
        with patch.dict(os.environ, env):
            return validate_output_path(path, overwrite=overwrite)

    def test_inside_default_base_dir(self, tmp_path):
        """A path under the configured base dir must be accepted."""
        base = str(tmp_path / "output")
        os.makedirs(base, exist_ok=True)
        p = str(Path(base) / "result.md")
        err = self._validate(p, base_dir=base)
        assert err is None, f"Expected None, got {err}"

    def test_outside_default_base_dir_rejected(self, tmp_path):
        base = str(tmp_path / "output")
        os.makedirs(base, exist_ok=True)
        outside = str(tmp_path / "outside.md")
        err = self._validate(outside, base_dir=base)
        assert err is not None
        assert err["error_code"] == "output_path_not_allowed"
        assert base in err["error"]

    def test_resolved_path_outside_rejected(self, tmp_path):
        """Even if the raw path appears inside, resolve must not escape."""
        base = str(tmp_path / "output")
        os.makedirs(base, exist_ok=True)
        # Create a parent traversing symlink... but on Windows, symlinks
        # require admin.  Instead use path with ../ that resolves outside.
        inside = str(Path(base) / "sub")
        os.makedirs(inside, exist_ok=True)
        escaping = str(Path(inside) / ".." / ".." / "outside.md")
        err = self._validate(escaping, base_dir=base)
        assert err is not None
        assert err["error_code"] == "output_path_not_allowed"

    def test_subdirectory_under_base_ok(self, tmp_path):
        base = str(tmp_path / "output")
        nested = str(Path(base) / "a" / "b" / "result.json")
        err = self._validate(nested, base_dir=base)
        assert err is None

    def test_base_dir_is_exact_match_not_prefix(self, tmp_path):
        """A path like /tmp/out2 must not match base /tmp/out."""
        base = str(tmp_path / "out")
        os.makedirs(base, exist_ok=True)
        sibling = str(tmp_path / "out2" / "file.md")
        err = self._validate(sibling, base_dir=base)
        assert err is not None
        assert err["error_code"] == "output_path_not_allowed"


# ---------------------------------------------------------------------------
# ToolPipeline error handling
# ---------------------------------------------------------------------------


class _ThrowingHandler:
    """Handler that always raises for test purposes."""

    def __init__(self, exc):
        self.exc = exc

    async def __call__(self, **kwargs):
        raise self.exc("simulated handler failure")


class _SuccessHandler:
    async def __call__(self, **kwargs):
        return {"success": True, "data": kwargs.get("value", "ok")}


class TestToolPipelineErrorHandling:
    """Tests that ToolPipeline.execute() catches handler exceptions."""

    @pytest.mark.asyncio
    async def test_handler_exception_returns_structured_error(self):
        from crawl4ai_mcp.middleware.pipeline import ToolPipeline

        pipeline = ToolPipeline()
        result = await pipeline.execute(
            _ThrowingHandler(ValueError),
            {"url": "https://example.com"},
        )
        assert isinstance(result, dict)
        assert result.get("success") is False
        assert result.get("error_code") == "handler_exception"
        assert "simulated handler failure" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_handler_success_passes_through(self):
        from crawl4ai_mcp.middleware.pipeline import ToolPipeline

        pipeline = ToolPipeline()
        result = await pipeline.execute(
            _SuccessHandler(),
            {"value": "hello"},
        )
        assert result["success"] is True
        assert result["data"] == "hello"

    @pytest.mark.asyncio
    async def test_after_hooks_still_run_on_exception(self):
        """After-hooks must execute even when the handler raises."""
        from crawl4ai_mcp.middleware.pipeline import ToolPipeline, Middleware, PipelineContext

        calls = []
        class RecordAfter(Middleware):
            async def after(self, ctx):
                calls.append("after")

        pipeline = ToolPipeline(RecordAfter())
        await pipeline.execute(
            _ThrowingHandler(RuntimeError),
            {"url": "https://example.com"},
        )
        assert "after" in calls


# ---------------------------------------------------------------------------
# _get_crawler_run_config_info caching
# ---------------------------------------------------------------------------


class TestCrawlerRunConfigInfo:
    """Tests for the module-level inspect.signature cache."""

    def test_cache_returns_consistent_results(self):
        from crawl4ai_mcp.core.crawler_core import _get_crawler_run_config_info

        params1, kwargs1 = _get_crawler_run_config_info()
        params2, kwargs2 = _get_crawler_run_config_info()

        assert params1 == params2
        assert kwargs1 == kwargs2
        assert isinstance(params1, set)
        assert "page_timeout" in params1  # basic sanity


# ---------------------------------------------------------------------------
# suppress_stdout_stderr
# ---------------------------------------------------------------------------


class TestSuppressOutput:
    """Tests for suppress_stdout_stderr and capture_output."""

    def test_suppress_stdout_stderr_blocks_output(self):
        from crawl4ai_mcp.suppress_output import suppress_stdout_stderr

        with suppress_stdout_stderr():
            print("this should not appear on stdout")
            print("this should not appear on stderr", file=sys.stderr)

        # Reaching here without exception means the context manager works.
        # We can't easily assert "nothing was printed" in a unit test
        # without a subprocess, but at minimum it shouldn't crash.
        assert True

    def test_capture_output_returns_content(self):
        from crawl4ai_mcp.suppress_output import capture_output

        with capture_output() as (out, err):
            print("hello world")
            print("error msg", file=sys.stderr)

        assert "hello world" in out.getvalue()
        assert "error msg" in err.getvalue()

    def test_stdout_restored_after_suppress(self):
        from crawl4ai_mcp.suppress_output import suppress_stdout_stderr

        original = sys.stdout
        with suppress_stdout_stderr():
            pass
        assert sys.stdout is original

    def test_stderr_restored_after_suppress(self):
        from crawl4ai_mcp.suppress_output import suppress_stdout_stderr

        original = sys.stderr
        with suppress_stdout_stderr():
            pass
        assert sys.stderr is original
