# MCP 常见问题

## 1. 如何启动 MCP 服务？

```bash
python -m mcp_server.server --transport stdio
```

## 2. 如何用 HTTP 模式？

```bash
python -m mcp_server.server --transport http --port 3333
```

## 3. 工具列表在哪看？

查看 [mcp_server/server.py](D:/78788/-/mcp_server/server.py) 中注册的 `resource` 与 `tool`。

## 4. 数据来源在哪配？

查看 [config/config.yaml](D:/78788/-/config/config.yaml) 中的 `platforms` 和 `rss`。

## 5. 许可证是什么？

当前仓库继续遵守 GPL-3.0，详见 [LICENSE](D:/78788/-/LICENSE)。
