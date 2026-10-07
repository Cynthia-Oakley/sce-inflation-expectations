"""Opt-in dated E renderer; preserves the existing survey/persona contract."""
from datetime import date
from .environment_authoring.vintages import timestamp

PROMPT_VERSION = 'sce-q8-q9-v3-dated-abstract-v1'


def build_dated_messages(ob, base_builder):
    info = ob.macro_information
    cutoff = timestamp(info['as_of'])
    latest, history = [], {}
    for s in info.get('signals', []):
        if timestamp(s['published_at']) > cutoff:
            raise ValueError('future release in prompt')
        if not s.get('reference_period') or not s.get('source_version'):
            raise ValueError('dated prompt requires observation/version metadata')
        label = f"{s['measure']} [{s['unit']}]"
        value = f"{s['reference_period']}: {float(s['value']):g}"
        if s.get('role') == 'history':
            history.setdefault(label, []).append((s['reference_period'], value))
        else:
            status = s.get('eligibility', 'unknown')
            latest.append(f"- {label}; {value}; published {s['published_at']}; version {s['source_version']}; evidence {status}.")
    blocks = ['Latest supplied reports (each retains its own observation month):\n' + '\n'.join(latest)]
    if history:
        lines = [f"- {label}: " + '; '.join(v for _, v in sorted(values))
                 for label, values in sorted(history.items())]
        blocks.append('Earlier supplied observations (dates shown; gaps are not filled or treated as zero):\n' + '\n'.join(lines))
    news = []
    for e in info.get('events', []):
        if len(e['pub_date']) == 10:
            if date.fromisoformat(e['pub_date']) > cutoff.date():
                raise ValueError('future news day in prompt')
            if e.get('text_vintage_status') != 'unverified_archive_snapshot':
                raise ValueError('day-only news requires explicit unverified evidence flag')
            status = 'publication day only; archived text vintage unverified'
        else:
            if timestamp(e['pub_date']) > cutoff:
                raise ValueError('future news in prompt')
            status = e.get('text_vintage_status', 'text vintage not supplied')
        news.append(f"- {e['pub_date']}: {e['headline']}" + (f" — {e['abstract']}" if e.get('abstract') else '') + f" [evidence: {status}]")
    if news:
        blocks.append('Supplied news headlines and summaries:\n' + '\n'.join(news))
    messages = base_builder(ob, include_event_abstracts=True)
    content = messages[0]['content']
    before, questions = content.split('\n\nQuestion 1 (point estimate):', 1)
    # Keep persona and survey dates; replace the old E rendering as a whole.
    intro = before.split('\n\n', 2)[:2]
    intro[1] = intro[1].split('You only know information')[0] + (
        f"Use the supplied reports dated no later than {info['as_of']}. "
        'Their observation months may differ. Missing months mean no supplied observation, not zero change. '
        'Use these inputs rather than recalling later historical outcomes. '
        'A supplied unverified vintage must not be treated as proven historical information.')
    return [{'role': 'user', 'content': '\n\n'.join(intro + blocks) + '\n\nQuestion 1 (point estimate):' + questions}]
