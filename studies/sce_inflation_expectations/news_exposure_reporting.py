"""Append aggregate news-trial results to the existing local reading page."""
import hashlib
import html
import json
from pathlib import Path

NAMES = {'shared': '共享', 'random': '随机', 'matched': '相关加权'}
COLORS = {'real': '#333333', 'shared': '#7a8793', 'random': '#b56a1b', 'matched': '#256c91'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def chart(result, width=False):
    """Small labelled static SVG; all plotted values come from the saved analysis."""
    title = '不同人Q9中心的分散程度' if width else 'Q9中心中位数：同批真人与三组模拟'
    key = 'cross_person_iqr_pp' if width else 'median_pp'
    rows = []
    for month, values in result['months'].items():
        q9 = values['Q9']
        for arm in ('real', 'shared', 'random', 'matched'):
            d = q9['real'] if arm == 'real' else q9['arms'][arm]['distribution']
            rows.append((month, arm, d[key]))
    upper = max(value for _, _, value in rows) * 1.18
    esc = html.escape
    parts = [f'<svg viewBox="0 0 690 400" role="img" aria-label="{esc(title)}" style="width:100%;height:auto;display:block"><title>{esc(title)}</title>',
             f'<text x="12" y="26" font-size="18" fill="#222">{esc(title)}</text>']
    left, length = 135, 465
    for fraction in (0, .25, .5, .75, 1):
        x = left + fraction*length
        parts.append(f'<line x1="{x}" y1="42" x2="{x}" y2="340" stroke="#dddddd"/>')
        parts.append(f'<text x="{x}" y="365" font-size="12" text-anchor="middle">{upper*fraction:.1f}</text>')
    for index, (month, arm, value) in enumerate(rows):
        y = 50 + index*35
        name = '真人' if arm == 'real' else NAMES[arm]
        label = f'{month[4:]}月 · {name}'
        end = left + value/upper*length
        parts.append(f'<text x="124" y="{y+15}" text-anchor="end" font-size="14">{esc(label)}</text>')
        parts.append(f'<rect x="{left}" y="{y}" width="{max(0,end-left)}" height="22" fill="{COLORS[arm]}"/>')
        parts.append(f'<text x="{end+6}" y="{y+16}" font-size="13">{value:.2f}</text>')
    unit = '跨人四分位宽度（百分点）' if width else '未来一年通胀预期（%）'
    parts.append(f'<text x="370" y="391" text-anchor="middle" font-size="14">{unit}</text></svg>')
    return ''.join(parts)


def render(root, analysis, page, prior_directory, out):
    root, analysis, page, prior_directory, out = map(lambda p: Path(p).resolve(), (root, analysis, page, prior_directory, out))
    if out.exists() or not out.is_relative_to(root/'outputs'):
        raise ValueError('new ignored output directory required')
    result_path = analysis/'summary.json'
    result = json.loads(result_path.read_text())
    prior = json.loads((prior_directory/'summary.json').read_text())
    before = page.read_text()
    if sha(page) != prior['existing_html_after_sha256'] or 'id="news-exposure-results"' in before or before.count('<footer>') != 1:
        raise ValueError('page hash/append gate failed; do not overwrite another edit')
    if result['status'] != 'completed_offline_analysis' or result['actual_simulation_calls'] != 288:
        raise ValueError('completed actual result required')
    cells = []
    for month, value in result['months'].items():
        q9 = value['Q9']
        for arm in ('shared','random','matched'):
            d = q9['arms'][arm]
            cells.append(f'<tr><td>{month[:4]}-{month[4:]}</td><td>{NAMES[arm]}</td>'
                f'<td>{q9["n_common"]}</td><td>{d["distribution"]["median_pp"]:.3f}%</td>'
                f'<td>{d["median_absolute_error_pp"]:.3f}</td><td>{d["distribution_W1_pp"]:.3f}</td>'
                f'<td>{d["distribution"]["cross_person_iqr_pp"]:.3f}</td></tr>')
    section = ('<section id="news-exposure-results"><h2>真实模拟完成：新闻分配有帮助吗？</h2>'
        '<p class="important">288次调用均生成有效问卷。相关加权在6月有小幅改善，5月没有稳定改善；两个月的整体回答分布几乎没变，尚未解决同质化和偏低问题。</p>'
        '<p>这是同批48人的A路线开发实验：5月Q9真人两份概率不合格，共同有效46人；6月48人。不能把小样本误差称作全国指标误差。三组保持人口、消费篮子、价格信息、问卷、模型和温度0.5相同，每人3条共同头版＋5条个人新闻。</p>'
        '<p>补标977篇/123批费用估算$0.160；真实模拟估算$0.176，总计约$0.34，均在已授权上限内。价格按登记费率与token计算，不是服务商账单。没有重试。</p>'
        '<div style="overflow-x:auto"><table style="min-width:730px;width:100%;border-collapse:collapse"><thead><tr>'
        '<th>月份</th><th>新闻方式</th><th>同批有效人数</th><th>模拟Q9中心中位数</th><th>中位数误差<br>百分点</th><th>分布距离W1<br>百分点</th><th>跨人宽度<br>百分点</th>'
        '</tr></thead><tbody>'+''.join(cells)+'</tbody></table></div>'
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:18px">'+chart(result)+chart(result,True)+'</div>'
        '<p>图源：本轮冻结近似计分器重算真实/模拟十档概率，2021年5月46人、6月48人，等权共同样本。左图中位数使用项目经验分位数口径；右图为不同人中心的线性四分位宽度，不是一个人的预测区间。深色为真人，灰色共享，棕色随机，蓝色相关加权。</p>'
        '<h3>最值得关注的差异</h3><p>真人跨人宽度约4.93/4.63个百分点，相关加权组仅0.57/0.94；但是模型个人的概率区间反而偏宽。不同人的中心挤在一起，并没有因为每个人给较宽的概率范围而解决。</p>'
        '<p>相关加权相对随机，中位数误差在5月不变、6月减少0.168个百分点；分布距离只少0.008/0.002个百分点。配对重抽样区间都包含零，单次新闻抽样和模型生成还没有单独重复检验。</p>'
        '<p>按评价调查权重比较，同批样本Q9误差也更大：随机/相关加权分别5月0.434/0.196、6月2.499/1.835个百分点。这是辅助检查，不能挑更好看的口径。全国完整月与此小样本分开记录。</p>'
        '<h3>下一步</h3><p>保留新闻库和50/50配置，先核查一年期判断、通缩概率和共同价格数据的锚定。当前不加大新闻匹配规模，也不依据这两个月改比例后重新报告。选定有理论依据、能清楚区分的改进后，再登记未参与调整的月份与额外种子。</p>'
        '<p>NYT/A1与住房、合成篮子均是接触代理，不是实测阅读记录。共同头版只是一次抽样；纸版刊载日和历史文字版本尚未核验，本轮不声称严格B预测。</p>'
        '<p><a href="news_exposure_results_20261011.md">完整实验记录</a> · <a href="news_exposure_results_20261011.json">可核查统计汇总</a> · <a href="#news-simulation-readiness">查看六份完整输入示例</a></p></section>')
    out.mkdir(parents=True)
    (out/'news_review_before.html').write_text(before)
    updated = before.replace('<footer>',section+'<footer>',1).replace('完整候选已精筛，尚未授权真实Simulation','完整候选已精筛，真实Simulation已获授权并完成288次调用；结果见本页新增结果区',1)
    page.write_text(updated)
    receipt = {'status':'real_results_appended', 'analysis_summary_sha256':sha(result_path),
               'existing_html_before_sha256':hashlib.sha256(before.encode()).hexdigest(),
               'existing_html_after_sha256':sha(page),'result_section_id':'news-exposure-results',
               'preserved_prior_page_snapshot':'news_review_before.html','browser_visual_verification':False,
               'new_api_calls':0,'source_sha256':sha(Path(__file__))}
    (out/'summary.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    return receipt
