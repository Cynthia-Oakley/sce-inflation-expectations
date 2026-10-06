# 价格体验机制配置

使用入口：`../../../docs/PRICE_EXPERIENCE_MECHANISM.md`。

- `expression_shared.json`：家庭表述，不显示篮子、不调整信息顺序。
- `basket_shared.json`：显示合成篮子，原公共信息顺序。
- `focus_only.json`：不显示篮子，按篮子排序公共信息。
- `basket_focus.json`：显示篮子并排序。
- `ce_field_map.json`：本轮 CE 码值映射与字典哈希，不是运行臂。

四臂均保留同一公共事实与相同 Q8/Q9；排序假设不是实测注意力。
当前只允许 A 历史重建。真实决策必须选择 `sce-q8-q9-experience-v1`。
scripted 只验输入/记录接线，其回答不使用该机制。
