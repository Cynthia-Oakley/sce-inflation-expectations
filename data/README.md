# 数据目录

`raw/` 原始快照；`restricted/` 授权数据；`interim/` 清洗中间表；`processed/` 合格的 P/E 输入；`evaluation/` 真值；`cache/` 服务缓存。以上默认被 Git 忽略。`fixtures/` 只存小型、合成、无个人信息的测试样例。

SCE 既有来源台账为 [sce_source_manifest.json](../docs/sce_source_manifest.json)；2026-09-29 补下的 SCE/ACS/BLS 资料登记在 [peb_source_manifest.json](../docs/peb_source_manifest.json)。审计方法见 [数据审计](../docs/SCE_DATA_AUDIT.md)。后续追加来源应同时写许可范围、参考期、首次发布/修订版本证据、抓取日与哈希；未知可得日不能自动通过过滤。

数据流：raw → interim → processed → study；真实回答/真值走 evaluation 独立路径。执行 B 的输入构建器不得直接加载整份真实微观问卷。

Git 忽略不等于已备份。大文件留有下载与校验说明；受限文件按许可做本地安全备份。提交时选择许可允许且足够复核结果的快照，不能把整份 data 目录打包。
