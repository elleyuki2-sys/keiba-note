const KEY="keiba-note-records-v1";
let editId=null, periodMode="month", calendarDate=new Date();

function toNumber(v){
  if(typeof v==="number") return Number.isFinite(v)?v:0;
  if(v===null||v===undefined||v==="") return 0;
  const n=Number(String(v).replace(/,/g,""));
  return Number.isFinite(n)?n:0;
}
function normalizeRecord(r,i){
  return {
    id: r&&r.id!=null ? r.id : Date.now()+i,
    date: typeof r?.date==="string" && r.date ? r.date.slice(0,10) : "",
    course: typeof r?.course==="string" && r.course ? r.course : "その他",
    race: toNumber(r?.race),
    type: typeof r?.type==="string" && r.type.trim() && r.type!=="undefined" ? r.type : "その他",
    inv: toNumber(r?.inv),
    ret: toNumber(r?.ret),
    memo: typeof r?.memo==="string" ? r.memo : ""
  };
}
function loadData(){
  try{
    const raw=JSON.parse(localStorage.getItem(KEY)||"[]");
    const arr=Array.isArray(raw)?raw:[];
    const normalized=arr.map(normalizeRecord);
    if(JSON.stringify(arr)!==JSON.stringify(normalized)) localStorage.setItem(KEY,JSON.stringify(normalized));
    return normalized;
  }catch(e){ return []; }
}
let data=loadData();
const $=x=>document.getElementById(x);
const yen=x=>"¥"+Math.round(toNumber(x)).toLocaleString("ja-JP");
const sign=x=>{x=toNumber(x);return (x>=0?"+":"")+yen(x)};
function saveData(){localStorage.setItem(KEY,JSON.stringify(data))}
function cls(x){return toNumber(x)>=0?"positive":"negative"}
function stats(a){
  const inv=a.reduce((s,r)=>s+toNumber(r.inv),0), ret=a.reduce((s,r)=>s+toNumber(r.ret),0);
  const hit=a.filter(r=>toNumber(r.ret)>0).length;
  return {inv,ret,p:ret-inv,rate:inv?ret/inv*100:0,hitRate:a.length?hit/a.length*100:0,n:a.length};
}
function render(){
  const s=stats(data);
  $("summary").innerHTML=`<div class="card"><span>累計収支</span><b class="${cls(s.p)}">${sign(s.p)}</b><small>投資 ${yen(s.inv)}</small></div><div class="card"><span>回収率</span><b>${s.rate.toFixed(1)}%</b></div><div class="card"><span>的中率</span><b>${s.hitRate.toFixed(1)}%</b></div><div class="card"><span>記録レース</span><b>${s.n}</b></div>`;
  renderPeriod(); renderBets(); renderCourses(); renderRecords(); renderRanks(); draw(); renderCalendar();
}
function renderPeriod(){
  const n=new Date();
  let title,arr;
  if(periodMode==="year"){
    const key=String(n.getFullYear()); arr=data.filter(r=>r.date.startsWith(key)); title=n.getFullYear()+"年の成績";
  }else{
    const key=n.getFullYear()+"-"+String(n.getMonth()+1).padStart(2,"0"); arr=data.filter(r=>r.date.startsWith(key)); title=n.getFullYear()+"年"+(n.getMonth()+1)+"月の成績";
  }
  const s=stats(arr); $("periodTitle").textContent=title;
  $("periodStats").innerHTML=[["投資額",yen(s.inv),""],["払戻額",yen(s.ret),""],["収支",sign(s.p),cls(s.p)],["回収率",s.rate.toFixed(1)+"%",""],["的中率",s.hitRate.toFixed(1)+"%",""],["記録レース",s.n,""]].map(x=>`<div class="stat"><span>${x[0]}</span><b class="${x[2]}">${x[1]}</b></div>`).join("");
}
function renderBets(){
  const types=[...new Set(data.map(r=>r.type||"その他"))];
  $("bets").innerHTML=types.length?types.map(t=>{const a=data.filter(r=>(r.type||"その他")===t),s=stats(a);return `<div class="bet"><h3>${t}</h3><p><span>投資</span><b>${yen(s.inv)}</b></p><p><span>払戻</span><b>${yen(s.ret)}</b></p><p><span>回収率</span><b>${s.rate.toFixed(1)}%</b></p><p><span>的中率</span><b>${s.hitRate.toFixed(1)}%</b></p><strong class="${cls(s.p)}">${sign(s.p)}</strong></div>`}).join(""):"<p class='muted'>データがありません。</p>";
}
function renderCourses(){
  const courses=[...new Set(data.map(r=>r.course||"その他"))];
  $("courses").innerHTML=courses.length?courses.map(c=>{const a=data.filter(r=>(r.course||"その他")===c),s=stats(a);return `<div class="courseCard"><h3>${c}</h3><div><span>投資</span><b>${yen(s.inv)}</b></div><div><span>払戻</span><b>${yen(s.ret)}</b></div><div><span>収支</span><b class="${cls(s.p)}">${sign(s.p)}</b></div><div><span>回収率</span><b>${s.rate.toFixed(1)}%</b></div><div><span>的中率</span><b>${s.hitRate.toFixed(1)}%</b></div><small>${s.n}レース</small></div>`}).join(""):"<p class='muted'>データがありません。</p>";
}
function renderRanks(){
  const grouped=[...new Set(data.map(r=>r.type||"その他"))].map(t=>{const s=stats(data.filter(r=>(r.type||"その他")===t));return {t,...s}}).filter(x=>x.n);
  const ret=[...grouped].sort((a,b)=>b.rate-a.rate).slice(0,5),hit=[...grouped].sort((a,b)=>b.hitRate-a.hitRate).slice(0,5);
  const row=(x,i,key,suffix)=>`<div class="rank"><b>${i+1}</b><span>${x.t}</span><strong>${x[key].toFixed(1)}${suffix}</strong><small>${x.n}R</small></div>`;
  $("returnRank").innerHTML=ret.length?ret.map((x,i)=>row(x,i,"rate","%")).join(""):"<p class='muted'>データがありません。</p>";
  $("hitRank").innerHTML=hit.length?hit.map((x,i)=>row(x,i,"hitRate","%")).join(""):"<p class='muted'>データがありません。</p>";
}
function renderRecords(){
  const el=$("records");el.innerHTML=data.length?[...data].sort((a,b)=>b.date.localeCompare(a.date)||toNumber(b.id)-toNumber(a.id)).map(r=>{const p=toNumber(r.ret)-toNumber(r.inv);return `<div class="record"><div class="muted">${r.date}</div><div><b>${r.course}${r.race}R　${r.type}</b><div class="muted">${r.memo||"メモなし"} / 投資 ${yen(r.inv)} → 払戻 ${yen(r.ret)}</div><div class="actions"><button data-e="${r.id}">編集</button><button data-d="${r.id}">削除</button></div></div><b class="${cls(p)}">${sign(p)}</b></div>`}).join(""):"<p class='muted'>まだ収支データがありません。</p>";
}
function draw(){
  const c=$("chart"),w=c.clientWidth||800,h=290,d=devicePixelRatio||1;c.width=w*d;c.height=h*d;const x=c.getContext("2d");x.scale(d,d);x.clearRect(0,0,w,h);
  const n=+$('months').value,now=new Date(),ms=[];for(let i=n-1;i>=0;i--){const q=new Date(now.getFullYear(),now.getMonth()-i,1);ms.push(q.getFullYear()+"-"+String(q.getMonth()+1).padStart(2,"0"))}
  const v=ms.map(k=>data.filter(r=>r.date.startsWith(k)).reduce((s,r)=>s+toNumber(r.ret)-toNumber(r.inv),0));
  const mx=Math.max(...v,0),mn=Math.min(...v,0),range=Math.max(mx-mn,1),L=55,R=15,T=15,B=38,pw=w-L-R,ph=h-T-B,zero=T+mx/range*ph;
  x.strokeStyle="#e5e7eb";x.fillStyle="#6b7280";x.font="12px sans-serif";x.textAlign="right";[mx,0,mn].forEach(q=>{const y=T+(mx-q)/range*ph;x.beginPath();x.moveTo(L,y);x.lineTo(w-R,y);x.stroke();x.fillText((q>=0?"+":"")+yen(q),L-7,y+4)});
  const gap=pw/n,bw=Math.max(7,gap*.5);x.textAlign="center";v.forEach((q,i)=>{const xx=L+gap*i+gap/2,y=T+(mx-q)/range*ph;x.fillStyle=q>=0?"#059669":"#dc2626";x.fillRect(xx-bw/2,Math.min(y,zero),bw,Math.max(Math.abs(y-zero),2));x.fillStyle="#6b7280";x.fillText(ms[i].slice(5).replace("-","/"),xx,h-14)});
}
function renderCalendar(){
  const y=calendarDate.getFullYear(),m=calendarDate.getMonth();$("calendarTitle").textContent=y+"年"+(m+1)+"月";
  const first=new Date(y,m,1).getDay(),days=new Date(y,m+1,0).getDate(),daily={};
  data.forEach(r=>{if(r.date.startsWith(y+"-"+String(m+1).padStart(2,"0"))){const d=Number(r.date.slice(8,10));daily[d]=(daily[d]||0)+toNumber(r.ret)-toNumber(r.inv)}});
  let html=["日","月","火","水","木","金","土"].map(x=>`<div class="calHead">${x}</div>`).join("");
  for(let i=0;i<first;i++) html+='<div class="day empty"></div>';
  for(let d=1;d<=days;d++){const p=daily[d]||0;html+=`<div class="day ${p>0?'up':p<0?'down':''}"><span>${d}</span>${daily[d]!==undefined?`<b>${p>=0?"+":""}${Math.round(p).toLocaleString("ja-JP")}</b>`:""}</div>`}
  $("calendar").innerHTML=html;
}
function open(r=null){editId=r?r.id:null;$("mtitle").textContent=r?"収支を編集":"収支を記録";$("save").textContent=r?"変更を保存":"記録する";$("date").value=r?r.date:new Date().toISOString().slice(0,10);$("course").value=r?r.course:"";$("race").value=r?r.race:"";$("type").value=r?r.type:"複勝";$("inv").value=r?r.inv:"";$("ret").value=r?r.ret:"";$("memo").value=r?r.memo:"";$("modal").classList.remove("hide")}
function close(){ $("modal").classList.add("hide");$("form").reset();editId=null }
$("add").onclick=()=>open();$("close").onclick=close;$("modal").onclick=e=>{if(e.target.id==="modal")close()};
$("form").onsubmit=e=>{e.preventDefault();const r={id:editId||Date.now(),date:$("date").value,course:$("course").value,race:toNumber($("race").value),type:$("type").value,inv:toNumber($("inv").value),ret:toNumber($("ret").value),memo:$("memo").value.trim()},i=data.findIndex(x=>String(x.id)===String(r.id));if(i>=0)data[i]=r;else data.push(r);saveData();render();close()};
$("records").onclick=e=>{const b=e.target.closest("button");if(!b)return;const id=b.dataset.e||b.dataset.d;if(b.dataset.e){const r=data.find(x=>String(x.id)===String(id));if(r)open(r)}else if(confirm("この記録を削除しますか？")){data=data.filter(x=>String(x.id)!==String(id));saveData();render()}};
$("clear").onclick=()=>{if(data.length&&confirm("すべての収支データを削除します。よろしいですか？")){data=[];saveData();render()}};
$("months").onchange=draw;addEventListener("resize",draw);
document.querySelectorAll(".tab").forEach(b=>b.onclick=()=>{periodMode=b.dataset.period;document.querySelectorAll(".tab").forEach(x=>x.classList.toggle("active",x===b));renderPeriod()});
$("prevMonth").onclick=()=>{calendarDate.setMonth(calendarDate.getMonth()-1);renderCalendar()};$("nextMonth").onclick=()=>{calendarDate.setMonth(calendarDate.getMonth()+1);renderCalendar()};
render();
