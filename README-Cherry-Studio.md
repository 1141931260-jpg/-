# MCP 接入说明

本仓库提供 `trendradar-mcp` 服务入口，可用于支持 MCP 的客户端。

## 启动

```bash
python -m mcp_server.server --transport stdio
```

或：

```bash
python -m mcp_server.server --transport http --port 3333
```

## 说明

- `stdio`: 适合本地 MCP 客户端接入
- `http`: 适合局域网或服务化部署

更详细的工具清单可直接查看 [mcp_server/server.py](D:/78788/-/mcp_server/server.py)。
