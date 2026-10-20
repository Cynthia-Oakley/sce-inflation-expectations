# 不带答案数值的输出结构示例

2026-10-20，版本：`sce-output-structure-example-v1`。按用户要求完整展开所有字段。以下是结构示意，尖括号是待替换的占位符，不是可直接提交的JSON；模型应填入自己的数字，数字不带引号，返回完整合法JSON。没有给出任何示例概率答案。

## Q8与Q9一同回答

```text
{
  "point_pct": <signed_number>,
  "q9": {
    "bin1": <probability>,
    "bin2": <probability>,
    "bin3": <probability>,
    "bin4": <probability>,
    "bin5": <probability>,
    "bin6": <probability>,
    "bin7": <probability>,
    "bin8": <probability>,
    "bin9": <probability>,
    "bin10": <probability>
  },
  "reason": "<brief_reason>"
}
```

## 仅Q9的格式检查

```text
{
  "q9": {
    "bin1": <probability>,
    "bin2": <probability>,
    "bin3": <probability>,
    "bin4": <probability>,
    "bin5": <probability>,
    "bin6": <probability>,
    "bin7": <probability>,
    "bin8": <probability>,
    "bin9": <probability>,
    "bin10": <probability>
  }
}
```

## 注入及当前状态

- 共用模块为`studies/sce_inflation_expectations/output_format_example.py`；向最后一条用户消息追加格式说明，保留此前P/E、个人先验与题目原文。
- 明确q9是对象、十个bin都要填写、值为数字、合计100%；输出不使用平铺键、占位符、省略号或代码围栏。全问卷保留point_pct与reason，Q9单题不请求这两个额外字段。
- 新版OpenRouter公开格式入口已接入：`outputs/sce_openrouter_q9_structure_preparation_20261020_v1/`。初次交付为离线prepare；用户随后明确要求真实尝试，已完成一次请求，结果见下节。
- 3项离线检查通过：完整嵌套/不含概率答案、Q9单题字段范围、追加时不改变原消息。不能据此宣称真实遵循率提高。
- 已执行的旧提示、答案和协议保持原样；旧直接调用脚本另保全于`outputs/sce_openrouter_format_source_snapshot_20261020_before_template_v1/`。旧结果按旧版本解释。
- 后续正式采购角色对照在新批次封存时，三组统一使用同一结构示例；不得一组加、一组不加后把差异归因于采购角色。当前已冻结的旧输入不覆盖。

## 新模板真实检查：一次直接匹配

2026-10-20，用户授权后仅调用一次Qwen2.5-72B/DeepInfra-fp8，温度0.5、JSON模式、max_tokens1024，无自动重试。公开背景和旧问题原文保留，模型/供应商/参数与上一格式检查相同，仅在消息末尾追加855字节结构说明。

回包直接为`{"q9":{"bin1":10,"bin2":20,"bin3":30,"bin4":20,"bin5":10,"bin6":5,"bin7":2,"bin8":1,"bin9":1,"bin10":1}}`。**嵌套结构与十个数字均匹配，概率合计100%，原读取器一次通过。**没有字段转换、概率修补、归一化或重试，finish_reason为stop。

用时9.667秒，输入522 token、输出97 token，API报告费用$0.00022672。保持此前OpenRouter累计$1上限，本次$0.01子上限；不使用平台Chat/Sim额度。

这是新模板下的一份成功回答，不能估计长期格式通过率，也不是拟合效果或异质性改善证据。前后各一份、温度非零，不将前后差异称统计识别的因果效应。公开记录：[output_structure_result_v1.json](output_structure_result_v1.json)；完整原答及授权仅在本地运行包保存，已执行包不再运行。
