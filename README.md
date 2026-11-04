# 骑手招聘 Agent 化信息收集平台 · 任务 1/5

**Agent 对话引擎与政策知识库**（clawhunt #1808 / 契约 v1）

求职者扫码与 AI 助手对话，几分钟完成 7 项报名；政策回答**必须带出处**，
检索不到就转人工、绝不编造；未满 18 周岁识别后立即终止。

## 三条命令

```bash
python run.py demo                    # 零依赖跑通一次完整报名（不需要装任何包）
python -m unittest discover -s tests  # 40 项测试
docker compose up                     # PG16+pgvector + Redis 7.2 + API
```

起服务后：

```bash
curl -s -X POST localhost:8080/api/v1/agent/sessions
curl -s -X POST localhost:8080/api/v1/agent/sessions/<sid>/messages \
     -H 'Content-Type: application/json' -d '{"text":"我叫李强"}'
```

## 7 项槽位与动作

| 槽位 | 示例输入 | 抽出 |
|---|---|---|
| 称呼 | 我叫李强 / 我姓李 | 李强 |
| 出生年月 | 1993年4月 / 93年4月 / 1995年生的，1月 / １９９１年５月 | 1993-04 |
| 意向区域 | 住在文一西路 / 靠三墩镇这边 | 文一西路 / 三墩镇 |
| 岗位意向 | 全职 / 兼职 / 都行 | fulltime / parttime / undecided |
| 车辆 | 有电动车 / 有辆小电驴 / 没车 | true / false |
| 到岗时间 | 明天 / 下周一 | 明天 |
| 配送经验 | 干过两年外卖 / 没干过 | 2年配送经验 / 无经验 |

`actions` 取值：`show_stations` / `booking_confirmed` / `handoff` / `end_minor`。
收齐 7 项返回 `progress 7/7` 并附 `candidate` 与 `stations`。

## 硬口径（可自证，不是承诺）

| 要求 | 我们的实测 | 怎么复跑 |
|---|---|---|
| 7 项完整报名 | 7/7 | `python run.py demo` |
| 字段抽取准确率 ≥95% | **100.0%**（1404/1404） | `python tools/eval.py` |
| 政策问答正确率 ≥90% | **100.0%**（218/218） | 同上 |
| 违规输出 = 0 | **0** | 同上 |
| 未满 18 周岁终止 | **82/82** | 同上 |
| 评测集 ≥300 条 + 反例 ≥30 | 300 + 48 | `data/eval_300*.jsonl` |

**留出集 92.3%**（13 条可判定项 / 12 命中）。这是故意用「没为它写过规则」的说法测的：
`俺叫王强`、`九五年的五月`、`我九一年生人，五月`、`过两天就能来` 全部漏检。
规则版到不了 95%——**合同里的 ≥95% 需要接真 LLM 抽取**，本包已留好接口
（`MODEL_BASE_URL` / `MODEL_NAME`），规则层只作为降级与校验基线。

## 目录

```
app/            对话状态机、RAG、护栏、模型适配、存储、outbox
  slots.py      7 槽位状态机 + 抽取（含全角/零宽/中文数字归一）
  kb.py         政策检索：BM25 + 同义扩展 + 按 section 取最高 version
  guard.py      三类硬违规检测（收入承诺/歧视/索要敏感信息）+ 出处必填
  model.py      MockModel（确定性）与 HttpModel（OpenAI 兼容，带超时降级）
  store.py      内存 / PostgreSQL 双后端
  mocks/        任务 3 站点、任务 5 保险箱的 mock（按契约自己写，不等别人）
policy/         合成政策（v1/v2 两版，用来验「版本覆盖」）
data/           评测用例 300 条 + 反例 48 条
tools/          eval / holdout / verify / clean / make_manifest / check_package
tests/          40 项
```

## 契约对齐

- REST，前缀 `/api/v1`，JSON；错误体 `{code, message}`
- 会话接口：`POST /api/v1/agent/sessions`、`POST /api/v1/agent/sessions/{id}/messages`
- `candidate` / `station` / `booking` 字段名与枚举同契约
- outbox + Webhook，HMAC-SHA256 签名（`app/outbox.py`，`sign` / `verify` 可单独验）
- 依赖许可：fastapi(MIT) / pydantic(MIT) / uvicorn(BSD) / pg8000(BSD) / httpx(BSD)
- 送模型前先脱敏：`slots.mask()` 把手机号/身份证换 `〔手机号_1〕`，明文只在服务端

## 边界（如实说）

1. **规则版抽取到 92.3%（留出集）**，达不到 95%；上真 LLM 才能达标，接口已留。
2. **向量检索未启用**：需要 embedding 模型，mock 环境下没有。关键词层独立可跑，
   pgvector 扩展在 compose 里已就绪，接上后作为第二路召回。
3. **政策内容为合成数据**，真实政策由发单方中标后提供（单子明说不含真实政策）。
4. 任务 3（站点）、任务 5（保险箱）是**按契约写的 mock**，不依赖对方交付。
