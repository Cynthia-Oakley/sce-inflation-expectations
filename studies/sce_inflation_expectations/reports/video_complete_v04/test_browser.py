"""Check the local v04 preview and links after the author's page reorder."""
from pathlib import Path
import json
import urllib.request

ROOT=Path(__file__).resolve().parents[4];BUILD=ROOT/'tmp/video_complete_v04'


def call(action,args=None):
    body=json.dumps(dict(action=action,args=args or {},session='sce-video-samples')).encode()
    req=urllib.request.Request('http://127.0.0.1:10086/command',data=body,headers={'Content-Type':'application/json'})
    r=json.loads(urllib.request.urlopen(req,timeout=30).read());assert r['ok'],r
    return r['data']


def js(code):return call('evaluate',dict(code=code))['value']


def main():
    call('navigate',dict(url=(ROOT/'deliverables/video/v04/index.html').as_uri()+'#page=9'))
    call('cdp',dict(method='Emulation.setDeviceMetricsOverride',params=dict(width=1920,height=1080,deviceScaleFactor=1,mobile=False)))
    result=js('''(async()=>{
      const $=s=>document.querySelector(s),d=JSON.parse($('#story').textContent),checks=[];
      const assert=(v,n)=>{if(!v)throw Error(n);checks.push(n)};
      assert($('#counter').textContent==='9 / 9','starts at requested slide 9');
      for(let page=1;page<=9;page++){
        $('[data-index="'+(page-1)+'"]').click();
        await new Promise(r=>{let im=$('#slide');if(im.complete&&im.naturalWidth)r();else im.onload=r});
        assert($('#speech').textContent===d.slides[page-1].narration,'narration '+page);
        assert($('#slide').naturalWidth===1920,'image '+page);
        if(d.interactive_pages[String(page)])assert($('#interaction a').href.includes('#page='+d.interactive_pages[String(page)]+'&sample=A01'),'semantic interactive link '+page);
      }
      $('#present').click();let box=$('#slide').getBoundingClientRect();
      assert(box.width<=innerWidth+.1&&box.height<=innerHeight+.1,'slide 9 fits recording frame');
      assert(getComputedStyle($('.notes')).display==='none','narration off recording frame');
      return {checks:checks.length,failures:[],file_url:location.protocol==='file:'};
    })()''')
    call('screenshot',dict(format='png',path=str(BUILD/'recording_page9.png')))
    js("document.querySelector('#exit').click();true")
    call('cdp',dict(method='Emulation.clearDeviceMetricsOverride',params={}))
    (BUILD/'browser_acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
