"""Visual/interaction acceptance of the local v05 presentation pages."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[4]
BUILD = ROOT / 'tmp/video_complete_v05'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'video_complete_v04'))
from test_browser import call, js


def main():
    checks = []
    out = ROOT / 'deliverables/video/v05'
    try:
        call('navigate', dict(url=(out / 'index.html').as_uri() + f'?build={(out / "index.html").stat().st_mtime_ns}#page=5'))
        call('cdp', dict(method='Emulation.setDeviceMetricsOverride', params=dict(
            width=1920, height=1080, deviceScaleFactor=1, mobile=False)))
        checks.extend(js('''(async()=>{
          const $=s=>document.querySelector(s),data=JSON.parse($('#story').textContent),ok=[];
          const test=(v,n)=>{if(!v)throw Error(n);ok.push(n)};
          for(let page=1;page<=9;page++){
            $('[data-index="'+(page-1)+'"]').click();
            await new Promise(r=>{let im=$('#slide');if(im.complete&&im.naturalWidth)r();else im.onload=r});
            test($('#speech').textContent===data.slides[page-1].narration,'latest narration '+page);
            test($('#slide').naturalWidth===1920,'render '+page);
            if(data.interactive_pages[String(page)])test($('#interaction a').href.includes('#page='+data.interactive_pages[String(page)]+'&sample=A01'),'original demo route '+page);
          }
          test(!!document.querySelector('a[href="environment.html"]'),'environment scene linked');
          $('[data-index="7"]').click();$('#present').click();
          test(getComputedStyle($('.notes')).display==='none','recording hides notes');
          return ok;
        })()'''))
        call('screenshot', dict(format='png', path=str(BUILD / 'preview_page8.png')))
        for width,height in [(1920,1080),(1440,900)]:
            call('navigate', dict(url=(out / 'environment.html').as_uri() + f'?width={width}#recording'))
            call('cdp', dict(method='Emulation.setDeviceMetricsOverride', params=dict(
                width=width,height=height,deviceScaleFactor=1,mobile=False)))
            frame=js('''(()=>({bottom:document.querySelector('.time').getBoundingClientRect().bottom,
              height:innerHeight,width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
              navHidden:getComputedStyle(document.querySelector('nav')).display==='none',
              sources:['纽约时报','BLS','ATUS','美联储'].every(x=>document.body.innerText.includes(x))}))()''')
            assert frame['bottom'] <= height + 1, frame
            assert frame['scrollWidth'] <= width + 1, frame
            assert frame['navHidden'] and frame['sources'], frame
            checks.append(f'environment recording fits {width}x{height}')
            call('screenshot',dict(format='png',path=str(BUILD/f'environment_{width}.png')))
    finally:
        call('cdp',dict(method='Emulation.clearDeviceMetricsOverride',params={}))
    result=dict(checks=len(checks),passed=checks,failures=[],new_model_calls=0)
    (BUILD/'browser_acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
