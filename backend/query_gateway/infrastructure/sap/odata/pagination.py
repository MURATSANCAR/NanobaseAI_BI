"""OData next-link safety."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from query_gateway.domain.errors import GatewayError

ODATA_PAGINATION_VIOLATION = "ODATA_PAGINATION_VIOLATION"

MAX_PAGES = 10


def validate_next_link(
    next_link: str,
    *,
    base_url: str,
    entity_set: str,
    original_select: str | None = None,
    page_index: int = 0,
) -> str:
    if page_index >= MAX_PAGES:
        raise GatewayError(ODATA_PAGINATION_VIOLATION, "Pagination page limit exceeded.", status=400)

    base = urlparse(base_url)
    nxt = urlparse(next_link)

    if nxt.scheme and nxt.scheme != base.scheme:
        raise GatewayError(ODATA_PAGINATION_VIOLATION, "Next-link scheme mismatch.", status=400)
    if nxt.netloc and nxt.netloc != base.netloc:
        raise GatewayError(ODATA_PAGINATION_VIOLATION, "Next-link host mismatch.", status=400)

    path = nxt.path or ""
    if entity_set and entity_set not in path:
        raise GatewayError(ODATA_PAGINATION_VIOLATION, "Next-link entity set mismatch.", status=400)

    if original_select:
        qs = parse_qs(nxt.query or "")
        sel = (qs.get("$select") or [None])[0]
        if sel and sel != original_select:
            raise GatewayError(
                ODATA_PAGINATION_VIOLATION,
                "Next-link $select changed.",
                status=400,
            )

    # Rebuild absolute URL only from approved base + relative path/query
    if not nxt.netloc:
        return f"{base.scheme}://{base.netloc}{path}?{nxt.query}" if nxt.query else f"{base.scheme}://{base.netloc}{path}"
    return next_link
