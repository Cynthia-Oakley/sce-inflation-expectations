"""Append offline diagnostic aggregates to the existing reading artifact."""
import hashlib
import html
import json
from pathlib import Path


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def append_report(root, diagnostic, page, prior, out):
    root, diagnostic, page, prior, out = [Path(p).resolve() for p in (root,diagnostic,page,prior,out)]
    if out.exists() or not out.is_relative_to(root/'outputs'):
        raise ValueError('new output directory required')
    receipt = json.loads((prior/'summary.json').read_text())
    if sha(page) != receipt['existing_html_after_sha256']:
        raise ValueError('existing page changed; preserve and review before editing')
    before = page.read_text()
    if before.count('<footer>') != 1 or 'id="news-response-diagnostic"' in before:
        raise ValueError('page structure or duplicate section')
    result = json.loads((diagnostic/'summary.json').read_text())
    cells=[]
    for month,data in result['months'].items():
        s=data['pooled']; r=data['same_people_real_q9']
        cells.append(f'<tr><td>{month[:4]}-{month[4:]}</td><td>{s["point_mode_pp"]:.1f}%（{s["point_mode_count"]}/144份）</td>'
                     f'<td>{s["q9"]["positive_bin_count"]["median"]:.0f} / {r["positive_bin_count"]["median"]:.0f}</td>'
                     f'<td>{s["q9"]["deflation_probability_percent"]["median"]:.0f}% / {r["deflation_probability_percent"]["median"]:.0f}%</td>'
                     f'<td>{s["lexical_clues"]["base_effect"]["in_reason_count"]}/144份</td></tr>')
    section = ('<section id="news-response-diagnostic"><h2>零API复查：回答如何形成，下一步改什么</h2>'
        '<p class="important">模型常把同一组宏观数字解释为“通胀较高但会缓解”；个人中心回答相近，同时几乎人人给许多区间留概率。下一步先检验涨价持续性看法，不调整50/50再跑原两个月。</p>'
        '<div style="overflow-x:auto;width:100%"><table style="width:100%;min-width:660px"><thead><tr><th>月份</th><th>模型最常见点预测</th><th>非零档数中位数<br>模型 / 真人</th><th>通缩概率中位数<br>模型 / 真人</th><th>提到基数效应</th></tr></thead><tbody>'
        + ''.join(cells) + '</tbody></table></div>'
        '<p>来源：已保存的2021年5/6月真实新闻实验。每月48人×三组＝144份；是重复条件，不是144名独立居民。真人概率有效数为46/48。概率档数指十档中填了大于0的档数。</p>'
        '<h3>可以确认，和仍然不能确认的事</h3><p>288份模型回答都有一定通缩概率，真人则分别有31/46和33/48份填为0。原提示本来允许0，也没有给3.5%或4.5%的示例答案。集中已发生在拟合之前。</p>'
        '<p>187份理由出现“基数效应”，输入新闻未直接出现该词组；价格历史仍可能支持这种推断。此统计不能证明模型如何思考，也不能证明它记住了未来。点预测与密度均值不同并不自动是错误，真人也有差异。</p>'
        '<h3>准备好的对照：信息相同，原有看法不同</h3>'
        '<ol><li>不加持续性看法。</li><li>原本觉得快速涨价会在下一年缓解，允许新信息改变想法。</li><li>原本觉得快速涨价会在下一年持续，同样允许更新。</li></ol>'
        '<p>两种新增情景都区分“涨幅放缓”和“价格回到从前”。不指定预测数字，也不把两类人任意按比例合成全国。方向符合设定只能说明模型响应了条件，现实有效性仍需真实信念分布和后续检验。</p>'
        '<p><strong>已完成：</strong>288份本地输入预览，新闻、价格、问卷逐项配对核查；新增API与费用均为0。另发现shelter不应写成个人租金，新原型各组统一澄清，旧结果保留。</p>'
        '<p><strong>新月份预留：</strong>2022-03与2023-03，额外新闻种子104729/130363。现有本地调用日志未见这两月模拟，但真实统计和基线曾被研究过，不能称完全未见资料。新月份输入、运行包、预算仍需准备；目前没有启动新模拟。</p>'
        '<p><a href="response_diagnostic_20261011.md">完整诊断与准确路径</a> · <a href="persistence_probe_plan_20261011.md">具体对照、英文提示与判断标准</a> · <a href="response_diagnostic_20261011.json">统计汇总</a></p></section>')
    after = before.replace('<footer>', section+'<footer>',1)
    # Prove that all earlier sections survive byte-for-byte.
    if after.replace(section,'',1) != before:
        raise ValueError('previous content changed')
    out.mkdir(parents=True)
    (out/'news_review_before.html').write_text(before)
    page.write_text(after)
    report={'status':'offline_diagnostic_appended','new_api_calls':0,'browser_visual_verification':False,
            'existing_html_before_sha256':hashlib.sha256(before.encode()).hexdigest(),
            'existing_html_after_sha256':sha(page),'diagnostic_summary_sha256':sha(diagnostic/'summary.json'),
            'source_sha256':sha(__file__),'section_id':'news-response-diagnostic',
            'preserved_prior_page_snapshot':'news_review_before.html'}
    (out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report
