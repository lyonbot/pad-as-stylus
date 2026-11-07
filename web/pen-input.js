// Pen-only input lifecycle. Hover is independent of a previous contact's ID.
// Bind directly to the concrete fullscreen input surface.
window.createPenInput = ({surface, source = surface, emit, isRunning, onBoundary = () => {}}) => {
 let inRange=false, pointerId=null, contact=null, blocked=false, last=null;
 const handlers=[];
 const diagnostics={counts:{},hover:[],captureErrors:0};
 function sample(e,parent=e){return {pointerType:'pen',pointerId:parent.pointerId,
  clientX:e.clientX,clientY:e.clientY,pressure:e.pressure??parent.pressure??0,
  buttons:e.buttons??parent.buttons??0,tiltX:e.tiltX??parent.tiltX??0,tiltY:e.tiltY??parent.tiltY??0};}
 function send(e,type){last=sample(e);emit(last,type);}
 function reset(){inRange=false;pointerId=null;contact=null;blocked=false;last=null;}
 function enter(e){
  if(pointerId!==null&&pointerId!==e.pointerId&&contact!==null){emit(last||sample(e),'cancel');contact=null;}
  if(!inRange||pointerId!==e.pointerId||blocked){
   inRange=true;pointerId=e.pointerId;blocked=false;send(e,'enter');
  }
 }
 function boundary(e){
  if(e.pointerId!==pointerId&&e.pointerId!==contact)return;
  if(e.relatedTarget&&surface.contains(e.relatedTarget))return;
  if(!inRange&&contact===null)return;
  if(contact!==null){emit(last||sample(e),'up');contact=null;}
  send(e,'leave');inRange=false;pointerId=null;onBoundary();
 }
 function listen(type,fn){
  const handler=e=>{
   if(e.pointerType!=='pen')return;
   if(e.target?.closest?.('[data-no-pen-input]'))return;
   const key=type+':'+(!(e.buttons&1)?'hover':'contact');
   diagnostics.counts[key]=(diagnostics.counts[key]||0)+1;
   if(type==='pointermove'&&!(e.buttons&1)){diagnostics.hover.push({x:e.clientX,y:e.clientY,id:e.pointerId});if(diagnostics.hover.length>20)diagnostics.hover.shift();}
   if(isRunning())fn(e);
  };
  source.addEventListener(type,handler);handlers.push([type,handler]);
 }
 listen('pointerover',enter);
 listen('pointerenter',enter);
 listen('pointerdown',e=>{
  if(!(e.buttons&31))return;
  enter(e);
  if(contact!==null)return;
  e.preventDefault();contact=e.pointerId;send(e,'down');
  // Capture is an optimization; failure must never prevent down/up delivery.
  try{surface.setPointerCapture?.(e.pointerId);}catch{diagnostics.captureErrors++;}
  onBoundary();
 });
 listen('pointermove',e=>{
  if(blocked)return;
  if(!(e.buttons&31)){
   if(contact!==null){emit(last||sample(e),'up');contact=null;}
   enter(e); // A new hover ID recovers independently of the previous stroke.
  }else if(contact!==e.pointerId){return;}
  const samples=e.getCoalescedEvents?.()||[];
  for(const s of samples.length?samples:[e]){last=sample(s,e);emit(last,'move');}
 });
 listen('pointerup',e=>{
  if(contact!==e.pointerId)return;
  send(e,'up');contact=null;onBoundary();
 });
 function cancel(e){
  if(pointerId!==e.pointerId&&contact!==e.pointerId)return;
  emit(last||sample(e),'cancel');contact=null;inRange=false;pointerId=null;blocked=true;onBoundary();
 }
 listen('pointercancel',cancel);
 listen('lostpointercapture',e=>{if(contact===e.pointerId)cancel(e);});
 listen('pointerout',boundary);
 listen('pointerleave',boundary);
 return {reset,diagnostics,get state(){return {inRange,pointerId,contact,blocked}},
  destroy(){for(const [type,handler] of handlers)source.removeEventListener(type,handler);reset();}};
};
