const fmtMoney=n=>{const a=Math.abs(Number(n||0));return a>=1e8?`${(a/1e8).toFixed(2)} 億`:a>=1e4?`${(a/1e4).toFixed(1)} 萬`:`${a.toLocaleString("zh-TW")} 元`};
const fmtSignedMoney=n=>`${n<0?"−":n>0?"+":""}${fmtMoney(n)}`;
const fmtNum=n=>Number(n||0).toLocaleString("zh-TW");
const fmtPrice=n=>n==null?"—":Number(n).toFixed(2);
const escapeHtml=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[c]);
const stockCell=s=>`<div class="stock"><code>${escapeHtml(s.stock_id)}</code><strong>${escapeHtml(s.stock_name)}</strong>${s.is_seed?'<span class="seed">重點</span>':''}</div>`;
const metricCell=(label,value,kind="")=>`<td data-label="${label}" class="${kind}">${value}</td>`;
let data,windowDays=20;

function render(){
  if(!data)return;
  const key=`d${windowDays}`;
  const query=document.querySelector("#stockSearch").value.trim().toLocaleLowerCase("zh-TW");
  const active=data.stocks.filter(s=>s[key].gross_buy_twd||s[key].gross_sell_twd);
  const visible=active.filter(s=>!query||`${s.stock_id} ${s.stock_name}`.toLocaleLowerCase("zh-TW").includes(query));
  const buys=visible.filter(s=>s[key].net_lots>0).sort((a,b)=>b[key].net_lots-a[key].net_lots||b[key].net_flow_twd-a[key].net_flow_twd);
  const sells=visible.filter(s=>s[key].net_lots<0).sort((a,b)=>a[key].net_lots-b[key].net_lots||a[key].net_flow_twd-b[key].net_flow_twd);
  const positions=[...visible].sort((a,b)=>b[key].net_flow_twd-a[key].net_flow_twd);
  document.querySelectorAll(".range-text").forEach(el=>el.textContent=windowDays===1?"最近交易日":`近 ${windowDays} 個交易日`);
  document.querySelector("#resultCount").textContent=`${visible.length} 檔符合條件｜淨買 ${buys.length}・淨賣 ${sells.length}`;
  document.querySelector("#clearSearch").hidden=!query;
  document.querySelector("#buyRows").innerHTML=buys.map(s=>{const p=s[key];return `<tr>${metricCell("股票",stockCell(s))}${metricCell("淨買張數",fmtNum(p.net_lots),"positive")}${metricCell("淨買金額",fmtSignedMoney(p.net_flow_twd),p.net_flow_twd>=0?"positive":"negative")}</tr>`}).join("")||'<tr><td colspan="3" class="empty">沒有符合條件的淨買超股票</td></tr>';
  document.querySelector("#sellRows").innerHTML=sells.map(s=>{const p=s[key];return `<tr>${metricCell("股票",stockCell(s))}${metricCell("淨賣張數",fmtNum(Math.abs(p.net_lots)),"negative")}${metricCell("淨賣金額",fmtSignedMoney(p.net_flow_twd),p.net_flow_twd<=0?"negative":"positive")}</tr>`}).join("")||'<tr><td colspan="3" class="empty">沒有符合條件的淨賣超股票</td></tr>';
  document.querySelector("#positionRows").innerHTML=positions.map(s=>{const p=s[key],ret=s.estimated_return_pct;return `<tr>${metricCell("股票",stockCell(s))}${metricCell("區間淨張數",`${p.net_lots>0?"+":""}${fmtNum(p.net_lots)}`,p.net_lots>0?"positive":p.net_lots<0?"negative":"muted")}${metricCell("區間淨資金",fmtSignedMoney(p.net_flow_twd),p.net_flow_twd>0?"positive":p.net_flow_twd<0?"negative":"muted")}${metricCell("估算庫存",`${fmtNum(s.estimated_inventory_lots)} 張`)}${metricCell("估算成本",fmtPrice(s.estimated_cost))}${metricCell("收盤價",fmtPrice(s.latest_close))}${metricCell("估算報酬",ret==null?"—":`${ret>0?"+":""}${ret.toFixed(2)}%`,ret>0?"positive":ret<0?"negative":"muted")}</tr>`}).join("")||'<tr><td colspan="7" class="empty">沒有符合條件的股票</td></tr>';
  const topBuy=active.filter(s=>s[key].net_lots>0).sort((a,b)=>b[key].net_lots-a[key].net_lots)[0];
  const topSell=active.filter(s=>s[key].net_lots<0).sort((a,b)=>a[key].net_lots-b[key].net_lots)[0];
  document.querySelector("#buyLeader").textContent=topBuy?`${topBuy.stock_id} ${topBuy.stock_name}`:"—";
  document.querySelector("#buyLeaderFlow").textContent=topBuy?`${fmtNum(topBuy[key].net_lots)} 張｜${fmtSignedMoney(topBuy[key].net_flow_twd)}`:"—";
  document.querySelector("#sellLeader").textContent=topSell?`${topSell.stock_id} ${topSell.stock_name}`:"—";
  document.querySelector("#sellLeaderFlow").textContent=topSell?`${fmtNum(Math.abs(topSell[key].net_lots))} 張｜${fmtSignedMoney(topSell[key].net_flow_twd)}`:"—";
}

fetch("data/dashboard.json").then(r=>{if(!r.ok)throw Error(r.status);return r.json()}).then(d=>{
  if(!Array.isArray(d.stocks)||!d.stocks.length)throw Error("No stocks");
  data=d;
  document.querySelector("#latest").textContent=d.latest_session;
  document.querySelector("#note").textContent=`估算限制：${d.method_note} 觀察起點：${d.observed_from}；產生時間：${new Date(d.generated_at).toLocaleString("zh-TW")}`;
  const inv=[...d.stocks].sort((a,b)=>b.estimated_inventory_lots-a.estimated_inventory_lots)[0];
  document.querySelector("#inventoryLeader").textContent=`${inv.stock_id} ${inv.stock_name}`;
  document.querySelector("#inventoryLots").textContent=`${fmtNum(inv.estimated_inventory_lots)} 張｜成本 ${fmtPrice(inv.estimated_cost)}`;
  render();
}).catch(()=>{
  document.querySelector("#latest").textContent="資料讀取失敗";
  document.querySelector("#resultCount").textContent="請稍後重新整理";
  document.querySelectorAll("tbody").forEach(el=>el.innerHTML=`<tr><td colspan="${el.id==="positionRows"?7:3}" class="empty">目前沒有可顯示的資料，請重新整理</td></tr>`);
});

document.querySelectorAll(".windows button").forEach(b=>b.addEventListener("click",()=>{
  document.querySelectorAll(".windows button").forEach(x=>{x.classList.remove("active");x.setAttribute("aria-pressed","false")});
  b.classList.add("active");b.setAttribute("aria-pressed","true");windowDays=Number(b.dataset.window);render();
}));
document.querySelector("#stockSearch").addEventListener("input",render);
document.querySelector("#clearSearch").addEventListener("click",()=>{const input=document.querySelector("#stockSearch");input.value="";input.focus();render()});
