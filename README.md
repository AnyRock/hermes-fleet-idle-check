# hermes-fleet-idle-check

一个 90 行的小脚本：派 [Hermes Agent](https://hermes-agent.nousresearch.com) 子代理（`delegate_task`）之前，
先问一圈本地推理引擎"你现在忙不忙"，把最闲的那台写进派单调度位。

A tiny helper that picks the least-busy local inference engine before dispatching a Hermes subagent.

## 为什么需要它 / Why

Hermes 的子代理不会自己选引擎：出生时读 `delegation.provider` 配置，之后**整个生命周期钉在那台引擎上**。
这个配置每次派单时从磁盘现读（改即生效、无需重启），所以"选机器"的正确时机是**派单前一瞬间**：

```bash
python3 fleet_idle_check.py                 # -> PICK subflash
hermes config set delegation.provider subflash
# 然后正常 delegate_task
```

为什么不用 LiteLLM/nginx 这类请求级路由代理（我们试过分析后放弃了）：

1. **看不见直连流量**——least-busy 只统计穿过代理的请求；你的主会话、其他 agent 直连引擎时，代理会把子代理派到实际在用的机器。
2. **拆散会话**——agent 会话是多轮循环，每轮靠引擎侧前缀缓存；代理分不清哪些请求属于同一个会话，一旦换机，10 万 token 冷 prefill 实测 60+ 秒/轮。路由必须以子代理为单位、在派单瞬间定死。

本脚本读引擎**自报**的 `/metrics` live 段（地面真相，含所有直连流量），只做一次性推荐，不常驻、不拦截任何请求。

## 配置 / Config

`engines.json`（与脚本同目录，或作为第一个参数传入）：

```json
[
  { "provider": "subflash",  "base_url": "http://192.168.100.10:8080" },
  { "provider": "macstrata", "base_url": "http://192.168.100.20:8085", "key_env": "MACSTRATA_KEY" },
  { "provider": "localf",    "base_url": "http://127.0.0.1:8080", "resident": false }
]
```

- `provider`：Hermes `providers:` 段里的键名（`hermes config set delegation.provider <provider>` 用的就是它）
- `key_env`：鉴权 key 的环境变量名（进程 env 优先，其次 `~/.hermes/.env`）
- `resident: false`：手动档引擎——没起就跳过，脚本绝不拉起
- 并列空闲时按数组顺序取第一个（把默认偏好放前面）

## 前提 / Requirements

- 引擎暴露 Strata 风格的 `/metrics`（`live.state` / `live.queued` 字段）；其他引擎改一下 `probe()` 即可
- 所有引擎服务同一个模型 slug 时体验最好（换 provider 不用换 model）

MIT
