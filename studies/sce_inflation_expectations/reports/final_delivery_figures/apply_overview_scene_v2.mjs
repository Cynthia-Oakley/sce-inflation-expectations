// Each content box owns all of its rich-text paragraphs. No text overlays.
export function applyOverviewSceneV2(presentation,scene) {
  presentation.slides.keep([]);
  presentation.theme.defaultFont=scene.latin_font;
  const slide=presentation.slides.add({width:scene.width,height:scene.height,background:{fill:'#FFFFFF'}});
  for(const a of scene.arrows) {
    for(let i=1;i<a.points.length;i++) {
      const [x1,y1]=a.points[i-1], [x2,y2]=a.points[i];
      slide.shapes.add({geometry:'connector',kind:'straight',name:`${a.name}-${i}`,
        position:{left:Math.min(x1,x2),top:Math.min(y1,y2),width:Math.abs(x2-x1),height:Math.abs(y2-y1),horizontalFlip:x2<x1,verticalFlip:y2<y1},
        line:{fill:a.color,width:a.width,style:'solid'},
        ...(i===a.points.length-1?{tail:{type:'triangle',width:'med',length:'med'}}:{})});
    }
  }
  for(const b of scene.boxes) {
    const shape=slide.shapes.add({geometry:'rect',name:b.name,
      position:{left:b.x,top:b.y,width:b.w,height:b.h},fill:b.fill,
      line:{fill:b.stroke,width:b.stroke==='none'?0:1.4,style:'solid'}});
    shape.text.style={typeface:scene.chinese_font,fontSize:27,color:'#172A3A',
      alignment:'left',verticalAlignment:'top',autoFit:'none',wrap:'square',insets:b.inset};
    shape.text=b.paragraphs.map(p=>({spaceBefore:0,spaceAfter:p.after,
      runs:p.runs.map(r=>({run:r.text,style:{fontSize:`${p.size}px`,typeface:r.font,bold:r.bold,color:p.color}}))}));
  }
  slide.speakerNotes.text=scene.notes;
  return slide;
}
