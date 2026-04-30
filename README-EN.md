# Trending Aggregation and Notification Tool

A locally maintained project for collecting, filtering, analyzing, and pushing trending news and RSS content.

## Features

- Trending platform crawling
- RSS feed aggregation
- Keyword / AI filtering
- Multi-channel notifications
- MCP server support

## Quick Start

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the main app:

```bash
python -m trendradar
```

Run MCP server:

```bash
python -m mcp_server.server
```

## Config

Main config file: `config/config.yaml`

Key sections:

- `platforms`
- `rss`
- `display`
- `notification`
- `ai`
- `ai_translation`

## Notes

This repository is a locally maintained derivative of an open-source project, adjusted for a simpler deployment and notification workflow.

The project remains under GPL-3.0. See `LICENSE`.
