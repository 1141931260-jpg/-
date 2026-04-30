# 热点聚合与推送工具

一个本地维护的热点新闻 / RSS 聚合、分析与推送项目。

支持：

- 热榜平台抓取
- RSS 订阅抓取
- 关键词筛选 / AI 筛选
- 多渠道通知推送
- MCP Server 查询与分析

## 快速开始

安装依赖：

```bash
pip install -r requirements.txt
```

运行主程序：

```bash
python -m trendradar
```

启动 MCP Server：

```bash
python -m mcp_server.server
```

Windows 可直接使用：

```bash
setup-windows.bat
start-http.bat
```

## 主要配置

核心配置文件在 [config/config.yaml](D:/78788/-/config/config.yaml)。

常用项：

- `platforms`: 热榜源
- `rss`: RSS 源
- `display`: 推送展示区域
- `notification`: 推送渠道
- `ai`: AI 模型配置
- `ai_translation`: 推送翻译

## 目录结构

- `trendradar/`: 主程序
- `mcp_server/`: MCP 服务
- `config/`: 配置文件
- `docker/`: Docker 部署
- `docs/`: 静态文档页
- `output/`: 输出数据

## 说明

这是一个基于开源项目二次整理和本地维护的版本，已按当前使用场景调整配置、推送内容和文档结构。

原项目遵循 GPL-3.0 许可证，当前仓库继续遵守该许可证。详见 [LICENSE](D:/78788/-/LICENSE)。
