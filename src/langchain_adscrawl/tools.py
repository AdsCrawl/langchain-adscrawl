"""AdsCrawl LangChain tool implementation."""
from __future__ import annotations

import os
from typing import Any, ClassVar, Literal
from urllib.parse import urlsplit

import httpx
from langchain_core.tools import BaseTool, ToolException
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

ContentMode = Literal["html", "markdown", "json"]
WaitUntil = Literal["domcontentloaded", "load", "networkidle"]


class AdsCrawlReadInput(BaseModel):
    """Public inputs accepted by AdsCrawlReadTool."""

    url: str = Field(description="Public HTTP(S) URL to render and extract.")
    content_mode: ContentMode = Field(
        default="html", description="Response format: html, markdown, or json."
    )
    selector: str | None = Field(
        default=None, description="Optional CSS selector passed as contentSelector."
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("url must be an absolute HTTP(S) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("url must not contain credentials")
        if parsed.port not in {None, 80, 443}:
            raise ValueError("url may use only ports 80 and 443")
        return value


class AdsCrawlReadTool(BaseTool):
    """Read rendered HTML or Readability content through AdsCrawl."""

    name: str = "adscrawl_read"
    description: str = "Fetch a public URL via AdsCrawl as HTML, Readability Markdown, or JSON."
    args_schema: type[BaseModel] = AdsCrawlReadInput
    api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    timeout: int = Field(default=120_000, strict=True, ge=1, le=3_600_000, exclude=True)
    wait_until: WaitUntil = Field(default="domcontentloaded", exclude=True)
    client: httpx.Client | None = Field(default=None, exclude=True, repr=False)
    async_client: httpx.AsyncClient | None = Field(default=None, exclude=True, repr=False)
    model_config = ConfigDict(arbitrary_types_allowed=True)
    endpoint: ClassVar[str] = "https://api.adscrawl.net/html"

    def model_post_init(self, __context: Any) -> None:
        if self.api_key is None:
            value = os.getenv("ADSCRAWL_API_KEY")
            if value:
                object.__setattr__(self, "api_key", SecretStr(value))

    def _headers(self) -> dict[str, str]:
        value = self.api_key.get_secret_value() if self.api_key is not None else ""
        if not value.strip() or value.strip() in {"YOUR_ADSCRAWL_API_KEY", "your_api_key_here"}:
            raise ToolException("AdsCrawl API key is not configured")
        return {"content-type": "application/json", "x-api-key": value}

    def _payload(self, url: str, content_mode: ContentMode, selector: str | None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "url": url,
            "contentMode": content_mode,
            "waitUntil": self.wait_until,
            "timeout": self.timeout,
        }
        if selector is not None:
            payload["contentSelector"] = selector
        return payload

    @staticmethod
    def _result(response: httpx.Response, mode: ContentMode) -> str | dict[str, Any]:
        if not 200 <= response.status_code < 300:
            raise ToolException(f"AdsCrawl request failed with HTTP {response.status_code}")
        if mode != "json":
            return response.text
        try:
            result = response.json()
        except ValueError:
            raise ToolException("AdsCrawl returned an invalid JSON response") from None
        if not isinstance(result, dict):
            raise ToolException("AdsCrawl JSON response must be an article object")
        return result

    def _run(
        self, url: str, content_mode: ContentMode = "html", selector: str | None = None
    ) -> str | dict[str, Any]:
        own = self.client is None
        client = self.client or httpx.Client()
        try:
            response = client.post(
                self.endpoint,
                headers=self._headers(),
                json=self._payload(url, content_mode, selector),
                timeout=self.timeout / 1000,
                follow_redirects=False,
            )
            return self._result(response, content_mode)
        except httpx.TimeoutException:
            raise ToolException("AdsCrawl request timed out") from None
        except httpx.RequestError:
            raise ToolException("AdsCrawl request could not be completed") from None
        finally:
            if own:
                client.close()

    async def _arun(
        self, url: str, content_mode: ContentMode = "html", selector: str | None = None
    ) -> str | dict[str, Any]:
        own = self.async_client is None
        client = self.async_client or httpx.AsyncClient()
        try:
            response = await client.post(
                self.endpoint,
                headers=self._headers(),
                json=self._payload(url, content_mode, selector),
                timeout=self.timeout / 1000,
                follow_redirects=False,
            )
            return self._result(response, content_mode)
        except httpx.TimeoutException:
            raise ToolException("AdsCrawl request timed out") from None
        except httpx.RequestError:
            raise ToolException("AdsCrawl request could not be completed") from None
        finally:
            if own:
                await client.aclose()
