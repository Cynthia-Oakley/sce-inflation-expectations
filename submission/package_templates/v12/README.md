# 水上挽月｜SCE通胀预期模拟研究包 v12

SocioVerse Challenge 2026，赛道A：历史重建与未来预测。论文与视频单独提交。本包按 `studies/` 布局提供完整原工程、公开源快照、实际输入输出和便携复现入口。

## 两个入口

**快速核对论文结果，0API：**在解压后的包根执行：

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python studies/sce_inflation_expectations/run.py --mode all
```

这会从正式逐答卷数据复算概率归一化、密度、权重中位数、MAE/W1/IQR、条件指标和A/B的Normal后验质量。20人平台例子仅检验接口，和真实答卷复算分开。无需API Key；安装依赖后，复算阶段禁止网络。

**在自己的设备上用自己的Key重新生成：**完整步骤见 [PORTABLE_REPRODUCTION.md](PORTABLE_REPRODUCTION.md)。可先进行少量家庭/时期的检查，再选择原名单全量运行：

```sh
python review.py install --workspace ./review_workspace
python review.py check --workspace ./review_workspace --out ./review_check
python review.py plan --workspace ./review_workspace --scope smoke
```

`prepare`重新运行公开源整理、人口与先验、环境时间与新闻匹配；`run`批量真实作答，月度/周度使用刚生成的本人回答继续递推；`evaluate`独立评价新回答并在完整Core时接Normal；`calibrate`重估原训练期组合与宏观基线；`downstream`实际重新估计下游回归。付费前必须明确 `--confirm-paid` 和自己的 `--budget-usd`。

## 先看哪些材料

1. [PORTABLE_REPRODUCTION.md](PORTABLE_REPRODUCTION.md)：自己的设备与Key从源资料跑到结果，包括网络容错和恢复。
2. [DIRECTORY_GUIDE.md](DIRECTORY_GUIDE.md)：两种运行路径的目录地图。
3. `studies/sce_inflation_expectations/README.md`：研究对象、P/E/B、实验与评价口径。
4. `studies/sce_inflation_expectations/reproduction_data/portable/evidence/`：逐调用凭证、request ID/时间/usage、公开SCE编号与内部Agent编码、输入输出连接及来源哈希。
5. `studies/sce_inflation_expectations/reports/PAPER_METRIC_GUIDE.md`：论文数字、样本支持、组合参数和费用对应。

## 本地开发与外部模型

我们用OpenRouter→固定SiliconFlow FP8的DeepSeek V3.2，温度0.5、JSON、关闭思考、最多1024输出token；不依赖MCP托管的单选问卷服务。Q8是数值预期，Q9是十档概率，原适配器校验后使用冻结密度拟合器计分。评审提供自己的OpenRouter Key，作者Key从不交付。

四条最终任务的66,822份完整原样Prompt、67,147条原始回复记录和67,334个有效状态均保留；包括失败、补跑和复用来源。新源资料层补充候选新闻与标签、公开问卷和人口/环境生成输入、匿名SCE编号与内部代码映射。316个无返回request ID的失败记录如实为null，不伪造服务端凭证。

## 研究边界

同一冻结算法用于真人与模拟问卷，和纽约联储官方连续分布指标仍有近似差异，单列测量桥接。A有真人微观评价；近期B、月度、周度只有全国真值，不能把模拟群体分歧当作微观拟合优度。Normal是有限人口质量的统计扩展，没有创造新的LLM信息。固定组合参数沿用A早48个月的估计，后续任务不按真值重拟。

固定代码、输入、种子和规则支持方法复现，但温度0.5和外部服务版本不保证新回答逐字一致。封包验收没有新增付费API调用；服务端连通性需用评审自己的Key验证。新运行全部写新目录，不覆盖封存研究。

本ZIP包含第三方新闻摘录及公开微观源快照，**仅供赛事保密评审，不随GitHub公开发布**；来源声明不等于新闻公开再分发许可。数据本来的匿名调查编号和日期不再另行遮蔽，仅排除Key、密码、认证头和付款秘密。纽约联储不参与或背书本研究。
