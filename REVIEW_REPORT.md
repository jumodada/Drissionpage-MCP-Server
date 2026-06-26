# DrissionPage MCP Server 实测报告

> 测试日期：2026/06/26
> 测试人：Claude (Opus 4.8)
> 项目仓库：https://github.com/jumodada/Drissionpage-MCP-Server
> PyPI 最新：`drissionpage-mcp==0.3.1`
> 仓库当前：`0.4.0`（未发布）

---

## 一、测试方法

为了避免 IDE/MCP 客户端的额外变量，全程使用**最小 stdio JSON-RPC 客户端**直接和 server 通信，路径如下：

1. 干净 venv 安装 PyPI 上的 `drissionpage-mcp`（拿到 **0.3.1**）
2. 跑 `drissionpage-mcp doctor` 和 `doctor --launch-browser` 验证发布产物
3. 自写 minimal stdio MCP client，按协议走完：
   - `initialize`
   - `notifications/initialized`
   - `tools/list`
   - `resources/list`
   - `prompts/list`
   - `resources/read drissionpage://tools/catalog`
   - 然后串行 `tools/call`：navigate / get_url / find / get_text / get_html / screenshot / wait / type / get_property / 关页
4. 切换到仓库 0.4.0（`pip install -e .`）重测一遍
5. 跑 `pytest tests/`：**94 passed in 4.72s**
6. 单独跑选择器对照实验（`h1` vs `tag:h1` vs `css:h1` vs `xpath://h1`）和 CSS 属性选择器实验

## 二、总体结论

**架构和工程素养是这一档（个人 / 小团队 MCP 项目）里的优等生**——Pydantic schema、`tool_errors` 上下文管理器、`isError` + 结构化 `error.code` 枚举、`### JSON_RESULT` 双输出、`drissionpage://` 资源、4 个 task prompts、`doctor` 诊断子命令带 JSON_RESULT 块……每一项单看都做得到位。

但**实际让 LLM 调用时翻车的点，几乎没有一个被测试套件覆盖**，原因下面具体说。

---

## 三、真正影响可用性的问题（按严重度排）

### 🔴 P0-1：选择器语义和工具描述完全不一致（最致命）

工具描述写的是 `"CSS selector or XPath to find the element"`，但 `DrissionPage.ele()` 默认**既不是 CSS，也不是 XPath**，而是"先按文本模糊匹配，再尝试别的"。

实测对照（页面 = `https://example.com`）：

| 选择器 | 结果 | 命中标签 |
|---|---|---|
| `"h1"` | ✓ found=true | `<style>` ❌（CSS 文本里有 "h1" 字样） |
| `"tag:h1"` | ✓ found=true | `<h1>` ✓ |
| `"css:h1"` | ✓ found=true | `<h1>` ✓ |
| `"xpath://h1"` | ✓ found=true | `<h1>` ✓ |

httpbin 表单页：

| 选择器 | 结果 |
|---|---|
| `"input[name='custname']"` (纯 CSS) | ✗ ELEMENT_NOT_FOUND |
| `"css:input[name='custname']"` | ✓ |
| `"@name=custname"` | ✓ |

**问题严重性**：
LLM 看到 "CSS selector or XPath" 就会理所当然写 `h1` 或 `input[name=x]`，然后：
- 要么找不到元素（后续动作全部失败）
- 要么找到错的元素**还告诉它 `found=true`** —— LLM 完全没机会发现自己错了

后者尤其凶险，可能导致 LLM 自信地操作到错误的 DOM 节点。

**建议修复（任选或组合）**：

1. 描述改为如实表述：
   ```
   DrissionPage locator: 'tag:h1' / 'css:.foo' / 'xpath://h1' / '@name=x'.
   Bare strings are treated as fuzzy text match, NOT CSS.
   Examples: 'css:input[name=q]', 'xpath://button[contains(text(),"Submit")]'
   ```

2. 在 wrapper 里**自动加 `css:` 前缀**：当输入像合法 CSS 时透明转换。把 DrissionPage 这个怪癖屏蔽掉，对 LLM 才友好。

3. 在 element 返回信息里加 `matched_by: "text_fuzzy" / "css" / "xpath" / "tag"` 字段——让 LLM 看见这次匹配究竟是怎么发生的，发现异常时能自我纠偏。

**推荐做法**：方案 1 + 方案 2 一起做。方案 2 是 MCP 工具的天职——把底层库的人类便利 API 翻译成 LLM 友好接口。

---

### 🔴 P0-2：`serverInfo.version` 永远是 `1.28.0`

通过 MCP 协议读到的 server 版本始终是 **MCP SDK 自己的版本号**，不是 drissionpage-mcp 自己的：

```
[1] initialize: protocol='2024-11-05',
    server={'name': 'DrissionPage MCP', 'version': '1.28.0'}
```

**根因**：`server.py:194-196` 调的是 `self.server.create_initialization_options()`，该方法没传 `server_version`，默认填了 MCP 库版本。

**修法**（一段代码）：

```python
from mcp.server.models import InitializationOptions
from mcp.server.lowlevel import NotificationOptions

await self.server.run(
    read_stream,
    write_stream,
    InitializationOptions(
        server_name=self.name,
        server_version=self.version,
        capabilities=self.server.get_capabilities(
            notification_options=NotificationOptions(),
            experimental_capabilities={},
        ),
    ),
)
```

---

### 🟠 P1-3：参数命名不友好 — `element_get_property` 实际要 `property_name`

实测：

```
✗ element_get_property({"selector": "input[name='custname']", "property": "value"})
   → error.code = MCP_ARGUMENT_INVALID
```

工具 description 没提参数名，但 Pydantic schema 里写的是 `property_name`。LLM 自然会写 `property`。

**建议**：
- 接受 `property` 作为别名（Pydantic `Field(alias='property')`）
- 或工具 description 里给出完整调用例子
- 全局检查所有 `xxx_name` 字段做同样处理（避免和 Python 关键字冲突时是合理的，但要对 LLM 友好）

---

### 🟠 P1-4：PyPI 0.3.1 和仓库 0.4.0 严重脱节

| 项目 | 0.3.1 (PyPI) | 0.4.0 (Repo) |
|---|---|---|
| 工具数 | 21（含 `_input_text` / `_sleep` 别名） | 19（去掉别名） |
| Resources | 0 个 ❌ | 4 个 ✓ |
| Prompts | 0 个 ❌ | 4 个 ✓ |
| README 描述 | 与 0.4.0 一致 | 与 0.4.0 一致 |

**问题**：用户 `pip install drissionpage-mcp` 装到 0.3.1，但 GitHub README 在吹 4+4 个 resources/prompts。结果用户 `resources/list` 返回 0 个，会怀疑安装出问题或 server 坏了。

**建议**：
- 尽快推 0.4.0 到 PyPI
- 在推之前，README 顶部加一行 `> 当前 PyPI 最新 = 0.3.1；0.4.0 待发布`

---

### 🟡 P2-5：测试套件 100% mock，没有真浏览器集成测试

`tests/test_tab.py:185` 那个 `test_element_actions_and_readers` 全程喂 `FakePage`：

```python
async def test_element_actions_and_readers() -> None:
    element = FakeElement()
    page = FakePage(element)
    tab = PageTab(page, FakeContext())
    ...
    found = await tab.find_element("#name")
    assert found == {"found": True, "selector": "#name", "tag": "input", ...}
```

FakePage 不论传什么 selector 都返回预设 element。所以 **P0-1 那个选择器 bug 在测试里根本不会被发现**。

**建议**：加一个 `tests/test_real_browser.py`，用 `data:text/html,<html><body><h1>x</h1><input name=q></body></html>` 内联页面（不依赖外网）跑 5 个真实 case：

- `element_find("h1")` 应当返回 `tag="h1"`（这一条目前会失败）
- `element_find("css:h1")` 也应该返回 `tag="h1"`
- `element_find("input[name=q]")` 应该找到 input
- `element_get_text("tag:h1")` 应该返回 `"x"`
- `element_find("不存在选择器")` 应该正确返回 `ELEMENT_NOT_FOUND`

5 个用例可以拦下 95% 真实失败模式。

---

### 🟡 P2-6：`element_find` 错命中时不报错

返回 `{"found": true, "tag": "style", ...}` 把"我找到了一个不太对的"也算成功。LLM 无法察觉。

**建议**：
- 如果 selector 有明确意图（`css:`/`xpath:`/`tag:`），命中类型不符就降为 warning + `confidence: low`
- 或在返回里加 `matched_by` 字段（同 P0-1 方案 3）

---

### 🟢 P3 小事

- **失败路径 timeout 太长**：`element_find` 找不到等 10s 才返回，连续失败时延迟难受。建议失败路径默认 1-2s。
- **README chrome 路径检测命令写反了**：`which google-chrome` 写在 Linux 段，`which chromium` 写在 macOS 段，应该反过来（README_CN 同样问题）。
- **MANIFEST.in**：发布时建议确认 `playground/` 不会进 wheel。
- **`policy_summary` 资源很赞**，但 `browser_fill_form_safely` prompt 仅是"提示用户确认"，没有 server 端写保护开关。可考虑给 `element_click` / `element_type` 加 `requireApproval` 模式（CLI flag 或环境变量），符合 MCP "destructive" 工具最佳实践。

---

## 四、跑通且做得好的部分

这些是**值得保留并继续推**的设计：

- **`doctor` 子命令** — 开箱即用诊断 chrome 路径、mcp 包版本、python 版本，**且双格式输出**（人类可读 + `### JSON_RESULT` 块）。用户复制 JSON 给排查者，体验拔群。
- **`### JSON_RESULT` 双格式响应** — 人类读 text，LLM 抓 JSON。比单纯 stringify dict 友好 10 倍。
- **错误用 `error.code` 枚举** — `ELEMENT_NOT_FOUND` / `MCP_ARGUMENT_INVALID` 等结构化代码，比 stack trace 字符串好处理。
- **`tool_errors` 上下文管理器 + `response.add_code(...)`** — 把"这一步等价 Python 代码"也返回给 LLM，可观察性细节做到位。
- **19 个工具颗粒度合适** — 不是 `browser_do_anything(json)` 万能门面，每个工具有 Pydantic schema，LLM 几乎不会传错类型。
- **94 个单元测试 + 4.7s 跑完 + coverage.xml** — CI 信号好。
- **Prompts 设计** — `browser_navigate_and_summarize` / `browser_extract_structured_data` / `browser_fill_form_safely` / `browser_debug_page_issue` 这种"任务模板"是 MCP 比较少见的好实践。

---

## 五、原始测试数据

### 5.1 doctor 输出

```
DrissionPage MCP doctor
status: ok
version: 0.3.1
platform: Darwin 23.3.0 arm64
checks:
  - [ok] python: 3.11.11
  - [ok] mcp_package: 1.28.0
  - [ok] drissionpage_package: 4.1.1.4
  - [ok] browser_binary: /Applications/Google Chrome.app/Contents/MacOS/Google Chrome
  - [ok] config: default environment
  - [ok] browser_launch: launched successfully
```

### 5.2 0.3.1 协议探测

```
[1] initialize: server={'name': 'DrissionPage MCP', 'version': '1.28.0'}  ⚠️
[2] tools/list: 21 tools
[3] resources/list: 0 resources  ⚠️
[4] prompts/list: 0 prompts      ⚠️
```

### 5.3 0.4.0 协议探测

```
[1] initialize: server={'name': 'DrissionPage MCP', 'version': '1.28.0'}  ⚠️ 仍未修
[2] tools/list: 19 tools
[3] resources/list: 4 resources  ✓
[4] prompts/list: 4 prompts      ✓
```

### 5.4 工具调用结果（0.4.0，示例 example.com → httpbin）

```
✓ page_navigate(example.com)                  [2307ms]
✓ page_get_url()                              [12ms]
✓ element_find({selector:"h1"})               [20ms]  ← found=true 但命中 <style>
✓ element_get_text({selector:"h1"})           [3ms]   ← text=""（因为命中 style）
✓ element_get_html({selector:"body"})         [6ms]
✓ page_screenshot({full_page:false})          [67ms]  42259 bytes
✓ wait_time({seconds:0.5})                    [519ms]
✓ wait_for_element({selector:"h1",timeout:5}) [9ms]
✓ page_navigate(httpbin/forms/post)           [5438ms]
✗ element_type({selector:"input[name='...']"}) [10009ms] ELEMENT_NOT_FOUND
✗ element_get_property({...,"property":"value"}) [4ms] MCP_ARGUMENT_INVALID
✗ element_find({selector:"#not-here"})        [10014ms] ELEMENT_NOT_FOUND ✓ 预期
✓ page_close()                                [1016ms]
```

### 5.5 选择器对照实验

```
example.com:
  "h1"          → found=true, tag="style"  ❌
  "tag:h1"      → found=true, tag="h1"     ✓
  "css:h1"      → found=true, tag="h1"     ✓
  "xpath://h1"  → found=true, tag="h1"     ✓

httpbin form:
  "input[name='custname']"     → ELEMENT_NOT_FOUND ❌
  "css:input[name='custname']" → found, <input>   ✓
  "@name=custname"             → found, <input>   ✓
```

---

## 六、给作者的优化路线（按 ROI 排）

| 序号 | 任务 | 工作量 | 收益 |
|---|---|---|---|
| 1 | 修选择器语义（P0-1）：自动 `css:` 前缀 + 描述如实化 | 半天 | 整套元素工具可用度翻倍 |
| 2 | 修 `serverInfo` 版本（P0-2） | 5 分钟 | 客户端能正确识别版本 |
| 3 | 加 `property` 别名 + 每个工具 description 加调用 example（P1-3） | 1 小时 | LLM 调用成功率明显提升 |
| 4 | 把 0.4.0 推上 PyPI（P1-4） | 30 分钟 | 文档和实际一致 |
| 5 | 加 5 个真浏览器集成测试（P2-5） | 半天 | 上面这些 bug 以后不会回归 |

**做完这 5 条**：从"能 demo"升级到"敢推荐给别人长期用"。

---

## 七、个人结论

**当前状态**：架构方向对，beta 阶段名副其实。

**适合**：
- 自己写脚本玩、做实验
- 跟 Codex / Claude Code 接起来做轻量自动化探索

**还不太适合**：
- 接生产
- 给不熟悉 DrissionPage 选择器约定的用户用（选择器陷阱会让他们一脸懵）

但这个项目的**底层工程质量明显在线**——doctor、双格式输出、structured errors、prompts/resources 架构、稳定的 Pydantic 边界——这些东西做对的人不多。把 P0-1 和 P0-2 修了，再发个 0.4.1，就可以撕掉 beta 标签往 1.0 走了。
