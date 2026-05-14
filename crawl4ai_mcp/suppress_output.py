"""
Output suppression utilities for crawl4ai MCP server.
"""

import os
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from io import StringIO


@contextmanager
def suppress_stdout_stderr():
    """Context manager to suppress stdout and stderr output."""
    with open(os.devnull, 'w') as devnull:
        with redirect_stdout(devnull), redirect_stderr(devnull):
            yield


@contextmanager
def capture_output():
    """Context manager to capture and return stdout/stderr output."""
    captured_stdout = StringIO()
    captured_stderr = StringIO()
    with redirect_stdout(captured_stdout), redirect_stderr(captured_stderr):
        yield captured_stdout, captured_stderr