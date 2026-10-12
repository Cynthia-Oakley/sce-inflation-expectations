"""Build the concise public reading report; contains no respondent-level data."""
from pathlib import Path
from xml.sax.saxutils import escape
import hashlib
import json
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.graphics.shapes import Drawing, Line, Rect, String

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / 'outputs/sce_mechanism_retro_20261013_v1'
OUT.mkdir(parents=True, exist_ok=True)
PDF = OUT / 'sce_mechanism_review_20261013.pdf'
CONFIDENCE = ROOT/'docs/literature/sce/belief_proxies/confidence_result_20261012.json'
HISTORY = ROOT/'docs/literature/sce/heterogeneity_and_probability/lifetime_text_trial_summary_20261012.json'
confidence_metrics = json.loads(CONFIDENCE.read_text())['Q9_four_month_two_repeat_equal_cell_average']
history_metrics = json.loads(HISTORY.read_text())['results']['averages']['Q9']
pdfmetrics.registerFont(TTFont('CN', '/System/Library/Fonts/Supplemental/Arial Unicode.ttf'))
pdfmetrics.registerFont(TTFont('EN', '/System/Library/Fonts/Supplemental/Times New Roman.ttf'))
INK = colors.HexColor('#26343b')
TEAL = colors.HexColor('#246c68')
GREY = colors.HexColor('#62727a')
PALE = colors.HexColor('#e5efec')
title = ParagraphStyle('Title', fontName='CN', fontSize=21, leading=29, textColor=INK, spaceAfter=12)
head = ParagraphStyle('Head', fontName='CN', fontSize=12, leading=18, textColor=TEAL, spaceBefore=9, spaceAfter=5)
body = ParagraphStyle('Body', fontName='CN', fontSize=10.5, leading=16.2, wordWrap='CJK', firstLineIndent=21, spaceAfter=8, textColor=INK)
note = ParagraphStyle('Note', fontName='CN', fontSize=8.7, leading=13, wordWrap='CJK', spaceAfter=6, textColor=GREY)
flow = []

def p(text, style=body):
    flow.append(Paragraph(escape(text), style))

def h(text):
    p(text, head)

def newpage(section, subtitle):
    if flow:
        flow.append(PageBreak())
    p(section, title)
    p(subtitle, note)

def link(label, url):
    flow.append(Paragraph('<link href="' + escape(url, {'"': '&quot;'}) + '" color="#246c68">' + escape(label) + '</link>', note))

newpage('我们现在缺的是什么', '水上挽月 · SCE 一年期通胀预期项目\n证据核查截至2026-10-12，综合报告完成于2026-10-13 · 本轮新增付费API调用0')
h('结论：流程已跑通，居民的信念形成过程仍不充分')
p('我们已经能把人口、历史价格和新闻送入模型，收回问卷、计分、保存轨迹并比较结果。但是，收到不同信息之后，人如何感知、解释和更新信念，仍主要由同一个基础模型自行发挥。这个中间过程是下一步更值得检验的地方。')
h('对五个问题的直接回答')
p('提示词扰动：三种中性开场已有18份完整预览，尚未真实交叉运行。旧“居民答题视角”有40份真实回答，但同时改变了行为引导。')
p('购买频率：Diary已整理2,835条家庭周记录，尚无分类频率进入模拟。以前试过的是支出份额，不能据此判定频率无效。')
p('变量机制：人口标签应通过接触、感知、解释或回答环节发挥作用；不是每个标签都必须让预测数值发生变化。')
p('新增因素：先研究感知通胀、持续性判断和近期家庭冲击；幸福、人格、社交网络有不同程度的依据，宗教暂不优先。')
p('两周复盘：工程积累可保留。央行信心有中心改善，近期价格有弱信号；多数其他机制没有稳定改善，更没有恢复真人的人际差异。')
h('必须分开衡量的三种差异')
p('人际差异：不同人的中心判断相差多少。个人不确定性：一个人的概率铺多宽。生成波动：同一输入重复调用相差多少。后两者变大，不等于恢复了第一种。')
p('本报告是综合阅读版。完整变量说明、16个实验族和来源台账，保存在 docs/reviews/20261012_mechanism_retro/。统计口径不同的实验不横向排名。', note)

newpage('1  等价措辞：先测稳健性', '不要把技术噪声自动当作居民性格；目前未进行新的真实调用。')
h('已有实现')
p('6人×3种中性开场，共18份实际提示已离线生成。每人的三份提示去掉开场后，人口、环境、数字与问卷正文逐字一致。这个检查证明事实没有变，但语义是否等价仍需人工审阅。真实运行入口还没有接入这批模板。')
p('旧实验曾修改“以家庭受访者作答”等说明，共40份真实回答。那组同时改变了回答框架，反而使两个月的人际跨度进一步缩窄，不能证明轻微改写能改善异质性。')
h('落地方式')
p('先做6人×3模板×2次生成的36次候选小试。同一人尝试全部模板，每次独立会话，按预登记顺序调用。锁定P/E、日期、单位、新闻、信心强度、问卷原文、概率档位和输出规则，只改中性的开场或标题。')
p('先比较“同模板重复差异”和“换模板差异”，再辅助看SCE误差。如果模板变化大，说明结果对表达敏感；不能挑最像真人的模板作为赢家，也不能把三种模板的比例称为美国居民的真实表达分布。')
p('需要补独立运行适配器、完整消息核验与36条离线干跑。通过后再确认具体预算与发送范围，本轮不消耗旧实验授权。')
h('为什么不称为RFT')
p('Rejection fine-tuning会生成、筛选样本，并用筛选结果训练模型权重。我们现在只改变输入文字，没有训练模型。适合称“等价措辞稳健性检验”。固定每人一种模板还可能把模板效应与个人效应混在一起，所以先做同人交叉。')
link('方法参考：FormatSpread，等价格式下的模型敏感性', 'https://arxiv.org/html/2310.11324v2')
link('训练概念参考：Llama 2，§3.2.3 Rejection Sampling Fine-Tuning', 'https://arxiv.org/html/2307.09288v2')

newpage('2  购买频率：有价值，但需补一层', '支出份额、购买日数、购物次数、本人购物责任和注意力不是同一个量。')
h('我们已经有多少基础')
p('CE Diary已经物化2,835个家庭周记录：2,455条购买日支持完整，136条部分支持，其余为无正发布金额记录或无支出记录。当前字段只统计全类别在七天中出现有效支出的天数，没有类别频率，也没有进入真实模型。')
h('从现有文件可以做什么')
p('第一步，计算居家食品、外食、家用日用品、个人护理等类别的出现日数，并记录缺失、部分支持和来源。每类可为0—7日，同一天可买多类。不能把没有记录全部当零，也不能把支出行数当购物趟数。')
p('第二步，在Diary内部用共同人口字段匹配完整的“支出结构＋购买日向量”，保留供体池和回退规则。检验两周是否一致、类别是否太稀疏。Diary与Interview是不同家庭，不能按ID拼成一户实测。')
p('第三步，先测频率描述在同信息下有没有影响；再另测频率是否应该改变个人能看见的价格线索。后者比较匹配与同库存置换，控制信息量，不同时改变心理标签、问卷或历史叙述。')
h('理论支持与局限')
p('美国购物研究支持高频接触与通胀预期有关，但其基础测度是12个月商品购买数量，并以购物行程出现比例作稳健性检验。我们的短期购买日代理不等于论文测度，更不等于已知道SCE每个人的注意力。频率不一定在所有家庭都比金额权重更重要。')
p('现有2020Q4文件有后续修订信息。路线A可披露为事后合成代理；路线B必须补截止前资料和版本证据。低频品类若数据太稀疏，应降为情景分析，而非假装匹配精准。')
link('理论与测度：Exposure to Grocery Prices and Inflation Expectations', 'https://eml.berkeley.edu/~ulrike/Papers/paper_DMOW.pdf')
link('数据说明：BLS CE PUMD指南', 'https://www.bls.gov/cex/pumd-getting-started-guide.htm')

newpage('3  现有变量如何真正发挥作用', '传导机制 → 落地方法 → 当前缺口；详细证据见完整报告第5节。')
h('年龄和生活经历')
p('历史经历影响记忆和持续性判断。时代库已经程序化，数字/文字两轮未改善整体效果。下一种候选是当前冲击检索少量相关经历，不能继续单纯加长历史表；年龄也不等于真实记忆。')
h('收入、就业、住房')
p('通过预算压力、生活变化和账单接触影响注意。收入档不等于最近收入下降，房主不等于天天看市场房租。把稳定画像和近期状态分开，再匹配真实可接触的价格。简单Q1描述已试过，不能原样重复并称新机制。')
h('教育、数理能力与金融理解')
p('影响信息选择，以及对同比/环比、价格水平/涨幅和概率的理解。需要检查同事实下的理解差异，而非写“能力低”后假定机制成立。不能要求低素养者故意算错或固定报高通胀。')
h('支出、频率与地区')
p('决定哪些商品和账单进入生活视野。支出侧车可用，分类购买频率和购物责任仍缺。实际地区试验主要是汽油匹配，不是水电燃气全覆盖；小样不稳定不能推出地区无效。')
h('新闻、媒体与政策信心')
p('版面和渠道决定可见性，信任影响接受程度。新闻分类、头版背景与50/50抽取已经运行，但比例是假设。美联储信心有局部成效；政府信任不是同一变量，合成全国比例也不是真人态度。')
h('宏观信息与原有信念')
p('主体统计表仍高度共享，可能使模型更像收到统一经济简报的人。近期实验每月冷启动，尚无经过校验的个人信念更新状态。下一步区分过去价格感知、冲击持续性和信号可信度；不能把同期真实Q9或三年期答案反推后放回输入。')
link('机制依据：纽约联储随机信息实验，信息会使预期向中心收敛', 'https://www.newyorkfed.org/research/staff_reports/sr543.html')

newpage('4  新因素的优先级', '文献支持人的某种行为，不等于给模型加一个标签就能复现。')
h('优先：感知通胀与主观持续性')
p('先理解“过去一年我觉得涨了多少”，再理解“这个冲击还会持续多久”。同样的油价上涨，有人想到供给短缺，有人想到需求；同样加息，有人想到需求收缩，有人想到融资成本。可先做同事实、不同解释的情景对照，但没有调查分布前不随机给全国居民分经济学流派。')
link('Andre等：Subjective Models of the Macroeconomy', 'https://doi.org/10.1093/restud/rdac008')
h('优先核查：近期财务冲击与情绪线索回忆')
p('近期失去收入、预算变紧与长期收入档不同，可能唤起不同价格记忆。SCE Q1有同人数据，但简单标签已未稳定改善。新的增量应是状态怎样改变检索和注意。A可披露用当期状态，B不能拿尚未发布的当期Q1。')
h('第二层：幸福、乐观、人格与知识自信')
p('人格与通胀有直接关联研究，但本轮核查的证据来自奥地利，不能把系数直接移植到美国。一般乐观不必然降低通胀预期；对需求旺盛的乐观也可能提高它。GSS幸福/财务满意是状态，不是大五人格，风险偏好也不等于概率宽度。')
p('先核同人量表、共同人口字段和历史版本。把CE、GSS、ANES等独立抽样标签拼在一起，无法保证它们之间未观测的联合关系真实。')
h('后续：社交网络、广播与党派渠道')
p('美国研究支持显著价格信号经社会联系传播，但公开县际联系不是SCE个人朋友圈。可先补渠道习惯，再做无网络、同信息量随机边和同质边对照。政府信任、Fed信任、媒体信任、党派各不相同；部分政治差异还可能是表达性作答。')
h('暂不优先：宗教名称本身')
p('本轮未找到足以可靠外推到美国一年期SCE的直接证据。未来可研究社群交流和互助，当前不按宗派赋予通胀方向。没有证据不代表效应为零，只代表暂不适合投入主线。')

newpage('5  两周做成了什么', '完整清单覆盖16个实验族；“功能可用”和“预测改善”分开登记。')
h('已经保留的基础设施')
p('数据验收、P/E白名单与来源时间记录；冻结的项目近似Q9计分器；本地官方引擎、真实LLM、Core/Normal、逐次提示与回包、轨迹和费用估算；统一评价、新闻分类与抽取、CE合成篮子、政策和历史生成器。')
p('关键完整运行：2021年5/6月每月300 Core，共600次真实调用，再统计扩展到当月人口。全国近似Q9中心约2.95/3.86，对照同口径约4.00/4.80。流程完成，但均偏低，人际分布也偏窄。Normal不能创造Core原本没有的差异。')
h('有线索，作为候选保留')
p('央行信心四时期试验降低平均中心误差，但分布改善小；近期全国价格两月试验有弱信号。原生SCE支出完成了本地统计研究，LLM对照尚未运行，不能与已跑的CE合成篮子混为一谈。')
h('当前版本暂停升级，保留结果')
p('CE篮子与排序、Q1简单描述、单品类接触、地区汽油匹配、50/50新闻匹配，均未稳定同时改善水平和分布。篮子、新闻池及50/50参照配置仍保留。两种年龄经历呈现均未通过升级标准。')
p('Qwen旧输入全年复用略改善中心，却未稳定改善方向与分布；旧提示还继承DeepSeek前期回答。继续广撒模型暂停。宏观就业/收入更新完成回测，但未证明能改善SCE行为。')
h('已经有长窗口，但不是新版Agent长跑')
p('全国统计基线已到2026年8月，共80月；微观分布基线到2025年10月，共70月。旧2021全年模型实验存在，但新版77信号＋新闻＋信心＋个人机制尚未独立长跨度验证。四期12/48人仍是开发样本。')
h('仍未完成')
p('严格等价模板实跑、分类购买频率试验、原生QSP5真实篮子LLM对照、新版机制的未调参月份验证，以及干净环境中的最终自包含复现包。基础设施可运行，不意味着已经完成比赛研究。')

newpage('6  结果应该怎样读', '以下是各自实验内部的同期比较，不能跨图挑最低误差作为“最好版本”。')

def bars(labels, values, caption, top):
    d = Drawing(490, 133)
    left, right, bottom = 105, 432, 31
    for v in [0, top / 2, top]:
        x = left + (right-left) * v/top
        d.add(Line(x, bottom, x, 118, strokeColor=colors.HexColor('#dce3e1'), strokeWidth=.5))
        d.add(String(x, 16, f'{v:g}', fontName='EN', fontSize=9, textAnchor='middle', fillColor=GREY))
    for i, (label, val) in enumerate(zip(labels, values)):
        y = 100-i*28
        d.add(String(left-8, y+2, label, fontName='CN', fontSize=10, textAnchor='end', fillColor=INK))
        d.add(Rect(left, y, (right-left)*val/top, 14, fillColor=TEAL if i == 0 else colors.HexColor('#91b4aa'), strokeColor=None))
        d.add(String(left+(right-left)*val/top+5, y+2, f'{val:.3f}', fontName='EN', fontSize=10, fillColor=INK))
    d.add(String(268, 1, 'Q9样本中心平均绝对误差（百分点，越低越好）', fontName='CN', fontSize=8.5, textAnchor='middle', fillColor=GREY))
    flow.append(d)
    p(caption, note)

h('央行信心：中心有改善，人群差异仍不够')
bars(['无信心句', '有信心句'], [confidence_metrics[k]['median_absolute_error_pp'] for k in ['no_added_confidence', 'national_confidence']], '来源：confidence_trial_20261011。2022-03/09、2023-03、2024-03各48人，两次生成，四月等权。两组均有同一政策短讯。', .9)
p('768次请求，767份有效Q9。中心误差约降23.3%，但分布距离只改善约2.3%；模拟人际中间50%跨度0.72pp，真人5.78pp。八个误差改善区间中七个跨零，表示小样本证据精度不足，不等于证明没有效果。')
h('文字经历：比数字版好，仍比不加经历差')
bars(['原输入', '数字经历', '文字经历'], [history_metrics[k]['median_absolute_error_pp'] for k in ['original', 'numeric_history', 'text_history']], '来源：lifetime_text_trial_20261012。相同四时期各12人，同期三组两次生成，四月等权。288请求，287份模拟Q9有效。', 1.0)
p('文字版相对数字版低约15.6%，但仍高于原输入，且分布距离和人际差异未过门槛。因此保留程序与负结果，暂停把这两版经历作为正式输入升级。')
p('这两幅图的样本规模不同。0.534不能与上图0.565直接排名。图中“中心”是同批开发样本的Q9个人密度均值的跨人中位数，非美国全国官方headline。', note)

newpage('7  接下来怎样推进', '先证明机制有用，再扩大人数和时期；本报告不启动任何付费调用。')
h('第一步：零API补齐接触测度与运行准备')
p('补Diary分类购买日数、共同人口分布、缺失和两周一致性；核验能否形成稳定的条件供体。并行补三模板独立入口、人工语义审查及离线干跑。这两项都有现成基础，不需要先扩大数据或模型规模。')
h('第二步：只选一个行为机制')
p('优先频率对应的价格接触，或同事实下的持续性解释。不要一轮同时加幸福、社交、人生经历和概率风格。模板试验是独立稳健性检查，不以变得更随机为成功标准。实际调用前另登记范围与预算。')
h('第三步：按固定标准决定是否升级')
p('同时看群体中心、分布距离、主要群组差异；原始十档概率与Q8也保留。只变宽、不更接近真实分布不算成功。配对同人、重复生成与同库存置换分别回答不同问题，不能混在一起解释。')
h('第四步：进入没有参与该机制调参的时期')
p('先预登记4—6个不同经济时期，通过后再扩12—24个月与更大Core。此前反复查看的月份只能叫开发时期；扩大Normal不增加独立模型证据。A事后重建与B事前预测分别说明允许的信息。')
h('同时完成交付工程')
p('清理过期状态说明、锁定依赖与源版本、在干净目录用可公开小样一键复算。原始轨迹和15份待审改动不自动进入提交包。复现能力是成果，最终研究包仍需单独验收。')
h('若最终仍模拟不像')
p('可以形成有价值的机制边界研究，但仍需有效基线、固定评价和跨时期证据。明确哪些机制在人类研究中有依据，却未被模型重现；哪些只改善平均数、未恢复分布。负结果应解释边界，不能代替尚未完成的验证。')
link('补充直接相关研究：Inflation Attitudes of Large Language Models（2025，本轮核查摘要）', 'https://arxiv.org/abs/2512.14306')
link('社交传导：Cleveland Fed, The Expectations of Others', 'https://www.clevelandfed.org/-/media/project/clevelandfedtenant/clevelandfedsite/publications/working-papers/2023/wp2322.pdf')
p('完整来源、逐实验路径与数据条件：同项目 docs/reviews/20261012_mechanism_retro/README.md。主报告 review.md 可继续编辑；本PDF是本次复盘的固定阅读版。', note)

def footer(canvas, doc):
    canvas.setStrokeColor(colors.HexColor('#d8e0dc'))
    canvas.line(42, 38, A4[0]-42, 38)
    canvas.setFont('CN', 8)
    canvas.setFillColor(GREY)
    canvas.drawString(42, 24, '水上挽月 · 机制与项目复盘 · 2026-10-13')
    canvas.drawRightString(A4[0]-42, 24, f'{doc.page} / 8')

SimpleDocTemplate(str(PDF), pagesize=A4, leftMargin=42, rightMargin=42, topMargin=37, bottomMargin=51,
                  title='SCE机制与两周项目复盘', author='水上挽月').build(flow, onFirstPage=footer, onLaterPages=footer)
receipt = {
    'finalized_on': '2026-10-13', 'evidence_cutoff': '2026-10-12',
    'pdf': str(PDF.relative_to(ROOT)), 'pdf_sha256': hashlib.sha256(PDF.read_bytes()).hexdigest(),
    'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in [HERE/'review.md', HERE/'prompt_frequency_audit.md', HERE/'missing_factors_evidence.md', HERE/'experiment_inventory.md', CONFIDENCE, HISTORY, Path(__file__)]},
    'new_simulation_calls': 0, 'new_project_paid_api_calls': 0,
    'counts_and_metrics': 'Existing public aggregate receipts only; no participant-level rows in PDF.',
    'visual_qa': 'pending'
}
(OUT/'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
print(PDF)
