"""Read-only Wix Stores access provider for the ROVEBURY Council.

This adapter implements the allowlisted ``wix`` capability from
``backend.access``. Phase 5D.1 intentionally keeps it isolated from the
default live registry until its deterministic contract is validated.

Security and scope:
- fixed ROVEBURY Wix site ID; the user query cannot choose another site;
- fixed Wix Stores Catalog V3 read endpoints only;
- POST is used only for Wix query/search read operations;
- bounded product results and bounded evidence text;
- API key comes from environment or explicit constructor injection;
- credentials are sent only in HTTP headers and never enter evidence;
- no LLM calls and no Council orchestration changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
import re
from typing import Any, Mapping, Sequence

import httpx

from .access import CAPABILITY_WIX


WIX_QUERY_PRODUCTS_URL = "https://www.wixapis.com/stores/v3/products/query"
WIX_SEARCH_PRODUCTS_URL = "https://www.wixapis.com/stores/v3/products/search"
_ALLOWED_URLS = frozenset({WIX_QUERY_PRODUCTS_URL, WIX_SEARCH_PRODUCTS_URL})

DEFAULT_SITE_ID = os.getenv(
    "ROVEBURY_WIX_SITE_ID",
    "b72c88db-3b85-411c-a838-cca09faeaa9a",
)
DEFAULT_SITE_URL = os.getenv(
    "ROVEBURY_WIX_SITE_URL",
    "https://www.rovebury.com/",
)
DEFAULT_TIMEOUT_SECONDS = 15.0
MAX_PRODUCTS = 8
MAX_SEARCH_EXPRESSION_CHARS = 80
MAX_EVIDENCE_CHARS = 8_000

_SITE_ID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


@dataclass(frozen=True)
class WixReadIntent:
    """Deterministic read intent derived from the raw current query."""

    kind: str
    search_expression: str | None = None


def _normalise_space(value: str) -> str:
    return " ".join((value or "").strip().split())


def _safe_site_id(site_id: str) -> str:
    candidate = _normalise_space(site_id)
    if not _SITE_ID_RE.fullmatch(candidate):
        raise ValueError("site_id must be a Wix GUID")
    return candidate.lower()


def _bounded_text(value: Any, limit: int) -> str:
    text = _normalise_space(str(value if value is not None else ""))
    return text[:limit] if len(text) > limit else text


def _quoted_expression(text: str) -> str | None:
    matches = re.findall(r'''["“”']([^"“”']{2,120})["“”']''', text)
    if not matches:
        return None
    best = max(matches, key=len)
    best = _bounded_text(best, MAX_SEARCH_EXPRESSION_CHARS)
    return best or None


def parse_wix_read_intent(query: str) -> WixReadIntent:
    """Parse a deliberately small Wix read-only product intent.

    Product-name lookup is accepted only when a name is explicitly delimited
    or introduced by a narrow ``product named/called`` phrase. Everything
    else falls back to a bounded catalog read instead of guessing entities.
    """
    text = _normalise_space(query)
    quoted = _quoted_expression(text)
    if quoted:
        return WixReadIntent(kind="search_product", search_expression=quoted)

    patterns = (
        r"\bproduct\s+(?:named|called)\s+([^?.!]{2,80})",
        r"\bproduto\s+(?:chamado|chamada)\s+([^?.!]{2,80})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            expression = _bounded_text(
                match.group(1), MAX_SEARCH_EXPRESSION_CHARS
            )
            if expression:
                return WixReadIntent(
                    kind="search_product",
                    search_expression=expression,
                )

    return WixReadIntent(kind="catalog")


def _money_text(payload: Mapping[str, Any] | None) -> str:
    if not isinstance(payload, Mapping):
        return ""
    formatted = _bounded_text(payload.get("formattedAmount", ""), 60)
    if formatted:
        return formatted
    return _bounded_text(payload.get("amount", ""), 60)


def _price_range_text(product: Mapping[str, Any]) -> str:
    price_range = product.get("actualPriceRange", {})
    if not isinstance(price_range, Mapping):
        return ""
    minimum = _money_text(price_range.get("minValue"))
    maximum = _money_text(price_range.get("maxValue"))
    if minimum and maximum:
        return minimum if minimum == maximum else f"{minimum} to {maximum}"
    return minimum or maximum


def _product_url(product: Mapping[str, Any]) -> str:
    url_info = product.get("url", {})
    if not isinstance(url_info, Mapping):
        return ""
    return _bounded_text(url_info.get("url", ""), 1_000)


def _inventory_status(product: Mapping[str, Any]) -> str:
    inventory = product.get("inventory", {})
    if not isinstance(inventory, Mapping):
        return ""
    return _bounded_text(inventory.get("availabilityStatus", ""), 100)


def _format_product(product: Mapping[str, Any]) -> str:
    lines = []
    fields = (
        ("Name", product.get("name")),
        ("Product ID", product.get("id")),
        ("Slug", product.get("slug")),
        ("Visible", product.get("visible")),
        ("Product type", product.get("productType")),
        ("Availability", _inventory_status(product)),
        ("Current price", _price_range_text(product)),
        ("Currency", product.get("currency")),
        ("Updated at", product.get("updatedDate")),
        ("Product URL", _product_url(product)),
    )
    for label, value in fields:
        if value is None or value == "":
            continue
        if isinstance(value, bool):
            rendered = "yes" if value else "no"
        else:
            rendered = _bounded_text(value, 1_000)
        if rendered:
            lines.append(f"{label}: {rendered}")
    return "\n".join(lines)


class WixReadProvider:
    """Callable fixed-scope read-only provider for the ``wix`` capability."""

    def __init__(
        self,
        *,
        site_id: str = DEFAULT_SITE_ID,
        site_url: str = DEFAULT_SITE_URL,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.site_id = _safe_site_id(site_id)
        self.site_url = _normalise_space(site_url) or DEFAULT_SITE_URL
        self.api_key = (
            api_key if api_key is not None else os.getenv("ROVEBURY_WIX_API_KEY")
        )
        if not self.api_key:
            raise ValueError("Wix API key is not configured")
        self.timeout = float(timeout)
        self.transport = transport

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": self.api_key,
            "wix-site-id": self.site_id,
            "User-Agent": "ROVEBURY-Council/1.0",
        }

    async def _post_json(self, url: str, body: dict[str, Any]) -> Any:
        if url not in _ALLOWED_URLS:
            raise ValueError("Wix provider URL is not allowlisted")
        async with httpx.AsyncClient(
            headers=self._headers(),
            timeout=self.timeout,
            follow_redirects=False,
            transport=self.transport,
        ) as client:
            response = await client.post(url, json=body)
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _observed_at() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _catalog_body(self) -> dict[str, Any]:
        return {
            "query": {"cursorPaging": {"limit": MAX_PRODUCTS}},
            "fields": ["URL", "CURRENCY"],
        }

    def _search_body(self, expression: str) -> dict[str, Any]:
        return {
            "search": {
                "search": {"expression": expression},
                "cursorPaging": {"limit": MAX_PRODUCTS},
            },
            "fields": ["URL", "CURRENCY"],
        }

    def _build_evidence(
        self,
        products: Sequence[Mapping[str, Any]],
        *,
        intent: WixReadIntent,
    ) -> list[dict[str, str]]:
        bounded_products = list(products[:MAX_PRODUCTS])
        if intent.kind == "search_product":
            heading = (
                "Wix Stores live product search"
                f' for "{intent.search_expression}"'
            )
        else:
            heading = "Wix Stores live catalog snapshot"

        blocks = [
            heading,
            f"Site ID: {self.site_id}",
            f"Products returned: {len(bounded_products)}",
        ]
        for index, product in enumerate(bounded_products, start=1):
            formatted = _format_product(product)
            if not formatted:
                continue
            blocks.extend(["", f"[Product {index}]", formatted])

        content = "\n".join(blocks)
        if len(content) > MAX_EVIDENCE_CHARS:
            content = content[:MAX_EVIDENCE_CHARS] + "\n[Wix evidence truncated]"

        locator = self.site_url
        if intent.kind == "search_product" and len(bounded_products) == 1:
            locator = _product_url(bounded_products[0]) or locator

        return [{
            "source_name": "Wix Stores catalog (ROVEBURY)",
            "locator": locator,
            "observed_at": self._observed_at(),
            "content": content,
        }]

    async def __call__(self, request: dict[str, Any]) -> list[dict[str, str]]:
        capability = str(request.get("capability", ""))
        if capability != CAPABILITY_WIX:
            raise ValueError("WixReadProvider only accepts the wix capability")

        query = str(request.get("query", ""))
        intent = parse_wix_read_intent(query)

        if intent.kind == "search_product":
            expression = _bounded_text(
                intent.search_expression,
                MAX_SEARCH_EXPRESSION_CHARS,
            )
            if not expression:
                return []
            payload = await self._post_json(
                WIX_SEARCH_PRODUCTS_URL,
                self._search_body(expression),
            )
        else:
            payload = await self._post_json(
                WIX_QUERY_PRODUCTS_URL,
                self._catalog_body(),
            )

        if not isinstance(payload, dict):
            return []
        products = payload.get("products", [])
        if not isinstance(products, list):
            return []
        safe_products = [p for p in products if isinstance(p, Mapping)]
        return self._build_evidence(safe_products, intent=intent)


def build_wix_read_provider(
    *,
    site_id: str = DEFAULT_SITE_ID,
    site_url: str = DEFAULT_SITE_URL,
    api_key: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    transport: httpx.AsyncBaseTransport | None = None,
) -> WixReadProvider:
    """Construct the provider for later explicit registry registration."""
    return WixReadProvider(
        site_id=site_id,
        site_url=site_url,
        api_key=api_key,
        timeout=timeout,
        transport=transport,
    )
