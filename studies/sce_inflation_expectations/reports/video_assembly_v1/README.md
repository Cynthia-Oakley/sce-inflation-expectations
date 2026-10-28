# 十段作者录屏的离线拼接

入口为 `assemble.py`，只读取录屏，不调用模型，不修改原片或研究数据。按 `part_01_`—`part_10_` 的内容顺序拼接，递归归档目录不参与。

在项目根目录执行（需 FFmpeg/ffprobe 在 PATH 中）：

```sh
python studies/sce_inflation_expectations/reports/video_assembly_v1/assemble.py \
  --clips deliverables/video/recordings/clips \
  --out deliverables/video/recordings/exports/assembled_v01
```

输出目录必须是新目录，重做时使用 `assembled_v02` 等，不覆盖已验收版本。

- 画幅统一为 1920×1080、30 fps、H.264；按比例缩放、居中留边，不裁画面，不拉伸。
- 静态页最后一帧保留到整段讲解结束，兼容画面轨短于音轨的 WPS 录屏。
- 逐条检查音轨响度，选择有效人声轨，避免误用 WPS 的空系统音轨；转成立体声后两遍响度归一化，目标 −16 LUFS、−1.5 dBTP。
- 原时长不到五分钟则保留原速。超过时才统一使用 `setpts` 与保持音调的 `atempo`，目标不超过 4分58秒。
- 采用直接切换，不添加音乐、字幕或转场，不删改作者讲解。
- MP4 内有十段章节；旁附 `chapters.txt`、输入/音轨/时间与原片哈希清单 `assembly_manifest.json`。`processing/` 留存各段标准化副本和处理日志。
- 成片做完整音视频解码检查、时长/音量检查，并验证十个原片哈希均未改变；画面仍需抽帧检查和作者播放确认。

2026-10-29 首版输入合计约 4分28秒，无需加速。成片和录屏均为本地媒体，不自动上传 Git 或放入研究包。
