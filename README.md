# 低频工具按需挂载，省下一半 prompt token

> AstrBot 插件 · 用框架原生 `remove_tool` 按需裁剪工具 schema，不改核心

## 它解决什么问题

工具装多了，代价不是「模型不会用」，而是**每次开口前先读一遍工具说明书**。

实测一条管理员私聊请求：

```
prompt_tokens = 18908    cache_read_input_tokens = 16000
```

那 16000 的静态前缀里，人格只占约 1500 token，剩下几乎全是 74 个工具的 schema。模型每次回复前先读一万多字的接口文档，语气自然往「操作员」跑——这不是人格写得不够好，是被工具说明书淹了。

而且这 51 个低频工具，一个月也用不上几次：浏览器、adb 手机、开发工位、QQ 空间、人格快照……

## 做法

在 `on_llm_request`（priority 99）里对每个工具组判断：

| 情况 | 处理 |
|---|---|
| 本轮消息命中该组触发词 | **保留**，并给这个会话记一个到期时间 |
| 没命中，但还在 TTL 内（默认 25 分钟） | 保留 |
| 其余 | `req.func_tool.remove_tool(name)` 摘掉 |

TTL 是关键：不然「点一下那个视频」这种第二轮追问，工具已经没了，她会直接说「我做不到」。

组用**前缀匹配**（`browser_`），MCP 或插件以后新增的工具自动归组。**只摘认识的组**，其余工具（表情包、日记、上下文、自身状态、shell/文件、联网搜索）一律不碰——不认识的默认保留，宁可多花 token 也不误杀。

## 工具组

| 组 | 前缀 / 名单 | 触发词（节选） |
|---|---|---|
| `browser` | `browser_*` | 浏览器、打开网页、截图、爬、抓取 |
| `phone` | `phone_*` | 手机、模拟器、adb、点一下、滑动 |
| `dev` | `dev_*` | 改代码、工位、探针、重载、回滚 |
| `qzone` | `search_wyc_tools` / `call_wyc_tools` / `run_wyc_tool` | 空间、说说、日志、留言 |
| `persona` | `persona_*` | 人格、提示词、改设定、存档 |
| `misc` | `block_user` / `end_session` / `get_full_dynamic_life_state` / `steam_price` / `complain_to_receivers` | 拉黑、结束、日程、steam、告状 |
| `bili_write` | `post_comment` / `like_video` / `coin_video` / `fav_video` / `follow_up` / `watch_video` 等 11 个 | B站写操作、评论、投币、收藏 |

常驻不动的约 23 个：表情包、日记、上下文、自身状态、内建 shell/文件、联网搜索、`send_message`、`future_task`。

## 安装

### 方式一：插件市场（推荐）

WebUI 插件市场搜索「按需挂载工具」。

### 方式二：Releases 下载

从 [Releases](../../releases) 下载 zip，WebUI → 插件 → 上传安装。

### 方式三：手动克隆

```bash
cd AstrBot/data/plugins
git clone https://github.com/RandyLuaW/astrbot_plugin_lazy_tools.git
```

无额外 Python 依赖。

## 配置项

| 键 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `enabled` | bool | `true` | 关掉后所有工具始终挂着（等于停用本插件） |
| `ttl_minutes` | int | `25` | 触发之后这组工具保持多久（分钟） |
| `always_on` | list | `[]` | 永远保持挂载的组名，可选 `browser` / `phone` / `dev` / `qzone` / `persona` / `misc` / `bili_write` |
| `extra_keywords` | list | `[]` | 给内置组追加触发词，每条形如 `phone=开模拟器,看手机` |
| `debug` | bool | `false` | 每轮都打印摘除了哪些工具 |

## 调参建议

- **经常第二轮就「失忆」**：`ttl_minutes` 调到 40–60
- **某个组几乎每轮都要用**：直接放进 `always_on`，别靠触发词赌
- **触发词不灵**：用 `extra_keywords` 补你们群里的说法（外号、黑话）
- **想确认到底摘了什么**：`debug: true`，看一轮日志再关

## 注意事项

- 只做减法，不与 `astrbot_plugin_tool_guard`（priority 100）冲突——两者都只摘工具，互不干扰
- 摘除是**请求级**的，不动插件注册表，热重载/重启后自然恢复
- 依赖框架的 `ProviderRequest.func_tool.remove_tool()`，AstrBot `>= 4.24.0`

## License

MIT
