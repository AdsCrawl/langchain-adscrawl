# langchain-adscrawl

A small, standalone [LangChain](https://docs.langchain.com/oss/python/langchain/tools) tool for reading rendered public webpages through [AdsCrawl's `/html` API](https://docs.adscrawl.net/api-reference/html).

Maintained by AdsCrawl. This is not a LangChain-maintained package, an endorsement, or a claim of inclusion in LangChain's official integration directory. The initial version is distributed as source on GitHub; it has **not been published to PyPI**.

## What the tool does

`AdsCrawlReadTool` implements LangChain's `BaseTool` interface with both `invoke()` and native-async `ainvoke()`. It sends one request to `https://api.adscrawl.net/html` and returns the response in one of three modes:

| `content_mode` | Returned value | Intended use |
| --- | --- | --- |
| `html` (default) | Rendered HTML string | General page content, including non-article pages |
| `markdown` | Readability Markdown string | Readable article content |
| `json` | Readability article dictionary | Article title, byline, excerpt and body, when available |

Markdown and JSON are **article extraction modes**, not a promise to convert any entire site into Markdown or arbitrary structured data. They can fail when Readability does not find an article. An optional `selector` maps to the API's `contentSelector` field; with article modes, Readability runs against that element.

This package does not expose screenshots, forms, cookies, proxy credentials, CDP, MCP sessions or persistent browser profiles. Those are different AdsCrawl capabilities, not features of this tool.

## Install from source

Python 3.10 or later and Git are required:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install "git+https://github.com/AdsCrawl/langchain-adscrawl.git@main"
```

For reproducible deployments, replace `main` with a reviewed commit SHA. Do not use `pip install langchain-adscrawl` until a registry release actually exists.

## Read a page without an LLM

Create your own AdsCrawl key following the [official quickstart](https://docs.adscrawl.net/quickstart), then set it in your server environment:

```bash
export ADSCRAWL_API_KEY="YOUR_ADSCRAWL_API_KEY"
```

The value above is only a placeholder and must be replaced locally. Never commit a real key. The package does not load a `.env` file automatically.

```python
from langchain_adscrawl import AdsCrawlReadTool

reader = AdsCrawlReadTool()
html = reader.invoke({
    "url": "https://example.com",
    "content_mode": "html",
})
print(html)
```

No OpenAI or other model key is needed for a direct tool invocation. A real AdsCrawl request may consume credits; this repository and its source installation are free, not necessarily the underlying service usage.

## Async and article output

```python
import asyncio
from langchain_adscrawl import AdsCrawlReadTool

async def main():
    reader = AdsCrawlReadTool(timeout=120_000, wait_until="domcontentloaded")
    article = await reader.ainvoke({
        "url": "https://example.com/article",
        "content_mode": "json",
        # "selector": "article",  # Only use a selector present on your target page.
    })
    print(article.get("title"))

asyncio.run(main())
```

`https://example.com/article` is an illustrative URL, not a claim that an article exists there. Use a public article you are authorized to access. `timeout` is in milliseconds (1–3,600,000); `wait_until` is `domcontentloaded`, `load`, or `networkidle`. A later navigation event can help deferred page content, but can also take longer or time out.

You can also pass `api_key` as a `SecretStr` constructor value obtained from your secret manager. The model-facing input schema contains only `url`, `content_mode` and `selector`, never the key or transport configuration.

## Use in a LangChain agent

Pass the tool instance in the `tools` list of LangChain's [`create_agent`](https://docs.langchain.com/oss/python/langchain/agents) just as you would another `BaseTool`. Configure your model separately; this package deliberately does not depend on a model provider or choose a model for you.

Before giving any agent the tool, enforce your own URL/domain allowlist and usage budget. The tool validates HTTP(S) URL syntax, rejects embedded credentials and non-80/443 ports, but it is **not a complete SSRF filter, authorization layer or prompt-injection defense**. Page content is untrusted data.

## Errors, clients and usage limits

- Non-success HTTP responses and transport failures raise a sanitized LangChain `ToolException`. Raw error bodies, headers and transport exception chains are not forwarded to the model.
- The default implementation does not retry requests and explicitly refuses HTTP redirects at the API endpoint. Decide whether another attempt is appropriate before making a second potentially billable request.
- A local timeout or cancellation does not establish whether a remote task completed. This is not a durable task manager.
- The tool creates and closes a local HTTP client for each call by default. You may inject `client=httpx.Client(...)` and/or `async_client=httpx.AsyncClient(...)` for pooling or tests; their lifecycle belongs to you. The configured timeout and redirect refusal still apply to the request.
- Authentication, credits, concurrency limits, site restrictions and Readability failures can prevent a result. No bypass or success guarantee is made.

The target URL and configuration are sent to AdsCrawl. If you feed the result to a model, that content is also sent to your selected model provider. Your application's callbacks or LangSmith tracing may record URLs and tool outputs; review those settings before using sensitive pages. This library does not configure tracing for your application.

## Development and validation

```bash
git clone https://github.com/AdsCrawl/langchain-adscrawl.git
cd langchain-adscrawl
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test,lint]" build
python -m pytest tests/unit_tests
python -m ruff check .
python -m build
python -m pip check
```

Tests use placeholder credentials and mocked transports. They include the applicable LangChain standard **unit** suite and request-contract, async, validation and error-safety checks. They do not invoke the real AdsCrawl service or a model, and are not production end-to-end verification. See [CONTRIBUTING.md](CONTRIBUTING.md) for the maintenance and release checklist.

The architecture follows LangChain's [standalone integration implementation guide](https://docs.langchain.com/oss/python/contributing/implement-langchain) and [standard test guide](https://docs.langchain.com/oss/python/contributing/standard-tests-langchain). Official directory listing is a separate process that requires a published package; see [LangChain's current publishing rules](https://docs.langchain.com/oss/python/contributing/publish-langchain).

## License

MIT. See [LICENSE](LICENSE).
