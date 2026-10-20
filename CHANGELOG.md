# 更新日志

所有重要变更记录于此。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## [1.1.2] - 2026-10-20

### 修复

- **`bili_recall` 改为常驻**：它是 B站 记忆检索，属于读操作，之前跟着 `bili_write` 组一起被摘，等于把「记性」锁在触发词后面。现在从写组移出，始终挂载。

### 变更

- 注释脱敏：去掉个人化的原话引用，改为按工具性质说明为什么常驻。

## [1.1.1] - 2026-10-20

### 修复

- **`qzone` 组不再按需摘除**：`search_wyc_tools` 是她查聊天记录（`get_group_msg_history` / `get_friend_msg_history`）的唯一入口，而「要不要翻记录」往往不是用户话里带的词——触发词匹配不上，整组工具就不在，她会去调一个不存在的工具然后静默失败。三个 schema 约几百 token，换「想查就能查」值得。
- 组数 7 → 6，常驻工具相应多 3 个。

## [1.1.0] - 2026-10-20

### 新增

- **新增 `bili_write` 工具组**：11 个 B站写操作工具（`post_comment`、`like_video`、`coin_video`、`fav_video`、`follow_up`、`bili_block_user`、`bili_parse_video`、`bili_recall`、`watch_video`、`bili_watch_videos`、`watch_and_share_video_private`）默认摘除，命中触发词才挂载。
  这些工具单次会话用不上几次，但 schema 每次都占着上下文；摘掉后管理员私聊的静态前缀进一步下降。

### 变更

- 工具组数 6 → 7。常驻工具不变（表情包、日记、上下文、自身状态、内建 shell/文件、联网搜索等约 23 个）。

## [1.0.0] - 2026-10-20

### 新增

- 首个公开版本。
- 6 组工具按需挂载：`browser` / `phone` / `dev` / `qzone` / `persona` / `misc`。
- 前缀匹配自动归组，未知工具不误杀。
- 触发词命中后按 TTL（默认 25 分钟）保持挂载，支持 `always_on` 与 `extra_keywords`。
- 使用框架原生 `remove_tool`，不改 AstrBot 核心，摘除只在请求级生效。
