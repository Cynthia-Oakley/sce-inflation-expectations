"""Check the local preview through the existing task's browser bridge."""
from pathlib import Path
import json
import urllib.request

ROOT=Path(__file__).resolve().parents[4];BUILD=ROOT/'tmp/video_complete_v03'


def call(action,args=None):
    payload=json.dumps(dict(action=action,args=args or {},session='sce-video-samples')).encode()
    req=urllib.request.Request('http://127.0.0.1:10086/command',data=payload,headers={'Content-Type':'application/json'})
    r=json.loads(urllib.request.urlopen(req,timeout=30).read())
    assert r['ok'],r
    return r['data']


def js(code):return call('evaluate',dict(code=code))['value']


def main():
    url=(ROOT/'deliverables/video/v03/index.html').as_uri()
    call('navigate',dict(url=url))
    call('cdp',dict(method='Emulation.setDeviceMetricsOverride',params=dict(width=1920,height=1080,deviceScaleFactor=1,mobile=False)))
    result=js('''(async()=>{
      const checks=[],assert=(v,n)=>{if(!v)throw Error(n);checks.push(n)},$=s=>document.querySelector(s);
      const story=JSON.parse($('#story').textContent);assert(story.slides.length===9,'nine pages');
      let seen=0;
      for(let page=1;page<=9;page++){
        $('[data-index="'+(page-1)+'"]').click();
        await new Promise(resolve=>{const img=$('#slide');if(img.complete&&img.naturalWidth)resolve();else img.onload=resolve});
        assert($('#counter').textContent===page+' / 9','counter '+page);
        assert($('#speech').textContent===story.slides[page-1].narration,'narration '+page);
        assert($('#slide').naturalWidth===1920&&$('#slide').naturalHeight===1080,'image '+page);
        if([2,4,5].includes(page))assert($('#interaction a').href.includes('#page='+page+'&sample=A01'),'interactive link '+page);
        else assert($('#interaction a')===null,'static page '+page);
        $('#present').click();
        const r=$('#slide').getBoundingClientRect();
        assert(getComputedStyle($('.notes')).display==='none','notes hidden '+page);
        assert(r.width<=innerWidth+.1&&r.height<=innerHeight+.1,'screen fits '+page);
        document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));seen++;
      }
      $('[data-index="0"]').click();
      document.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));
      assert($('#counter').textContent==='2 / 9','keyboard navigation');
      $('[data-index="0"]').click();
      return {checks:checks.length,checked_pages:seen,failures:[],file_url:location.protocol==='file:'};
    })()''')
    call('screenshot',dict(format='png',path=str(BUILD/'preview_page01.png')))
    js("document.querySelector('[data-index=\"8\"]').click();document.querySelector('#present').click();true")
    call('screenshot',dict(format='png',path=str(BUILD/'recording_page09.png')))
    js("document.querySelector('#exit').click();document.querySelector('[data-index=\"0\"]').click();true")
    call('cdp',dict(method='Emulation.clearDeviceMetricsOverride',params={}))
    (BUILD/'browser_acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
