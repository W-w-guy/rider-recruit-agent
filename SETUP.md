# 启动说明

## 一、最省事：零依赖跑通

需要有 Python 3.10+（推荐 3.12，与契约一致）。**不需要装任何第三方包**：

```bash
python run.py demo
# 输出 demo_report.json，末行 demo: OK
```

它做的事：走完 7 项报名 → 建 candidate → 问 3 个政策问题（2 个带出处、1 个转人工）。

## 二、起 HTTP 服务（本地）

```bash
python -m pip install -r requirements.txt
python run.py serve
# 或 uvicorn app.main:app --port 8080
```

不设 `DATABASE_URL` 时用内存后端（数据不落盘，适合试跑）。
OpenAPI 文档：<http://localhost:8080/docs>

## 三、docker compose 一键起（契约要求）

```bash
docker compose up --build
```

三个容器：`db`（pgvector/pgvector:pg16）、`cache`（redis:7.2）、`api`。
`api` 会等 db 与 cache 健康后再起。端口可用 `API_PORT` 覆盖：

```bash
API_PORT=18080 docker compose up
```

验证：

```bash
curl -s localhost:8080/health
# {"status":"ok","version":"1.0.0","store":"postgres",...}
```

## 四、接真实模型（可选）

```bash
export MODEL_BASE_URL=https://api.deepseek.com/v1
export MODEL_NAME=deepseek-chat
export MODEL_API_KEY=sk-...        # 若服务需要
```

不设 `MODEL_BASE_URL` 时用 `MockModel`（确定性规则改写）。
模型超时会自动降级：政策问答转人工，**报名流程不中断**（`degraded: true`）。

## 五、自检

```bash
python tools/clean.py          # 清缓存（清完自检残留）
python tools/make_manifest.py  # 重算 MANIFEST
python tools/verify.py         # 6 项全过
```

## 六、常见问题

| 现象 | 原因与处理 |
|---|---|
| `localhost:8080` 不通 | `api` 要等 `db` 健康（约 10–20 秒）；`docker compose ps` 看状态 |
| 端口被占 | `API_PORT=18080 docker compose up` |
| 数据没了 | 没设 `DATABASE_URL` 时是内存后端；compose 里是 PG，数据在 `pgdata` 卷 |
| 政策答不出 | 属预期：检索不到就转人工（`handoff.requested` 事件进 outbox） |
