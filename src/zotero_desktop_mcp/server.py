from __future__ import annotations

import json
import re
from html import unescape

import httpx
from fastmcp import FastMCP

ZOTERO_BASE = "http://localhost:23119"
ZOTERO_API = f"{ZOTERO_BASE}/api/users/0"

mcp = FastMCP("zotero-desktop")


async def _get(path: str, params: dict | None = None) -> httpx.Response:
    async with httpx.AsyncClient() as client:
        return await client.get(f"{ZOTERO_BASE}{path}", params=params, timeout=30)


async def _post(path: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient() as client:
        return await client.post(f"{ZOTERO_BASE}{path}", timeout=30, **kwargs)


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", "", html)
    return unescape(text).strip()


def _format_item(data: dict) -> str:
    d = data.get("data", data)
    item_type = d.get("itemType", "unknown")
    title = d.get("title", "Untitled")
    key = d.get("key", data.get("key", ""))
    creators = d.get("creators", [])
    authors = ", ".join(
        c.get("name", f"{c.get('lastName', '')}, {c.get('firstName', '')}").strip(", ")
        for c in creators
    )
    date = d.get("date", "")
    parts = [f"**{title}**", f"  Key: `{key}`", f"  Type: {item_type}"]
    if authors:
        parts.append(f"  Authors: {authors}")
    if date:
        parts.append(f"  Date: {date}")
    publication = d.get("publicationTitle") or d.get("journalAbbreviation") or ""
    if publication:
        parts.append(f"  Publication: {publication}")
    doi = d.get("DOI", "")
    if doi:
        parts.append(f"  DOI: {doi}")
    return "\n".join(parts)


@mcp.tool(description="Check if Zotero desktop is running and responsive.")
async def ping_zotero() -> str:
    try:
        resp = await _post("/connector/ping")
        return f"Zotero is running. (Status {resp.status_code})"
    except httpx.ConnectError:
        return "Error: Cannot connect to Zotero. Make sure Zotero is running and the local API is enabled in Preferences > Advanced."


@mcp.tool(description="Search items in the local Zotero library by keyword.")
async def search_items(
    query: str,
    qmode: str = "titleCreatorYear",
    limit: int = 25,
) -> str:
    """Search items in Zotero. qmode can be: titleCreatorYear, everything, or title."""
    try:
        resp = await _get(
            "/api/users/0/items",
            params={
                "q": query,
                "qmode": qmode,
                "limit": limit,
                "itemType": "-attachment",
            },
        )
        if resp.status_code != 200:
            return f"Error: Zotero returned status {resp.status_code}"
        items = resp.json()
        if not items:
            return f"No items found for '{query}'."
        total = resp.headers.get("Total-Results", len(items))
        lines = [f"Found {total} result(s) for '{query}' (showing {len(items)}):\n"]
        for item in items:
            lines.append(_format_item(item))
            lines.append("")
        return "\n".join(lines)
    except httpx.ConnectError:
        return "Error: Cannot connect to Zotero. Is it running?"


@mcp.tool(description="Get details of a specific Zotero item by its key. Supports format: json, bibtex, ris, csljson.")
async def get_item(item_key: str, format: str = "json") -> str:
    try:
        params = {}
        if format != "json":
            params["format"] = format
        resp = await _get(f"/api/users/0/items/{item_key}", params=params or None)
        if resp.status_code == 404:
            return f"Item '{item_key}' not found."
        if resp.status_code != 200:
            return f"Error: Zotero returned status {resp.status_code}"
        if format != "json":
            return resp.text
        item = resp.json()
        result = _format_item(item)
        d = item.get("data", item)
        abstract = d.get("abstractNote", "")
        if abstract:
            result += f"\n  Abstract: {abstract}"
        tags = d.get("tags", [])
        if tags:
            tag_str = ", ".join(t.get("tag", "") for t in tags)
            result += f"\n  Tags: {tag_str}"
        url = d.get("url", "")
        if url:
            result += f"\n  URL: {url}"
        return result
    except httpx.ConnectError:
        return "Error: Cannot connect to Zotero. Is it running?"


@mcp.tool(description="Get child items (attachments and notes) for a Zotero item.")
async def get_item_children(item_key: str) -> str:
    try:
        resp = await _get(f"/api/users/0/items/{item_key}/children")
        if resp.status_code == 404:
            return f"Item '{item_key}' not found."
        if resp.status_code != 200:
            return f"Error: Zotero returned status {resp.status_code}"
        children = resp.json()
        if not children:
            return f"No children found for item '{item_key}'."
        attachments = []
        notes = []
        for child in children:
            d = child.get("data", child)
            item_type = d.get("itemType", "")
            key = d.get("key", child.get("key", ""))
            if item_type == "attachment":
                title = d.get("title", "Untitled")
                content_type = d.get("contentType", "")
                attachments.append(f"- **{title}** (Key: `{key}`, Type: {content_type})")
            elif item_type == "note":
                note_html = d.get("note", "")
                note_text = _strip_html(note_html)
                preview = note_text[:200] + ("..." if len(note_text) > 200 else "")
                notes.append(f"- Note `{key}`: {preview}")
            else:
                attachments.append(f"- {item_type} `{key}`: {d.get('title', '')}")
        parts = [f"Children of item `{item_key}`:\n"]
        if attachments:
            parts.append("**Attachments:**")
            parts.extend(attachments)
            parts.append("")
        if notes:
            parts.append("**Notes:**")
            parts.extend(notes)
        return "\n".join(parts)
    except httpx.ConnectError:
        return "Error: Cannot connect to Zotero. Is it running?"


@mcp.tool(description="Get full-text content of a PDF attachment from Zotero's full-text index.")
async def get_fulltext(item_key: str) -> str:
    try:
        resp = await _get(f"/api/users/0/items/{item_key}/fulltext")
        if resp.status_code == 404:
            # Maybe it's a parent item — try finding PDF child
            children_resp = await _get(f"/api/users/0/items/{item_key}/children")
            if children_resp.status_code == 200:
                for child in children_resp.json():
                    d = child.get("data", child)
                    if d.get("contentType") == "application/pdf":
                        pdf_key = d.get("key", child.get("key", ""))
                        ft_resp = await _get(f"/api/users/0/items/{pdf_key}/fulltext")
                        if ft_resp.status_code == 200:
                            data = ft_resp.json()
                            return data.get("content", "No content available.")
            return f"No full-text index found for item '{item_key}'. The PDF may not be indexed yet."
        if resp.status_code != 200:
            return f"Error: Zotero returned status {resp.status_code}"
        data = resp.json()
        return data.get("content", "No content available.")
    except httpx.ConnectError:
        return "Error: Cannot connect to Zotero. Is it running?"


@mcp.tool(description="List all collections in the Zotero library.")
async def list_collections(limit: int = 100) -> str:
    try:
        resp = await _get("/api/users/0/collections", params={"limit": limit})
        if resp.status_code != 200:
            return f"Error: Zotero returned status {resp.status_code}"
        collections = resp.json()
        if not collections:
            return "No collections found."
        # Build hierarchy
        by_key: dict[str, dict] = {}
        for c in collections:
            d = c.get("data", c)
            by_key[d["key"]] = d
        roots = []
        children_map: dict[str, list] = {}
        for d in by_key.values():
            parent = d.get("parentCollection")
            if parent:
                children_map.setdefault(parent, []).append(d)
            else:
                roots.append(d)

        def _render(items: list[dict], indent: int = 0) -> list[str]:
            lines = []
            for item in sorted(items, key=lambda x: x.get("name", "")):
                prefix = "  " * indent
                lines.append(f"{prefix}- **{item['name']}** (`{item['key']}`)")
                sub = children_map.get(item["key"], [])
                if sub:
                    lines.extend(_render(sub, indent + 1))
            return lines

        parts = [f"Collections ({len(collections)} total):\n"]
        parts.extend(_render(roots))
        return "\n".join(parts)
    except httpx.ConnectError:
        return "Error: Cannot connect to Zotero. Is it running?"


@mcp.tool(description="Get items in a specific Zotero collection.")
async def get_collection_items(collection_key: str, limit: int = 50) -> str:
    try:
        resp = await _get(
            f"/api/users/0/collections/{collection_key}/items",
            params={"limit": limit, "itemType": "-attachment"},
        )
        if resp.status_code == 404:
            return f"Collection '{collection_key}' not found."
        if resp.status_code != 200:
            return f"Error: Zotero returned status {resp.status_code}"
        items = resp.json()
        if not items:
            return f"No items in collection '{collection_key}'."
        total = resp.headers.get("Total-Results", len(items))
        lines = [f"Collection `{collection_key}` — {total} item(s) (showing {len(items)}):\n"]
        for item in items:
            lines.append(_format_item(item))
            lines.append("")
        return "\n".join(lines)
    except httpx.ConnectError:
        return "Error: Cannot connect to Zotero. Is it running?"


@mcp.tool(description="List all tags in the Zotero library.")
async def list_tags(limit: int = 200) -> str:
    try:
        resp = await _get("/api/users/0/tags", params={"limit": limit})
        if resp.status_code != 200:
            return f"Error: Zotero returned status {resp.status_code}"
        tags = resp.json()
        if not tags:
            return "No tags found."
        tag_names = sorted(
            t.get("tag", t.get("data", {}).get("tag", "")) for t in tags
        )
        total = resp.headers.get("Total-Results", len(tag_names))
        return f"Tags ({total} total):\n" + ", ".join(tag_names)
    except httpx.ConnectError:
        return "Error: Cannot connect to Zotero. Is it running?"


@mcp.tool(description="Export Zotero items in a specific format. Supported formats: bibtex, ris, csljson, coins, refer, tei.")
async def export_items(item_keys: list[str], format: str = "bibtex") -> str:
    try:
        resp = await _get(
            "/api/users/0/items",
            params={
                "itemKey": ",".join(item_keys),
                "format": format,
            },
        )
        if resp.status_code != 200:
            return f"Error: Zotero returned status {resp.status_code}"
        text = resp.text
        if not text.strip():
            return f"No export data returned for keys: {', '.join(item_keys)}"
        return text
    except httpx.ConnectError:
        return "Error: Cannot connect to Zotero. Is it running?"


@mcp.tool(description="Create a standalone note in Zotero via the connector API. Note: the local API has limited write support — this creates a standalone note, not a child note.")
async def create_note(note_text: str, tags: list[str] | None = None) -> str:
    try:
        paragraphs = note_text.split("\n")
        html_note = "".join(f"<p>{p}</p>" for p in paragraphs if p.strip())
        item = {
            "itemType": "note",
            "note": html_note,
            "tags": [{"tag": t} for t in (tags or [])],
        }
        import uuid

        payload = {
            "items": [item],
            "uri": "http://localhost",
        }
        resp = await _post(
            f"/connector/saveItems?sessionID={uuid.uuid4().hex}",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code == 201:
            return "Note created successfully in Zotero."
        return f"Zotero responded with status {resp.status_code}: {resp.text}"
    except httpx.ConnectError:
        return "Error: Cannot connect to Zotero. Is it running?"


@mcp.tool(description="Get items in the Zotero library that have a specific tag.")
async def get_items_by_tag(tag: str, limit: int = 50) -> str:
    try:
        resp = await _get(
            "/api/users/0/items",
            params={"tag": tag, "limit": limit, "itemType": "-attachment"},
        )
        if resp.status_code != 200:
            return f"Error: Zotero returned status {resp.status_code}"
        items = resp.json()
        if not items:
            return f"No items found with tag '{tag}'."
        total = resp.headers.get("Total-Results", len(items))
        lines = [f"Items tagged '{tag}' ({total} total, showing {len(items)}):\n"]
        for item in items:
            lines.append(_format_item(item))
            lines.append("")
        return "\n".join(lines)
    except httpx.ConnectError:
        return "Error: Cannot connect to Zotero. Is it running?"


@mcp.tool(description="Get recently added items from the Zotero library, sorted by date added (newest first).")
async def get_recent_items(limit: int = 20) -> str:
    try:
        resp = await _get(
            "/api/users/0/items",
            params={
                "limit": limit,
                "itemType": "-attachment",
                "sort": "dateAdded",
                "direction": "desc",
            },
        )
        if resp.status_code != 200:
            return f"Error: Zotero returned status {resp.status_code}"
        items = resp.json()
        if not items:
            return "No items found."
        lines = [f"Recently added items (showing {len(items)}):\n"]
        for item in items:
            d = item.get("data", item)
            date_added = d.get("dateAdded", "")[:10]  # YYYY-MM-DD
            formatted = _format_item(item)
            lines.append(f"{formatted}\n  Added: {date_added}")
            lines.append("")
        return "\n".join(lines)
    except httpx.ConnectError:
        return "Error: Cannot connect to Zotero. Is it running?"


@mcp.tool(description="Get the full text content of a Zotero note by its item key.")
async def get_note(item_key: str) -> str:
    try:
        resp = await _get(f"/api/users/0/items/{item_key}")
        if resp.status_code == 404:
            return f"Item '{item_key}' not found."
        if resp.status_code != 200:
            return f"Error: Zotero returned status {resp.status_code}"
        item = resp.json()
        d = item.get("data", item)
        if d.get("itemType") != "note":
            return f"Item '{item_key}' is not a note (type: {d.get('itemType', 'unknown')})."
        note_html = d.get("note", "")
        note_text = _strip_html(note_html)
        tags = d.get("tags", [])
        result = f"Note `{item_key}`:\n\n{note_text}"
        if tags:
            tag_str = ", ".join(t.get("tag", "") for t in tags)
            result += f"\n\nTags: {tag_str}"
        return result
    except httpx.ConnectError:
        return "Error: Cannot connect to Zotero. Is it running?"


@mcp.tool(description="List all items in the Zotero library with pagination support.")
async def list_all_items(
    limit: int = 50,
    start: int = 0,
    sort: str = "dateModified",
    direction: str = "desc",
) -> str:
    """
    Browse all items in the library.
    sort: title, dateAdded, dateModified, creator, itemType, date, publisher, publicationTitle, journalAbbreviation, language, accessDate, libraryCatalog, callNumber, rights, addedBy, numItems
    direction: asc or desc
    """
    try:
        resp = await _get(
            "/api/users/0/items",
            params={
                "limit": limit,
                "start": start,
                "sort": sort,
                "direction": direction,
                "itemType": "-attachment",
            },
        )
        if resp.status_code != 200:
            return f"Error: Zotero returned status {resp.status_code}"
        items = resp.json()
        if not items:
            return "No items found."
        total = resp.headers.get("Total-Results", "?")
        lines = [
            f"Library items — total: {total}, showing {len(items)} starting at {start} (sorted by {sort} {direction}):\n"
        ]
        for item in items:
            lines.append(_format_item(item))
            lines.append("")
        try:
            if int(total) > start + len(items):
                lines.append(f"(Use start={start + len(items)} to get the next page)")
        except (ValueError, TypeError):
            pass
        return "\n".join(lines)
    except httpx.ConnectError:
        return "Error: Cannot connect to Zotero. Is it running?"


def main():
    mcp.run()


if __name__ == "__main__":
    main()
