import json
from traceback import format_exception

import httpx
import pytest
from langchain_core.tools import ToolException
from langchain_tests.unit_tests.tools import ToolsUnitTests
from pydantic import ValidationError

from langchain_adscrawl import AdsCrawlReadTool

KEY = "offline-test-key"
URL = "https://example.com/article"


@pytest.fixture(autouse=True)
def isolate_credentials(monkeypatch):
    monkeypatch.delenv("ADSCRAWL_API_KEY", raising=False)


def client_for(handler, **kwargs):
    return httpx.Client(transport=httpx.MockTransport(handler), **kwargs)


class TestAdsCrawlReadTool(ToolsUnitTests):
    @property
    def tool_constructor(self):
        return AdsCrawlReadTool

    @property
    def tool_constructor_params(self):
        return {"api_key": KEY}

    @property
    def tool_invoke_params_example(self):
        return {"url": URL}


def test_sync_html_contract_and_explicit_request_options():
    seen = {}

    def handler(request):
        seen.update(url=str(request.url), body=request.read(), headers=request.headers)
        return httpx.Response(200, text="<html>ok</html>")

    c = client_for(handler)
    try:
        assert AdsCrawlReadTool(api_key=KEY, client=c).invoke({"url": URL}) == "<html>ok</html>"
    finally:
        c.close()
    assert seen["url"] == AdsCrawlReadTool.endpoint
    assert json.loads(seen["body"])["contentMode"] == "html"
    assert seen["headers"]["x-api-key"] == KEY


@pytest.mark.parametrize("mode,body", [("html", "<p>x</p>"), ("markdown", "# x")])
def test_text_modes_are_returned_raw(mode, body):
    c = client_for(lambda r: httpx.Response(200, text=body))
    try:
        assert AdsCrawlReadTool(api_key=KEY, client=c).invoke(
            {"url": URL, "content_mode": mode}
        ) == body
    finally:
        c.close()


@pytest.mark.parametrize("value", [{"title": "x"}, [], "text", 1, None])
def test_json_requires_article_object(value):
    c = client_for(
        (lambda r: httpx.Response(200, text="null"))
        if value is None
        else (lambda r: httpx.Response(200, json=value))
    )
    try:
        tool = AdsCrawlReadTool(api_key=KEY, client=c)
        if isinstance(value, dict):
            assert tool.invoke({"url": URL, "content_mode": "json"}) == value
        else:
            with pytest.raises(ToolException, match="article object"):
                tool.invoke({"url": URL, "content_mode": "json"})
    finally:
        c.close()


@pytest.mark.asyncio
async def test_async_contract():
    seen = {}

    def handler(request):
        seen["body"] = request.read()
        return httpx.Response(200, text="# async")

    c = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        assert await AdsCrawlReadTool(api_key=KEY, async_client=c).ainvoke(
            {"url": URL, "content_mode": "markdown"}
        ) == "# async"
    finally:
        await c.aclose()
    assert json.loads(seen["body"])["contentMode"] == "markdown"


@pytest.mark.parametrize("status", [301, 302, 307, 308, 401, 402, 422, 429, 500])
def test_every_non_2xx_status_is_tool_error(status):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            status, headers={"location": "https://leak.invalid"}, text="secret body"
        )

    c = client_for(handler, follow_redirects=True)
    try:
        with pytest.raises(ToolException, match=f"HTTP {status}"):
            AdsCrawlReadTool(api_key=KEY, client=c).invoke({"url": URL})
    finally:
        c.close()
    assert len(seen) == 1


def test_http_errors_hide_chain_and_raw_error():
    fake_secret = "unit-secret-123"
    original = "original request body unit-secret-123"

    def handler(request):
        raise httpx.ReadError(original, request=request)

    c = client_for(handler)
    try:
        with pytest.raises(ToolException) as info:
            AdsCrawlReadTool(api_key=fake_secret, client=c)._run(URL)
    finally:
        c.close()
    error = info.value
    assert str(error) == "AdsCrawl request could not be completed"
    assert error.__cause__ is None
    assert fake_secret not in "".join(format_exception(error))
    assert original not in "".join(format_exception(error))


def test_invalid_json_and_timeout_are_safe():
    c = client_for(lambda r: httpx.Response(200, text="not json"))
    try:
        with pytest.raises(ToolException, match="invalid JSON"):
            AdsCrawlReadTool(api_key=KEY, client=c).invoke({"url": URL, "content_mode": "json"})
    finally:
        c.close()

    def timeout(r):
        raise httpx.ReadTimeout("raw secret error")

    c = client_for(timeout)
    try:
        with pytest.raises(ToolException, match="timed out") as info:
            AdsCrawlReadTool(api_key=KEY, client=c).invoke({"url": URL})
        assert info.value.__cause__ is None
        assert "raw secret error" not in "".join(format_exception(info.value))
    finally:
        c.close()


def test_validation_schema_and_strict_timeout():
    for bad in ["ftp://example.com", "https://user:pass@example.com", "https://example.com:8080"]:
        with pytest.raises(ValidationError):
            AdsCrawlReadTool().invoke({"url": bad})
    for bad in ["pdf", "HTML"]:
        with pytest.raises(ValidationError):
            AdsCrawlReadTool().invoke({"url": URL, "content_mode": bad})
    for bad in [True, 1.5, 0, 3_600_001]:
        with pytest.raises(ValidationError):
            AdsCrawlReadTool(timeout=bad)
    for bad in ["wait", 1]:
        with pytest.raises(ValidationError):
            AdsCrawlReadTool(wait_until=bad)

    schema = AdsCrawlReadTool(api_key=KEY).tool_call_schema.model_json_schema()
    assert schema["properties"]["content_mode"]["enum"] == ["html", "markdown", "json"]
    assert set(schema["properties"]) == {"url", "content_mode", "selector"}


def test_selector_and_payload_timeout():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.read())
        return httpx.Response(200, text="x")

    c = client_for(handler)
    try:
        AdsCrawlReadTool(api_key=KEY, client=c, timeout=5000, wait_until="load").invoke(
            {"url": URL, "selector": "main"}
        )
    finally:
        c.close()
    assert seen["body"] == {
        "url": URL, "contentMode": "html", "waitUntil": "load", "timeout": 5000,
        "contentSelector": "main",
    }


@pytest.mark.parametrize("value", [None, "", "YOUR_ADSCRAWL_API_KEY"])
def test_missing_or_placeholder_key_rejected_before_network(value):
    called = False

    def handler(request):
        nonlocal called
        called = True
        raise AssertionError("network must not be called")

    c = client_for(handler)
    try:
        kwargs = {} if value is None else {"api_key": value}
        with pytest.raises(ToolException, match="not configured"):
            AdsCrawlReadTool(client=c, **kwargs).invoke({"url": URL})
    finally:
        c.close()
    assert not called


def test_placeholder_environment_key_rejected(monkeypatch):
    monkeypatch.setenv("ADSCRAWL_API_KEY", "YOUR_ADSCRAWL_API_KEY")
    with pytest.raises(ToolException, match="not configured"):
        AdsCrawlReadTool().invoke({"url": URL})


def test_key_not_serialized_and_env(monkeypatch):
    monkeypatch.setenv("ADSCRAWL_API_KEY", "env-secret")
    tool = AdsCrawlReadTool()
    assert "env-secret" not in repr(tool) and "env-secret" not in str(tool.model_dump())


@pytest.mark.parametrize("url", ["http://:80", "https://:443/path"])
def test_missing_hostname_rejected_before_network(url):
    calls = []
    with client_for(lambda request: calls.append(request)) as client:
        with pytest.raises(ValidationError):
            AdsCrawlReadTool(api_key=KEY, client=client).invoke({"url": url})
    assert calls == []


def test_whitespace_key_rejected_before_network():
    calls = []
    with client_for(lambda request: calls.append(request)) as client:
        with pytest.raises(ToolException, match="not configured"):
            AdsCrawlReadTool(api_key="   ", client=client).invoke({"url": URL})
    assert calls == []


def test_injected_client_timeout_and_ownership():
    seen = {}

    def handler(request):
        seen.update(request.extensions["timeout"])
        return httpx.Response(200, text="page")

    with client_for(handler, timeout=999) as client:
        AdsCrawlReadTool(api_key=KEY, client=client, timeout=5000).invoke({"url": URL})
        assert not client.is_closed
    assert seen == {key: 5.0 for key in ("connect", "read", "write", "pool")}
