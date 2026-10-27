// Shared, editable geometry for the live presentation and local PPTX mirror.
// Call only inside a fresh artifactSession.run presentation callback.
export function applyOverviewScene(presentation, scene) {
  presentation.slides.keep([]);
  presentation.theme.defaultFont = scene.font;
  const slide = presentation.slides.add({
    width: scene.width, height: scene.height, background: { fill: '#FFFFFF' },
  });
  for (const e of scene.items) {
    if (e.kind === 'rect') {
      slide.shapes.add({
        geometry: 'rect', name: e.name,
        position: { left:e.x, top:e.y, width:e.w, height:e.h },
        fill:e.fill,
        line:{fill:e.stroke,width:e.stroke==='none'?0:e.width,style:e.dash?'dashed':'solid'},
      });
    } else if (e.kind === 'text') {
      const shape = slide.shapes.add({
        geometry:'textbox',name:e.name,
        position:{left:e.x,top:e.y,width:e.w,height:e.h},
        fill:'none',line:{fill:'none',width:0},
      });
      shape.text=e.text;
      shape.text.style={typeface:e.font,fontSize:e.size,bold:e.bold,color:e.fill,
        alignment:e.align,verticalAlignment:'top',autoFit:'none',wrap:'none',insets:0};
    } else {
      for(let i=1;i<e.points.length;i++) {
        const [x1,y1]=e.points[i-1]; const [x2,y2]=e.points[i];
        const final=e.arrow && i===e.points.length-1;
        slide.shapes.add({
          geometry:'connector',kind:'straight',name:`${e.name}-${i}`,
          position:{left:Math.min(x1,x2),top:Math.min(y1,y2),width:Math.abs(x2-x1),height:Math.abs(y2-y1),
            horizontalFlip:x2<x1,verticalFlip:y2<y1},
          line:{fill:e.stroke,width:e.width,style:e.dash?'dashed':'solid'},
          ...(final?{tail:{type:'triangle',width:'med',length:'med'}}:{}),
        });
      }
    }
  }
  slide.speakerNotes.text=scene.notes;
  return slide;
}
