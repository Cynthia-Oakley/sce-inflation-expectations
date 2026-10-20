"""Thin registration table for the experiment catalog (panel metadata only).

This table supplements discovered evaluation caches with human-registered
display metadata: Chinese name, research-purpose section, mechanism group,
parent batch, run status and evidence stage. Research purpose is registered
by protocol/human judgement here, never inferred from sample size. Batches
without an entry fall back to 待登记 (unregistered) and are never guessed.
Only batches actually present in the scan are linked from the panel.
"""
from __future__ import annotations

# Research-purpose sections, in display order.
SECTIONS = ('技术检查', '小样机制对照', '扩大验证', '独立验证', '未来预测封存', '历史版本', '待登记')

RUN_STATUSES = ('完成', '部分完成', '停止')
EVIDENCE_STAGES = ('开发', '独立验证', '待复核')

# batch dir name -> registration entry.
# mechanism_group chains experiments of the same mechanism; parent links to a
# batch dir name that actually exists (None when the parent is not in the scan).
CATALOG = {
    'sce_reference_validation_evaluation_20261017_v1': {
        'label': '参考12期（扩大验证）', 'section': '扩大验证',
        'mechanism_group': '参考配置', 'parent': None,
        'run_status': '完成', 'evidence_stage': '开发',
        'note': '12 个非连续月 × 192 人 × 2 遍，单臂 reference（DeepSeek-Flash，T=0.5）'},
    'sce_information_exposure_evaluation_20261019_v1': {
        'label': '新闻条数×统计详略6期', 'section': '小样机制对照',
        'mechanism_group': '新闻接触量', 'parent': None,
        'run_status': '完成', 'evidence_stage': '开发',
        'note': '统一条数对照：3/8/20 篇 × 完整/精简统计共六臂 + baseline（96 人 × 2 遍）'},
    'sce_news_breadth_evaluation_20261019_v1': {
        'label': '新闻匹配/随机6期', 'section': '小样机制对照',
        'mechanism_group': '新闻接触量', 'parent': 'sce_information_exposure_evaluation_20261019_v1',
        'run_status': '完成', 'evidence_stage': '开发',
        'note': '差异化分配对照：baseline / news_matched / news_randomized 三臂（96 人 × 2 遍）'},
    'sce_procurement_qwen_evaluation_20261020_v2': {
        'label': 'Qwen采购角色6期', 'section': '小样机制对照',
        'mechanism_group': '采购经历与可见价格', 'parent': None,
        'run_status': '完成', 'evidence_stage': '开发',
        'note': 'shared_price / matched_role / shuffled_role 三臂（Qwen-2.5-72B，96 人 × 2 遍）'},
    'sce_cognition_evaluation_20261016_v1': {
        'label': '认知引导小样4期', 'section': '小样机制对照',
        'mechanism_group': '认知引导', 'parent': None,
        'run_status': '完成', 'evidence_stage': '开发',
        'note': 'label_only / question_answer / faithful_paraphrase 三臂（24 人 × 2 遍）'},
    'sce_consumer_context_evaluation_20261018_v1': {
        'label': '消费者语境小样3期', 'section': '小样机制对照',
        'mechanism_group': '消费者语境', 'parent': None,
        'run_status': '完成', 'evidence_stage': '开发',
        'note': 'baseline / consumer_context 两臂（24 人 × 2 遍）'},
    'sce_finance_validation_evaluation_20261017_v1': {
        'label': '家庭金融跨月4期', 'section': '小样机制对照',
        'mechanism_group': '家庭金融信息', 'parent': 'sce_household_finance_evaluation_20261016_v1',
        'run_status': '完成', 'evidence_stage': '开发',
        'note': 'baseline / financial_facts 两臂（48 人 × 2 遍，跨月）'},
    'sce_financial_outlook_evaluation_20261017_v1': {
        'label': '上期财务展望4期', 'section': '小样机制对照',
        'mechanism_group': '家庭金融信息', 'parent': None,
        'run_status': '完成', 'evidence_stage': '开发',
        'note': 'baseline / previous_financial_outlook 两臂（48 人 × 2 遍）'},
    'sce_household_finance_evaluation_20261016_v1': {
        'label': '家庭金融小样4期', 'section': '小样机制对照',
        'mechanism_group': '家庭金融信息', 'parent': None,
        'run_status': '完成', 'evidence_stage': '开发',
        'note': 'baseline / financial_facts / financial_perspective 三臂（24 人 × 2 遍）'},
    'sce_psychological_state_evaluation_20261017_v1': {
        'label': '心理状态小样4期', 'section': '小样机制对照',
        'mechanism_group': '合成心理状态', 'parent': None,
        'run_status': '完成', 'evidence_stage': '开发',
        'note': 'matched / permuted / baseline 三臂（48 人 × 2 遍）'},
    'sce_psychological_wave_evaluation_20261018_v1': {
        'label': '心理状态波次小样3期', 'section': '小样机制对照',
        'mechanism_group': '合成心理状态', 'parent': 'sce_psychological_state_evaluation_20261017_v1',
        'run_status': '完成', 'evidence_stage': '开发',
        'note': 'matched / permuted / baseline 三臂（48 人 × 2 遍）'},
    'sce_q8_only_evaluation_20261019_v1': {
        'label': 'Q8通道小样4期', 'section': '技术检查',
        'mechanism_group': 'Q8 通道', 'parent': None,
        'run_status': '完成', 'evidence_stage': '开发',
        'note': 'direct / q8_delta 两臂（24 人 × 2 遍）'},
    'sce_qwen_migration_evaluation_20261019_v1': {
        'label': 'Qwen迁移小样3期', 'section': '技术检查',
        'mechanism_group': '模型迁移', 'parent': None,
        'run_status': '完成', 'evidence_stage': '开发',
        'note': 'qwen / baseline 两臂（Qwen-2.5-72B 对 DeepSeek-Flash 同输入，24 人 × 2 遍）'},
    'sce_temperature_evaluation_20261019_v1': {
        'label': '温度技术检查4期', 'section': '技术检查',
        'mechanism_group': '采样温度', 'parent': None,
        'run_status': '完成', 'evidence_stage': '开发',
        'note': 'baseline / temperature_08 / temperature_10 三臂，4 遍重复（24 人）'},
    # 旧契约批次：登记为历史版本，v0 适配器不接入分析
    'sce_anchor_role_evaluation_20261014_v1': {
        'label': '锚定角色小样（旧契约）', 'section': '历史版本',
        'mechanism_group': '锚定角色', 'parent': None,
        'run_status': '完成', 'evidence_stage': '开发',
        'note': '旧 case 契约，面板未接入分析'},
    'sce_expanded_state_evaluation_20261014_v1': {
        'label': '扩展状态小样（旧契约）', 'section': '历史版本',
        'mechanism_group': '扩展状态', 'parent': None,
        'run_status': '完成', 'evidence_stage': '开发',
        'note': '旧 case 契约，面板未接入分析'},
    'sce_information_update_evaluation_20261014_v1': {
        'label': '信息更新小样（旧契约）', 'section': '历史版本',
        'mechanism_group': '信息更新复用', 'parent': None,
        'run_status': '完成', 'evidence_stage': '开发',
        'note': '旧 case 契约，面板未接入分析'},
    'sce_purchase_frequency_evaluation_20261015_v1': {
        'label': '购买频率小样（旧契约）', 'section': '历史版本',
        'mechanism_group': '购买频率', 'parent': None,
        'run_status': '完成', 'evidence_stage': '开发',
        'note': '旧 case 契约，面板未接入分析'},
    'sce_revision_format_evaluation_20261015_v1': {
        'label': '答题格式小样（旧契约）', 'section': '历史版本',
        'mechanism_group': '答题格式', 'parent': None,
        'run_status': '完成', 'evidence_stage': '开发',
        'note': '旧 case 契约，面板未接入分析'},
}

# Pinned top entries for the catalog page.
REFERENCE_BATCH = 'sce_reference_validation_evaluation_20261017_v1'


def unregistered_entry(batch):
    return {'label': batch, 'section': '待登记', 'mechanism_group': '待登记',
            'parent': None, 'run_status': '未核实', 'evidence_stage': '待复核',
            'note': '未登记批次：同契约自动接入；研究用途与运行状态待人工登记，不猜测条件'}


def entry_for(batch):
    return dict(CATALOG.get(batch, unregistered_entry(batch)))
