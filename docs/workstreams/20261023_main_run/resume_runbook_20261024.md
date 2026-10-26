# A82续跑：仅发送未尝试位置

**最终状态：2026-10-24 14:34:42全部生成与独立评价完成。**root为outputs/sce_monthly_main_resilient_20261024_v1，41,984唯一尝试/82月各512，微观评价及全国readout全部落盘。已报$28.90737、含未知预留$30.11564，7轮恢复/210秒冷却，无自动重试或供应商回退。原包不能再次run。用户随后要求补齐351请求错误＋10Q9技术异常，新命令见[技术补跑说明](technical_repair_20261024.md)，准备完成但尚未调用；不重启本页旧包。下面“尚未启动/等待用户”只描述当时准备阶段。

**历史续跑入口：第7节“有界容错续跑”。**该包已由用户执行并完成，不可重复启动。旧包和旧调度源码不修改。

**10:49最新状态：**第6节手动包已由用户运行并遇HTTP502停止，累计8,192尝试/8,098完整可用/92请求错误＋2部分字段不全，已报$5.65464/含未知预留$5.97572，33,792未发送，无在途。原manual_v1启动命令不能再次执行；后续需新恢复包。502由程序按fatal规则处理，exit_code=0不是全量完成。本轮只核查原因，没有新增API或修改冻结调度策略。

**最新：第一段续跑也已于09:51:52停止。**累计2,048尝试、2,000可用、48连接失败，已报$1.391825979、含未知预留$1.556431318。用户希望亲自在本地Terminal启动并持续看进度，已离线准备`outputs/sce_monthly_main_manual_20261024_v1/`，只续39,936未发送位置。本包尚未授权/启动，命令见第6节；下面前五节是第一次续跑经过，不代表仍在运行。

2026-10-24。用户在本轮明确说“续跑吧”，沿用原41,984次范围与$40全批总上限。此续跑已启动，不要重复运行旧包。

## 1. 当前范围

- 原批次2019年1、2月共1,024次尝试原样保留；其中1,005份可用、19次连接失败，失败不补发。
- 新队列仅含40,960个从未发送的位置，2019年3月至2025年10月，输入/模型/供应商/温度/抽样/计分不改。
- 原首32次格式门槛已通过，继续复用；新队列沿原并发调度（开始最多8，32份结束后最多64）。
- 原已报$0.70477，未知失败按上界预留后$0.77180；续跑预算从这笔累计金额接着计，不是再给$40。
- 保持无自动重试、无供应商回退、连续三次错误/HTTP等既定停止规则。未添加夜间自动恢复或重复调度。

## 2. 在哪里运行

上次从用户Mac的原生Terminal启动独立Python后台进程。本次先尝试同一台Mac的macOS `launchd` 一次性任务，但进程在打开入口脚本时阻塞，未进入worker、未创建调用目录、0新增API。已撤销该服务并保存`launchd_blocked_before_worker.json`，没有修改Mac权限；随后从已授权本地执行通道以`Popen(start_new_session=True, stdin=DEVNULL)`启动独立worker，见`detached_launch.json`。两次都不是云端计算机。

运行不要求Codex逐批调用，也不会消耗Codex模型额度；无需Terminal窗口保持打开。没有周期任务或失败后自动重启。macOS后台服务读取Documents入口的阻塞原因尚未确认，不宣称已证明是TCC；这一尝试的0API状态和撤销已核实。分离进程已产生实际worker心跳，仍应以新鲜进度和最终回执判断状态，不能承诺强制退出应用、系统重启或断电下的存活。运行期间用`caffeinate -i`防空闲睡眠，锁屏通常不结束进程；不保证合盖、主动睡眠或断网时继续。停止时段的`pmset`查询未查到睡眠转换记录，仅能说没有找到睡眠证据，不能排除网络或上游服务故障。原日志只记录`APIConnectionError`，未保存可能含密钥的异常正文。

## 3. 启动经过与等效终端命令

```sh
cd '/Users/wushuyue/Documents/科研/DISC/socioverse_challenge'
/Users/wushuyue/anaconda3/envs/socioverse/bin/python scripts/continue_sce_monthly_main.py start --run-dir outputs/sce_monthly_main_resume_20261024_v1/supervisor
```

以上首次启动已执行，但系统服务在读脚本前卡住，随后已安全撤销，未产生付费调用。实际工作进程由本地执行通道启动；等效原生Terminal命令如下，仅供追溯，当前不要重复执行：

```sh
cd '/Users/wushuyue/Documents/科研/DISC/socioverse_challenge'
nohup /Users/wushuyue/anaconda3/envs/socioverse/bin/python -u scripts/continue_sce_monthly_main.py _worker --run-dir outputs/sce_monthly_main_resume_20261024_v1/supervisor > outputs/sce_monthly_main_resume_20261024_v1/supervisor/manual_terminal.log 2>&1 < /dev/null &
```

worker独占锁会拒绝重复执行；不要删除锁或改旧执行登记来绕过它。`_worker`只在已有授权和启动锁的本恢复包中使用，不能当成任意旧运行的通用重启命令。

## 4. 查看进度（可以重复执行，零API）

```sh
cd '/Users/wushuyue/Documents/科研/DISC/socioverse_challenge'
/Users/wushuyue/anaconda3/envs/socioverse/bin/python scripts/continue_sce_monthly_main.py status --run-dir outputs/sce_monthly_main_resume_20261024_v1/supervisor
```

`supervisor/progress.json`每10秒更新：既有尝试、新尝试、累计完成、错误、未发送、在途、已报费用、未知费用预留和阶段。旧进度文件已终止更新，不要再用它判断新任务状态。

## 5. 档案与评价

全部新产物位于`outputs/sce_monthly_main_resume_20261024_v1/`：

- `package/`：原协议逐字复制，新增续跑范围、旧账本哈希及本次明确授权；协议本身没有改。
- `calls/`：只含本次新增请求、原回答及费用。
- `combined/`：原账本与新账本按原始字节拼接，原文件不覆盖；评价继续匹配原冻结协议、真值及统计口径。
- `evaluation/`、`readout/`：合并全范围完成后另起进程生成；遇到约定停止不把部分样本冒充完整成绩。
- `supervisor/`：启动锁、一次性后台任务、10秒进度、分阶段日志及最终回执。

实现`experiments/monthly_main_continuation.py`复用既有队列、费用保护、状态处理和评价器。8项离线定向检查覆盖：未确认发送不补发、旧成功与失败均不重跑、身份/提示漂移拦截、费用不双计、原字节合并、进度相加和一次性启动。没有为本次恢复重新生成P/E、拟合真值或重跑旧1,024份。

## 6. 本地Terminal手动启动＋持续进度（最新入口）

```sh
cd '/Users/wushuyue/Documents/科研/DISC/socioverse_challenge'
/Users/wushuyue/anaconda3/envs/socioverse/bin/python -u scripts/run_sce_monthly_main_console.py run --run-dir outputs/sce_monthly_main_manual_20261024_v1/supervisor --confirm-continuation
```

只有用户执行这条带明确确认标志的命令，才记录本次人工续跑授权并发送请求。新包在此之前没有authorization/launch_lock/调用目录，本轮准备0新API。保留旧2,048次（含48失败），只续39,936未发送位置；同一OpenRouter→SiliconFlow FP8 DeepSeek V3.2、相同P/E/抽样/提示/温度/8→64并发及停止规则，全批累计$40，不再另给$40。

程序在本机启动独立worker，终端每10秒显示：累计完成、本次完成、可用、失败、在途、API已报费用、未知费用预留及阶段；超过60秒没有新进度会提示，停止/完成会明确输出。Ctrl+C仅退出观察，后台任务继续；重复run会被锁拦截。需要重新打开观察时执行：

```sh
cd '/Users/wushuyue/Documents/科研/DISC/socioverse_challenge'
/Users/wushuyue/anaconda3/envs/socioverse/bin/python -u scripts/run_sce_monthly_main_console.py watch --run-dir outputs/sce_monthly_main_manual_20261024_v1/supervisor
```

`watch`只读本地文件，0API；不能用重复run来替代watch。终端可见性不改变网络稳定性，仍可能触发原停止规则。工程来源为`monthly_main_console.py`及薄CLI；新增5项检查连同原续跑8项共13项通过，未修改已冻结/已运行的续跑实现。

## 7. 有界容错续跑（最新）

用户要求放宽临时故障门槛。新增调度外层复用原单次队列，临时停止后收齐在途、保存不可改写分段，再冷却并仅继续未发送位置；不重发任何成功或失败请求，不自动切换供应商。

- 原保留8,192次（92请求错误＋2部分字段不全），本次最多33,792个从未发送位置。
- 从原已计/预留$5.975720966接算，**仍是整批累计$40**，不是另给$40。
- 初始32并发；一段完成256次且未触发暂停后最多64。故障恢复按该段峰值并发减半，最低8。
- 可恢复：连接/超时，以及408、429、500、502、503、504等明确列出的服务错误；依据原队列触发临时停止，先收齐在途，再冷却30/60/120/240/300秒。合法`Retry-After`长于默认冷却时优先遵守；超出总等待上限则停止。
- 一个健康段（至少128个无请求错误回答且请求成功率≥95%）可重置持续故障计数。最多5轮未恢复冷却、累计冷却30分钟或总恢复轮数50后停止，避免持续断网下无限消耗位置。
- 凭证/余额/请求配置等不可恢复HTTP错误、模型或供应商不符、异常收费/预算上限、来源哈希变化等仍停止。
- 新增`execution_policy.json`独立封存传输附录；原研究protocol SHA、模型参数、P/E、名单、权重、先验和计分/真值均保持，评价读取原协议一致的合并账本。

### 由用户在本地Terminal启动

```sh
cd '/Users/wushuyue/Documents/科研/DISC/socioverse_challenge'
/Users/wushuyue/anaconda3/envs/socioverse/bin/python -u scripts/run_sce_resilient_main.py run --run-dir outputs/sce_monthly_main_resilient_20261024_v1/supervisor --confirm-continuation
```

尚未自动启动或写本包授权；用户执行上述确认命令后记录人工许可并启动独立worker。终端每10秒显示累计进度、费用、在途、阶段，以及“网络冷却中/剩余秒数/恢复后并发/已恢复轮数”。Ctrl+C只退出观察，已启动的任务继续；恢复观察用：

```sh
cd '/Users/wushuyue/Documents/科研/DISC/socioverse_challenge'
/Users/wushuyue/anaconda3/envs/socioverse/bin/python -u scripts/run_sce_resilient_main.py watch --run-dir outputs/sce_monthly_main_resilient_20261024_v1/supervisor
```

每个`calls/segment_XXXX/`逐请求存档，暂停前已经收齐的失败也不重发。结束后仅一次组成新段flat账本，再与旧8,192次原字节合并。完整范围全部尝试完成后，在独立进程执行旧评价/全国组合。进程崩溃、断电等仍不会自动重启；未确认发送的位置不得直接当作未发送。

检查：23项（新增容错10项＋原续跑/控制台13项），覆盖502后恢复且不重发、持续断网有界停止、降并发、401/供应商错误立即停、累计预算保护、过长Retry-After、旧月度进度不被双计等。零真实API用于这些检查。本层复用已有queue.execute、live_sender、初始状态处理、合并器与评价器，没有新建另一套模拟或密度计分。
