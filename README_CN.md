# DrissionPage MCP Server

> 基于 DrissionPage 为 Codex、Claude Code 和 MCP 客户端提供专业的浏览器自动化能力

[![PyPI](https://img.shields.io/pypi/v/drissionpage-mcp.svg?cacheSeconds=3600)](https://pypi.org/project/drissionpage-mcp/)
[![Downloads](https://pepy.tech/badge/drissionpage-mcp/month)](https://pepy.tech/project/drissionpage-mcp)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/jumodada/Drissionpage-MCP-Server/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/jumodada/Drissionpage-MCP-Server/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/jumodada/Drissionpage-MCP-Server/branch/main/graph/badge.svg)](https://codecov.io/gh/jumodada/Drissionpage-MCP-Server)
[![Status](https://img.shields.io/badge/status-beta-yellow.svg)]()

**官方仓库**: [GitHub](https://github.com/jumodada/Drissionpage-MCP-Server) | [GitCode](https://gitcode.com/g1879/DrissionMCP)

[English Version](README.md) | [中文版本](README_CN.md)

## 🧭 客户端安装导航

- [安装与截图指引](#-首次成功路径)
- [Codex CLI/IDE 快速配置](#-在-codex-cliide-中配置30-秒)
- [Codex CLI/IDE 集成示例](#codex-cli--ide)
- [Claude Code 配置](#claude-code)
- [Cursor 配置](#cursor)
- [Claude Desktop 配置](#claude-desktop)
- [故障排除](#-故障排除)

---

## 🚀 什么是 DrissionPage MCP？

**DrissionPage MCP Server** 是一个本地模型上下文协议（MCP）服务器，为 Codex CLI/IDE、Claude Code、Claude Desktop 和其他 MCP 客户端提供 DrissionPage 浏览器自动化工具。

与基于截图的方法不同，它通过 25 个强大工具和 MCP Resources/Prompts 提供**结构化、确定性的网页自动化**，利用高性能浏览器自动化框架 [DrissionPage](https://github.com/g1879/DrissionPage) 的效率。

### 🌟 为什么选择 DrissionPage MCP？

- **LLM 优化**：使用结构化数据而不需要视觉模型
- **确定性**：通过 CSS/XPath 归一化实现适合 LLM 的可靠元素选择
- **快速轻量**：基于 DrissionPage 高效引擎构建，开销最小
- **类型安全**：所有工具都具有完整的类型提示和 Pydantic 验证
- **开源友好**：包含兼容性说明、故障排除和 CI 检查，便于维护和贡献
- **易于集成**：简单的 `pip install` + Codex TOML 或 MCP JSON 配置即可使用

### ✅ 质量保障与真实场景验证

DrissionPage MCP 有严格的回归测试和真实浏览器场景验证：

- **严格自动化测试**：CI 会运行单元、协议、schema snapshot、响应合同、资源/提示词、发布元数据、安全策略、浏览器集成和覆盖率检查。
- **95% 覆盖率底线**：CI 强制执行当前 95% 覆盖率门槛，并上传覆盖率报告。
- **真实浏览器验证**：Chrome/Chromium 集成测试会直接调用暴露给客户端的 MCP 工具。
- **场景化验证**：playground MCP Lab 覆盖表单、电商页面、社交 feed、时间线、动态等待、iframe 和失败恢复等场景，不依赖公共演示网站。

---

## ⚡ 首次成功路径

```bash
# 从 PyPI 安装
python -m pip install -U drissionpage-mcp

# 验证包和本地环境
drissionpage-mcp --version
drissionpage-mcp doctor
```

然后添加下面的 Codex 或 MCP 客户端配置并重启客户端。

<p align="center">
  <img src="https://raw.githubusercontent.com/jumodada/Drissionpage-MCP-Server/assets/01-install.png" width="700" alt="pip install drissionpage-mcp">
  <br><br>
  <img src="https://raw.githubusercontent.com/jumodada/Drissionpage-MCP-Server/assets/03-doctor.png" width="700" alt="drissionpage-mcp doctor 全部检查通过">
</p>

---

## 📦 在 Codex CLI/IDE 中配置（30 秒）

Codex 通过 `config.toml` 支持本地 stdio MCP Server；Codex CLI 和 IDE 扩展共用同一份 MCP 配置。

1. **编辑 Codex 配置文件**：
   - 用户级：`~/.codex/config.toml`
   - 项目级：受信任项目中的 `.codex/config.toml`

2. **添加以下配置**：
   ```toml
   [mcp_servers.drissionpage]
   command = "drissionpage-mcp"
   startup_timeout_sec = 20
   tool_timeout_sec = 60
   ```

3. **重启 Codex**。TUI 中可运行 `/mcp`，终端可运行 `codex mcp list` 检查连接。

<p align="center">
  <img src="https://raw.githubusercontent.com/jumodada/Drissionpage-MCP-Server/assets/06-codex.png" width="700" alt="Codex config.toml 配置">
</p>

Claude Code、Claude Desktop 和其他 JSON 配置 MCP 客户端见[集成示例](#-集成示例)。

---

## 🎯 快速示例

### 导航和截图
```
"访问 https://example.com 并为我截图"
```

### 搜索和提取
```
"打开维基百科，搜索 Python，获取第一段文字"
```

### 表单自动化
```
"填写 https://httpbin.org/forms/post 的表单并提交"
```

### 数据抓取
```
"从 news.ycombinator.com 获取前 10 条新闻标题"
```

---

## 🛠️ 25 个强大工具 + MCP Resources/Prompts

### 🌐 导航工具（4 个）
- `page_navigate` - 导航到任意 URL；可用 `new_tab` 在新标签页打开
- `page_go_back` / `page_go_forward` - 浏览器历史记录
- `page_refresh` - 重新加载当前页面

### 🗂️ 标签页工具（3 个）
- `tab_list` - 列出当前打开的浏览器标签页和稳定 MCP tab ID
- `tab_switch` - 切换到 `tab_list` 返回的标签页
- `tab_close` - 关闭单个标签页，不关闭整个浏览器

### 🎯 元素交互与提取（8 个）
- `element_find` - 通过 CSS 选择器或 XPath 查找单个元素；`h1` 等裸选择器按 CSS 处理
- `element_find_all` - 提取重复列表、卡片和表格元素，返回有界文本、属性和推荐 selector
- `element_click` - 点击任意元素
- `element_type` - 向元素输入文本
- `element_get_text` - 获取元素或整页文本
- `element_get_attribute` - 获取 HTML attribute
- `element_get_property` - 获取实时 DOM property，例如输入框当前 value
- `element_get_html` - 获取元素或整页 HTML

### 🧾 表单工具（1 个）
- `form_inspect` - 检查表单和控件，返回 label、selector、必填/禁用状态、选项和安全的可选 value

### 📸 页面操作（6 个）
- `page_screenshot` - 捕获完整页面或视口
- `page_snapshot` - 返回有界页面 outline，包括标题、链接、按钮、输入框、表单和 selector 推荐
- `page_resize` - 调整浏览器窗口
- `page_click_xy` - 通过坐标点击
- `page_close` - 关闭浏览器
- `page_get_url` - 获取当前 URL

### ⏱️ 等待操作（3 个）
- `wait_for_element` - 等待元素出现（带超时）
- `wait_for_url` - 等待当前 URL 包含指定文本
- `wait_time` - 延迟执行

### 🧩 MCP Resources 和 Prompts
- Resources：`drissionpage://session/summary`、`drissionpage://session/history`、`drissionpage://page/current`、`drissionpage://tools/catalog`、`drissionpage://policy/summary`
- Prompts：`browser_navigate_and_summarize`、`browser_extract_structured_data`、`browser_fill_form_safely`、`browser_debug_page_issue`

---

## 📚 文档

| 指南 | 描述 |
|-------|-------------|
| [README_CN.md](README_CN.md) | 安装、工具和架构说明 |
| [docs/compatibility.md](docs/compatibility.md) | Python、DrissionPage、MCP 和浏览器兼容性 |
| [docs/tool-contract.md](docs/tool-contract.md) | MCP 工具名称、输入、注解和响应格式 |
| [docs/troubleshooting.md](docs/troubleshooting.md) | doctor 命令、浏览器启动和客户端配置排查 |
| [CHANGELOG.md](CHANGELOG.md) | 版本变更 |

---

## 🏗️ 架构

采用**清晰、模块化的设计**：

```
DrissionMCP/
├── drissionpage_mcp/
│   ├── cli.py              # 入口点
│   ├── server.py           # MCP 服务器
│   ├── context.py          # 浏览器管理
│   ├── response.py         # 响应格式化
│   ├── tab.py              # 页面操作
│   └── tools/              # 25 个自动化、标签页管理、页面理解与表单检查工具
├── tests/                  # 单元测试
└── playground/             # MCP Lab 业务场景测试场
```

**核心原则**：
- ✅ 所有工具使用类型安全的 Pydantic 模型
- ✅ 全面使用 async/await
- ✅ 清晰的关注点分离
- ✅ 全面的错误处理
- ✅ 核心工具注册和响应行为具有单元/协议测试覆盖

---

## 🔧 配置

### Codex CLI / IDE（推荐）
```toml
[mcp_servers.drissionpage]
command = "drissionpage-mcp"
startup_timeout_sec = 20
tool_timeout_sec = 60

# 可选浏览器/运行时环境变量：
# [mcp_servers.drissionpage.env]
# CHROME_PATH = "/custom/path/to/chrome"
# DP_HEADLESS = "1"
# DP_NO_SANDBOX = "1"
```

也可以用 Codex CLI 添加：

```bash
codex mcp add drissionpage -- drissionpage-mcp
```

如果 Codex/Cursor/Claude Desktop 从 GUI 启动后找不到 shell `PATH` 或
虚拟环境中的 `drissionpage-mcp`，请改用绝对 Python 路径：

```toml
[mcp_servers.drissionpage]
command = "/absolute/path/to/python"
args = ["-m", "drissionpage_mcp.cli"]
startup_timeout_sec = 20
tool_timeout_sec = 60
```

### JSON MCP 客户端
```json
{
  "mcpServers": {
    "drissionpage": {
      "command": "drissionpage-mcp"
    }
  }
}
```

GUI 客户端的绝对 Python fallback：

```json
{
  "mcpServers": {
    "drissionpage": {
      "command": "/absolute/path/to/python",
      "args": ["-m", "drissionpage_mcp.cli"],
      "env": {
        "CHROME_PATH": "/custom/path/to/chrome",
        "DP_HEADLESS": "1",
        "DP_NO_SANDBOX": "1"
      }
    }
  }
}
```

### JSON 高级配置
```json
{
  "mcpServers": {
    "drissionpage": {
      "command": "drissionpage-mcp",
      "args": ["--log-level", "DEBUG"],
      "env": {
        "CHROME_PATH": "/custom/path/to/chrome"
      }
    }
  }
}
```

---

## 📋 环境要求

- **Python 3.10+**（推荐 3.11+）
- **Chrome 或 Chromium** 浏览器
- **任何 MCP 兼容客户端**：Codex CLI/IDE、Claude Code、Claude Desktop、Cursor、VS Code 等

---

## 🧪 测试

### 验证安装
```bash
# 环境诊断；加 --launch-browser 可测试浏览器启动
drissionpage-mcp doctor
drissionpage-mcp doctor --launch-browser

# 源码检出测试
python -m pip install -e ".[dev]"
python -m pytest tests/

# 覆盖率报告（CI 会执行当前 95% 覆盖率底线并上传 coverage.xml）
python -m pytest tests/ --cov=drissionpage_mcp --cov-report=term-missing --cov-report=xml

# 真实浏览器 MCP Lab 场景检查
DP_HEADLESS=1 python playground/run_mcp_lab.py --all --json
```

GitHub Actions 已配置 lint、单元、协议、打包、浏览器集成和覆盖率检查；
Codecov 通过 `codecov.yml` 和 CI workflow 上传覆盖率。

### 试用
```bash
# 无浏览器 MCP 工具注册检查
python playground/run_mcp_lab.py --case registry

# 本地确定性测试站点检查
python playground/run_mcp_lab.py --case site

# 真实浏览器表单检查场景
DP_HEADLESS=1 python playground/run_mcp_lab.py --case form-inspect
```

---

## 🚀 使用场景

✅ **自动化测试** - 测试 Web 应用程序
✅ **数据抓取** - 从网站提取结构化数据
✅ **表单自动化** - 填写和提交表单
✅ **监控** - 检查更新或变化
✅ **截图验证** - 捕获和验证页面状态
✅ **内容分析** - 以编程方式分析网页内容

---

## 🐛 故障排除

### 工具未加载？
```bash
drissionpage-mcp --version
```
应输出已安装的包版本，例如：`drissionpage-mcp 0.5.1`。

### 浏览器问题？
```bash
# 检查浏览器安装
which google-chrome    # Linux
which chromium         # macOS
```

### Codex / MCP 客户端找不到服务器？
- Codex：运行 `codex mcp list`，TUI 中运行 `/mcp`
- JSON 客户端：验证配置文件路径和 JSON 语法
- 修改后重启 Codex 或 MCP 客户端
- 检查日志：`drissionpage-mcp --log-level DEBUG`

完整故障排除指南请参阅 [docs/troubleshooting.md](docs/troubleshooting.md)。

---

## 📊 项目状态

| 组件 | 状态 |
|-----------|--------|
| **核心功能** | ✅ 完成 |
| **测试** | ✅ 严格单元/协议/schema 检查 + 真实浏览器场景验证 |
| **文档** | ✅ 安装、兼容性、故障排除、发布清单 |
| **包** | ✅ PyPI 元数据和构建检查 |
| **状态** | 🟡 Beta；真实浏览器行为取决于本地 Chrome/Chromium 和目标站点 |

**版本**: 0.5.1 | **许可证**: Apache 2.0 | **维护**: ✅ 活跃

---

## 🗺️ 路线图

### 当前版本 (v0.5.1)
- [x] 25 个核心自动化、标签页管理、页面理解与表单检查工具，已移除 alias 工具面
- [x] stdio MCP 服务器集成
- [x] 本地环境 doctor 诊断
- [x] 稳定 JSON 镜像、`structuredContent` 和逐工具 typed MCP `outputSchema`
- [x] 常见失败会在 `error.details.hints` 中返回结构化恢复建议
- [x] `page_snapshot` 会平衡输出预算，链接密集页面仍能暴露按钮、输入框和表单
- [x] `form_inspect` 只读表单 inventory，返回 label、selector、必填状态、选项和安全的可选 value
- [x] 标签页管理：`tab_list`、`tab_switch`、`tab_close` 和 `page_navigate(new_tab=true)`
- [x] 脱敏 session history resource，以及有界输出的响应大小 metadata
- [x] 针对导航和截图路径的可选本地安全策略
- [x] Resources、Prompts、eval harness、兼容性和故障排除文档
- [x] PyPI 发布

### 未来版本 (v0.5+)
- [ ] 表单填写工具
- [ ] 文件上传支持
- [ ] Shadow DOM 选择器
- [ ] 会话持久化
- [ ] 代理支持
- [ ] 网络拦截

---

## 📖 集成示例

### Codex CLI / IDE
```toml
[mcp_servers.drissionpage]
command = "drissionpage-mcp"
startup_timeout_sec = 20
tool_timeout_sec = 60
```

验证：

```bash
codex mcp list
```

### Claude Code
```json
{
  "mcpServers": {
    "drissionpage": {
      "command": "drissionpage-mcp"
    }
  }
}
```

配置文件：`~/.config/claude-code/mcp_settings.json`（macOS/Linux）或
`%APPDATA%\claude-code\mcp_settings.json`（Windows）。

<p align="center">
  <img src="https://raw.githubusercontent.com/jumodada/Drissionpage-MCP-Server/assets/04-claude-code.png" width="700" alt="Claude Code mcp_settings.json 配置">
</p>

### Cursor
```json
{
  "mcpServers": {
    "drissionpage": {
      "command": "drissionpage-mcp"
    }
  }
}
```

配置文件：`~/.cursor/mcp.json`（全局）或 `.cursor/mcp.json`（项目）。也可以从
**Cursor Settings → Tools & MCPs → New MCP Server** 添加。

<p align="center">
  <img src="https://raw.githubusercontent.com/jumodada/Drissionpage-MCP-Server/assets/05-cursor.png" width="700" alt="Cursor mcp.json 配置">
  <br><br>
  <img src="https://raw.githubusercontent.com/jumodada/Drissionpage-MCP-Server/assets/08-cursor-ui.png" width="540" alt="Cursor 设置 — 添加新的 MCP 服务器">
</p>

### Claude Desktop
```json
{
  "mcpServers": {
    "drissionpage": {
      "command": "drissionpage-mcp"
    }
  }
}
```

连接成功后，工具会自动加载：

<p align="center">
  <img src="https://raw.githubusercontent.com/jumodada/Drissionpage-MCP-Server/assets/07-connected.png" width="700" alt="MCP 客户端已加载 DrissionPage 工具">
</p>

---

## 🤝 贡献

欢迎贡献！

1. Fork 仓库
2. 创建功能分支
3. 进行聚焦修改
4. 运行相关检查
5. 提交 Pull Request

开发设置、验证和兼容性要求请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 🔒 安全

- 在您的本地环境中运行
- 使用本地浏览器，可能访问已登录会话、Cookie、下载内容和页面内容
- 可以打开并操作本机可访问的网站
- 不需要外部 API 凭据

**最佳实践**：
- 对敏感工作流使用专用浏览器配置文件
- 在认证站点或生产系统上执行操作前，先检查 MCP 客户端提示
- 遵守网站服务条款、robots.txt 和速率限制
- 安全报告和使用建议见 [SECURITY.md](SECURITY.md)

---

## 📄 许可证

采用 **Apache License 2.0** 许可 - 详见 [LICENSE](LICENSE)

---

## 📈 统计

[![Downloads](https://pepy.tech/badge/drissionpage-mcp)](https://pepy.tech/project/drissionpage-mcp)
[![PyPI Version](https://img.shields.io/pypi/v/drissionpage-mcp.svg?cacheSeconds=3600)](https://pypi.org/project/drissionpage-mcp/)

---

## 🌟 表达支持

如果您觉得这个项目有用，请考虑：
- ⭐ 在 [GitHub](https://github.com/jumodada/Drissionpage-MCP-Server) 上加星
- 📤 分享给您的网络
- 💬 留下反馈或建议
- 🐛 报告问题以帮助改进

---

**用 ❤️ 制作，作者 [Wukunyun](https://github.com/jumodada)**

**准备好自动化您的工作流程了吗？** 立即安装：`python -m pip install -U drissionpage-mcp`

---

## 🆕 最新版本：v0.5.1

发布日期：2026-06-30。本版本让多标签页浏览和长会话恢复更稳定，同时保留 0.5 表单工作流：

- `tab_list`、`tab_switch` 和 `tab_close` 可以管理 MCP 工具或页面交互打开的标签页，例如 `target="_blank"` 链接。
- `page_navigate` 现在支持 `new_tab=true`，可在新的受跟踪标签页中打开 URL。
- `drissionpage://session/history` 会返回最近工具操作，并对敏感参数脱敏。
- `page_snapshot`、`element_find_all` 和 `form_inspect` 增加 `meta.approx_tokens` 与大小信息，便于控制响应预算。
- `form_inspect` 可以检查表单和控件，返回 label、selector、method/action、必填/禁用/只读状态、select options，以及 opt-in 的非 password value。
- 失败 payload 会在 `error.details.hints` 中返回机器可读的恢复建议。
- 元素缺失和 selector 失败会建议 `page_snapshot`、`element_find_all`、`wait_for_element` 以及 iframe / 动态内容检查。
- `page_snapshot` 现在会在遵守总 `max_elements` 上限的同时，让链接密集页面仍返回输入框、按钮和表单。
- timeout、浏览器启动、截图、导航、policy、参数错误和未知工具失败现在都有针对性的下一步建议。
- `MCP_ARGUMENT_INVALID` 继续保护严格 schema，并会提示客户端使用准确的 snake_case 字段名。
- 浏览器启动失败会提示 `drissionpage-mcp doctor --launch-browser`、`CHROME_PATH`、`DP_HEADLESS` 和 `DP_NO_SANDBOX`。
- 顶层 JSON_RESULT envelope、严格输入 schema 和 typed `outputSchema` 合同保持不变；公开工具数变为 25 个。
