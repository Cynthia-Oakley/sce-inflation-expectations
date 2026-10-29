# 给评委的补充说明：外部模型、回答格式与密钥

2026-10-29。随v10提交包提供，旧v09原件保留；历史答卷、研究参数和结果不变，本轮不调用API。

## 本地运行与回答格式

本研究采用SocioVerse本地开发方式。正式行为生成通过OpenRouter调用固定SiliconFlow FP8供应商的DeepSeek V3.2，未使用平台MCP托管的问卷模拟服务。回答由本研究的study适配器处理：Q8为数值点预期，Q9为十档概率JSON；它们经字段校验和已声明的概率归一化后进入计分与汇总。自定义回答格式不要求转换为平台在线问卷的单选选项。

提交包不包含作者API Key。评审无需密钥即可运行默认入口，复算已封存的模型原文、有效答卷、密度计分、全国/微观指标与Normal扩展。若需重新生成LLM回答，应使用评审者自己的OpenRouter账户和API Key，并按下述配置恢复合法输入、准备独立运行包及确认费用。非零温度的重新生成可能产生不同答案；历史原文和结果复算用于核对已报告结论。

## 1. 默认审查：不需要账号或密钥

在解压包根安装锁定依赖后执行：

```sh
python studies/sce_inflation_expectations/run.py --mode all
```

默认禁止Python网络连接、0次LLM调用。它依次运行20户两步工程示例、全国及下游误差复算、四个正式任务的逐答卷复算。工程示例用scripted规则，不能作为DeepSeek实际生成的证明；正式模型原文及有效答卷在study的reproduction_data/micro/中。

仅复算微观答卷使用`--mode micro`。增加`--refit-density`会从概率向量重新运行冻结数值密度拟合器，不调用语言模型。

## 2. 正式模型的外部接口与回答契约

历史实际配置：

- 服务：OpenRouter，OpenAI兼容接口`https://openrouter.ai/api/v1`。
- 模型：`deepseek/deepseek-v3.2`。
- 固定路由：`siliconflow/fp8`，预期返回供应商SiliconFlow；禁止自动回退到其他供应商。
- `temperature=0.5`，`max_tokens=1024`，`response_format={"type":"json_object"}`，`reasoning={"enabled":false}`。
- 原始模型输出为JSON对象：`point_pct`是有限数值；`q9`是包含`bin1`至`bin10`的嵌套对象；`reason`为简短理由。概率档按研究问卷的从高通胀至高通缩顺序，见study计分代码，不按字母排序或任意重排。
- Q8与Q9分别校验。Q9须十档完整、有限且非负、总和为正，按已批准策略等比例归一化至100；原始输出、原始总和、归一化标记与技术失败保留。缺档、负数或无法解析的文本不静默补成合法答卷。

正式实现的位置：`studies/sce_inflation_expectations/runtime/openrouter_frozen_runtime.py`及其冻结消息执行器、`studies/sce_inflation_expectations/components/behavior/q9_normalization.py`。具体路径以包内FILE_GUIDE和SOURCE_INDEX的迁移映射为准；原开发仓库相应文件仍在study根目录。

这些是本研究的历史冻结配置，不保证供应商未来始终提供同一版本或价格。供应商不可用或返回模型身份变化时，应停止并记录，不能静默更换后仍称原条件复现。历史请求价格上界、预算和技术失败规则，以选定任务的冻结protocol为准。

## 3. 自备API Key如何准备

仅在需要新的真实LLM生成时，评审者自行开通有余额的OpenRouter账户，确认该账户可访问目标模型和固定供应商，并在自己的终端会话配置`OPENROUTER_API_KEY`。作者不会提供、代充或嵌入账户密钥，密钥也不应写入提交文件、命令行参数或报告。

macOS默认zsh中可隐藏输入（此操作本身不联网）：

```sh
read -s 'OPENROUTER_API_KEY?OpenRouter API Key: '
export OPENROUTER_API_KEY
```

运行适配器会读取该环境变量；原受控工作区也支持本地.env，但不得提交该文件。生成结束后可`unset OPENROUTER_API_KEY`。密钥不必发给作者或赛事联系人。

## 4. 解压即可预览的完整输入及单次再生成

实际输入在 `studies/sce_inflation_expectations/reproduction_data/inputs/`：66,822个位置均含人口、先验、价格、政策和选中新闻摘录。24,852份B/月度/周度输入完整，按原消息哈希连接既有答卷；A的41,970份因真实个人日期遮蔽而只提供模板，不接受作为完整样本发送。

在包根执行，默认只打印真实Prompt和参数，不读取Key或联网：

```sh
python studies/sce_inflation_expectations/simulation/reviewer_request.py \
  --candidate-dir studies/sce_inflation_expectations/reproduction_data/inputs
```

确认需要付费生成后，先按第3节在自己的终端安全设置 `OPENROUTER_API_KEY`，再执行：

```sh
python studies/sce_inflation_expectations/simulation/reviewer_request.py \
  --candidate-dir studies/sce_inflation_expectations/reproduction_data/inputs \
  --confirm-paid --out reviewer_generated_01
```

这是一份完整历史输入的条件单步请求。每次最多发送一次、SDK不自动重试、不切换供应商，输出目录必须全新；保留输入、请求前意图、模型原文及脱敏回执。可同时增加 `--run`、`--period`、`--household` 选择完整集合中的另一份样本；匿名编号可从输入与model_outputs按run/period/household/原Prompt哈希对接。找不到完整记录或存在占位槽时，脚本拒绝发送。

入口在固定历史单价上界下计算保守预留，超过$0.01时拒绝发送，并附供应商单价和输出token上限；这不是服务端美元硬限额。供应商未来可能不可用、改价或返回不同模型身份，程序会记录并停止。网络失败可能已计费，不自动重发。新回答只存原文，正式概率校验、归一化与计分须走既有study流程，不冒称新回答自动成为论文结果。本轮只完成离线与注入验收，没有真实联网测试。

## 4.1 完整历史与自主递推的边界

A的真实日期不附、原始ID和私人匹配对应表不附；公开层不承诺恢复全部A条件。完整库的自备Key批量运行仍需明确范围和预算。`run.py --mode generate`继续作为受控完整工作区委托入口，不等同于这个便携单次命令。

后月和后周的封存Prompt携带当年那次运行的模拟前态；原样重发只能重做给定前态的一步。新的自主链必须将本次新输出传给下期，另行执行时间规则、发布后重校准和失败字段保留机制。非零温度重新生成不会保证与历史原文逐字一致。

本包包含第三方选中新闻文字，仅按作者要求供赛事保密评审，不能随未来公开GitHub直接再分发。版权与使用范围见inputs/NEWS_REVIEW_NOTICE.md。作者Key无需也不得提交给评委。

## 5. 研究格式与官方依据

官方赛事页面明确区分在线平台和本地自备Key方式，并要求成果落为标准study；官方FAQ说明本地LLM密钥由使用者提供、外部模拟器可以通过接口适配，且真实LLM非零温度结果不保证逐次相同。没有据此发现所有本地研究都必须使用MCP问卷服务或单选输出的要求。此为对公开规则的核查，不代替评审对本项目具体实现的判断；本项目实际大批生成使用本地冻结消息适配器，官方Core用于接口装配与离线验收，两者分开说明。

- 赛事要求：https://socioverse.fudan-disc.com/challenge/
- 官方FAQ：https://socioverse.fudan-disc.com/docs/zh/faq/
- 自定义模拟器适配：https://socioverse.fudan-disc.com/docs/zh/guides/wrap-legacy-model/

来源核查日2026-10-29。赛事动态正文SHA256沿用已核对的dce3d93a9ceab1377cf27a5d93d6b5f3fdebaaa70ee6154606339c2fc09bee53。
