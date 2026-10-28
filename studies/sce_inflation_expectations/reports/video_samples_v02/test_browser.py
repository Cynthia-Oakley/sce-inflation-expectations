"""Visual and behavioral checks through the existing local browser bridge."""
import json
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parents[4]
BUILD=ROOT/'tmp/video_samples_v02'

def call(action,args=None):
    payload=json.dumps(dict(action=action,args=args or {},session='sce-video-samples')).encode()
    req=urllib.request.Request('http://127.0.0.1:10086/command',data=payload,headers={'Content-Type':'application/json'})
    value=json.loads(urllib.request.urlopen(req,timeout=30).read())
    assert value['ok'],value
    return value['data']

def js(code):return call('evaluate',dict(code=code))['value']

call('navigate',dict(url='http://127.0.0.1:8765/index.html'))
call('cdp',dict(method='Emulation.setDeviceMetricsOverride',params=dict(width=1920,height=1080,deviceScaleFactor=1,mobile=False)))
result=js("""(()=>{
const t=[],a=window.SCE_DEMO,$=s=>document.querySelector(s),assert=(v,n)=>{if(!v)throw Error(n);t.push(n)};
window.__demoErrors=[];window.addEventListener('error',e=>window.__demoErrors.push(e.message));
assert(a.data.samples.length===24,'24 paired records loaded');
for(const s of a.data.samples){
 a.state.sample=s.id;a.render();
 assert($('#input-stamp').textContent.startsWith(s.id),'input ID '+s.id);
 assert(Math.abs(parseFloat($('#q8').textContent)-s.q8)<1e-9,'Q8 paired '+s.id);
 assert($('#reason').textContent.includes(s.response.reason),'reason paired '+s.id);
 assert(s.news.every(n=>Date.parse(n.published_at)<=Date.parse(s.cutoff)),'news before cutoff '+s.id);
 assert(Date.parse(s.food_published)<=Date.parse(s.cutoff),'food before cutoff '+s.id);
 assert(a.data.samples.find(x=>x.id===a.state.compare).month===s.month,'comparison same month '+s.id);
}
$('#home').click();
for(const part of ['profile','belief','environment','questions','format']){
 document.querySelector('[data-section="'+part+'"]').click();
 assert($('#prompt-view').textContent.includes(a.current().sections[part][0]),'verbatim section '+part);
}
$('#raw').click();assert($('#detail').open,'raw dialog opens');assert($('#dialog-body').textContent===a.current().response_raw,'raw response unchanged');$('#close-dialog').click();
$('#fullprompt').click();assert($('#dialog-body').textContent.includes(a.current().messages[0].content),'full prompt unchanged');$('#close-dialog').click();
let previous=a.state.sample;$('#random').click();assert(a.state.sample!==previous,'random switches paired sample');$('#home').click();assert(a.state.sample==='A01','restore A01');
for(const view of ['news','food','time']){document.querySelector('[data-compare="'+view+'"]').click();assert($('#compare-left').textContent.includes('A01'),'compare left '+view);assert($('#compare-right').textContent.includes('A02'),'compare right '+view);}
for(const month of ['202206','202506','202106']){$('#month').value=month;$('#month').dispatchEvent(new Event('change'));assert(a.current().month===month,'month filter '+month);}
$('#home').click();
for(const step of ['1','2','3','all']){document.querySelector('[data-step="'+step+'"]').click();assert(a.state.step===step,'calculation step '+step);}
$('#normal').click();assert($('#dialog-body').textContent.includes('1297'),'actual population 1297');$('#close-dialog').click();
for(const [month,m]of Object.entries(a.data.months)){let c=0,med=null;for(const atom of m.atoms){c+=atom.mass;if(c>=.5&&med===null)med=atom.x;}assert(Math.abs(med-m.median)<1e-10,'weighted median '+month);assert(Math.abs(c-1)<1e-10,'population mass '+month);}
assert(window.__demoErrors.length===0,'no client errors');
$('#home').click();document.querySelector('[data-section="profile"]').click();document.querySelector('[data-compare="news"]').click();a.showPage('2');
return {checks:t.length,failures:[],sample:'A01',title:document.title,document_width:document.documentElement.scrollWidth,viewport_width:innerWidth};
})()""")
shots=[]
for page,mode in [('2',None),('4','news'),('4','food'),('4','time'),('5',None)]:
    js(f"(()=>{{window.SCE_DEMO.showPage('{page}');"+(f"document.querySelector('[data-compare=\"{mode}\"]').click();" if mode else '')+"return true})()")
    filename=f'html_page{page}_{mode or "main"}_1920.png'
    shots.append(call('screenshot',dict(format='png',path=str(BUILD/filename))))
js("document.getElementById('recording').click();window.SCE_DEMO.showPage('2');true")
result['recording_layout']=js("JSON.stringify({height:document.documentElement.scrollHeight,viewport:innerHeight,width:document.documentElement.scrollWidth,viewWidth:innerWidth})")
shots.append(call('screenshot',dict(format='png',path=str(BUILD/'html_recording_1920.png'))))
result['recording_pages']={}
for page in ['2','4','5']:
    js(f"window.SCE_DEMO.showPage('{page}');true")
    result['recording_pages'][page]=js("JSON.stringify({height:document.documentElement.scrollHeight,viewport:innerHeight,width:document.documentElement.scrollWidth,viewWidth:innerWidth})")
    shots.append(call('screenshot',dict(format='png',path=str(BUILD/f'html_recording_page{page}.png'))))
call('cdp',dict(method='Emulation.setDeviceMetricsOverride',params=dict(width=1440,height=900,deviceScaleFactor=1,mobile=False)))
result['desktop_1440']=js("JSON.stringify({width:document.documentElement.scrollWidth,viewWidth:innerWidth})")
call('cdp',dict(method='Emulation.setDeviceMetricsOverride',params=dict(width=390,height=844,deviceScaleFactor=1,mobile=True)))
result['mobile_390']=js("JSON.stringify({width:document.documentElement.scrollWidth,viewWidth:innerWidth})")
shots.append(call('screenshot',dict(format='png',path=str(BUILD/'html_mobile_390.png'))))
call('cdp',dict(method='Emulation.setDeviceMetricsOverride',params=dict(width=1920,height=1080,deviceScaleFactor=1,mobile=False)))
js("document.body.classList.remove('recording');window.SCE_DEMO.state.recording=false;document.getElementById('recording').textContent='演示模式';window.SCE_DEMO.showPage('2');true")
result['screenshots']=shots
(BUILD/'browser_acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in result.items() if k!='screenshots'},ensure_ascii=False))
