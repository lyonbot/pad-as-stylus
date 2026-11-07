const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
function setup({pen=false}={}){
 const listeners={},log=[],ctx={window:{}};
 const surface={addEventListener:(t,f)=>listeners[t]=f,removeEventListener(){}};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/touch-input.js'),'utf8'),ctx);
 const state={pen,running:true};
 const input=ctx.window.createTouchInput({surface,emit:(s,t)=>log.push([t,s.slot,s.clientX,s.clientY]),isRunning:()=>state.running,penActive:()=>state.pen});
 const fire=(type,id,x=0,y=0,pointerType='touch',target={})=>listeners[type]({pointerType,pointerId:id,clientX:x,clientY:y,target,preventDefault(){}});
 return {input,log,fire,state};
}
test('two fingers get distinct slots and reuse freed ones',()=>{
 const h=setup();h.fire('pointerdown',7,1,2);h.fire('pointerdown',9,3,4);h.fire('pointerup',7);h.fire('pointerdown',11);
 assert.deepEqual(h.log.map(e=>[e[0],e[1]]),[['down',0],['down',1],['up',0],['down',0]]);
});
test('pen in range blocks new touches; pen entry cancels active ones',()=>{
 const h=setup({pen:true});h.fire('pointerdown',1);assert.equal(h.log.length,0);
 h.state.pen=false;h.fire('pointerdown',1,5,6);h.fire('pointerdown',2,7,8);h.input.cancelAll();
 assert.deepEqual(h.log.map(e=>e[0]),['down','down','cancel','cancel']);assert.equal(h.input.active,0);
});
test('ignores pen pointers, tool buttons and stopped state',()=>{
 const h=setup();h.fire('pointerdown',1,0,0,'pen');h.fire('pointerdown',2,0,0,'touch',{closest:()=>({})});
 h.state.running=false;h.fire('pointerdown',3);assert.equal(h.log.length,0);
});
