# 上手教程（约两个晚上）

这份文档教你**亲手**把本仓库跑通、部署到一台云主机，并准备面试口述。  
它是学习参考实现，不是替你写的「成品作品集」。你需要自己理解、改一改、用自己的 Git 历史推到自己的 GitHub。

> 前置：会 Linux / Shell，用过 Grafana，能在本机跑 Ollama 一类本地模型更佳。  
> 目标岗位画像：云平台 / DevOps（云、Ansible、CI/CD、监控、LLM 接入与负责任 AI）。

---

## 晚上 1：本地跑通 API + 测试 + Compose

### 步骤 1 — 拿到代码并建虚拟环境

```bash
# 假设你已把本目录放到自己机器
cd aiops-log-assistant
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -U pip
pip install -r requirements-dev.txt
```

**验收：** `python -c "import fastapi, httpx, prometheus_client; print('ok')"` 无报错。

### 步骤 2 — 跑测试与静态检查

```bash
ruff check .
ruff format --check .
pytest -q
```

**验收：** pytest 全绿。测试里 **mock 了 LLM**，不需要本机已有 Ollama。

**面试口述点：** 为什么要 mock？——单测应稳定、快、不依赖外网和大模型；LLM 用契约测试 / 集成测试另做。

### 步骤 3 — 只起 API，走规则兜底

```bash
uvicorn app.main:app --reload --port 8000
# 另开终端
curl -s http://127.0.0.1:8000/healthz | jq .
curl -s -X POST http://127.0.0.1:8000/analyze \
  -H 'Content-Type: application/json' \
  -d '{"text":"Out of memory: Killed process 1234 (java)","force_fallback":true}' | jq .
```

**验收：** `analysis_source` 为 `rule_fallback`，`matched_rule` 为 `oom_killer`。

**面试口述点：** 线上模型冷启动或超时怎么办？——显式降级到规则引擎，并在响应里标明来源，避免运维误判。

### 步骤 4 — 验证脱敏（Responsible AI）

```bash
curl -s -X POST http://127.0.0.1:8000/analyze \
  -H 'Content-Type: application/json' \
  -d '{"text":"timeout to 10.0.0.8 user bob@acme.test","force_fallback":true}' | jq .
```

**验收：** `redacted_preview` 里看不到真实 IP / 邮箱；`redaction_counts` 有计数。

**面试口述点：** 为什么先脱敏再送给模型？——减少 PII 出域；本地模型也做，是纵深防御；对应「负责任 AI」。

### 步骤 5 — Docker Compose 一键栈

```bash
docker compose up -d --build
docker compose ps
curl -s http://127.0.0.1:8000/healthz
# 拉模型（体积大，需耐心；内存建议 ≥16GB 再跑 7B）
docker compose exec ollama ollama pull qwen2.5:7b
```

用样本日志打真实 LLM 路径：

```bash
python3 - <<'PY'
import json, pathlib, urllib.request
text = pathlib.Path("samples/network_timeout.txt").read_text()
req = urllib.request.Request(
    "http://127.0.0.1:8000/analyze",
    data=json.dumps({"text": text, "context": "api-gateway demo"}).encode(),
    headers={"Content-Type": "application/json"},
)
print(urllib.request.urlopen(req, timeout=120).read().decode())
PY
```

打开：

- Grafana `http://127.0.0.1:3000`（默认 admin/admin，**立刻改密码**）
- Prometheus `http://127.0.0.1:9090` → 查 `aiops_analyze_requests_total`

**验收：** Compose 四件套 Up；Grafana 能看到 Prometheus 数据源；打几次 `/analyze` 后指标增加。

**面试口述点：** 为什么监控「分析服务自己」？——工具链也是生产依赖，要看延迟、错误率、LLM 失败次数。

### 步骤 6 — Shell 巡检脚本

```bash
./scripts/inspect_journal.sh
```

无 systemd 时会自动改用 `samples/` 里的合成日志。

**验收：** 脚本退出码 0，并打印格式化 JSON。

---

## 晚上 2：CI 理解 + 云主机 Ansible 部署 + GitHub

### 步骤 7 — 读懂 CI 并推到你自己的仓库

1. 在 GitHub **新建空仓库**（用你的账号）。
2. 本地初始化并推送（**不要**复制别人的作者信息；用你自己的 `git config user.name/email`）：

```bash
git init
git add .
git commit -m "Initial import: AI ops log assistant learning project"
git branch -M main
git remote add origin git@github.com:<YOUR_USER>/<YOUR_REPO>.git
git push -u origin main
```

3. 打开 Actions，确认 `lint-and-test` 与 `docker` 任务。  
   向 `main` 推送成功后，镜像会尝试推到 `ghcr.io/<you>/<repo>`（需仓库 Packages 写权限，一般 GITHUB_TOKEN 即可）。

**验收：** Actions 全绿；Packages 里能看到镜像（若权限/可见性允许）。

**面试口述点：** PR 上也跑 lint/test/build，但只在默认分支 push 镜像——避免把每个 PR 都推进正式 registry。

### 步骤 8 — 准备一台 Ubuntu 云主机

任选其一（最低配可先做演示）：

- 阿里云 ECS：Ubuntu 22.04，开放安全组 **22 / 8000 / 3000 / 9090**
- AWS EC2：同样系统与安全组端口

本机安装 Ansible：

```bash
pip install ansible
cd ansible
ansible-galaxy collection install -r requirements.yml
cp inventory.example.ini inventory.ini
# 编辑 ansible_host、ansible_user，配置 SSH 密钥
```

**切记：** `inventory.ini`、密钥、密码不要提交进 Git（已在 `.gitignore`）。

### 步骤 9 — 一键部署

```bash
ansible-playbook -i inventory.ini deploy.yml
```

**验收：** Playbook 末尾 `/healthz` 检查成功；公网 `http://<公网IP>:8000/healthz` 可访问。

**面试口述点：** 安全组（云）和 UFW（主机）各管一层；Compose 适合单机演示，生产可演进到 K8s/Helm（README「下一步」已写）。

### 步骤 10 — 截图与 README 个性化

至少准备 4 张图贴进你自己的 README（替换占位说明）：

1. `/analyze` 的 JSON 结果  
2. Grafana 看板有流量  
3. GitHub Actions 绿勾  
4. 浏览器打开云主机 `/healthz`

再改两处证明「这是你的」：例如换一个默认模型名、加一条你自己的规则到 `app/rules.py`。

---

## 设计决策 → 面试怎么讲

| 设计 | 30 秒讲法 |
|------|-----------|
| OpenAI 兼容接口 | 本地 Ollama 和云厂商 API 只改环境变量，降低锁定 |
| 先脱敏 | 负责任 AI；即使本地模型也默认脱敏 |
| 规则兜底 | 可用性优先；来源字段诚实标注 |
| 强制 JSON 结构化 | 方便后面接工单 / 机器人，不只是聊天 |
| Prometheus 指标 | 请求量、延迟、LLM 错误、脱敏次数可观测 |
| Ansible + Compose | 云主机交付可重复；密钥不进仓库 |
| 合成样本 | 可公开；无真实客户数据 |

---

## 高频追问 & 回答提纲（自己补细节）

**Q: LLM 返回不是 JSON 怎么办？**  
A: 提示词要求 JSON-only；解析时容忍 markdown fence；失败则抛 `LLMError` 走规则兜底。可再加 JSON Schema / retry。

**Q: 如何防止提示词注入或编造 IP？**  
A: 系统提示禁止编造；输入侧脱敏；置信度字段；关键动作仍需人工确认（助手建议 ≠ 自动变更）。

**Q: 7B 模型和更大模型如何选？**  
A: 演示用 7B 平衡显存/内存；生产可换云 API。用同一客户端协议切换。

**Q: 和「直接把日志贴进 ChatGPT」比优势？**  
A: 可部署、可监控、可降级、可 CI、可脱敏、可审计；数据路径可控。

**Q: 你在项目里具体做了什么？（务必诚实）**  
A: 对照本教程说出：你跑通了哪几步、改过哪几个文件、部署在哪朵云、指标截图在哪。没做的不要说。

**Q: Ansible 里 secrets 怎么管？**  
A: 本参考实现用 gitignore + 本地 inventory；进阶可用 Ansible Vault / 云厂商密钥管理，面试可主动提到演进。

---

## 简历 bullet 模板（填你自己的真实数据，禁止虚构）

把下面空白换成你**亲手测过**的数字；测不出来就删掉该句，不要编。

```
• 设计并实现运维日志/告警分析助手（FastAPI + OpenAI 兼容 LLM）：接入本地 Ollama，
  输出结构化根因与排查步骤；LLM 不可用时自动降级规则引擎；对 IP/邮箱等脱敏。

• 使用 Docker Compose 集成 Prometheus/Grafana，观测分析接口的 QPS、延迟与 LLM 错误；
  本地压测/演示中 p95 延迟约 ____ ms（样本：____），规则兜底路径约 ____ ms。

• 编写 GitHub Actions：ruff + pytest + 镜像构建，main 分支推送 GHCR；
  流水线时长约 ____ 分钟。

• 使用 Ansible 将整栈部署到 ____（阿里云 ECS / AWS EC2），安全组与 UFW 放行 ____ 端口；
  从空机到 /healthz 就绪约 ____ 分钟。

• 提供 journalctl 巡检脚本，将最近错误日志一键送入分析 API，缩短排障信息整理时间
  （个人使用场景下约从 ____ 分钟降到 ____ 分钟 — 仅在有真实对比时填写）。
```

---

## 建议你额外改动的「个性化」清单（加分）

1. 在 `app/rules.py` 增加 1～2 条你真实排过的故障特征（不要贴生产敏感信息）。  
2. 把 Grafana 看板改成你喜欢的布局并截图。  
3. 换一个模型（如更小的 `qwen2.5:3b`）并记录内存占用。  
4. 给 `/analyze` 加简单 API Token（演示即可）。  
5. 写一篇简短的「一次用它辅助排查」笔记链到 README（必须是你真做的）。

做完以上，你在面试里打开自己的仓库演示即可；作品替不善言辞的人说话，但每一句讲解都要对应你亲手做过的步骤。
