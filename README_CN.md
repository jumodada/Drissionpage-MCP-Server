# DrissionPage MCP Server

> 基于 DrissionPage 为 Codex、Claude Code 和 MCP 客户端提供专业的浏览器自动化能力

[![PyPI](https://img.shields.io/pypi/v/drissionpage-mcp.svg?cacheSeconds=3600)](https://pypi.org/project/drissionpage-mcp/) [![Downloads](https://pepy.tech/badge/drissionpage-mcp/month)](https://pepy.tech/project/drissionpage-mcp) [![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0) [![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/) [![CI](https://github.com/jumodada/Drissionpage-MCP-Server/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/jumodada/Drissionpage-MCP-Server/actions/workflows/ci.yml) [![codecov](https://codecov.io/gh/jumodada/Drissionpage-MCP-Server/branch/main/graph/badge.svg)](https://codecov.io/gh/jumodada/Drissionpage-MCP-Server) [![Status](https://img.shields.io/badge/status-beta-yellow.svg)]()

[![DrissionPage MCP 交互式 Browser Lab](https://raw.githubusercontent.com/jumodada/Drissionpage-MCP-Server/assets/drissionpage-mcp-browser-lab.gif)](https://drissionpage-mcp.vercel.app)

**[打开交互式 Browser Lab](https://drissionpage-mcp.vercel.app)**，追踪旋转目标、重放自然点击、拖动滑块并验证可观察状态。

**官方仓库**: [GitHub](https://github.com/jumodada/Drissionpage-MCP-Server) | [GitCode](https://gitcode.com/g1879/DrissionMCP)

[English Version](README.md) | [中文版本](README_CN.md)

## 🖱️ 视觉驱动的人机交互

**DrissionPage MCP 0.7.0 为多模态 AI 打通普通浏览器工作的闭环：** 在现有视觉交互层上，增加结构化表单完成、带证据的提交、浏览器对话框处理和完整性校验下载。

> **一次 MCP 调用即可连接视觉理解与真实浏览器交互。** 模型负责判断“在哪里操作”，DrissionPage MCP 负责决定“鼠标如何移动过去并完成点击”。

```text
截图 / 页面观察
        ↓
多模态模型识别 viewport 坐标
        ↓
page_click_xy(profile="natural")
        ↓
三次贝塞尔移动 → 反应停顿 → 按下 → 保持 → 释放
        ↓
观察并验证页面状态变化
```

### 这层人机交互能力有什么不同？

- **自然指针动力学**：使用 20–35 个三次贝塞尔移动点，不再是坐标瞬移。
- **符合人手节奏的时间模型**：8–25ms 点间隔、smoothstep 先加速后减速，到位后停顿 100–300ms。
- **真实点击语义**：按下后保持 50–120ms，并为左键、右键和中键提供正确的 Chromium CDP 按键状态。
- **有界微运动**：中间点加入 ±0.5 CSS 像素微抖，最终点仍精确落在目标坐标。
- **失败安全**：动作链被中断时也会保证释放已经按下的鼠标按钮。
- **模型可读的执行证据**：结果会返回 profile、起点、目标点、移动步数、反应延迟、按键时长和计划总时长。

这让 AI 可以操作 canvas 控件、可视化编辑器、地图、图表、缺少语义信息的组件、响应式界面，以及 selector 或 accessibility metadata 不完整的交互表面。存在可靠 selector 时仍优先使用结构化 DOM 自动化；视觉人机交互层的价值，是扩展 MCP agent 在结构化信息不足时仍然可以操作的范围。

```json
{
  "x": 442,
  "y": 369,
  "start_x": 100,
  "start_y": 100,
  "profile": "natural",
  "button": "left",
  "element": "视觉识别出的控件"
}
```

该能力用于合法的普通 UI 自动化、测试、无障碍工作流和技术研究；安全验证或反自动化挑战的完成不作为保证支持的产品能力。

## 🧭 客户端安装导航

- [视觉驱动的人机交互](#视觉驱动的人机交互)
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

项目仍以 62 个工具和 MCP Resources/Prompts 提供的**结构化、确定性自动化**为默认路径。0.7.0 新增自主表单完成、副作用回执、原生对话框响应、增强点击语义和安全下载产物；当 selector 或 accessibility metadata 不足时，可选的**视觉驱动人机交互层**会把 viewport 坐标和有界拖拽路径转换为自然的 Chromium 指针动作链，并由高性能浏览器自动化框架 [DrissionPage](https://github.com/g1879/DrissionPage) 执行。

### 🌟 为什么选择 DrissionPage MCP？

- **结构化优先、视觉就绪**：有可靠 DOM 时使用结构化信息，需要视觉操作时接收多模态模型坐标
- **确定性**：通过 CSS/XPath 归一化实现适合 LLM 的可靠元素选择
- **视觉交互能力**：把多模态模型输出的坐标转换为自然指针移动和具有真实时长的点击
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

## 🛠️ 62 个强大工具 + MCP Resources/Prompts

### 🌐 导航工具（4 个）
- `page_navigate` - 导航到任意 URL；可用 `new_tab` 在新标签页打开，也可用 `observe` 返回变化摘要
- `page_go_back` - 返回浏览器历史上一页
- `page_go_forward` - 前进到浏览器历史下一页
- `page_refresh` - 重新加载当前页面

### 🗂️ 标签页工具（3 个）
- `tab_list` - 列出当前打开的浏览器标签页和稳定 MCP tab ID
- `tab_switch` - 切换到 `tab_list` 返回的标签页
- `tab_close` - 关闭单个标签页，不关闭整个浏览器

### 🎯 元素交互与提取（14 个）
- `element_find` - 通过 CSS 选择器或 XPath 查找单个元素；`h1` 等裸选择器按 CSS 处理
- `element_find_all` - 提取重复列表、卡片和表格元素，返回有界文本、属性和推荐 selector
- `element_click` - 点击任意元素，并以兼容方式支持左/右/中键和单击/双击语义
- `element_click_and_download` - 将一次原生点击与 `DP_MCP_DOWNLOAD_ROOT` 下的一份完整性校验产物关联
- `element_type` - 向元素输入文本
- `element_upload_file` - 从 `DP_MCP_UPLOAD_ROOT` 上传文件到 `input[type=file]`
- `element_scroll_into_view` - 将元素滚动到视口内
- `element_hover` - 悬停元素以触发菜单/提示状态
- `element_select` - 按 value、text 或 index 选择下拉选项
- `element_check` - 勾选或取消 checkbox/radio
- `element_get_text` - 获取元素或整页文本
- `element_get_attribute` - 获取 HTML attribute
- `element_get_property` - 获取实时 DOM property，例如输入框当前 value
- `element_get_html` - 获取元素或整页 HTML

### 🧾 表单工具（3 个）
- `form_inspect` - 检查表单和控件，返回 label、selector、必填/禁用状态、选项和安全的可选 value
- `form_fill` - 填写原生和富控件，不提交，并返回逐字段验证与脱敏结果
- `form_submit` - 对已授权表单执行一次提交，返回 postcondition 证据、operation-key 重放状态和 typed receipt

### 📸 页面操作（18 个）
- `page_screenshot` - 捕获完整页面或视口
- `page_screenshot_save` - 保存截图到 `DP_MCP_SCREENSHOT_ROOT`
- `page_snapshot` - 返回有界页面 outline，包括标题、链接、按钮、输入框、表单和 selector 推荐
- `page_observe` - 返回紧凑页面指纹，包括 URL、标题、元素数量、可见文本样本、当前焦点元素和最近 console 摘要
- `page_evaluate` - 在当前页面运行有界 JavaScript，并返回 JSON-safe 结果
- `page_scroll` - 按方向或坐标滚动页面
- `keyboard_press` - 向当前焦点元素/页面发送键盘输入
- `page_resize` - 调整浏览器窗口
- `page_pointer_move` - 沿自然贝塞尔轨迹移动到视觉模型识别出的 viewport 坐标，但不点击
- `page_pointer_drag` - 执行失败安全的坐标拖拽，可经过最多六个可选有序路径点，并保留距离驱动时长和精确终点修正
- `page_pointer_drag_element` - 在动作前即时解析 source 与目标几何；支持顶层文档或一个同源 iframe 中的 CSS/XPath，以及嵌套 open Shadow DOM 中的 CSS 路径
- `page_detect_challenges` - 只读检测验证组件信号，供模型自主路由
- `page_click_xy_batch` - 在一次有界自主调用内执行多个视觉坐标点击
- `page_wait_challenge_result` - 轮询 token 长度和可配置成功/重试/挑战信号，不返回 token 内容
- `page_click_xy` - 将视觉模型识别出的 viewport 坐标转换为自然贝塞尔指针移动和真实时长点击
- `page_close` - 关闭浏览器
- `page_get_url` - 获取当前 URL
- `page_dialog_respond` - 通过能力探测后的原生路径接受或取消一个待处理 alert、confirm 或 prompt

### 🧱 iframe / Shadow DOM（5 个）
- `frame_list` - 列出 iframe/frame，不改变全局 frame 状态
- `frame_snapshot` - 对指定 iframe 返回有界 outline
- `frame_find` - 在指定 iframe 内查找元素
- `shadow_find` - 在 open shadow root 内查找单个元素
- `shadow_find_all` - 在 open shadow root 内提取重复元素

### 🍪 Cookie 与 Storage（4 个）
- `browser_cookies_get` - 读取归一化 cookie，默认脱敏 value
- `storage_get` - 按 key 或整体读取 localStorage/sessionStorage
- `storage_set` - 设置一个 storage 项，结果不回显 value
- `storage_clear` - 清理一个 storage key 或整个区域

### 🧪 调试与可观察性（1 个）
- `page_console_logs` - 读取有界浏览器 console 消息，支持级别过滤、cursor 分页和数量限制

### ⏱️ 等待操作（4 个）
- `wait_for_element` - 等待元素出现（带超时）
- `wait_for_url` - 等待当前 URL 包含指定文本
- `wait_until` - 等待可观察条件，例如 clickable、hidden、stable、文本或 URL 匹配
- `wait_time` - 延迟执行

### 🧩 MCP Resources 和 Prompts
- Resources：`drissionpage://session/summary`、`drissionpage://session/history`、`drissionpage://session/state`、`drissionpage://session/config`、`drissionpage://guide/model-usage`、`drissionpage://page/current`、`drissionpage://tools/catalog`、`drissionpage://policy/summary`
- Prompts：`drissionpage_mcp_usage_playbook`、`browser_navigate_and_summarize`、`browser_extract_structured_data`、`browser_fill_form_safely`、`browser_vision_guided_interaction`、`browser_debug_page_issue`

---

## 📚 文档

| 指南 | 描述 |
|-------|-------------|
| [README_CN.md](README_CN.md) | 安装、工具和架构说明 |
| [docs/long-term-roadmap-and-target-architecture.md](docs/long-term-roadmap-and-target-architecture.md) | 长期产品目标、总体架构和 1.0 路线图 |
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
│   └── tools/              # 62 个自动化、任务完成、标签页/iframe/shadow、页面理解与可观察性工具
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
        "DP_HEADLESS": "1"
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
应输出已安装的包版本，例如：`drissionpage-mcp 0.7.0`。

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
| **文档** | ✅ 安装、兼容性、故障排除和公共工具合同 |
| **包** | ✅ PyPI 元数据和构建检查 |
| **状态** | 🟡 Beta；真实浏览器行为取决于本地 Chrome/Chromium 和目标站点 |

**版本**: 0.7.0 | **许可证**: Apache 2.0 | **维护**: ✅ 活跃

---

## 🗺️ 路线图

### 当前版本 (v0.7.0)
- [x] 62 个核心自动化、任务完成、标签页/iframe/shadow、页面理解、工作流、网络监听与 console 可观察性工具，已移除 alias 工具面
- [x] stdio MCP 服务器集成
- [x] 本地环境 doctor 诊断
- [x] 稳定 JSON 镜像、`structuredContent` 和逐工具 typed MCP `outputSchema`
- [x] 常见失败会在 `error.details.hints` 中返回结构化恢复建议
- [x] `page_snapshot` 会平衡输出预算，链接密集页面仍能暴露按钮、输入框和表单
- [x] `form_inspect` 只读表单 inventory，返回 label、selector、必填状态、选项和安全的可选 value
- [x] 标签页管理：`tab_list`、`tab_switch`、`tab_close` 和 `page_navigate(new_tab=true)`
- [x] 可观察动作：`page_observe`、`page_evaluate`、`wait_until`，以及导航、点击、输入中的可选 `observe=true` 变化摘要
- [x] Console 可观察性：`page_console_logs`、`page_observe` 中的 console 摘要，以及 `observe=true` 中的 console 变化字段
- [x] Workflow helper：`browser_open_and_snapshot`、`browser_extract_links`，以及保持不提交语义的兼容工具 `form_fill_preview`
- [x] 可验证的 `form_fill` 与 operation-key 感知的 `form_submit`，返回 typed `ActionReceipt`，歧义结果不会盲目重复提交
- [x] 能力探测后的 `page_dialog_respond`、兼容扩展的双击/右键语义，以及返回安全 `ArtifactRef` 的 `element_click_and_download`
- [x] Network listener beta：`network_listen_start`、`network_listen_wait`、`network_listen_stop`，用于 HTTP/XHR/Fetch 观察
- [x] `page_pointer_move`、`page_pointer_drag` 与 `page_click_xy` 自然指针动作链：三次贝塞尔轨迹、smoothstep 缓动、有界抖动、反应延迟和真实按键停留
- [x] 有界的可选 `page_pointer_drag.waypoints`，在一次按住手势中完成画布路径、地图操作、框选或可视化编辑器连线
- [x] 文件上传、滚动、hover、select/check、键盘、iframe、shadow DOM、cookie 和 storage 工具，面向 DrissionPage 4.x
- [x] 默认保持 Chrome sandbox 开启；`DP_NO_SANDBOX=1` 仅用于受限容器/root 环境
- [x] 脱敏 session history resource，以及有界输出的响应大小 metadata
- [x] 针对导航和截图路径的可选本地安全策略
- [x] Resources、Prompts、eval harness、兼容性和故障排除文档
- [x] PyPI 发布

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

## 🆕 最新版本：v0.7.0

发布日期：2026-07-18。本版本在保持现有工具合同的前提下，打通第一阶段已授权任务完成闭环：

- `form_fill` 以真实交互语义处理原生和富控件，并提供逐字段验证和秘密脱敏。
- `form_submit` 使用 `operation_key` 执行一次已授权提交，返回有界 postcondition 证据和 typed `ActionReceipt`；歧义结果不会盲目重复提交。
- `page_dialog_respond` 通过能力探测后的原生路径处理待处理 alert、confirm 和 prompt。
- `element_click` 兼容扩展右键、中键和双击语义，现有默认值不变。
- `element_click_and_download` 将一次原生点击与一份完成产物、校验和、安全相对路径和 `ArtifactRef` 关联；相同 operation key 重放不会再次点击。
- 公开工具数现为 62 个，并继续使用严格输入 schema 和 typed output envelope。
- W01-W08 每项十轮的可靠性 benchmark 与剩余 coverage/稳定性硬化明确安排到 0.7.1；0.7.0 不声明已达到该阈值。
