# -*- coding: utf-8 -*-
"""按需挂载工具：低频工具组默认摘掉，命中触发词才挂上来。

为什么需要
----------
    管理员私聊一次请求会挂 74 个工具。实测那条日志里
    `prompt_tokens=18908 / cache_read_input_tokens=16000`——这 16000 token 的
    静态前缀里，人格只占约 1500，剩下的几乎全是工具 schema。
    她每次开口前先读一万多字的接口文档，语气自然往"操作员"跑；
    而且 51 个工具一个月也用不上几次。

做法
----
    在 `on_llm_request` 里对每个工具组判断：

      - 本轮消息命中触发词 → 保留，并给这个会话记一个到期时间
      - 没命中但还在 TTL 内（默认 25 分钟）→ 保留
      - 其余 → `req.func_tool.remove_tool(name)` 摘掉

    TTL 是关键：不然"点一下那个视频"这种第二轮追问，工具已经没了，
    她会直接说"我做不到"。

    组用**前缀匹配**（`browser_`），MCP 或插件以后加新工具也自动归组。
    只摘认识的组，其余工具（表情包、日记、上下文、自身状态、shell/文件、
    联网搜索）一律不碰——不认识的默认保留，宁可多花 token 也不误杀。

优先级
------
    99，排在 tool_guard(100) 之后。两者都只做减法，互不干扰。
"""

from __future__ import annotations

import time
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

PLUGIN_NAME = "astrbot_plugin_lazy_tools"

HOOK_PRIORITY = 99

# 工具组定义：match 是工具名**前缀**，keywords 是触发词（大小写不敏感的子串匹配）。
# 宁可触发词放宽（多挂一组 = 多花几千 token），也不要漏（她当场变傻）。
GROUPS: list[dict[str, Any]] = [
    {
        "name": "browser",
        "match": ["browser_"],
        "keywords": [
            "浏览器", "网页", "网址", "链接", "官网", "页面",
            "http://", "https://", "www.", "打开这个网站", "上网查", "搜一下网",
        ],
    },
    {
        "name": "phone",
        "match": ["phone_"],
        "keywords": [
            "手机", "模拟器", "安卓", "android", "adb",
            "b站", "bilibili", "哔哩", "抖音", "小红书",
            "开个app", "装个app", "打开app",
        ],
    },
    {
        "name": "dev",
        "match": ["dev_"],
        "keywords": [
            "工位", "staging", "探针", "改代码", "插件代码",
            "重构", "打补丁", "自己的代码", "改个插件", "dev_",
        ],
    },
    # qzone 组不摘了：search_wyc_tools 是她查聊天记录（get_group_msg_history /
    # get_friend_msg_history）的唯一入口，而"要不要查记录"往往不是用户话里带的词
    # ——触发词匹配不上就整个组不在，她会调一个不存在的工具，然后静默失败。
    # 三个 schema 大概几百 token，换"想查就能查"，值。
    {
        "name": "persona",
        "match": ["persona_"],
        "keywords": ["人格", "快照", "退回", "回滚", "设回来", "改设定"],
    },
    {
        "name": "misc",
        "match": [
            "block_user",
            "end_session",
            "get_full_dynamic_life_state",
            "steam_price",
            "complain_to_receivers",
        ],
        "keywords": ["拉黑", "骚扰", "steam", "游戏价格", "告状", "投诉", "生活状态"],
    },
    {
        # 永不放行的组：B站插件里几件"不该由她自己决定"的事。
        # keywords 故意留空，命中不了任何一句话，所以每次请求都会被摘掉。
        #
        # 注意 bili_action **不在这里**：插件对写操作用的是幂等队列，
        # key = f"tool_comment:{oid}:{digest(comment_text)}"，同一条评论
        # 重复提交会被挡住，但"同一个视频再评一条不同的话"是允许的——
        # 那属于她自己的意愿，不该替她拦。
        "name": "bili_write",
        "match": [
            "post_comment",
            "like_video",
            "coin_video",
            "fav_video",
            "follow_up",
            "bili_block_user",
            "watch_and_share_video_private",
            "bili_parse_video",
            "bili_recall",
            # watch_video 是"取素材+评分+写记忆"一体：素材被插件自己的 LLM
            # 消化掉，打分发生在没有上下文的地方。她要真看，走 bili_read。
            "watch_video",
            "bili_watch_videos",
        ],
        "keywords": [],
    },
]

DEFAULT_CONFIG = {
    "enabled": True,
    "ttl_minutes": 25,
    "always_on": [],
    "extra_keywords": [],
    "debug": False,
}


def _flag(v: Any) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on", "是")
    return bool(v)


def _as_list(v: Any) -> list[str]:
    if isinstance(v, str):
        v = v.replace("，", ",").split("\n")
        out: list[str] = []
        for line in v:
            out.extend(x.strip() for x in line.split(","))
        return [x for x in out if x]
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()]
    return []


class LazyToolsPlugin(Star):
    def __init__(self, context: Context, config: Any = None):
        super().__init__(context)
        self.cfg = dict(DEFAULT_CONFIG)
        if isinstance(config, dict):
            self.cfg.update({k: v for k, v in config.items() if k in DEFAULT_CONFIG})
        self._groups = self._build_groups()
        # (umo, group) -> 到期时间（monotonic）
        self._until: dict[tuple[str, str], float] = {}
        # umo -> 上次摘除的工具名集合，用于"变化时才记日志"
        self._last_removed: dict[str, frozenset[str]] = {}

    async def initialize(self) -> None:
        names = [g["name"] for g in self._groups]
        logger.info(
            f"[lazy-tools] 就绪，{len(names)} 组按需挂载：{names}"
            f"｜TTL {self._cfg('ttl_minutes')} 分钟"
            f"｜常驻 {_as_list(self._cfg('always_on')) or '（无）'}"
        )

    async def terminate(self) -> None:
        self._until.clear()
        self._last_removed.clear()

    # ---------- 配置 ----------

    def _cfg(self, key: str) -> Any:
        return self.cfg.get(key, DEFAULT_CONFIG.get(key))

    def _build_groups(self) -> list[dict[str, Any]]:
        """把 extra_keywords 合进内置组。

        extra_keywords 每条形如 `group=词1,词2`；组名不认识就忽略。
        """
        groups = [dict(g) for g in GROUPS]
        by_name = {g["name"]: g for g in groups}
        for line in _as_list(self._cfg("extra_keywords")):
            if "=" not in line:
                continue
            gname, _, rest = line.partition("=")
            gname = gname.strip()
            g = by_name.get(gname)
            if g is None:
                logger.warning(f"[lazy-tools] extra_keywords 里的组不存在：{gname}")
                continue
            extra = [w for w in _as_list(rest)]
            g["keywords"] = list(g["keywords"]) + extra
        return groups

    # ---------- 判定 ----------

    @staticmethod
    def _message_of(event: AstrMessageEvent) -> str:
        try:
            text = event.get_message_str()
        except Exception:
            text = getattr(event, "message_str", "") or ""
        return str(text or "")

    @staticmethod
    def _hit(text: str, keywords: list[str]) -> str:
        low = text.lower()
        for kw in keywords:
            if kw and kw.lower() in low:
                return kw
        return ""

    @staticmethod
    def _matches(tool_name: str, patterns: list[str]) -> bool:
        """`match` 里的条目一律按**前缀**匹配。

        写成 `browser_` 就能覆盖全部浏览器工具；写成 `block_user` 这种完整
        名字也成立（前缀等于自身）。MCP 或插件以后加工具会自动归组。
        支持末尾带 `*` 的写法，等价于去掉星号。
        """
        for p in patterns:
            if not p:
                continue
            p = p[:-1] if p.endswith("*") else p
            if tool_name.startswith(p):
                return True
        return False

    def _always_on(self) -> set[str]:
        return set(_as_list(self._cfg("always_on")))

    # ---------- 主逻辑 ----------

    @filter.on_llm_request(priority=HOOK_PRIORITY)
    async def trim_tools(self, event: AstrMessageEvent, req: Any) -> None:
        if not _flag(self._cfg("enabled")):
            return

        tool_set = getattr(req, "func_tool", None)
        if tool_set is None or not hasattr(tool_set, "remove_tool"):
            return

        present = [
            str(getattr(t, "name", "") or "")
            for t in (getattr(tool_set, "tools", []) or [])
        ]
        if not present:
            return

        umo = str(getattr(event, "unified_msg_origin", "") or "")
        text = self._message_of(event)
        now = time.monotonic()
        ttl = max(1, int(self._cfg("ttl_minutes") or 25)) * 60
        always = self._always_on()

        removed: list[str] = []
        for group in self._groups:
            gname = group["name"]
            key = (umo, gname)
            members = [n for n in present if self._matches(n, group["match"])]
            if not members:
                continue

            if gname in always:
                continue

            kw = self._hit(text, group["keywords"])
            if kw:
                if self._until.get(key, 0) < now:
                    logger.info(
                        f"[lazy-tools] {umo} 挂上 {gname}（命中「{kw}」），"
                        f"{ttl // 60} 分钟内保持"
                    )
                self._until[key] = now + ttl
                continue

            if self._until.get(key, 0) > now:
                continue

            for name in members:
                try:
                    tool_set.remove_tool(name)
                    removed.append(name)
                except Exception:
                    continue

        # 过期记录清理，避免长跑进程里字典无限长
        if len(self._until) > 256:
            for k in [k for k, v in self._until.items() if v < now]:
                self._until.pop(k, None)

        last = self._last_removed.get(umo)
        if removed:
            cur = frozenset(removed)
            if cur != last or _flag(self._cfg("debug")):
                self._last_removed[umo] = cur
                logger.info(
                    f"[lazy-tools] {umo} 摘除 {len(set(removed))} 个："
                    f"{sorted(set(removed))}"
                )
        elif last:
            self._last_removed.pop(umo, None)
            logger.info(f"[lazy-tools] {umo} 工具已全部挂齐")
