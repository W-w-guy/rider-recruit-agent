# 骑手招聘 Agent 化信息收集平台 · 任务 1/5

**Agent 对话引擎与政策知识库**（clawhunt #1808 / 契约 v1）

求职者扫码与 AI 助手对话，几分钟完成 7 项报名；政策回答**必须带出处**，
检索不到就转人工、绝不编造；未满 18 周岁识别后立即终止。

## 三条命令

```bash
python run.py demo                    # 零依赖跑通一次完整报名（不需要装任何包）
python -m unittest discover -s tests  # 67 项测试（含验收第1~8条）
docker compose up                     # PG16+pgvector + Redis 7.2 + API
python tools/diagnose.py               # 模型体检报告：分数归因
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

## 责任边界（请先读这一节）

合同写「字段抽取准确率 ≥95%」。这个数字**由接入的大模型决定，不由本框架决定**。
因此本包承诺与不承诺的东西，必须分清：

| 属于 | 内容 | 谁负责 |
|---|---|---|
| **本框架** | 模型可插拔（OpenAI 兼容，改 3 个环境变量即生效） | 我方 |
| | 模型不可用/超时 → 自动降级到规则，报名不中断 | 我方 |
| | 模型幻觉护栏（原文片段 + 确定性换算，杜绝「三年半→5年」） | 我方 |
| | 硬违规 0、PII 不进模型、未成年拦截 | 我方 |
| | 判等口径、等价类归一、评测集与一键复跑 | 我方 |
| | **分数归因报告**（分清是模型不行还是框架不行） | 我方 |
| **接入的模型** | 语义能力：方言、错字、模糊时间、非标准经验说法 | **客户选型** |

**我们不承诺某一固定准确率。** 因为换一个模型，分数就变；承诺了也是假的。
我们承诺的是：**你接上模型、跑一条命令，拿到的是真实可归因的分数。**

## 一条命令做模型体检

```bash
# ① 先看规则基线（不花一分钱，不需要 key）
python tools/diagnose.py

# ② 接入你自己的模型再看一次
export MODEL_BASE_URL=https://api.deepseek.com/v1
export MODEL_NAME=deepseek-chat
export MODEL_API_KEY=sk-xxx      # 只读进进程内存，不落盘、不进日志
python tools/diagnose.py
```

输出三段：**准确率（按字段+加权）／盲测集／框架侧指标（安全三项、降级率）**，
并直接指出最弱的三个字段。低于 95% 时，先换更强模型复跑同一条命令。

## 我方实测（如实披露，不含修饰）

| 指标 | 纯规则（不接模型） | deepseek-flash |
|---|---|---|
| 主评测集 300 条 | 95.57% | 99.30% |
| **盲测 45 条（未参与设计）** | **77.78%** | **91.10%** |
| 注入拦截 | 45/45 | 45/45 |
| 敏感信息不泄漏 | 25/25 | 25/25 |
| 未满 18 岁拦截 | 20/20 | 20/20 |
| 政策问答正确率 | 100%（见 VERIFICATION） | — |

**为什么同时报两个数**：300 条在开发中被反复迭代，分数偏乐观；
盲测 45 条是本实现未参与设计的句子，**91.10% 才是真实水平**。
盲测差距集中在「大概周五」「周一行不行」「干了半年」这类需要世界知识与语用常识的说法
——那正是大模型该补的部分，也正是本框架预留接口的意义。

我方不宣称盲测已达 95%。建议接入语义抽取能力更强的模型后复跑 `diagnose.py` 复核。

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
