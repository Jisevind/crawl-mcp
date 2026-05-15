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
# (libnspr4, libnss3, libdbus-1-3, etc.) inside Docker/uvx environments
# where LD_LIBRARY_PATH may not propagate to child processes.
try:
    import subprocess
    # Check if critical Chromium library is available; install if missing
    rc = subprocess.run(
        ["ldconfig", "-p"],
        capture_output=True, timeout=10
    )
    if b"libnspr4" not in rc.stdout:
        # Install just the critical libs first (small packages, fast)
        subprocess.run(
            ["apt-get", "update", "-qq"],
            capture_output=True, timeout=60
        )
        subprocess.run(
            ["apt-get", "install", "-y", "-qq", "--no-install-recommends",
             "libnspr4", "libnss3", "libdbus-1-3",
             "libatk1.0-0t64", "libatk-bridge2.0-0t64", "libcups2t64",
             "libxkbcommon0", "libatspi2.0-0t64", "libxcomposite1",
             "libxdamage1", "libxfixes3", "libxrandr2", "libgbm1",
             "libasound2t64"],
            capture_output=True, timeout=120
        )
        subprocess.run(["ldconfig"], capture_output=True, timeout=10)
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
