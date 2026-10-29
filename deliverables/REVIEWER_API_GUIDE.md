# 给评委的补充说明：外部模型、回答格式与密钥

2026-10-29。随v09提交包提供，旧v08原件保留；历史答卷、研究参数和结果不变，本轮不调用API。

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

## 4. 现有真实生成入口的条件与命令

当前ZIP的`--mode generate`是受控工作区委托入口，不是“输入Key即可恢复所有历史资料”的独立下载器。先按包根PRIVATE_INPUTS_REQUIRED.json恢复合法的人口、历史匹配、环境/新闻与完整消息输入，另建独立数据完整工作区；完成原执行器要求的prepare、review、输入哈希和新批次预算授权。不得直接修改已经完成的原批次授权或日志。

满足这些前置条件后，可从解压包根执行下列命令模板。尖括号内容必须替换成真实存在、经过检查的新工作区与新运行目录；不应原样执行占位符：

```sh
python studies/sce_inflation_expectations/run.py --mode generate \
  --source-workspace <合法输入齐全的工作区绝对路径> \
  --prepared-run outputs/<已prepare并授权的新运行目录> \
  --executor full-a \
  --confirm-paid
```

`full-a`委托`scripts/run_sce_full_a_personal.py`；`recent-b`委托`scripts/run_sce_recent_b.py`。该入口先调用所选执行器的review，再调用run，保留原有范围、预算和归档保护；它不是统一的任意批次选择器。大批运行前应在独立测试配置下验证小规模调用，不能为省事直接启动82个月。

**当前仍未提供的能力：**本包没有可以只凭ZIP和Key直接重新询问一户正式历史家庭的便携命令。视频中的单户演示在作者受控工作区运行，不能把该演示路径冒称评审解压后的通用命令。如需增加便携联网自检，应另加入已取得分享许可的完整小样本输入及专用限量脚本，离线验收后再封包；本稿不宣称该功能已经实现。

## 5. 研究格式与官方依据

官方赛事页面明确区分在线平台和本地自备Key方式，并要求成果落为标准study；官方FAQ说明本地LLM密钥由使用者提供、外部模拟器可以通过接口适配，且真实LLM非零温度结果不保证逐次相同。没有据此发现所有本地研究都必须使用MCP问卷服务或单选输出的要求。此为对公开规则的核查，不代替评审对本项目具体实现的判断；本项目实际大批生成使用本地冻结消息适配器，官方Core用于接口装配与离线验收，两者分开说明。

- 赛事要求：https://socioverse.fudan-disc.com/challenge/
- 官方FAQ：https://socioverse.fudan-disc.com/docs/zh/faq/
- 自定义模拟器适配：https://socioverse.fudan-disc.com/docs/zh/guides/wrap-legacy-model/

来源核查日2026-10-29。赛事动态正文SHA256沿用已核对的dce3d93a9ceab1377cf27a5d93d6b5f3fdebaaa70ee6154606339c2fc09bee53。
