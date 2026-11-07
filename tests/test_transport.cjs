const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
function setup(){
 let now=0,id=0;const timers=new Map(),sockets=[],states=[];
 class Socket{constructor(){this.sent=[];this.bufferedAmount=0;sockets.push(this)}send(data){this.sent.push(data)}close(){this.closed=true}}
 const ctx={window:{},WebSocket:Socket,ArrayBuffer,DataView,setInterval:()=>++id,clearInterval(){},setTimeout(fn,delay){const key=++id;timers.set(key,{fn,time:now+delay});return key},clearTimeout(key){timers.delete(key)}};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/transport.js'),'utf8'),ctx);
 const transport=new ctx.window.PenTransport({url:()=> 'ws://test/ws',ratio:()=>1.6,onState:state=>states.push(state),clock:()=>now});
 function ready(socket=sockets.at(-1)){socket.onopen();socket.onmessage({data:JSON.stringify({type:'ready',version:1})});}
 function advance(ms){const end=now+ms;while(true){const next=[...timers].filter(([,v])=>v.time<=end).sort((a,b)=>a[1].time-b[1].time)[0];if(!next)break;now=next[1].time;timers.delete(next[0]);next[1].fn()}now=end;}
 return {transport,sockets,states,ready,advance,ctx};
}
const event=type=>({type,x:.25,y:.5,pressure:.7,buttons:type==='up'?0:1});
test('ordered binary batch retains down and up',()=>{
 const h=setup();h.transport.start();h.ready();h.transport.send(event('down'));h.transport.send(event('move'));h.transport.send(event('up'));h.transport.flush();
 const data=h.sockets[0].sent.at(-1),v=new DataView(data);assert.equal(data.byteLength,44);assert.equal(v.getUint16(2),3);assert.deepEqual([v.getUint8(8),v.getUint8(20),v.getUint8(32)],[2,3,4]);
});
test('disconnect automatically reconnects and discards old queued input',()=>{
 const h=setup();h.transport.start();h.ready();const old=h.sockets[0];h.transport.send(event('down'));old.onclose({code:1006});
 assert.equal(h.transport.queue.length,0);h.advance(250);assert.equal(h.sockets.length,2);h.ready();assert.equal(h.transport.ready,true);
 assert.equal(h.sockets[1].sent.length,1);assert.equal(typeof h.sockets[1].sent[0],'string');
 old.onmessage({data:'late garbage'});assert.equal(h.transport.ready,true);
});
test('missing ACK triggers reconnection without waiting for TCP close',()=>{
 const h=setup();h.transport.start();h.ready();h.transport.send(event('down'));h.transport.flush();h.advance(1201);h.transport.tick();
 assert.equal(h.transport.ready,false);assert.equal(h.sockets[0].closed,true);h.advance(250);assert.equal(h.sockets.length,2);
});
test('explicit stop never reconnects',()=>{
 const h=setup();h.transport.start();h.ready();const old=h.sockets[0];h.transport.stop();old.onclose({code:1006});h.advance(10000);assert.equal(h.sockets.length,1);
});
test('replaced session does not fight the other page by reconnecting',()=>{
 const h=setup();h.transport.start();h.ready();h.sockets[0].onclose({code:4001});h.advance(10000);assert.equal(h.sockets.length,1);assert.equal(h.transport.running,false);
});
test('backpressure disconnects instead of replaying stale strokes',()=>{
 const h=setup();h.transport.start();h.ready();h.sockets[0].bufferedAmount=40000;h.transport.send(event('down'));h.transport.flush();assert.equal(h.transport.ready,false);assert.equal(h.transport.queue.length,0);
});
