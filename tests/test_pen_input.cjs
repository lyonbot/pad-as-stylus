const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

function setup({captureThrows=false}={}){
 const listeners=new Map(),events=[];
 const source={addEventListener(type,fn){listeners.set(type,fn)},removeEventListener(type){listeners.delete(type)}};
 const surface={contains(node){return node===surface},setPointerCapture(){if(captureThrows)throw Error('NotFoundError')}};
 const context={window:{},document:source};vm.createContext(context);
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/pen-input.js'),'utf8'),context);
 let running=true;
 const input=context.window.createPenInput({surface,source,isRunning:()=>running,emit:(event,type)=>events.push({...event,type})});
 function fire(type,extra={}){const event={type,pointerType:'pen',pointerId:1,buttons:0,pressure:0,clientX:10,clientY:20,relatedTarget:null,preventDefault(){},...extra};listeners.get(type)?.(event);}
 return {input,events,fire,surface,pause(){running=false},resume(){running=true}};
}
const types=h=>h.events.map(e=>e.type);

test('over/enter opens hover once, then movement is sent before any down',()=>{
 const h=setup();h.fire('pointerover');h.fire('pointerenter');h.fire('pointermove',{clientX:100});
 assert.deepEqual(types(h),['enter','move']);assert.equal(h.events[1].clientX,100);
});
test('failed capture cannot block down, a new hover ID releases old contact',()=>{
 const h=setup({captureThrows:true});h.fire('pointerdown',{buttons:1});
 h.fire('pointerover',{pointerId:2});h.fire('pointerenter',{pointerId:2});h.fire('pointermove',{pointerId:2});
 assert.deepEqual(types(h),['enter','down','cancel','enter','move']);assert.equal(h.input.state.contact,null);
 assert.equal(h.input.diagnostics.captureErrors,1);
});
test('hover with a new ID recovers even if enter and up were missed',()=>{
 const h=setup();h.fire('pointerdown',{buttons:1});h.fire('pointermove',{pointerId:2});
 assert.deepEqual(types(h),['enter','down','up','enter','move']);
});
test('up keeps proximity, normal lost capture does not cancel hover',()=>{
 const h=setup();h.fire('pointerdown',{buttons:1});h.fire('pointerup');h.fire('lostpointercapture');h.fire('pointermove');
 assert.deepEqual(types(h),['enter','down','up','move']);
});
test('internal out ignored, real out and leave close range once',()=>{
 const h=setup();h.fire('pointerenter');h.fire('pointerout',{relatedTarget:h.surface});
 h.fire('pointerout');h.fire('pointerleave');assert.deepEqual(types(h),['enter','leave']);
});
test('cancel blocks stray moves until next over/enter',()=>{
 const h=setup();h.fire('pointerdown',{buttons:1});h.fire('pointercancel');h.fire('pointermove');
 h.fire('pointerover');h.fire('pointermove');
 assert.deepEqual(types(h),['enter','down','cancel','enter','move']);
});
test('late leave from an old pointer cannot release the current stroke',()=>{
 const h=setup();h.fire('pointerenter',{pointerId:1});h.fire('pointerdown',{pointerId:2,buttons:1});
 h.fire('pointerleave',{pointerId:1});
 assert.equal(h.input.state.contact,2);assert.deepEqual(types(h),['enter','enter','down']);
});
test('coalesced samples inherit parent pen type, buttons, tilt and pressure',()=>{
 const h=setup();h.fire('pointerenter');h.fire('pointermove',{getCoalescedEvents:()=>[{clientX:40,clientY:50}]});
 assert.equal(h.events[1].pointerType,'pen');assert.equal(h.events[1].buttons,0);assert.equal(h.events[1].clientX,40);
});
test('finger input ignored and reset allows a clean new session',()=>{
 const h=setup();h.fire('pointerdown',{pointerType:'touch',buttons:1});assert.deepEqual(types(h),[]);
 h.fire('pointerdown',{buttons:1});h.pause();h.input.reset();h.fire('pointermove');h.resume();h.fire('pointermove',{pointerId:3});
 assert.deepEqual(types(h),['enter','down','enter','move']);
});
test('hover diagnostics survive a long contact stroke',()=>{
 const h=setup();h.fire('pointermove');h.fire('pointerdown',{buttons:1});for(let i=0;i<400;i++)h.fire('pointermove',{buttons:1});
 assert.equal(h.input.diagnostics.counts['pointermove:hover'],1);assert.equal(h.input.diagnostics.hover.length,1);
});
test('barrel button down/drag/up and chord transitions reach the native mapper',()=>{
 const h=setup();h.fire('pointerdown',{buttons:2});h.fire('pointermove',{buttons:2});
 h.fire('pointermove',{buttons:3});h.fire('pointermove',{buttons:2});h.fire('pointerup',{buttons:0});
 assert.deepEqual(types(h),['enter','down','move','move','move','up']);
 assert.deepEqual(h.events.map(e=>e.buttons),[2,2,2,3,2,0]);
});
