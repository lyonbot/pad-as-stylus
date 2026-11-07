// Finger input: reports raw contacts only. Gesture recognition lives in the Mac bridge.
// Fingers are ignored while the pen is in range so a resting palm cannot scroll.
window.createTouchInput = ({surface, emit, isRunning, penActive}) => {
 const slots=new Map(), last=new Map(), handlers=[];
 const MAX_SLOTS=10;
 const sample=(e,slot)=>({clientX:e.clientX,clientY:e.clientY,slot});
 const slotFor=()=>{const used=new Set(slots.values());for(let i=0;i<MAX_SLOTS;i++)if(!used.has(i))return i;return -1;};
 const eligible=e=>e.pointerType==='touch'&&!e.target?.closest?.('[data-no-pen-input]');
 function listen(type,fn){surface.addEventListener(type,fn);handlers.push([type,fn]);}
 listen('pointerdown',e=>{
  if(!eligible(e)||!isRunning()||penActive()||slots.has(e.pointerId))return;
  const slot=slotFor();if(slot<0)return;
  e.preventDefault();slots.set(e.pointerId,slot);
  const s=sample(e,slot);last.set(e.pointerId,s);emit(s,'down');
 });
 listen('pointermove',e=>{
  if(e.pointerType!=='touch'||!slots.has(e.pointerId)||!isRunning())return;
  const s=sample(e,slots.get(e.pointerId));last.set(e.pointerId,s);emit(s,'move');
 });
 const finish=type=>e=>{
  if(e.pointerType!=='touch'||!slots.has(e.pointerId))return;
  emit(sample(e,slots.get(e.pointerId)),type);slots.delete(e.pointerId);last.delete(e.pointerId);
 };
 listen('pointerup',finish('up'));
 listen('pointercancel',finish('cancel'));
 function cancelAll(){for(const id of slots.keys())emit(last.get(id),'cancel');slots.clear();last.clear();}
 function reset(){slots.clear();last.clear();}
 return {cancelAll,reset,get active(){return slots.size},
  destroy(){for(const [type,fn] of handlers)surface.removeEventListener(type,fn);reset();}};
};
