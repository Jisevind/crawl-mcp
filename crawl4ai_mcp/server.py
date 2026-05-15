"""
Crawl4AI MCP Server - FastMCP 3.0 Version

Uses FastMCP 3.0 with clean STDIO transport for MCP communication.
"""

import os
import sys
import warnings

# Set environment variables before any imports
os.environ["FASTMCP_SHOW_SERVER_BANNER"] = "false"
os.environ["FASTMCP_LOG_ENABLED"] = "false"
os.environ["PYTHONWARNINGS"] = "ignore"
os.environ["TERM"] = "dumb"
os.environ["SHELL"] = "/bin/sh"

# Rebuild shared library cache so Chromium can find its dependencies
# (libnspr4, libnss3, libdbus-1-3, etc.) inside Docker/uvx environments.
# Docker containers often have packages registered in dpkg but the
# actual .so files missing — reinstall ensures the files are on disk.
# This runs as a best-effort init with retries; failures are printed to
# stderr (visible in mcp-stderr.log) so users can debug their environment.
try:
    import subprocess
    import time

    def _log(msg: str) -> None:
        """Emit a startup log line that shows up in the MCP stderr log."""
        print(f"[crawl4ai-mcp] {msg}", file=sys.stderr, flush=True)

    def _run(cmd: list, timeout: int = 60) -> subprocess.CompletedProcess:
        """Run a command, capture output, and log failures to stderr."""
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        if r.returncode != 0:
            out = (r.stderr or b"").decode().strip()[:300]
            if out:
                _log(f"  cmd {' '.join(cmd[:3])}… rc={r.returncode}: {out}")
        return r

    def _ensure_chromium_libs() -> None:
        # 1. Try ldconfig — may fail in Hermes MCP sandbox (/etc readonly).
        #    Chrome doesn't need ldconfig if LD_LIBRARY_PATH is set.
        if _run(["ldconfig"], timeout=10).returncode != 0:
            _log("ldconfig skipped (/etc not writable), using LD_LIBRARY_PATH instead")

        # 2. Check if chrome binary actually works
        check = _run(
            ["/root/.cache/ms-playwright/chromium-1187/chrome-linux/chrome",
             "--version"],
            timeout=10,
        )
        if check.returncode == 0:
            _log("chrome ok, skipping lib install")
        else:
            _log("chrome missing shared libs, installing…")

            # 3. Update apt cache (retry once with full output if -qq fails)
            up = _run(["apt-get", "update", "-qq"], timeout=90)
            if up.returncode != 0:
                _log("apt-get update -qq failed, retrying without -qq…")
                up = _run(["apt-get", "update"], timeout=120)

            if up.returncode == 0:
                # 4. Install libs in small batches (avoids pulling systemd)
                _batches = [
                    ["libnspr4", "libnss3", "libdbus-1-3"],
                    ["libatk1.0-0t64", "libatk-bridge2.0-0t64", "libatspi2.0-0t64"],
                    ["libxkbcommon0", "libxcomposite1", "libxdamage1", "libxfixes3"],
                    ["libxrandr2", "libgbm1", "libasound2t64", "libcups2t64"],
                ]
                for batch in _batches:
                    _run(
                        ["apt-get", "install", "--reinstall", "-y", "-qq",
                         "--no-install-recommends"] + batch,
                        timeout=90,
                    )

            else:
                _log("apt-get update failed — libs cannot be installed automatically")
                _log("build a custom Docker image or pre-install the libraries listed in Dockerfile.hermes")
                return

            # 5. Set LD_LIBRARY_PATH so Chrome finds libs even without ldconfig
            libpath = "/usr/lib/x86_64-linux-gnu"
            existing = os.environ.get("LD_LIBRARY_PATH", "")
            if libpath not in existing:
                os.environ["LD_LIBRARY_PATH"] = f"{libpath}:{existing}" if existing else libpath
                _log(f"LD_LIBRARY_PATH set to {os.environ['LD_LIBRARY_PATH']}")

            # 6. Verify
            v = _run(
                ["/root/.cache/ms-playwright/chromium-1187/chrome-linux/chrome",
                 "--version"],
                timeout=10,
            )
            if v.returncode == 0:
                _log("libs installed, chrome ok")
            else:
                _log("libs may still be incomplete — see errors above")

        # 7. Register browser with Playwright's Node.js driver so the
        #    "Executable doesn't exist at …/chrome" error goes away.
        _log("registering browser with playwright driver…")
        pw = _run([sys.executable, "-m", "playwright", "install", "chromium"],
                  timeout=60)
        if pw.returncode != 0:
            _log("playwright install exited non-zero — see previous line")

    _ensure_chromium_libs()
except Exception:
    pass

warnings.filterwarnings("ignore")
warnings.simplefilter("ignore")

import logging
logging.disable(logging.CRITICAL)

# Import FastMCP 3.0
from fastmcp import FastMCP

from .server_tools import register_all_tools

# Create MCP server with clean initialization
mcp = FastMCP("Crawl4AI")

# Tool module loading state (owned by server.py)
_tools_imported = False
_tool_modules = (None, None, None, None, None)


def _load_tool_modules() -> bool:
    """Load tool modules only when needed.

    Returns:
        True if modules were loaded successfully, False otherwise.
    """
    global _tools_imported, _tool_modules
    if _tools_imported:
        return True

    try:
        from .tools import web_crawling as _wc
        from .tools import search as _s
        from .tools import youtube as _yt
        from .tools import file_processing as _fp
        from .tools import utilities as _ut

        _tool_modules = (_wc, _s, _yt, _fp, _ut)
        _tools_imported = True
        return True
    except ImportError as ie1:
        print(f"Warning: relative import failed ({ie1}), trying absolute import...", file=sys.stderr)
        try:
            from crawl4ai_mcp.tools import web_crawling as _wc
            from crawl4ai_mcp.tools import search as _s
            from crawl4ai_mcp.tools import youtube as _yt
            from crawl4ai_mcp.tools import file_processing as _fp
            from crawl4ai_mcp.tools import utilities as _ut

            _tool_modules = (_wc, _s, _yt, _fp, _ut)
            _tools_imported = True
            return True
        except ImportError as ie2:
            print(f"Warning: absolute import also failed ({ie2}). No tools registered.", file=sys.stderr)
            _tools_imported = False
            return False


def is_tools_imported() -> bool:
    """Check if tool modules are imported."""
    return _tools_imported


def get_tool_modules():
    """Get the loaded tool modules.

    Returns:
        Tuple of (web_crawling, search, youtube, file_processing, utilities).
    """
    if not _tools_imported:
        _load_tool_modules()
    return _tool_modules


def _get_modules():
    """Get tool modules, loading them if needed.

    Returns the tuple (web_crawling, search, youtube, file_processing, utilities)
    or None if modules couldn't be loaded.
    """
    if not _tools_imported:
        _load_tool_modules()
    if not _tools_imported:
        return None
    return _tool_modules


# Register all MCP tools
register_all_tools(mcp, _get_modules)


def main():
    """Clean main entry point - FastMCP 3.0"""
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print("Crawl4AI MCP Server - FastMCP 3.0 Version")
        print("Usage: python -m crawl4ai_mcp.server [--transport TRANSPORT]")
        print("Transports: stdio (default), http, sse (deprecated)")
        return

    # Parse args
    transport = "stdio"
    host = "127.0.0.1"
    port = 8000

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--transport" and i + 1 < len(args):
            transport = args[i + 1]
            i += 2
        elif args[i] == "--host" and i + 1 < len(args):
            host = args[i + 1]
            i += 2
        elif args[i] == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
            i += 2
        else:
            i += 1

    # Run server - clean FastMCP 3.0 execution
    try:
        if transport == "stdio":
            mcp.run()
        elif transport in ("http", "streamable-http"):
            mcp.run(transport="http", host=host, port=port)
        elif transport == "sse":
            mcp.run(transport="sse", host=host, port=port)
        else:
            print(f"Unknown transport: {transport}")
            sys.exit(1)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        if transport != "stdio":
            print(f"Server error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
