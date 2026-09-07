const KEY="keiba-note-records-v1";let data=JSON.parse(localStorage.getItem(KEY)||"[]"),editId=null;
const $=x=>document.getElementById(x), yen=x=>"¥"+Number(x).toLocaleString("ja-JP"), sign=x=>(x>=0?"+":"")+yen(x);
function saveData(){localStorage.setItem(KEY,JSON.stringify(data))}
function cls(x){return x>=0?"positive":"negative"}
function render(){
 let inv=data.reduce((s,r)=>s+r.inv,0),ret=data.reduce((s,r)=>s+r.ret,0),p=ret-inv,h=data.filter(r=>r.ret>0).length;
 $("summary").innerHTML=`<div class="card"><span>累計収支</span><b class="${cls(p)}">${sign(p)}</b><small>投資 ${yen(inv)}</small></div><div class="card"><span>回収率</span><b>${(inv?ret/inv*100:0).toFixed(1)}%</b></div><div class="card"><span>的中率</span><b>${(data.length?h/data.length*100:0).toFixed(1)}%</b></div><div class="card"><span>記録レース</span><b>${data.length}</b></div>`;
 const n=new Date(),key=n.getFullYear()+"-"+String(n.getMonth()+1).padStart(2,"0"),m=data.filter(r=>r.date.startsWith(key)),mi=m.reduce((s,r)=>s+r.inv,0),mr=m.reduce((s,r)=>s+r.ret,0),mp=mr-mi;
 $("monthTitle").textContent=n.getFullYear()+"年"+(n.getMonth()+1)+"月の成績";
 $("monthly").innerHTML=[["投資額",yen(mi),""],["払戻額",yen(mr),""],["収支",sign(mp),cls(mp)],["回収率",(mi?mr/mi*100:0).toFixed(1)+"%",""],["的中率",(m.length?m.filter(r=>r.ret>0).length/m.length*100:0).toFixed(1)+"%",""],["記録レース",m.length,""]].map(x=>`<div class="stat"><span>${x[0]}</span><b class="${x[2]}">${x[1]}</b></div>`).join("");
 renderBets();renderRecords();draw();
}
function renderBets(){
 const types=[...new Set(data.map(r=>r.type))];$("bets").innerHTML=types.length?types.map(t=>{let a=data.filter(r=>r.type===t),i=a.reduce((s,r)=>s+r.inv,0),r=a.reduce((s,r)=>s+r.ret,0),p=r-i;return `<div class="bet"><h3>${t}</h3><p><span>投資</span><b>${yen(i)}</b></p><p><span>払戻</span><b>${yen(r)}</b></p><p><span>回収率</span><b>${(i?r/i*100:0).toFixed(1)}%</b></p><p><span>的中率</span><b>${(a.filter(x=>x.ret>0).length/a.length*100).toFixed(1)}%</b></p><strong class="${cls(p)}">${sign(p)}</strong></div>`}).join(""):"<p class='muted'>データがありません。</p>";
}
function renderRecords(){
 const el=$("records");el.innerHTML=data.length?[...data].sort((a,b)=>b.date.localeCompare(a.date)||b.id-a.id).map(r=>{let p=r.ret-r.inv;return `<div class="record"><div class="muted">${r.date}</div><div><b>${r.course}${r.race}R　${r.type}</b><div class="muted">${r.memo||"メモなし"} / 投資 ${yen(r.inv)} → 払戻 ${yen(r.ret)}</div><div class="actions"><button data-e="${r.id}">編集</button><button data-d="${r.id}">削除</button></div></div><b class="${cls(p)}">${sign(p)}</b></div>`}).join(""):"<p class='muted'>まだ収支データがありません。</p>";
}
function draw(){
 const c=$("chart"),w=c.clientWidth,h=290,d=devicePixelRatio||1;c.width=w*d;c.height=h*d;let x=c.getContext("2d");x.scale(d,d);x.clearRect(0,0,w,h);
 let n=+$("months").value,now=new Date(),ms=[];for(let i=n-1;i>=0;i--){let q=new Date(now.getFullYear(),now.getMonth()-i,1);ms.push(q.getFullYear()+"-"+String(q.getMonth()+1).padStart(2,"0"))}
 let v=ms.map(k=>data.filter(r=>r.date.startsWith(k)).reduce((s,r)=>s+r.ret-r.inv,0)),mx=Math.max(...v,0),mn=Math.min(...v,0),range=Math.max(mx-mn,1),L=55,R=15,T=15,B=38,pw=w-L-R,ph=h-T-B,zero=T+mx/range*ph;
 x.strokeStyle="#e5e7eb";x.fillStyle="#6b7280";x.font="12px sans-serif";x.textAlign="right";[mx,0,mn].forEach(q=>{let y=T+(mx-q)/range*ph;x.beginPath();x.moveTo(L,y);x.lineTo(w-R,y);x.stroke();x.fillText((q>=0?"+":"")+yen(q),L-7,y+4)});
 let gap=pw/n,bw=Math.max(7,gap*.5);x.textAlign="center";v.forEach((q,i)=>{let xx=L+gap*i+gap/2,y=T+(mx-q)/range*ph;x.fillStyle=q>=0?"#059669":"#dc2626";x.fillRect(xx-bw/2,Math.min(y,zero),bw,Math.max(Math.abs(y-zero),2));x.fillStyle="#6b7280";x.fillText(ms[i].slice(5).replace("-","/"),xx,h-14)});
}
function open(r=null){editId=r?r.id:null;$("mtitle").textContent=r?"収支を編集":"収支を記録";$("save").textContent=r?"変更を保存":"記録する";$("date").value=r?r.date:new Date().toISOString().slice(0,10);$("course").value=r?r.course:"";$("race").value=r?r.race:"";$("type").value=r?r.type:"複勝";$("inv").value=r?r.inv:"";$("ret").value=r?r.ret:"";$("memo").value=r?r.memo:"";$("modal").classList.remove("hide")}
function close(){ $("modal").classList.add("hide");$("form").reset();editId=null}
$("add").onclick=()=>open();$("close").onclick=close;document.querySelector(".modal").onclick=e=>{if(e.target.id==="modal")close()};
$("form").onsubmit=e=>{e.preventDefault();let r={id:editId||Date.now(),date:$("date").value,course:$("course").value,race:+$("race").value,type:$("type").value,inv:+$("inv").value,ret:+$("ret").value,memo:$("memo").value.trim()},i=data.findIndex(x=>x.id===r.id);if(i>=0)data[i]=r;else data.push(r);saveData();render();close()};
$("records").onclick=e=>{let b=e.target.closest("button");if(!b)return;let id=+((b.dataset.e||b.dataset.d));if(b.dataset.e){let r=data.find(x=>x.id===id);open(r)}else if(confirm("この記録を削除しますか？")){data=data.filter(x=>x.id!==id);saveData();render()}};
$("clear").onclick=()=>{if(data.length&&confirm("すべての収支データを削除します。よろしいですか？")){data=[];saveData();render()}};$("months").onchange=draw;addEventListener("resize",draw);render();