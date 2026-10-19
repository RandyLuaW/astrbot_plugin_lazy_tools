# Mount low-frequency tools on demand, save half your prompt tokens

> AstrBot plugin · trims tool schemas per request using the native `remove_tool`, no core patches

## The problem

Installing more tools doesn't just make the model "unable to use them" — it makes it **read a tool manual before every reply**.

Measured on one admin private-chat request:

```
prompt_tokens = 18908    cache_read_input_tokens = 16000
```

Of that 16000-token static prefix, the persona is only ~1500. The rest is almost entirely JSON schemas for 74 tools. The model reads ten thousand words of API docs before speaking, so its tone drifts toward "operator". That's not a persona problem — it's drowning in tool docs.

And those 51 low-frequency tools are used a handful of times a month: browser, adb phone, dev workbench, Qzone, persona snapshots…

## How it works

On `on_llm_request` (priority 99), each tool group is evaluated:

| Situation | Action |
|---|---|
| Current message hits the group's keywords | **Keep**, and stamp an expiry for this session |
| No hit, but still inside TTL (25 min default) | Keep |
| Otherwise | `req.func_tool.remove_tool(name)` |

The TTL matters: without it, a follow-up like "open that video" arrives after the tool was already removed, and she just says "I can't".

Groups match by **prefix** (`browser_`), so new MCP or plugin tools join automatically. **Only known groups are touched** — stickers, journal, context, self-state, shell/files, web search are never removed. Unknown tools stay: better to spend tokens than to break something.

## Groups

| Group | Prefix / names | Keywords (excerpt) |
|---|---|---|
| `browser` | `browser_*` | browser, open page, screenshot, scrape |
| `phone` | `phone_*` | phone, emulator, adb, tap, swipe |
| `dev` | `dev_*` | edit code, workbench, probe, reload, revert |
| `qzone` | `search_wyc_tools` / `call_wyc_tools` / `run_wyc_tool` | Qzone, post, diary |
| `persona` | `persona_*` | persona, prompt, settings |
| `misc` | `block_user` / `end_session` / `get_full_dynamic_life_state` / `steam_price` / `complain_to_receivers` | block, end, schedule, steam |
| `bili_write` | `post_comment` / `like_video` / `coin_video` / `fav_video` / `follow_up` / `watch_video` … 11 total | Bilibili write actions |

About 23 tools stay resident: stickers, journal, context, self-state, built-in shell/files, web search, `send_message`, `future_task`.

## Install

### Option 1: Plugin marketplace (recommended)

Search "按需挂载工具" in the AstrBot WebUI plugin marketplace.

### Option 2: Download from Releases

Grab the zip from [Releases](../../releases), then WebUI → Plugins → Upload.

### Option 3: Clone manually

```bash
cd AstrBot/data/plugins
git clone https://github.com/RandyLuaW/astrbot_plugin_lazy_tools.git
```

No extra Python dependencies.

## Configuration

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `true` | When off, all tools stay mounted |
| `ttl_minutes` | int | `25` | How long a triggered group stays mounted |
| `always_on` | list | `[]` | Groups always mounted: `browser` / `phone` / `dev` / `qzone` / `persona` / `misc` / `bili_write` |
| `extra_keywords` | list | `[]` | Extra keywords per group, e.g. `phone=open emulator,look at phone` |
| `debug` | bool | `false` | Log removed tools every turn |

## Tuning

- **She "forgets" on the second turn**: raise `ttl_minutes` to 40–60
- **A group is needed almost every turn**: put it in `always_on` instead of relying on keywords
- **Keywords don't fire**: add your group's slang via `extra_keywords`
- **Want to see what's removed**: set `debug: true` for one round

## Notes

- Subtraction only; works alongside `astrbot_plugin_tool_guard` (priority 100) without conflict
- Removal is **per-request**; plugin registry is untouched and reload/restart restores everything
- Requires `ProviderRequest.func_tool.remove_tool()`, AstrBot `>= 4.24.0`

## License

MIT
