(() => {
 const kinds=['enter','leave','down','move','up','cancel','touch_down','touch_move','touch_up','touch_cancel'];
 function encodePenPacket(events,sequence){
  const data=new ArrayBuffer(8+12*events.length),v=new DataView(data);
  v.setUint8(0,1);v.setUint16(2,events.length);v.setUint32(4,sequence);
  events.forEach((e,i)=>{
   const o=8+12*i;v.setUint8(o,kinds.indexOf(e.type));v.setUint8(o+1,e.buttons||0);
   v.setUint16(o+2,Math.round(e.x*65535));v.setUint16(o+4,Math.round(e.y*65535));
   v.setUint16(o+6,Math.round((e.pressure||0)*65535));
   v.setInt16(o+8,Math.round((e.tiltX||0)*100));v.setInt16(o+10,Math.round((e.tiltY||0)*100));
  });return data;
 }
 class PenTransport {
  constructor({url,ratio,onState,onReset=()=>{},WebSocketClass=WebSocket,clock=()=>performance.now()}){
   Object.assign(this,{url,ratio,onState,onReset,WebSocketClass,clock});
   this.socket=null;this.queue=[];this.pending=new Map();this.ready=false;this.running=false;
   this.retryTimer=null;this.handshakeTimer=null;this.attempt=0;this.sequence=0;this.lastSent=0;
   this.stats={bytes:0,packets:0,samples:0,reconnects:0};this.timer=setInterval(()=>this.tick(),8);
  }
  start(){this.stop();this.running=true;this.attempt=0;this.connect();}
  connect(){
   if(!this.running)return;
   this.onState('connecting',this.attempt?'连接中断，正在自动重连…':'正在连接 Mac…');
   let socket;
   try{socket=new this.WebSocketClass(this.url());}catch{this.scheduleRetry();return;}
   this.socket=socket;socket.binaryType='arraybuffer';
   this.handshakeTimer=setTimeout(()=>{if(this.socket===socket)this.fail();},2000);
   socket.onopen=()=>{if(this.socket===socket)socket.send(JSON.stringify({type:'hello',version:1,ratio:this.ratio()}));};
   socket.onmessage=event=>{
    if(this.socket!==socket)return;
    try{
     if(!this.ready){
      const reply=JSON.parse(event.data);
      if(reply.type!=='ready'||reply.version!==1)throw Error('Invalid handshake');
      clearTimeout(this.handshakeTimer);this.handshakeTimer=null;
      this.ready=true;this.attempt=0;this.sequence=0;this.lastSent=this.clock();
      this.queue=[];this.pending.clear();this.onReset();this.onState('connected','已连接 · 等待手写笔');
     }else{
      if(!(event.data instanceof ArrayBuffer)||event.data.byteLength!==8)throw Error('Invalid ACK');
      const v=new DataView(event.data);
      if(v.getUint8(0)!==1||v.getUint8(1)!==1||v.getUint16(2)!==0)throw Error('Invalid ACK');
      this.pending.delete(v.getUint32(4));
     }
    }catch{this.fail();}
   };
   socket.onclose=event=>{
    if(this.socket!==socket)return;
    this.socket=null;this.clearInput();clearTimeout(this.handshakeTimer);this.handshakeTimer=null;
    if(event.code===4001||event.code===1008){
     this.running=false;this.onState('stopped',event.code===4001?'输入已被另一页面接管，请点击重新开始。':'输入协议错误，请刷新页面。');
    }else this.scheduleRetry();
   };
   socket.onerror=()=>{if(this.socket===socket)this.fail();};
  }
  clearInput(){this.ready=false;this.queue=[];this.pending.clear();this.onReset();}
  fail(){
   const socket=this.socket;this.socket=null;clearTimeout(this.handshakeTimer);this.handshakeTimer=null;
   this.clearInput();if(socket)socket.close();this.scheduleRetry();
  }
  scheduleRetry(){
   if(!this.running||this.retryTimer)return;
   const delay=Math.min(5000,250*2**Math.min(this.attempt++,5));this.stats.reconnects++;
   this.onState('reconnecting','连接中断，正在自动重连…');
   this.retryTimer=setTimeout(()=>{this.retryTimer=null;this.connect();},delay);
  }
  send(event){
   if(!this.ready)return;
   if(this.queue.length>32&&event.type==='move'&&this.queue.at(-1)?.type==='move')this.queue[this.queue.length-1]=event;
   else this.queue.push(event);
   if(this.queue.length>512)this.fail();
  }
  flush(){
   if(!this.ready||!this.socket)return;
   const now=this.clock();if(!this.queue.length&&now-this.lastSent<400)return;
   if(this.socket.bufferedAmount>32768){this.fail();return;}
   if(this.sequence>0xffffffff){this.fail();return;}
   const events=this.queue.splice(0,256),seq=this.sequence++,packet=encodePenPacket(events,seq);
   try{
    this.socket.send(packet);this.pending.set(seq,now);this.lastSent=now;
    this.stats.bytes+=packet.byteLength;this.stats.packets++;this.stats.samples+=events.length;
   }catch{this.fail();}
  }
  tick(){
   if(!this.ready)return;
   const oldest=this.pending.values().next();
   if(!oldest.done&&this.clock()-oldest.value>1200){this.fail();return;}
   this.flush();
  }
  stop(){
   this.running=false;clearTimeout(this.retryTimer);clearTimeout(this.handshakeTimer);
   this.retryTimer=null;this.handshakeTimer=null;
   const socket=this.socket;this.socket=null;this.clearInput();if(socket)socket.close();
  }
  destroy(){this.stop();clearInterval(this.timer);}
 }
 window.encodePenPacket=encodePenPacket;window.PenTransport=PenTransport;
})();
