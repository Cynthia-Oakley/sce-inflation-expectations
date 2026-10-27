// Native editable method diagram. Each text region owns its paragraphs.
export function applyOverviewSceneV3(presentation, scene) {
  presentation.slides.keep([]);
  presentation.theme.defaultFont=scene.latin_font;
  const slide=presentation.slides.add({width:scene.width,height:scene.height,background:{fill:'#FFFFFF'}});
  for(const b of scene.boxes) {
    const shape=slide.shapes.add({geometry:'rect',name:b.name,
      position:{left:b.x,top:b.y,width:b.w,height:b.h},fill:b.fill,
      line:{fill:b.stroke,width:b.stroke==='none'?0:1.1,style:'solid'}});
    shape.text.style={typeface:scene.chinese_font,fontSize:28,color:'#203447',alignment:'left',
      verticalAlignment:'top',autoFit:'none',wrap:'square',insets:b.inset};
    shape.text=b.paragraphs.map(p=>({spaceBefore:0,spaceAfter:Math.round(p.after),runs:p.runs.map(r=>({run:r.text,
      style:{fontSize:`${p.size}px`,typeface:r.font,bold:r.bold,color:p.color}}))}));
  }
  function path(name, points, color, width, dashed=false) {
    const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);
    const x=Math.min(...xs),y=Math.min(...ys),w=Math.max(...xs)-x,h=Math.max(...ys)-y;
    const commands=points.map(([px,py],i)=>i?{lineTo:{x:px-x,y:py-y}}:{moveTo:{x:px-x,y:py-y}});
    return slide.shapes.add({geometry:'custom',name,position:{left:x,top:y,width:Math.max(w,.1),height:Math.max(h,.1)},
      fill:'none',line:{fill:color,width,style:dashed?'dash':'solid'},
      customPaths:[{width:Math.max(w,.1),height:Math.max(h,.1),commands}]});
  }
  for(const a of scene.arrows) {
    for(let i=1;i<a.points.length;i++) {
      const [x1,y1]=a.points[i-1],[x2,y2]=a.points[i];
      slide.shapes.add({geometry:'connector',kind:'straight',name:`${a.name}-${i}`,
        position:{left:Math.min(x1,x2),top:Math.min(y1,y2),width:Math.abs(x2-x1),height:Math.abs(y2-y1),horizontalFlip:x2<x1,verticalFlip:y2<y1},
        line:{fill:a.color,width:a.width,style:'solid'},...(i===a.points.length-1?{tail:{type:'triangle',width:'med',length:'med'}}:{})});
    }
  }
  for(const g of scene.graphics) {
    if(g.kind==='path')path(g.name,g.points,g.color,g.width,g.dashed);
    else slide.shapes.add({geometry:'rect',name:g.name,position:{left:g.x,top:g.y,width:g.w,height:g.h},fill:g.fill,line:{fill:'none',width:0}});
  }
  slide.speakerNotes.text=scene.notes;
  return slide;
}
