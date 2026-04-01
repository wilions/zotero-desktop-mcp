# Zotero Desktop MCP

An MCP server that connects Claude (or any MCP client) to your local [Zotero](https://www.zotero.org/) library via Zotero Desktop's built-in HTTP API.

## Prerequisites

- [Zotero Desktop](https://www.zotero.org/download/) running locally
- Zotero local API enabled: **Edit → Preferences → Advanced → Allow other applications on this computer to communicate with Zotero**
- Python 3.11+

## Installation

### Using `uv` (recommended)

```bash
uvx zotero-desktop-mcp
```

### Using `pip`

```bash
pip install zotero-desktop-mcp
zotero-desktop-mcp
```

### From source

```bash
git clone https://github.com/wilions/zotero-desktop-mcp.git
cd zotero-desktop-mcp
pip install -e .
zotero-desktop-mcp
```

## Claude Desktop Configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "zotero-desktop": {
      "command": "uvx",
      "args": ["zotero-desktop-mcp"]
    }
  }
}
```

## Claude Code Configuration

```bash
claude mcp add zotero-desktop uvx zotero-desktop-mcp
```

## Tools

| Tool | Description |
|------|-------------|
| `ping_zotero` | Check if Zotero is running |
| `search_items` | Search library by keyword |
| `get_item` | Get item details (JSON, BibTeX, RIS, CSL-JSON) |
| `get_item_children` | List attachments and notes for an item |
| `get_fulltext` | Get full-text content of a PDF (from Zotero's index) |
| `list_collections` | List all collections as a tree |
| `get_collection_items` | Get items in a collection |
| `list_tags` | List all tags in the library |
| `export_items` | Export items in BibTeX, RIS, CSL-JSON, etc. |
| `create_note` | Create a standalone note |
| `get_items_by_tag` | Get items filtered by tag |
| `get_recent_items` | Get recently added items |
| `get_note` | Get full text of a note |
| `list_all_items` | Browse all items with pagination |

## Notes

- Zotero must be running for any tool to work
- The local API runs on `http://localhost:23119` — no authentication required
- Full-text search requires PDFs to be indexed in Zotero (**Tools → Index PDF**)
