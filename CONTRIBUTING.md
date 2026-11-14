# Contributing

Keep this integration small, predictable and faithful to the public AdsCrawl API. Fixes, tests and documentation improvements are welcome. Please discuss a new endpoint or a new capability before expanding the public surface.

## Local checks

```bash
python -m pip install -e ".[test,lint]" build
python -m pytest tests/unit_tests
python -m ruff check .
python -m build
python -m pip check
```

Use Python 3.10 or later. Before changing a supported dependency range, test the proposed lower bound as well as the current supported version. Pin `langchain-tests` because changes to its standard suite can change the requirements for an integration.

All tests under `tests/unit_tests/` are offline. Keep the applicable `langchain_tests.unit_tests.tools.ToolsUnitTests` adapter as well as focused tests of AdsCrawl's request contract. Test both sync and async paths, supported content modes, key exclusion from schema/serialization, client ownership, URL validation, HTTP status errors, redirects, timeouts and safe error messages. Do not replace a failing assertion with an unconditional skip.

No real service key belongs in this repository, a fixture, a test cassette, a screenshot or an issue. Use explicit synthetic credentials and mock HTTP transports. A passing mocked test is not live-service compatibility verification.

## Public API and documentation

- Keep `AdsCrawlReadTool` and `AdsCrawlReadInput` exports stable unless making a documented breaking change.
- Use only fields documented by the [official `/html` reference](https://docs.adscrawl.net/api-reference/html). Preserve the distinction between rendered HTML and Readability article extraction.
- Do not expose credentials, arbitrary service endpoints or unrelated browser actions to model-generated tool arguments.
- Do not add automatic retries or follow redirects without a careful security and usage-cost review.
- Update the README when changing any input, returned type, default or failure behavior.
- Review any tracing/logging changes for secret and page-content disclosure.

## Release checklist

1. Run the offline suite, lint, build and dependency checks above.
2. Install the built wheel into a clean environment, import the public classes, inspect the tool schema and run a mocked invocation.
3. Confirm that the wheel and source distribution contain the README, license and intended module files, but no environments, caches or credentials.
4. Perform a separately authorized live smoke test before claiming live compatibility; record its actual scope. A test with a real key can consume service credits and expose page content to a provider. Do not run it automatically in normal CI.
5. Publish a versioned registry release only through an authorized maintainer account. The initial GitHub version is source-only, not a completed PyPI release.
6. Only **after** a PyPI release exists, use LangChain's [Integration listing issue form](https://github.com/langchain-ai/docs/issues/new?template=06-integration-submission.yml). Do not tick its publication confirmation early, open a manual listing PR, request featured status as fact, or submit package code to the LangChain monorepo.

If a third-party community accepts an integration example, describe it as an AdsCrawl-maintained community example. Do not call it official LangChain support, an endorsement, or a merged listing before that has happened.
