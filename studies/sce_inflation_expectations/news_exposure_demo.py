"""Offline A1 common news and mildly personalized news; no LLM or truth input."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import html
import json
from pathlib import Path
import random
import re

ROOT = Path(__file__).resolve().parents[2]
CONFIG = Path(__file__).with_name('news_exposure_demo_config_v1.json')
# Descriptive routing tags AFTER existing semantic classification, not new recall rules.
TERMS = {
    'rental_housing': ('rent', 'rents', 'renting', 'rental', 'tenant', 'tenants', 'landlord', 'landlords', 'eviction'),
    'owned_housing': ('mortgage', 'mortgages', 'home price', 'home prices', 'homeowner', 'homeowners', 'property tax'),
    'food': ('food', 'foods', 'grocery', 'groceries', 'meat', 'beef', 'milk', 'bread'),
    'road_fuel': ('gasoline', 'gas pump', 'gas pumps', 'gas station', 'gas stations', 'fuel', 'diesel', 'oil', 'petroleum'),
    'utilities': ('electricity', 'utility', 'utilities', 'electric bill', 'natural gas'),
    'labor_income': ('job', 'jobs', 'employment', 'unemployment', 'worker', 'workers', 'wage', 'wages', 'salary', 'salaries'),
}
HOUSEHOLD_KEYS = {'demo_id', 'label_zh', 'housing_tenure', 'employed', 'synthetic_spending_shares'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def front_page_status(doc):
    """Section B page 1 is NOT the general front page; missing metadata stays unknown."""
    section = str(doc.get('print_section') or '').strip().upper()
    page = str(doc.get('print_page') or '').strip()
    if not section or not page:
        return 'unknown'
    return 'a1' if section == 'A' and page == '1' else 'other_recorded_page'


def news_tags(row):
    text = ' '.join(str(row.get(k) or '') for k in ('headline', 'abstract', 'snippet')).casefold()
    return sorted(name for name, terms in TERMS.items() if any(
        re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', text) for term in terms))


def household_interests(profile):
    if set(profile) != HOUSEHOLD_KEYS:
        raise ValueError('demo profiles accept only explicit non-answer fields')
    if profile['housing_tenure'] not in {'rent', 'own'} or type(profile['employed']) is not bool:
        raise ValueError('invalid demonstration profile')
    shares = profile['synthetic_spending_shares']
    if set(shares) != {'food', 'gasoline', 'utilities'} or any(
        isinstance(v, bool) or not isinstance(v, (float, int)) or not 0 <= v <= 1 for v in shares.values()
    ) or sum(shares.values()) > 1:
        raise ValueError('invalid partial synthetic spending shares')
    interests = {'rental_housing' if profile['housing_tenure'] == 'rent' else 'owned_housing'}
    if profile['employed']:
        interests.add('labor_income')
    # Illustrative thresholds; NOT estimated from SCE, CE or observed media exposure.
    for key, threshold, tag in [('food', .25, 'food'), ('gasoline', .08, 'road_fuel'), ('utilities', .08, 'utilities')]:
        if shares[key] >= threshold:
            interests.add(tag)
    return interests


def probabilities(rows, interests, mixing_weight, boost=2.):
    if not 0 <= mixing_weight <= 1 or boost < 1:
        raise ValueError('invalid mixture parameters')
    if not rows:
        return []
    scores = [boost if set(row['routing_tags']) & interests else 1. for row in rows]
    total = sum(scores)
    return [(1 - mixing_weight) / len(rows) + mixing_weight * score / total for score in scores]


def draw_news(rows, count, seed_key, interests=frozenset(), mixing_weight=0., boost=2.):
    if count < 0 or len({r['article_id'] for r in rows}) != len(rows):
        raise ValueError('negative count or duplicate article IDs')
    # The same random numbers across mixing weights make the offline contrast legible.
    rng = random.Random(int(hashlib.sha256(seed_key.encode()).hexdigest(), 16))
    available = sorted(rows, key=lambda r: r['article_id'])
    chosen, audit = [], []
    for _ in range(min(count, len(available))):
        probs = probabilities(available, interests, mixing_weight, boost)
        draw = rng.random()
        cumulative = 0.
        selected = len(available) - 1
        for i, prob in enumerate(probs):
            cumulative += prob
            if draw < cumulative:
                selected = i
                break
        row = available.pop(selected)
        chosen.append(row)
        audit.append({'article_id': row['article_id'], 'probability_given_remaining_pool': probs[selected],
                      'related_tags': sorted(set(row['routing_tags']) & interests), 'uniform_draw': draw})
    return chosen, audit


def exact_deduplicate(rows):
    """Only remove identical source text; different updates remain, not invented event clusters."""
    result, seen = [], set()
    for row in sorted(rows, key=lambda r: r['article_id']):
        key = tuple(' '.join((row.get(k) or '').split()).casefold() for k in ('headline', 'abstract', 'snippet'))
        if key not in seen:
            result.append(row)
            seen.add(key)
    return result


def verify_sources(plan):
    for name, expected in plan['source_sha256'].items():
        if sha(ROOT / name) != expected:
            raise ValueError('original trial source changed: ' + name)
    protected = json.loads((ROOT / 'docs/sources/sol_handoff_protected_files_20261010.json').read_text())['files_sha256']
    if any(sha(ROOT / name) != expected for name, expected in protected.items()):
        raise ValueError('protected user/Kimi work changed')
    return len(protected)


def prepare_window(inputs, info, labels):
    raw = {}
    for month in info['months']:
        for doc in json.loads((ROOT / 'data/raw/nyt_archive' / (month + '.json')).read_text())['response']['docs']:
            identity = doc.get('_id') or doc.get('uri') or doc.get('web_url')
            if identity and (doc.get('pub_date') or '')[:10] <= info['cutoff_date']:
                raw.setdefault(identity, doc)
    # Pool already enforces article identity, text and the exact old date-level window.
    pool = json.loads((inputs / ('pool_' + info['target'] + '.json')).read_text())
    enriched = []
    for original in pool:
        if original['pub_date'][:10] > info['cutoff_date']:
            raise ValueError('future news in prepared pool')
        doc = raw[original['canonical_source_id']]
        text = {k: doc.get(k) or '' for k in ('abstract', 'snippet')}
        text['headline'] = (doc.get('headline') or {}).get('main') or ''
        if any(original[k] != text[k] for k in text):
            raise ValueError('source text changed')
        row = {k: original[k] for k in ('article_id', 'headline', 'abstract', 'snippet', 'pub_date', 'web_url',
                                      'text_sha256', 'text_vintage_status')}
        row.update(print_section=doc.get('print_section'), print_page=doc.get('print_page'),
                   placement=front_page_status(doc), routing_tags=news_tags(row),
                   semantic_label=labels.get(row['article_id']))
        enriched.append(row)
    # Common news follows editorial placement, not inflation-related semantic labels.
    common = exact_deduplicate([r for r in enriched if r['placement'] == 'a1'])
    personal = exact_deduplicate([r for r in enriched if r['placement'] != 'a1' and
                                 r['semantic_label'] and r['semantic_label']['decision'] == 'keep'])
    stats = {'target': info['target'], 'cutoff_date': info['cutoff_date'], 'date_rule': info['date_rule'],
             'source_articles': len(pool), 'placement_counts': dict(Counter(r['placement'] for r in enriched)),
             'common_a1_candidates': len(common), 'personal_keep_candidates': len(personal),
             'personal_unknown_placement': sum(r['placement'] == 'unknown' for r in personal),
             'sample_status': 'personal library is limited to existing 347-article labeling trial; not full-month final selection',
             'paper_issue_date_status': 'not_independently_verified; online pub_date is not paper publication date'}
    return common, personal, stats


def render_news_input(common, personal):
    chunks = []
    for heading, rows in [('General news you encountered', common), ('Other news you encountered', personal)]:
        lines = [heading + ':']
        for row in rows:
            lines.append('- Online publication date ' + row['pub_date'][:10] + ': ' + row['headline'])
            if row['abstract']:
                lines.append('  ' + row['abstract'])
            # Preserve snippet if it carries evidence absent from the abstract.
            if row['snippet'] and row['snippet'] != row['abstract'] and row['snippet'] not in row['abstract']:
                lines.append('  Additional source excerpt: ' + row['snippet'])
        chunks.append('\n'.join(lines))
    return '\n\n'.join(chunks)


def preview_section(bundle, config):
    esc = html.escape
    rows = []
    for stats in bundle['windows']:
        rows.append('<li>' + esc(stats['target']) + '：A1候选 ' + str(stats['common_a1_candidates']) +
                    ' 篇；已有精筛中可用于个人分配的非A1/版面未知主要候选 ' + str(stats['personal_keep_candidates']) + ' 篇。</li>')
    cards = []
    for view in bundle['views']:
        heading = view['target'] + ' · ' + view['profile']['label_zh'] + ' · 相关性权重 ' + str(view['mixing_weight'])
        lists = []
        for title, articles in [('所有示例家庭共同看到：抽取的A1新闻', view['common_news']), ('本家庭抽取的其他经济新闻', view['personal_news'])]:
            items = []
            for r in articles:
                related = sorted(set(r['routing_tags']) & set(view['interests']))
                meta = r['pub_date'][:10] + ' · 版面记录：' + str(r.get('print_section') or '未知') + str(r.get('print_page') or '')
                if title.startswith('本家庭'):
                    meta += ' · 规则关联：' + (', '.join(related) if related else '无关联，仍可随机接触')
                items.append('<details><summary>' + esc(r['headline']) + '</summary><p class="meta">' + esc(meta) +
                             '</p><p>' + esc(r['abstract']) + '</p>' +
                             ('<p class="sub">原片段：' + esc(r['snippet']) + '</p>' if r['snippet'] != r['abstract'] else '') +
                             '<p><a href="' + esc(r['web_url'], quote=True) + '">原新闻</a></p></details>')
            lists.append('<h4>' + esc(title) + '</h4>' + ''.join(items))
        cards.append('<article class="exposure-card" data-month="' + esc(view['target']) + '" data-household="' +
                     esc(view['profile']['demo_id']) + '" data-mix="' + str(view['mixing_weight']) + '"><h3>' +
                     esc(heading) + '</h3><p>本次实际抽到 ' + str(view['related_selected']) + ' 条规则相关消息 / ' +
                     str(len(view['personal_news'])) + ' 条个人消息；单次抽样无需恰好等于30%。</p>' + ''.join(lists) +
                     '<details><summary>查看实际可送给模拟模型的新闻原文（只有新闻，不是完整P/E/B提示）</summary><pre style="white-space:pre-wrap">' +
                     esc(view['news_input_text']) + '</pre></details></article>')
    selects = []
    for field, label, options, default in [
        ('month', '月份', [(x['target'], x['target']) for x in bundle['windows']], bundle['windows'][0]['target']),
        ('household', '示例家庭', [(x['demo_id'], x['label_zh']) for x in config['households']], config['households'][0]['demo_id']),
        ('mix', '相关性权重', [(str(x), str(x)) for x in config['mixing_weights']], str(config['default_mixing_weight']))]:
        opts = ''.join('<option value="' + esc(value) + '"' + (' selected' if value == default else '') + '>' + esc(text) + '</option>' for value, text in options)
        selects.append('<label>' + label + ' <select id="exposure-' + field + '">' + opts + '</select></label>')
    return ('<section id="news-exposure-demo"><h2>从公共新闻库到每个家庭看到的消息</h2>'
            '<p class="important">离线实现，真实模型调用0次。共同背景只依据总头版A1，不按通胀相关性再筛；B1不是A1。个人消息取已有精筛主要候选，结合家庭相关性与随机性抽取。</p>'
            '<p>三种家庭完全合成，不来自真实SCE受访者；支出份额只作演示。默认相关性权重0.3：每次选择概率由70%均匀分布＋30%家庭相关加权分布组成，相关项加权2倍。不是固定30%消息必须相关，更不是估计到的真实阅读比例。</p>'
            '<ul>' + ''.join(rows) + '</ul><p>每个窗口共同3条＋个人5条仅为输入演示，不是最终每月新闻量。共同消息按固定种子随机抽自全主题A1候选；每个家庭共用同一组。比例0为纯随机，0.6仅作敏感性示例。</p>'
            '<p class="meta">沿用旧5/6月UTC日期级窗口，仅A路线回顾性机制样例；版面实际刊载日与历史文字版本未独立核验，不能当严格B预测输入。这里只去除原文完全相同的记录，尚未完成按事件整理。未证明模拟误差改善。</p>'
            '<div class="filters">' + ''.join(selects) + '</div><p id="exposure-count" class="meta"></p>' + ''.join(cards) + '</section>')


EXPOSURE_SCRIPT = '''<script id="news-exposure-filters">
const exposureControls=['month','household','mix'].map(k=>document.getElementById('exposure-'+k));
function applyExposureFilters(){const [month,household,mix]=exposureControls.map(c=>c.value);let n=0;document.querySelectorAll('.exposure-card').forEach(e=>{const show=e.dataset.month===month&&e.dataset.household===household&&e.dataset.mix===mix;e.hidden=!show;if(show)n++;});document.getElementById('exposure-count').textContent='显示 '+n+' / 18 组已生成输入；更换家庭或权重查看差异。';}
exposureControls.forEach(c=>c.addEventListener('change',applyExposureFilters));applyExposureFilters();
</script>'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, default=ROOT / 'outputs/sce_nyt_selection_trial_20261011_v1')
    parser.add_argument('--labels', type=Path, default=ROOT / 'outputs/sce_nyt_label_trial_20261011_v3')
    parser.add_argument('--config', type=Path, default=CONFIG)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--update-html', type=Path)
    parser.add_argument('--prior-demo', type=Path, help='Explicitly replace only a previous generated exposure section, verified by hash')
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text())
    if config['status'] != 'offline_demonstration_not_frozen_simulation':
        raise ValueError('only demonstration configs supported')
    for profile in config['households']:
        household_interests(profile)
    plan = json.loads((args.inputs / 'summary.json').read_text())
    protected_count = verify_sources(plan)
    state = json.loads((args.labels / 'state.json').read_text())
    if state['status'] != 'completed':
        raise ValueError('existing semantic label run is incomplete')
    labels = {}
    for line in (args.labels / 'labels.jsonl').read_text().splitlines():
        label = json.loads(line)['label']
        if label['article_id'] in labels:
            raise ValueError('duplicate label ID')
        labels[label['article_id']] = label
    if len(labels) != plan['unique_articles_to_label']:
        raise ValueError('label cardinality differs from prepared trial')
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'source_module.py').write_bytes(Path(__file__).read_bytes())
    (args.out / 'config_snapshot.json').write_bytes(args.config.read_bytes())
    bundle = {'schema': 'sce-news-exposure-offline-demo-v1', 'windows': [], 'views': []}
    for info in plan['windows']:
        if info['target'] not in {'202105', '202106'}:
            continue
        common_pool, personal_pool, stats = prepare_window(args.inputs, info, labels)
        if len(common_pool) < config['common_count'] or len(personal_pool) < config['personal_count']:
            raise ValueError('not enough eligible articles to fill demonstration')
        common, common_audit = draw_news(common_pool, config['common_count'], f"{config['seed']}|{info['target']}|common-a1")
        dump(args.out / ('library_' + info['target'] + '.json'), {'common_a1': common_pool, 'personal_keep': personal_pool})
        stats['common_selected_ids'] = [r['article_id'] for r in common]
        stats['common_draw_audit'] = common_audit
        bundle['windows'].append(stats)
        for profile in config['households']:
            interests = household_interests(profile)
            related = sum(bool(set(r['routing_tags']) & interests) for r in personal_pool)
            for mixing in config['mixing_weights']:
                personal, audit = draw_news(personal_pool, config['personal_count'],
                    f"{config['seed']}|{info['target']}|{profile['demo_id']}|personal", interests, mixing, config['affinity_boost'])
                bundle['views'].append({'target': info['target'], 'profile': profile, 'interests': sorted(interests),
                    'mixing_weight': mixing, 'common_news': common, 'personal_news': personal, 'draw_audit': audit,
                    'related_candidates': related, 'related_selected': sum(bool(set(r['routing_tags']) & interests) for r in personal),
                    'first_draw_related_probability': sum(p for r, p in zip(personal_pool, probabilities(personal_pool, interests, mixing, config['affinity_boost'])) if set(r['routing_tags']) & interests),
                    'news_input_text': render_news_input(common, personal)})
    dump(args.out / 'household_views.json', bundle)
    summary = {'status': 'offline_demo_complete_no_simulation', 'output_dir': str(args.out.resolve().relative_to(ROOT)),
               'windows': bundle['windows'], 'views_generated': len(bundle['views']),
               'common_count': config['common_count'], 'personal_count': config['personal_count'],
               'seed': config['seed'], 'affinity_boost': config['affinity_boost'], 'mixing_weights': config['mixing_weights'],
               'default_mixing_weight': config['default_mixing_weight'], 'source_plan_sha256': sha(args.inputs / 'summary.json'),
               'source_labels_sha256': sha(args.labels / 'labels.jsonl'), 'module_sha256': sha(Path(__file__)),
               'config_sha256': sha(args.config), 'protected_files_unchanged': protected_count,
               'new_api_calls': 0, 'new_simulation_calls': 0, 'real_personal_data_used': False,
               'sampling_results': [{k: v[k] for k in ('target', 'mixing_weight', 'related_candidates', 'related_selected', 'first_draw_related_probability')} |
                                    {'demo_id': v['profile']['demo_id']} for v in bundle['views']]}
    if args.update_html:
        before = args.update_html.read_text()
        summary['existing_html_before_sha256'] = sha(args.update_html)
        (args.out / 'news_review_before.html').write_text(before)
        base = before
        if 'id="news-exposure-demo"' in base:
            if not args.prior_demo:
                raise ValueError('existing exposure section must not be silently overwritten')
            previous = json.loads((args.prior_demo / 'summary.json').read_text())
            if summary['existing_html_before_sha256'] != previous['existing_html_after_sha256']:
                raise ValueError('HTML changed since previous demo; preserve and review those changes')
            start = base.index('<section id="news-exposure-demo">')
            end = base.index('</section>', start) + len('</section>')
            base = base[:start] + base[end:]
            base, script_count = re.subn(r'<script id="news-exposure-filters">.*?</script>', '', base, flags=re.S)
            if script_count != 1:
                raise ValueError('expected exactly one previous exposure filter script')
            summary['previous_demo'] = str(args.prior_demo)
        updated = base.replace('<footer>', preview_section(bundle, config) + '<footer>', 1)
        if updated == base:
            raise ValueError('expected existing HTML footer not found')
        updated = updated.replace('</body>', EXPOSURE_SCRIPT + '</body>', 1)
        args.update_html.write_text(updated)
        summary['existing_html_after_sha256'] = sha(args.update_html)
    summary['output_sha256'] = {p.name: sha(p) for p in sorted(args.out.glob('*.json'))}
    dump(args.out / 'summary.json', summary)
    print(json.dumps({'out': str(args.out), 'windows': bundle['windows'], 'views_generated': len(bundle['views']),
                      'new_api_calls': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
