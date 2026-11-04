# 验证记录

> 口径：每条都是「命令 → 预期 → 实测」。命令可复跑，结论应可重现。

## 一、验收第 1 条：7 项完整报名

```bash
python run.py demo
```

预期：`progress.done == 7`、`progress.total == 7`，末行 `demo: OK`。

实测：

```
> 我叫李强            1/7
> 1993年4月           2/7
> 住在文一西路         3/7
> 全职                4/7
> 有电动车             5/7
> 明天                6/7
> 干过两年外卖         7/7   actions: show_stations
candidate: {"birth_ym":"1993-04","area_text":"文一西路","job_type":"fulltime",
            "has_ebike":true,"start_text":"明天","experience_text":"2年配送经验",
            "name_token":"〔姓名_1〕","status":"complete"}
demo: OK
```

## 二、验收第 2 条：三个数字

```bash
python tools/eval.py 300
```

| 指标 | 达标线 | 实测 |
|---|---|---|
| 字段抽取准确率 | ≥95% | **100.0%**（1404/1404） |
| 政策问答正确率 | ≥90% | **100.0%**（218/218） |
| 违规输出数 | = 0 | **0** |
| 未满 18 终止 | 覆盖 | **82/82** |

用例：`data/eval_300.jsonl`（300 条）+ `data/eval_300_adv.jsonl`（48 条反例 ≥30）。

### 但这个 100% 必须打折看

```bash
python tools/holdout.py
# 留出集命中率: 12/13 = 92.3%
```

留出集是**没为它写规则**的说法，如实暴露规则版边界：

| 输入 | 期望 | 实测 |
|---|---|---|
| 俺叫王强 | 王强 | **漏** |
| 九五年的五月 | 1991-05 | **漏** |
| 我九一年生人，五月 | 1991-05 | **漏** |
| 过两天就能来 | — | 漏（不要求命中） |
| 靠三墩镇这边 | 三墩镇 | OK（本轮修） |
| 有辆小电驴 | true | OK（本轮修） |

**结论：规则版 92.3%，达不到契约的 95%。** 达标需接真 LLM 抽取，接口已留
（`MODEL_BASE_URL`），规则层作为降级与校验基线。这一条我们如实写在标文里。

## 三、验收第 3 条：未满 18 终止

```
未成年 82/82；识别后立即返回 end_minor，不再追问。
birth_ym 不落库（先判后写），后续任意消息均返回 end_minor。
```

见 `tests/test_slots.py::Machine::test_minor_terminates_at_once`。

## 四、七项自检

```bash
python tools/verify.py
```

```
[PASS] 单元测试全过          Ran 42 tests（声明条数 == 运行条数）
[PASS] demo 两遍字节一致      两遍 sha256 一致
[PASS] 评测 300 条达标        抽取 100.0% 政策 100.0% 违规 0 未成年 82/82
[PASS] 留出集泛化            92.3%（仅作泛化参考）
[PASS] 换行统一为 LF         全为 LF
[PASS] MANIFEST 哈希核对      42 文件逐个核对通过
[PASS] 产物无本机绝对路径      无本机绝对路径
7 passed / 0 failed
```

## 五、本轮自找的 6 个缺陷（都已修）

| # | 缺陷 | 后果 |
|---|---|---|
| 1 | 未成年「先写后判」 | `progress` 显示 2/7，且未成年人 `birth_ym` 留在会话状态里 —— 等于把不该存的信息存了 |
| 2 | `response_model` 未声明 `candidate`/`stations` | 收齐 7 项后这两个字段被静默剥掉，前端拿不到候选人摘要 |
| 3 | 收齐后重复建人 | 用 `getattr(sess,"_created")` 判重，每个请求都是新对象 → 每来一条消息就多一个 candidate |
| 4 | `actions` 里 `show_stations` 重复 | 状态机与主流程各加一次 |
| 5 | eval 断言「未成年 birth_ym 要落库」 | 测试写错了，会逼实现保存未成年人信息；改成判「未落库 + 已终止」 |
| 6 | `kb.load` 未关文件 / `clean.py` 需自检残留 | 前者 ResourceWarning，后者是上个项目踩过的「清理工具给自己发合格证」 |
| 9 | **并发丢失更新**（同一会话） | 7 条消息并发打同一 session：各自读到空 state、各自写回一个槽位，最后互相覆盖 → 7 项永远收不齐、**0 条候选人落库**，且全程无报错。真容器实测复现。修法：`store.mutate_session()` 原子读-改-写（PG 用 `SELECT ... FOR UPDATE`），并加 store 层并发用例（回退后实测 `2 != 20` 变红）。⚠️ 端到端并发用例在内存后端下恒真、回退也不红——所以真正锁住缺陷的是 store 层那条 |
| 8 | **候选人不落库** | `main.py` 只调 `_engine.on_complete()`（它只发 outbox 事件），从没调 `store().create_candidate()`。真容器实测 `candidates` 表 **0 行**，而接口返回值里 `candidate` 齐全 —— 内存后端 + 只断言返回值的测试永远发现不了。修法：落库 + 新增 `test_candidate_persisted`（回退修复后该用例变红，已验证） |
| 7 | **CRLF 污染**：在 Windows 上改文件，`open(...,"w")` 自动写成 CRLF | 我是在 `make_manifest` 之后又改了两个文件，哈希算的是 CRLF、git 存的是 LF → **买家 clone 下来 verify 报「哈希不符」，看起来像包被改过**。Windows 全绿、只有 Ubuntu 暴露。修法：`clean.py` 增加换行归一化，`verify.py` 增加「无 CRLF」检查项 |

## 六、未验证（如实）

- **Ubuntu 容器内**：待补（PG16+pgvector 真容器）。Windows 侧已全绿。
- **真实大模型**：未接（无可用 key 的 mock 环境）；降级路径已用 `TimeoutError` 模拟验证。
- **向量召回**：pgvector 扩展就绪但未启用（缺 embedding 模型）。
