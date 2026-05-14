"""Error handling middleware for Crawl4AI MCP Server.

Exception catching is handled by ToolPipeline.execute() which wraps the
handler call in a try/except. This middleware exists as a sentinel to
indicate that error handling is active in the pipeline.
"""

from .pipeline import Middleware, PipelineContext


class ErrorHandlingMiddleware(Middleware):
    """Sentinel middleware — error catching is done in ToolPipeline.execute()."""
