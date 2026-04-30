# MCP FAQ

## How do I start the MCP server?

```bash
python -m mcp_server.server --transport stdio
```

## How do I use HTTP transport?

```bash
python -m mcp_server.server --transport http --port 3333
```

## Where can I find the tool list?

Check `mcp_server/server.py` for registered MCP resources and tools.

## Where do I configure sources?

See `config/config.yaml`, especially `platforms` and `rss`.

## License

This repository remains under GPL-3.0. See `LICENSE`.
