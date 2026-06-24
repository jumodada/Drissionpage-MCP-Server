# DrissionPage MCP Server

> 基于 DrissionPage 为 Claude Code 和 MCP 客户端提供专业的浏览器自动化能力

[![PyPI](https://img.shields.io/pypi/v/drissionpage-mcp.svg)](https://pypi.org/project/drissionpage-mcp/)
[![Downloads](https://pepy.tech/badge/drissionpage-mcp/month)](https://pepy.tech/project/drissionpage-mcp)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/jumodada/Drissionpage-MCP-Server/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/jumodada/Drissionpage-MCP-Server/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/jumodada/Drissionpage-MCP-Server/branch/main/graph/badge.svg)](https://codecov.io/gh/jumodada/Drissionpage-MCP-Server)
[![Status](https://img.shields.io/badge/status-beta-yellow.svg)]()

**官方仓库**: [GitHub](https://github.com/jumodada/Drissionpage-MCP-Server) | [GitCode](https://gitcode.com/g1879/DrissionMCP)

[English Version](README.md) | [中文版本](README_CN.md)

---

## 🚀 什么是 DrissionPage MCP？

**DrissionPage MCP Server** 是一个本地模型上下文协议（MCP）服务器，为 Claude Code、Claude Desktop 和其他 MCP 客户端提供 DrissionPage 浏览器自动化工具。

与基于截图的方法不同，它通过 21 个强大工具提供**结构化、确定性的网页自动化**，利用高性能浏览器自动化框架 [DrissionPage](https://github.com/g1879/DrissionPage) 的效率。

### 🌟 为什么选择 DrissionPage MCP？

- **LLM 优化**：使用结构化数据而不需要视觉模型
- **确定性**：通过 CSS 和 XPath 支持实现可靠的元素选择
- **快速轻量**：基于 DrissionPage 高效引擎构建，开销最小
- **类型安全**：所有工具都具有完整的类型提示和 Pydantic 验证
- **开源友好**：包含兼容性说明、故障排除和 CI 检查，便于维护和贡献
- **易于集成**：简单的 `pip install` + JSON 配置即可使用

---

## ⚡ 首次成功路径

```bash
# 从 PyPI 安装
python -m pip install -U drissionpage-mcp

# 验证包和本地环境
drissionpage-mcp --version
drissionpage-mcp doctor
```

然后添加下面的 MCP 客户端配置并重启客户端。

---

## 📦 在 Claude Code 中配置（30 秒）

1. **编辑 MCP 配置文件**：
   - macOS/Linux: `~/.config/claude-code/mcp_settings.json`
   - Windows: `%APPDATA%\\claude-code\\mcp_settings.json`

2. **添加以下配置**：
   ```json
   {
     "mcpServers": {
       "drissionpage": {
         "command": "drissionpage-mcp"
       }
     }
   }
   ```

3. **重启 Claude Code** 即可开始使用！

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

## 🛠️ 21 个强大工具

### 🌐 导航工具（4 个）
- `page_navigate` - 导航到任意 URL
- `page_go_back` / `page_go_forward` - 浏览器历史记录
- `page_refresh` - 重新加载当前页面

### 🎯 元素交互与提取（8 个）
- `element_find` - 通过 CSS 选择器或 XPath 查找元素
- `element_click` - 点击任意元素
- `element_type` / `element_input_text` - 向元素输入文本
- `element_get_text` - 获取元素或整页文本
- `element_get_attribute` - 获取 HTML attribute
- `element_get_property` - 获取实时 DOM property，例如输入框当前 value
- `element_get_html` - 获取元素或整页 HTML

### 📸 页面操作（5 个）
- `page_screenshot` - 捕获完整页面或视口
- `page_resize` - 调整浏览器窗口
- `page_click_xy` - 通过坐标点击
- `page_close` - 关闭浏览器
- `page_get_url` - 获取当前 URL

### ⏱️ 等待操作（4 个）
- `wait_for_element` - 等待元素出现（带超时）
- `wait_for_url` - 等待当前 URL 包含指定文本
- `wait_time` / `wait_sleep` - 延迟执行

---

## 📚 文档

| 指南 | 描述 |
|-------|-------------|
| [README_CN.md](README_CN.md) | 安装、工具和架构说明 |
| [docs/compatibility.md](docs/compatibility.md) | Python、DrissionPage、MCP 和浏览器兼容性 |
| [docs/tool-contract.md](docs/tool-contract.md) | MCP 工具名称、输入、注解和响应格式 |
| [docs/troubleshooting.md](docs/troubleshooting.md) | doctor 命令、浏览器启动和客户端配置排查 |
| [docs/release-checklist.md](docs/release-checklist.md) | 发布验证和发布清单 |
| [examples/README.md](examples/README.md) | MCP 客户端配置示例 |
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
│   └── tools/              # 21 个自动化工具
├── examples/               # 配置模板
├── tests/                  # 单元测试
└── playground/             # 测试工具
```

**核心原则**：
- ✅ 所有工具使用类型安全的 Pydantic 模型
- ✅ 全面使用 async/await
- ✅ 清晰的关注点分离
- ✅ 全面的错误处理
- ✅ 核心工具注册和响应行为具有单元/协议测试覆盖

---

## 🔧 配置

### 基础配置（推荐）
```json
{
  "mcpServers": {
    "drissionpage": {
      "command": "drissionpage-mcp"
    }
  }
}
```

### 高级配置
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

更多配置选项请参阅 [examples/README.md](examples/README.md)。

---

## 📋 环境要求

- **Python 3.10+**（推荐 3.11+）
- **Chrome 或 Chromium** 浏览器
- **任何 MCP 兼容客户端**：Claude Code、Claude Desktop、Cursor、VS Code 等

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

# 覆盖率报告（CI 会执行当前 60% 覆盖率底线并上传 coverage.xml）
python -m pytest tests/ --cov=drissionpage_mcp --cov-report=term-missing --cov-report=xml
```

GitHub Actions 已配置 lint、单元、协议、打包、浏览器集成和覆盖率检查。
Codecov 通过 `codecov.yml` 和 CI workflow 上传覆盖率；公开仓库可使用当前
OIDC 上传配置，私有镜像通常需要先在 Codecov 中启用仓库。

### 试用
```bash
# 交互式测试
python playground/local_test.py

# 快速启动验证
python playground/quick_start.py
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
应输出已安装的包版本，例如：`drissionpage-mcp 0.3.0`。

### 浏览器问题？
```bash
# 检查浏览器安装
which google-chrome    # Linux
which chromium         # macOS
```

### Claude Code 找不到服务器？
- 验证配置文件路径
- 修改后重启 Claude Code
- 检查日志：`drissionpage-mcp --log-level DEBUG`

完整故障排除指南请参阅 [docs/troubleshooting.md](docs/troubleshooting.md)。

---

## 📊 项目状态

| 组件 | 状态 |
|-----------|--------|
| **核心功能** | ✅ 完成 |
| **测试** | ✅ 单元/协议检查，可选浏览器烟测 |
| **文档** | ✅ 安装、兼容性、故障排除、发布清单 |
| **包** | ✅ PyPI 元数据和构建检查 |
| **状态** | 🟡 Beta；真实浏览器行为取决于本地 Chrome/Chromium 和目标站点 |

**版本**: 0.3.0 | **许可证**: Apache 2.0 | **维护**: ✅ 活跃

---

## 🗺️ 路线图

### 当前版本 (v0.3.0)
- [x] 21 个核心自动化工具
- [x] stdio MCP 服务器集成
- [x] 本地环境 doctor 诊断
- [x] 兼容性和故障排除文档
- [x] PyPI 发布

### 未来版本 (v0.2+)
- [ ] 表单处理工具
- [ ] 文件上传支持
- [ ] Shadow DOM 选择器
- [ ] 会话持久化
- [ ] 代理支持
- [ ] 网络拦截

---

## 📖 集成示例

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

更多客户端配置请参阅 [examples/](examples/)。

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

## 🙏 致谢

- **[DrissionPage](https://github.com/g1879/DrissionPage)** - 优秀的浏览器自动化库
- **[Model Context Protocol](https://modelcontextprotocol.io/)** - 协议规范
- **[Claude](https://claude.ai)** - 使 AI 助手更强大和有用

---

## 💬 支持

- 📖 **[故障排除](docs/troubleshooting.md)**
- 🐛 **[报告问题](https://github.com/jumodada/Drissionpage-MCP-Server/issues)**
- 💡 **[功能请求](https://github.com/jumodada/Drissionpage-MCP-Server/discussions)**
- 🔗 **[GitHub 仓库](https://github.com/jumodada/Drissionpage-MCP-Server)**
- 📦 **[PyPI 包](https://pypi.org/project/drissionpage-mcp/)**

---

## 📈 统计

[![Downloads](https://pepy.tech/badge/drissionpage-mcp)](https://pepy.tech/project/drissionpage-mcp)
[![PyPI Version](https://badge.fury.io/py/drissionpage-mcp.svg)](https://pypi.org/project/drissionpage-mcp/)

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
