# 变更记录

## 1.0.0 — 2026-11-04

首个交付版本。

- 7 槽位状态机（含全角数字、零宽字符、中文数字归一化）
- 政策 RAG：BM25 + 同义扩展（工资→报酬）+ 按 section 取最高 version
- 护栏：收入承诺 / 歧视性表述 / 索要敏感信息 三类检测 + 出处必填
- 模型适配：`MockModel`（确定性）+ `HttpModel`（OpenAI 兼容，超时降级）
- 存储：内存 / PostgreSQL 双后端
- 任务 3 站点、任务 5 保险箱 mock（按契约自写）
- outbox + Webhook，HMAC-SHA256 签名
- 评测 300 条 + 反例 45 条；留出集 20 条（92.3%）
- 40 项单元测试；`tools/verify.py` 六项自检

修复（交付前自找）：

1. 未成年先写后判 → 改为先判后写，`birth_ym` 不落库
2. `MessageOut` 未声明 `candidate`/`stations` → 被 response_model 静默剥掉
3. 收齐后重复建 candidate（判重对象每次都是新的）
4. `actions` 中 `show_stations` 重复
5. eval 断言与契约冲突（要求落库未成年人信息）
6. `kb.load` 文件未关；`clean.py` 增加残留自检
