window.createPenTrail = canvas => {
 const ctx=canvas.getContext('2d'),lifetime=1500;
 let previous=null,segments=[],frame=null;
 function render(now){
  frame=null;const r=canvas.getBoundingClientRect();ctx.clearRect(0,0,r.width,r.height);
  segments=segments.filter(s=>now-s.time<lifetime);
  ctx.lineCap='round';ctx.lineJoin='round';
  for(const s of segments){
   const age=Math.max(0,(now-s.time)/lifetime);
   ctx.globalAlpha=(1-age)**2;ctx.strokeStyle=s.contact?'#91edce':'#69baff';ctx.fillStyle=ctx.strokeStyle;
   ctx.lineWidth=s.width;ctx.setLineDash(s.contact?[]:[5,5]);ctx.beginPath();
   if(s.from){ctx.moveTo(s.from.x,s.from.y);ctx.lineTo(s.x,s.y);ctx.stroke();}
   else{ctx.arc(s.x,s.y,s.width/2,0,Math.PI*2);ctx.fill();}
  }
  ctx.globalAlpha=1;
  if(segments.length)frame=requestAnimationFrame(render);else previous=null;
 }
 function fit(){
  const r=canvas.getBoundingClientRect(),dpr=window.devicePixelRatio||1;
  canvas.width=Math.round(r.width*dpr);canvas.height=Math.round(r.height*dpr);
  ctx.setTransform(dpr,0,0,dpr,0,0);segments=[];previous=null;
 }
 new ResizeObserver(fit).observe(canvas);fit();
 return {
  clear(){segments=[];previous=null;ctx.clearRect(0,0,canvas.width,canvas.height);if(frame!==null)cancelAnimationFrame(frame);frame=null;},
  break(){previous=null;},
  add(e,type){
   if(['enter','leave','cancel','up'].includes(type)){previous=null;return;}
   const r=canvas.getBoundingClientRect(),p={x:e.clientX-r.left,y:e.clientY-r.top,
    contact:type==='down'||(type==='move'&&!!(e.buttons&1))};
   if(type==='down')previous=null;
   segments.push({...p,time:performance.now(),width:p.contact?2+Math.max(0,e.pressure||0)*5:1.5,
    from:previous?.contact===p.contact?previous:null});previous=p;
   if(frame===null)frame=requestAnimationFrame(render);
  }
 };
};
