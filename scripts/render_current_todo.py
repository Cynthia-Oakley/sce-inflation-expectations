"""Render the current NEXT_ACTIONS checklist as a small local reading page."""

from html import escape
from pathlib import Path
import re


def main():
    root = Path(__file__).resolve().parents[1]
    source = (root / 'docs/NEXT_ACTIONS.md').read_text(encoding='utf-8')
    match = re.search(r'<!-- current-todo:start -->\s*(.*?)\s*<!-- current-todo:end -->', source, re.S)
    if match is None:
        raise ValueError('Current checklist markers are missing')
    section = match.group(1)
    title = re.search(r'^# (.+)$', section, re.M).group(1)
    note = next(line for line in section.splitlines() if line.startswith('更新：'))
    tasks = re.findall(r'^- \[([ x])\] (.+)$', section, re.M)
    if not tasks:
        raise ValueError('Current checklist contains no tasks')
    done = sum(status == 'x' for status, _ in tasks)
    rows = []
    for status, label in tasks:
        checked = ' checked' if status == 'x' else ''
        state = '已完成' if status == 'x' else '待办'
        rows.append(f'<li><input type="checkbox" disabled{checked} aria-label="{state}"><span>{escape(label)}</span><small>{state}</small></li>')
    page = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="refresh" content="10"><title>{escape(title)}</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#fafaf7;color:#26332f;font-family:system-ui,-apple-system,"PingFang SC",sans-serif}}main{{max-width:900px;margin:auto;padding:32px 24px}}h1{{font-size:25px;line-height:1.4;margin:0 0 16px}}p{{line-height:1.7}}progress{{width:100%;height:14px;accent-color:#326a56}}ul{{padding:0;list-style:none;margin:24px 0}}li{{display:flex;gap:14px;align-items:flex-start;border-bottom:1px solid #dce2dc;padding:17px 0;line-height:1.6}}input{{flex:none;width:20px;height:20px;margin-top:4px;accent-color:#326a56;opacity:1}}li span{{flex:1;min-width:0}}small{{flex:none;color:#66746e;font-size:12px;margin-top:4px}}a{{color:#326a56}}footer{{color:#66746e;font-size:13px;line-height:1.7}}@media(max-width:500px){{main{{padding:22px 16px}}h1{{font-size:22px}}li{{gap:10px}}}}
</style></head><body><main>
<h1>{escape(title)}</h1><p>{escape(note)}</p>
<p>已完成 {done} / {len(tasks)} 项</p><progress value="{done}" max="{len(tasks)}" aria-label="清单完成进度"></progress>
<ul>{''.join(rows)}</ul>
<footer>清单由Agent根据实际进展更新，本页每10秒刷新。打钩表示工作已完成，不代表实验假设得到支持。<br>文字来源：NEXT_ACTIONS.md。<a href="reviews/20261012_mechanism_retro/behavior_reorientation_20261013.md">方向方案</a></footer>
</main></body></html>'''
    output = root / 'docs/current_todo.html'
    output.write_text(page, encoding='utf-8')
    print(f'{done}/{len(tasks)} completed; saved {output}')


if __name__ == '__main__':
    main()
