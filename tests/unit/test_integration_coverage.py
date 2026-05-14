"""Integration-level tests for remaining CODE_REVIEW.md coverage gaps.

Covers:
- 7-stage anti-bot fallback chain (crawl_url_with_fallback)
- LLM client calls (OpenAI, Anthropic, Ollama)
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# 7-stage anti-bot fallback chain
# ---------------------------------------------------------------------------


def _make_mock_response(success=True, url="http://example.com", content="", markdown="",
                        extracted_data=None, error=None):
    """Build a quick mock result dict matching CrawlResponse shape."""
    resp = MagicMock()
    resp.success = success
    resp.url = url
    resp.content = content
    resp.markdown = markdown
    resp.raw_content = None
    if extracted_data is None:
        extracted_data = {}
    resp.extracted_data = extracted_data
    resp.error = error
    return resp


class TestFallbackChain:
    """Integration tests for the 7-stage anti-bot fallback chain."""

    @pytest.mark.asyncio
    async def test_static_fast_path_succeeds_returns_early(self):
        """Stage 1: static fetch finds content → no browser stages needed."""
        from crawl4ai_mcp.core.crawler_fallback import crawl_url_with_fallback

        mock_result = _make_mock_response(content="<html><body>Real content here</body></html>",
                                          markdown="Real content")

        with patch("crawl4ai_mcp.core.crawler_fallback._static_fetch_content",
                   new_callable=AsyncMock) as mock_static, \
             patch("crawl4ai_mcp.core.crawler_fallback._extract_spa_json_data",
                   return_value=(False, {}, "")) as mock_spa, \
             patch("crawl4ai_mcp.core.crawler_fallback._detect_spa_framework",
                   return_value=("", "")) as mock_detect, \
             patch("crawl4ai_mcp.core.crawler_fallback.crawl_url",
                   return_value=mock_result) as mock_crawl, \
             patch("crawl4ai_mcp.core.crawler_fallback._has_meaningful_content",
                   return_value=(True, "html")) as mock_meaningful, \
             patch("crawl4ai_mcp.core.crawler_fallback._is_block_page",
                   return_value=False):
            mock_static.return_value = (True, "<html><body>Test</body></html>", "")

            result = await crawl_url_with_fallback(url="http://test.example.com")

            assert result.success is True
            mock_crawl.assert_called()  # static fast path calls crawl_url internally
            assert mock_static.called

    @pytest.mark.asyncio
    async def test_static_fetch_fails_falls_through_to_browser(self):
        """Static fetch fails → browser-based stages fire."""
        from crawl4ai_mcp.core.crawler_fallback import crawl_url_with_fallback

        mock_browser_result = _make_mock_response(content="Browser content", markdown="Browser MD")

        with patch("crawl4ai_mcp.core.crawler_fallback._static_fetch_content",
                   new_callable=AsyncMock) as mock_static, \
             patch("crawl4ai_mcp.core.crawler_fallback._extract_spa_json_data",
                   return_value=(False, {}, "")) as mock_spa, \
             patch("crawl4ai_mcp.core.crawler_fallback._detect_spa_framework",
                   return_value=("", "")) as mock_detect, \
             patch("crawl4ai_mcp.core.crawler_fallback._has_meaningful_content",
                   return_value=(True, "html")) as mock_meaningful, \
             patch("crawl4ai_mcp.core.crawler_fallback._is_block_page",
                   return_value=False), \
             patch("crawl4ai_mcp.core.crawler_fallback.crawl_url",
                   return_value=mock_browser_result) as mock_crawl, \
             patch("crawl4ai_mcp.core.crawler_fallback.get_session_manager",
                   return_value=None), \
             patch("crawl4ai_mcp.core.crawler_fallback.get_strategy_cache",
                   return_value=None):
            mock_static.return_value = (False, "", "Connection refused")

            result = await crawl_url_with_fallback(
                url="http://blocked.example.com", timeout=15)

            assert result.success is True
            # crawl_url should have been called for stage 2 (browser)
            # at least once beyond the static fast path
            assert mock_crawl.call_count >= 2

    @pytest.mark.asyncio
    async def test_block_page_detection_skips_strategy(self):
        """Content detected as block page → strategy skipped (not treated as success)."""
        from crawl4ai_mcp.core.crawler_fallback import crawl_url_with_fallback

        blocked = _make_mock_response(content="Access Denied. Please verify you are human.",
                                      markdown="Access Denied")

        with patch("crawl4ai_mcp.core.crawler_fallback._static_fetch_content",
                   new_callable=AsyncMock) as mock_static, \
             patch("crawl4ai_mcp.core.crawler_fallback._extract_spa_json_data",
                   return_value=(False, {}, "")) as mock_spa, \
             patch("crawl4ai_mcp.core.crawler_fallback._detect_spa_framework",
                   return_value=("", "")) as mock_detect, \
             patch("crawl4ai_mcp.core.crawler_fallback._has_meaningful_content",
                   return_value=(True, "html")) as mock_meaningful, \
             patch("crawl4ai_mcp.core.crawler_fallback._is_block_page",
                   return_value=True), \
             patch("crawl4ai_mcp.core.crawler_fallback.crawl_url",
                   return_value=blocked) as mock_crawl, \
             patch("crawl4ai_mcp.core.crawler_fallback.get_session_manager",
                   return_value=None), \
             patch("crawl4ai_mcp.core.crawler_fallback.get_strategy_cache",
                   return_value=None):
            mock_static.return_value = (False, "", "Timeout")

            result = await crawl_url_with_fallback(
                url="http://blocked.example.com", timeout=10)

            assert result.success is False
            assert "all" in result.error.lower() or "failed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_all_stages_fail_returns_structured_error(self):
        """Every single stage (including AMP/RSS) fails → structured error dict."""
        from crawl4ai_mcp.core.crawler_fallback import crawl_url_with_fallback

        with patch("crawl4ai_mcp.core.crawler_fallback._static_fetch_content",
                   new_callable=AsyncMock) as mock_static, \
             patch("crawl4ai_mcp.core.crawler_fallback._extract_spa_json_data",
                   return_value=(False, {}, "")) as mock_spa, \
             patch("crawl4ai_mcp.core.crawler_fallback._detect_spa_framework",
                   return_value=("", "")), \
             patch("crawl4ai_mcp.core.crawler_fallback._has_meaningful_content",
                   return_value=(False, "")) as mock_meaningful, \
             patch("crawl4ai_mcp.core.crawler_fallback._is_block_page",
                   return_value=False), \
             patch("crawl4ai_mcp.core.crawler_fallback.crawl_url",
                   new_callable=AsyncMock) as mock_crawl, \
             patch("crawl4ai_mcp.core.crawler_fallback._build_amp_url",
                   return_value="") as mock_amp, \
             patch("crawl4ai_mcp.core.crawler_fallback._try_fetch_rss_feed",
                   new_callable=AsyncMock) as mock_rss, \
             patch("crawl4ai_mcp.core.crawler_fallback.get_session_manager",
                   return_value=None), \
             patch("crawl4ai_mcp.core.crawler_fallback.get_strategy_cache",
                   return_value=None):
            mock_static.return_value = (False, "", "Connection error")
            mock_crawl.return_value = _make_mock_response(success=False, error="Simulated failure")
            mock_rss.return_value = (False, "", [])

            result = await crawl_url_with_fallback(
                url="http://completely-blocked.example.com", timeout=10)

            assert result.success is False
            assert "all" in result.error.lower()
            assert "fallback_strategies_attempted" in (result.extracted_data or {})

    @pytest.mark.asyncio
    async def test_json_extraction_from_static_html(self):
        """Stage 7: SPA JSON data extracted from static HTML fallback."""
        from crawl4ai_mcp.core.crawler_fallback import crawl_url_with_fallback

        mock_amp = MagicMock()
        with patch("crawl4ai_mcp.core.crawler_fallback._static_fetch_content",
                   new_callable=AsyncMock) as mock_static, \
             patch("crawl4ai_mcp.core.crawler_fallback._extract_spa_json_data") as mock_spa, \
             patch("crawl4ai_mcp.core.crawler_fallback._detect_spa_framework",
                   return_value=("", "")), \
             patch("crawl4ai_mcp.core.crawler_fallback._has_meaningful_content",
                   return_value=(False, "")), \
             patch("crawl4ai_mcp.core.crawler_fallback._is_block_page",
                   return_value=False), \
             patch("crawl4ai_mcp.core.crawler_fallback.crawl_url",
                   new_callable=AsyncMock) as mock_crawl, \
             patch("crawl4ai_mcp.core.crawler_fallback._build_amp_url",
                   return_value="") as mock_amp, \
             patch("crawl4ai_mcp.core.crawler_fallback._try_fetch_rss_feed",
                   new_callable=AsyncMock) as mock_rss, \
             patch("crawl4ai_mcp.core.crawler_fallback._build_json_extraction_response",
                   new_callable=AsyncMock) as mock_json_resp, \
             patch("crawl4ai_mcp.core.crawler_fallback.get_session_manager",
                   return_value=None), \
             patch("crawl4ai_mcp.core.crawler_fallback.get_strategy_cache",
                   return_value=None):
            mock_static.return_value = (True, "<html><script>window.__NUXT__={}</script></html>", "")
            mock_crawl.return_value = _make_mock_response(success=False, error="All browser attempts failed")
            mock_rss.return_value = (False, "", [])
            # Stage 7: JSON extraction succeeds
            mock_spa.return_value = (True, {"data": "extracted"}, "nuxt_data")
            mock_json_resp.return_value = _make_mock_response(
                success=True, content="Extracted SPA content", markdown="Extracted MD",
                extracted_data={"fallback_strategy_used": "json_extraction"})

            result = await crawl_url_with_fallback(
                url="http://spa.example.com", timeout=10)

            assert result.success is True
            assert "json_extraction" in str(result.extracted_data.get("fallback_strategy_used", ""))


# ---------------------------------------------------------------------------
# LLM client tests (OpenAI / Anthropic / Ollama)
# ---------------------------------------------------------------------------


def _mock_openai_response(content: str):
    """Return a minimal object that mimics openai chat completion response."""
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


def _mock_anthropic_response(content: str):
    """Return a minimal object that mimics anthropic messages response."""
    text_block = MagicMock()
    text_block.text = content
    response = MagicMock()
    response.content = [text_block]
    return response


class TestLLMClients:
    """Mock-based tests for OpenAI, Anthropic, and Ollama LLM clients."""

    @pytest.mark.asyncio
    async def test_openai_summarize_returns_structured_result(self):
        """LLMClient.summarize() via OpenAI returns expected dict shape."""
        from crawl4ai_mcp.utils.llm_client import LLMClient

        mock_resp = _mock_openai_response(json.dumps({
            "summary": "This is a test summary about web scraping.",
            "key_topics": ["Python", "scraping", "data extraction"],
            "main_insights": ["Insight 1", "Insight 2"],
            "content_type": "document"
        }))

        client = LLMClient(provider="openai", model="gpt-4", api_key="test-key")
        with patch("openai.AsyncOpenAI") as mock_openai_class:
            mock_openai_class.return_value = MagicMock()
            mock_openai_class.return_value.chat.completions.create = AsyncMock(
                return_value=mock_resp)

            result = await client.summarize(
                content="Test content " * 50,
                title="Test Page",
                url="http://example.com",
                summary_length="short",
                llm_provider="openai",
                llm_model="gpt-4",
            )

        assert result["success"] is True
        assert "summary" in result
        assert "key_topics" in result
        assert result["llm_provider"] == "openai"

    @pytest.mark.asyncio
    async def test_anthropic_summarize_returns_structured_result(self):
        """LLMClient.summarize() via Anthropic returns expected dict shape."""
        from crawl4ai_mcp.utils.llm_client import LLMClient

        mock_resp = _mock_anthropic_response(json.dumps({
            "summary": "Anthropic-generated summary.",
            "key_topics": ["AI", "language models"],
            "main_insights": ["Key finding"],
            "content_type": "webpage"
        }))

        client = LLMClient(provider="anthropic", model="claude-3-sonnet", api_key="test-key")
        with patch("anthropic.AsyncAnthropic") as mock_anthro_class:
            mock_anthro_class.return_value = MagicMock()
            mock_anthro_class.return_value.messages.create = AsyncMock(
                return_value=mock_resp)

            result = await client.summarize(
                content="Some test content for Anthropic.",
                title="Anthropic Test",
                summary_length="medium",
                llm_provider="anthropic",
                llm_model="claude-3-sonnet",
            )

        assert result["success"] is True
        assert result["llm_provider"] == "anthropic"
        assert "summary" in result

    @pytest.mark.asyncio
    async def test_ollama_summarize_via_mock(self):
        """LLMClient.summarize() via Ollama with mocked aiohttp."""
        from crawl4ai_mcp.utils.llm_client import LLMClient

        client = LLMClient(provider="ollama", model="llama3")

        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"response": json.dumps({
            "summary": "Ollama summary here.",
            "key_topics": ["local", "inference"],
            "main_insights": [],
            "content_type": "document"
        })})
        mock_session.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_response

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await client.summarize(
                content="Test content " * 30,
                title="Ollama Test",
                summary_length="short",
                llm_provider="ollama",
                llm_model="llama3",
            )

        assert result["success"] is True
        assert result["llm_provider"] == "ollama"
        assert "summary" in result

    @pytest.mark.asyncio
    async def test_unsupported_provider_returns_error(self):
        """Calling with an unsupported provider returns a structured error."""
        from crawl4ai_mcp.utils.llm_client import LLMClient

        client = LLMClient(provider="unsupported", model="bad-model")
        result = await client.summarize(
            content="content",
            llm_provider="unsupported",
            llm_model="bad-model",
        )
        assert result["success"] is False
        assert "not supported" in result.get("error", "").lower()

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_error(self):
        """OpenAI call without a valid API key returns structured error."""
        from crawl4ai_mcp.utils.llm_client import LLMClient

        client = LLMClient(provider="openai", model="gpt-4")
        # No API key set — should get caught
        with patch("crawl4ai_mcp.utils.llm_client.resolve_api_key", return_value=None):
            result = await client.summarize(
                content="content",
                llm_provider="openai",
                llm_model="gpt-4",
            )
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_empty_llm_response_handled(self):
        """LLM returning empty string is handled gracefully."""
        from crawl4ai_mcp.utils.llm_client import LLMClient

        mock_resp = _mock_openai_response("")
        client = LLMClient(provider="openai", model="gpt-4", api_key="test-key")

        with patch("openai.AsyncOpenAI") as mock_class:
            mock_class.return_value = MagicMock()
            mock_class.return_value.chat.completions.create = AsyncMock(
                return_value=mock_resp)

            result = await client.summarize(
                content="content",
                llm_provider="openai",
                llm_model="gpt-4",
            )

        assert result["success"] is False
        assert "empty" in result.get("error", "").lower()
