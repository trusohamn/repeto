document.querySelectorAll('[data-print]').forEach(b=>b.addEventListener('click',()=>window.print()));
const io='IntersectionObserver' in window&&!matchMedia('(prefers-reduced-motion: reduce)').matches?new IntersectionObserver(es=>es.forEach(x=>{if(x.isIntersecting){x.target.classList.add('in');io.unobserve(x.target)}}),{threshold:.12}):null;
document.querySelectorAll('.reveal,section h2').forEach(el=>io?io.observe(el):el.classList.add('in'));
document.querySelectorAll('.cards').forEach(g=>g.querySelectorAll('.card').forEach((c,i)=>{c.style.setProperty('--d',(i%4)*.08+'s');c.style.setProperty('--r',(i%2?3:-3)+'deg');io?io.observe(c):c.classList.add('in')}));
const still=matchMedia('(prefers-reduced-motion: reduce)').matches;
const art=document.querySelector('.hero-art'),phones=art&&art.querySelector('.phones');
const bar=document.querySelector('.progress'),trail=document.querySelector('.trail');
const line=trail&&trail.querySelector('.trail-line'),walker=trail&&trail.querySelector('.traveller');
const len=line?line.getTotalLength():0;if(line){line.style.strokeDasharray=len;line.style.strokeDashoffset=len}
const stops=trail?[...trail.querySelectorAll('.stop')]:[],stepItems=document.querySelectorAll('.steps li');
const tracks=document.querySelectorAll('.marquee span');let lastY=scrollY,skew=0,ticking=false;
const frame=()=>{ticking=false;const y=scrollY,h=document.documentElement.scrollHeight-innerHeight;
 if(bar)bar.style.setProperty('--p',h>0?Math.min(1,y/h):0);
 if(phones&&y<innerHeight){phones.style.setProperty('--py',(-y*.06)+'px');art.style.transform=`translateY(${y*.15}px)`}
 if(line&&trail.offsetParent){const r=trail.parentElement.getBoundingClientRect();
  const p=Math.max(0,Math.min(1,(innerHeight*.75-r.top)/(r.height*.75)));line.style.strokeDashoffset=len*(1-p);
  const pt=line.getPointAtLength(len*p);walker.setAttribute('transform',`translate(${pt.x},${pt.y}) rotate(${Math.sin(p*40)*12})`);
  stops.forEach((s,i)=>{const on=p>=(i*250+125)/1000-.01;s.classList.toggle('on',on);stepItems[i]&&stepItems[i].classList.toggle('lit',on)})}
 skew=Math.max(-14,Math.min(14,(y-lastY)*.4));lastY=y;tracks.forEach(t=>t.style.setProperty('--sk',skew+'deg'));
 clearTimeout(window.__sk);window.__sk=setTimeout(()=>tracks.forEach(t=>t.style.setProperty('--sk','0deg')),120);};
if(!still){addEventListener('scroll',()=>{if(!ticking){ticking=true;requestAnimationFrame(frame)}},{passive:true});frame()}
if(art&&!still){const hero=art.closest('.hero');
 hero.addEventListener('pointermove',ev=>{const r=art.getBoundingClientRect();const dx=(ev.clientX-r.left-r.width/2)/r.width,dy=(ev.clientY-r.top-r.height/2)/r.height;
  phones.style.setProperty('--tilt',Math.max(-8,Math.min(8,dx*14))+'deg');phones.style.setProperty('--px',Math.max(-10,Math.min(10,dx*16))+'px')});
 hero.addEventListener('pointerleave',()=>{phones.style.setProperty('--tilt','0deg');phones.style.setProperty('--px','0px')});
 const glyphs=['♪','♫','♩','♬'],colors=['#e8604a','#f0962f','#2e8f8c','#4a62c4'];
 art.addEventListener('click',()=>{art.classList.add('boost');clearTimeout(art.__b);art.__b=setTimeout(()=>art.classList.remove('boost'),1600);
  for(let i=0;i<10;i++){const n=document.createElementNS('http://www.w3.org/2000/svg','text');const a=Math.random()*Math.PI*2,d=90+Math.random()*90;
   n.textContent=glyphs[i%4];n.setAttribute('x',i%2?74:326);n.setAttribute('y',250);n.setAttribute('font-size',22+Math.random()*16);n.setAttribute('fill',colors[i%4]);n.setAttribute('class','burst');
   n.style.setProperty('--bx',Math.cos(a)*d+'px');n.style.setProperty('--by',Math.sin(a)*d-40+'px');n.style.setProperty('--br',(Math.random()*80-40)+'deg');
   art.appendChild(n);setTimeout(()=>n.remove(),1200)}});}
const listbox=(select,n)=>{const btn=document.createElement('button'),pop=document.createElement('ul');
 btn.type='button';btn.className='pick-btn';btn.setAttribute('aria-haspopup','listbox');btn.setAttribute('aria-expanded','false');
 btn.setAttribute('aria-label',select.getAttribute('aria-label'));pop.className='pick-pop';pop.setAttribute('role','listbox');pop.tabIndex=-1;pop.id=select.id+'-list';
 pop.setAttribute('aria-label',select.getAttribute('aria-label'));btn.setAttribute('aria-controls',pop.id);pop.hidden=true;
 select.hidden=true;select.after(btn,pop);let active=0;
 const items=()=>[...pop.children];
 const mark=i=>{active=(i+items().length)%items().length;items().forEach((li,j)=>li.classList.toggle('active',j===active));
  pop.setAttribute('aria-activedescendant',items()[active].id);items()[active].scrollIntoView({block:'nearest'})};
 const sync=()=>{const o=select.options[select.selectedIndex];btn.textContent=o?o.text:'';if(o&&o.lang)btn.lang=o.lang;else btn.removeAttribute('lang');
  pop.replaceChildren(...[...select.options].map((o,j)=>{const li=document.createElement('li');li.id=`${pop.id}-${j}`;li.setAttribute('role','option');
   li.textContent=o.text;if(o.lang)li.lang=o.lang;li.setAttribute('aria-selected',String(o.selected));
   li.addEventListener('click',()=>choose(j));li.addEventListener('pointermove',()=>mark(j));return li}))};
 const open=()=>{document.querySelectorAll('.pick-pop:not([hidden])').forEach(p=>p!==pop&&p.__close());
  pop.hidden=false;pop.style.left='';const r=pop.getBoundingClientRect();if(r.right>innerWidth-8)pop.style.left=(-8-(r.right-innerWidth+8))+'px';btn.setAttribute('aria-expanded','true');mark(select.selectedIndex);pop.focus()};
 const close=(refocus=true)=>{if(pop.hidden)return;pop.hidden=true;btn.setAttribute('aria-expanded','false');if(refocus)btn.focus()};pop.__close=()=>close(false);
 const choose=j=>{close();if(select.selectedIndex!==j){select.selectedIndex=j;select.dispatchEvent(new Event('change'))}};
 btn.addEventListener('click',()=>pop.hidden?open():close());
 btn.addEventListener('keydown',ev=>{if(['ArrowDown','ArrowUp'].includes(ev.key)){ev.preventDefault();open()}});
 pop.addEventListener('keydown',ev=>{const k=ev.key;
  if(k==='ArrowDown'||k==='ArrowUp'){ev.preventDefault();mark(active+(k==='ArrowDown'?1:-1))}
  else if(k==='Home'||k==='End'){ev.preventDefault();mark(k==='Home'?0:items().length-1)}
  else if(k==='Enter'||k===' '){ev.preventDefault();choose(active)}
  else if(k==='Escape'){ev.preventDefault();close()}
  else if(k==='Tab')close(false);
  else if(k.length===1){const j=items().findIndex((li,x)=>x>active&&li.textContent.toLowerCase().startsWith(k.toLowerCase()));
   const f=j>=0?j:items().findIndex(li=>li.textContent.toLowerCase().startsWith(k.toLowerCase()));if(f>=0)mark(f)}});
 document.addEventListener('pointerdown',ev=>{if(!pop.hidden&&!btn.contains(ev.target)&&!pop.contains(ev.target))close(false)});
 sync();return sync;};
const pickData=document.getElementById('picker-data');
if(pickData){const data=JSON.parse(pickData.textContent),box=pickData.closest('.picker');
 const sp=box.querySelector('#pick-speak'),le=box.querySelector('#pick-learn'),cover=box.querySelector('.pick-cover'),go=box.querySelector('.pick-go');
 const syncSp=listbox(sp),syncLe=listbox(le);
 const show=()=>{const d=data[sp.value],c=d.courses.find(x=>x.target===le.value)||d.courses[0];
  cover.href=go.href=c.href;cover.querySelector('img').src=c.cover;box.querySelector('.meta').textContent=c.meta;
  go.textContent=d.start+' →';syncSp();syncLe();cover.classList.remove('swap');void cover.offsetWidth;cover.classList.add('swap');};
 const fill=()=>{const d=data[sp.value],keep=le.value;box.lang=sp.value;
  box.querySelector('[data-word=speak]').textContent=d.speak;box.querySelector('[data-word=learn]').textContent=d.learn;
  le.replaceChildren(...d.courses.map(c=>new Option(c.name,c.target)));
  if(d.courses.some(c=>c.target===keep))le.value=keep;show();};
 sp.addEventListener('change',fill);le.addEventListener('change',show);
}
