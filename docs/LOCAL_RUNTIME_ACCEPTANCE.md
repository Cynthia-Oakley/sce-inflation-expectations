# 本地运行验收

核查日：2026-10-01（T03-L 已执行，见末节）。结论：**SocioVerse2 核心 scripted 示例、SCE 计分测试与 v2 归档审计通过；study 单向导出入口已实现并验证；两个 MCP 服务连接与免费目录能力已实测。真实 LLM 与 SCE 端到端运行仍未验收。**

## 已实际验证

- Claude Code：`2.1.286`。用户确认已通过 Kimi API 对话，本轮未发新的模型请求。
- 环境：`/Users/wushuyue/anaconda3/envs/socioverse/bin/python`，Python `3.11.16`。终端默认 `python3` 仍为 base 的 `3.10.9`，启动前须激活 `socioverse`。
- SocioVerse2 `0.2.0`；官方 clone commit `fa678ff6aea0e5a6497a7ffac15459123200a150`。
- 包版本：duckdb `1.5.5`、pydantic `2.13.5`、pyarrow `25.0.1`、pandas `3.0.6`、numpy `2.4.6`、pytest `9.1.1`。这些是检测到的版本，不是已冻结的正式依赖锁。
- 从研究主仓库运行 `import socioverse; import socioverse.engine` 成功，包路径解析到官方 clone。
- 在临时 studies 目录复制官方 `opinion_diffusion`，调用 `scripts.demo_offline.main(['--llm','scripted','--no-report'], studies_root=临时目录)` 成功：12 人、4 步、48 次 rule 决策，退出 0，生成轨迹数据库。临时产物随测试清理；未覆盖用户已有 demo，未测试图形报告、MCP 或真实 LLM。
- 官方根目录 `.env` 与 `.mcp.json` 均为权限 `600`，且被 Git 忽略；配置列出 `event_tool` 与 `user_pool_survey_mcp`。两把服务 key 字段非空，未打印值；存在不等于服务端认证通过。

## 尚缺内容

- `openai` 未安装（`scipy`/`openpyxl` 已于 2026-10-01 T03-L 补齐，见末节）。
- 官方项目 `.env` 中 `SV_LLM_API_KEY`、`SV_LLM_BASE_URL`、`SV_LLM_MODEL` 未配置非空值；未查阅 Claude Code 私人模型配置。模拟 B 的模型/端点必须独立记录，不能从编码助手身份推断。
- SCE 原生运行适配、实际输入日志、完整归档尚未实现。
- 本轮没有验证 MCP 远端连通性、历史版本字段或付费工具。

## Kimi 的下一步

本节首段命令已在 2026-10-01 T03-L 执行完毕（结果见末节），保留作为复跑入口：

```bash
conda activate socioverse
cd /Users/wushuyue/Documents/科研/DISC/socioverse_challenge
python -m pip install scipy openpyxl
python -m unittest discover -s tests -p 'test_sce_q9_scoring.py'
python scripts/audit_cloud_v2_model.py
python scripts/audit_cloud_v2_environment.py
```

这些命令在 2026-10-01 T03-L 已全部执行通过；复跑时先 `conda activate socioverse`（终端默认 `python3` 是 base 的 3.10.9）。现有 Q9 测试通过仍不等于 Beta 完整复现。

需要真实 B 的 SDK 时，在官方 clone 的已激活环境安装：

```bash
cd /Users/wushuyue/Documents/科研/DISC/socioverse2_repo
python -m pip install -e '.[llm]'
```

随后由用户在本机配置模拟用 LLM 凭证和端点，核对该服务允许此类实验及计费方式。study 内显式 model 可能优先于环境变量，实际请求模型需要记录。先给出有限人数/月数、重试上限、预计 token 和费用，再执行已获授权范围内的真实调用。

MCP 连接与免费目录已在 2026-10-01 T03-L 实测通过（见末节）；`get_source_detail` 是付费结构化调用，不是免费目录。计价按组委会提供的邮件：结构化 `get_data/get_source_detail` 每次 $0.005，人群问卷模拟每人 $0.004；服务端价目尚未独立核查，开始付费批次前核对余额和预算。对历史 E 仍须检查发布时间/版本。

完成后在此追加日期、命令、结果路径和未通过项，并更新 `NEXT_ACTIONS.md`。不要用当前检测结果覆盖未来真正验收记录。

## 2026-10-01 T03-L 执行记录（Kimi）

**依赖补齐**（conda `socioverse`，Python 3.11.16，沿用既有环境）：

```bash
/Users/wushuyue/anaconda3/envs/socioverse/bin/python -m pip install scipy openpyxl
# 实装：scipy 1.17.1、openpyxl 3.1.5（附带 et-xmlfile 2.0.0）
```

**计分测试与 v2 归档审计**（均通过）：

```bash
python -m unittest discover -s tests -p 'test_sce_q9_scoring.py'   # Ran 5 tests, OK（17s）
python scripts/audit_cloud_v2_model.py        # answer_rows=40，P/E 公式重演 0 mismatch
python scripts/audit_cloud_v2_environment.py  # 两月 as_of 与六条 BLS 信号核对一致
python -m unittest discover -s tests          # 含新增导出测试共 Ran 12 tests, OK
```

注意：Q9 测试通过仍不等于 Beta 完整复现（开放尾/空档差异见 `SCE_Q9_SCORING_REPLICATION.md`）；v2 审计的 `limit` 字段依然成立——历史 Observation、run ID、费用明细未持久化，不可补造。

**study 单向导出入口（新实现）**：

- 新增 `scripts/export_study_runtime.py`：把主仓库 `studies/sce_inflation_expectations/` 单向导出到官方 clone 的 `studies/`（默认 `../../socioverse2_repo/studies`），排除 `__pycache__`/`runs/`/`versions/`/`trajectory/` 等派生内容，自动生成缺失的根 `__init__.py` 供 `import studies.sce_inflation_expectations`，并写 `RUNTIME_EXPORT.json`（导出时间、源 git HEAD 与 dirty/untracked 状态、逐文件 SHA-256）。非本脚本生成的目标目录拒绝覆盖；`--verify` 检出缺失/篡改/多余文件。新增 `tests/test_export_study_runtime.py`（7 项：round-trip、排除规则、篡改与多余文件检测、外来目录拒绝、重复导出）。
- 已执行真实导出：`python scripts/export_study_runtime.py` → 12 文件导出至 `/Users/wushuyue/Documents/科研/DISC/socioverse2_repo/studies/sce_inflation_expectations/`，`--verify` OK。该目录被官方仓 `.gitignore` 的 `studies/*/` 覆盖，不进上游 git（导出后官方仓 status 无新增项，仅剩原有 `gen_mcp_json` 两处修改）。
- 使用约定：SCE 源码只在主仓库改；运行副本改了任何东西都会在下一次 `--verify` 暴露，处理方式永远是重新导出。当前副本只是骨架+计分器，尚不能被官方运行器执行（无 model.py）。

**MCP 连接与免费目录验收**（`scripts/check_mcp_free_capabilities.py`，stdlib 实现，复用官方 `gen_mcp_json.load_env` 进程内读 key；输出与归档均无凭证值）：

```bash
python scripts/check_mcp_free_capabilities.py
```

- `event_tool`：`healthz` ok；MCP `initialize`/`tools/list` 成功。工具：`list_sources`、`get_data`、`get_source_detail`、`search_web`。免费目录 `list_sources` 实测返回 21 个来源（fred、nyfed_sce、bls、treasury、census_acs、cps_basic、cps_asec、sipp、world_bank、gdelt、nyt_archive 等）。付费工具 `get_data`/`get_source_detail`（约 $0.005/次，按组委会邮件，未独立核价）**未调用**。
- `user_pool_survey_mcp`：`tools/list` 成功（9 个工具）。免费探测全过：`get_user_pool_simulation_capabilities`（服务端模拟 LLM 登记为 gpt-4o-mini，另有 GPT/Qwen/DeepSeek 别名——仅记录，未调用）、`list_user_pool_platforms`、`match_user_pool_fields`（SCE 相关六字段探针）。池覆盖要点：`matraix_1m` 56,583 索引用户（AGE/GENDER/INCOME/EDUCATION 覆盖比 1.0/0.86/0.73/0.81）；`nemotron_usa` 59,994（无 INCOME）；`personahub` 199,466（六字段皆无）；`rednote_v2` 15,000、`x_mode_1` 5,000；`rednote`/`x` 索引为 0。计费工具 `run_user_pool_distribution_simulation` **未调用**。
- 脱敏归档：`data/raw/mcp_checks/2026-10-01/{event_tool,user_pool_survey_mcp}.json`（gitignored）。脱敏按字段名（key/token/secret/authorization/credential/password）递归置 `<redacted>`，`requires_api_key` 之类的布尔字段也被一并遮蔽，属过度脱敏、不影响证据效力。
- 边界：`list_sources` 存在 `nyfed_sce`/`fred` 不等于其回包带历史发布时间/vintage；历史 E 的时点可得性仍须在 T02 逐源验收。user_pool 各池人口结构不等于美国 SCE 代表性人口。

**本轮未动**：`scoring/sce_q9.py`（留给 Codex T01）；`openai` 未装、`SV_LLM_*` 仍未配置，真实 B 未验收；官方仓两处 `gen_mcp_json` 既有修改原样保留。
