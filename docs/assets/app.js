const fmtMoney=n=>{const a=Math.abs(Number(n||0));return a>=1e8?`${(a/1e8).toFixed(2)} 億`:a>=1e4?`${(a/1e4).toFixed(1)} 萬`:`${a.toLocaleString("zh-TW")} 元`};
const fmtSignedMoney=n=>`${n<0?"−":"+"}${fmtMoney(n)}`;
const fmtNum=n=>Number(n||0).toLocaleString("zh-TW");
const fmtPrice=n=>n==null?"—":Number(n).toFixed(2);
const stockCell=s=>`<div class="stock"><code>${s.stock_id}</code><strong>${s.stock_name}</strong>${s.is_seed?'<span class="seed">重點</span>':''}</div>`;
let data,windowDays=20;

function render(){
  const key=`d${windowDays}`;
  const active=data.stocks.filter(s=>s[key].gross_buy_twd||s[key].gross_sell_twd);
  const buys=active.filter(s=>s[key].net_lots>0).sort((a,b)=>Math.abs(b[key].net_flow_twd)-Math.abs(a[key].net_flow_twd));
  const sells=active.filter(s=>s[key].net_lots<0).sort((a,b)=>Math.abs(b[key].net_flow_twd)-Math.abs(a[key].net_flow_twd));
  const positions=[...active].sort((a,b)=>b[key].net_flow_twd-a[key].net_flow_twd);
  document.querySelectorAll(".range-text").forEach(el=>el.textContent=windowDays===1?"最近交易日":`近 ${windowDays} 個交易日`);
  document.querySelector("#buyRows").innerHTML=buys.map(s=>{const p=s[key];return `<tr><td>${stockCell(s)}</td><td class="positive">${fmtNum(p.net_lots)}</td><td class="positive">${fmtMoney(p.net_flow_twd)}</td></tr>`}).join("")||'<tr><td colspan="3" class="empty">本期沒有淨買超</td></tr>';
  document.querySelector("#sellRows").innerHTML=sells.map(s=>{const p=s[key];return `<tr><td>${stockCell(s)}</td><td class="negative">${fmtNum(Math.abs(p.net_lots))}</td><td class="negative">${fmtMoney(p.net_flow_twd)}</td></tr>`}).join("")||'<tr><td colspan="3" class="empty">本期沒有淨賣超</td></tr>';
  document.querySelector("#positionRows").innerHTML=positions.map(s=>{const p=s[key];const ret=s.estimated_return_pct;return `<tr><td>${stockCell(s)}</td><td class="${p.net_lots>0?'positive':p.net_lots<0?'negative':'muted'}">${p.net_lots>0?'+':''}${fmtNum(p.net_lots)}</td><td class="${p.net_flow_twd>0?'positive':p.net_flow_twd<0?'negative':'muted'}">${fmtSignedMoney(p.net_flow_twd)}</td><td>${fmtNum(s.estimated_inventory_lots)} 張</td><td>${fmtPrice(s.estimated_cost)}</td><td>${fmtPrice(s.latest_close)}</td><td class="${ret>0?'positive':ret<0?'negative':'muted'}">${ret==null?'—':`${ret>0?'+':''}${ret.toFixed(2)}%`}</td></tr>`}).join("");
  const topBuy=buys[0],topSell=sells[0];
  document.querySelector("#buyLeader").textContent=topBuy?`${topBuy.stock_id} ${topBuy.stock_name}`:"—";
  document.querySelector("#buyLeaderFlow").textContent=topBuy?fmtMoney(topBuy[key].net_flow_twd):"—";
  document.querySelector("#sellLeader").textContent=topSell?`${topSell.stock_id} ${topSell.stock_name}`:"—";
  document.querySelector("#sellLeaderFlow").textContent=topSell?fmtMoney(topSell[key].net_flow_twd):"—";
}

fetch("data/dashboard.json").then(r=>{if(!r.ok)throw Error(r.status);return r.json()}).then(d=>{
  data=d;
  document.querySelector("#latest").textContent=d.latest_session;
  document.querySelector("#note").innerHTML=`<strong>估算限制：</strong>${d.method_note}　觀察起點：${d.observed_from}；產生時間：${new Date(d.generated_at).toLocaleString("zh-TW")}`;
  const inv=[...d.stocks].sort((a,b)=>b.estimated_inventory_lots-a.estimated_inventory_lots)[0];
  document.querySelector("#inventoryLeader").textContent=`${inv.stock_id} ${inv.stock_name}`;
  document.querySelector("#inventoryLots").textContent=`${fmtNum(inv.estimated_inventory_lots)} 張｜成本 ${fmtPrice(inv.estimated_cost)}`;
  render();
}).catch(()=>{document.querySelectorAll("tbody").forEach(el=>el.innerHTML='<tr><td colspan="7" class="empty">目前沒有可顯示的資料</td></tr>')});

document.querySelectorAll(".windows button").forEach(b=>b.addEventListener("click",()=>{document.querySelectorAll(".windows button").forEach(x=>x.classList.remove("active"));b.classList.add("active");windowDays=Number(b.dataset.window);render()}));
