"""Inline Streamlit v2 chart with a locally bundled Lightweight Charts library."""
from pathlib import Path
import streamlit as st

HTML = """
<section class="market-chart">
  <div class="chart-toolbar"><div><span class="eyebrow">PERFORMANCE / </span><span class="chart-date"></span></div>
    <div class="actions"><button class="fit" type="button">重設縮放</button><button class="show-all" type="button">顯示全部</button></div></div>
  <div class="canvas" role="img" aria-label="多檔歷史漲跌幅互動圖表"></div>
  <div class="legend" aria-label="標的數值與曲線開關"></div>
  <div class="chart-footer"><span>拖曳平移 · 滾輪縮放 · 點擊標的開關曲線</span><a href="https://www.tradingview.com/" target="_blank" rel="noopener noreferrer">TradingView Lightweight Charts™</a></div>
</section>
"""
CSS = """
.market-chart {font-family:var(--st-font),sans-serif;color:var(--st-text-color);width:100%;}
.chart-toolbar {display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:6px 0 16px;font-size:13px;}
.eyebrow {color:#94a3b8;font-size:11px;letter-spacing:1.5px;}
.chart-date {font-variant-numeric:tabular-nums;}
.actions {display:flex;gap:8px;}
button {font:inherit;cursor:pointer;color:inherit;}
.actions button {border:1px solid var(--st-border-color);background:transparent;border-radius:6px;padding:7px 12px;font-size:12px;}
button:hover {background:var(--st-secondary-background-color);}
button:focus-visible {outline:2px solid var(--st-primary-color);outline-offset:2px;}
.canvas {height:410px;width:100%;border-radius:8px;overflow:hidden;}
.legend {display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:8px;margin-top:18px;}
.legend button {display:flex;align-items:center;gap:8px;padding:10px 12px;min-width:0;border:1px solid var(--st-border-color);border-radius:7px;background:transparent;text-align:left;}
.legend button[aria-pressed="false"] {opacity:.4;}
.swatch {width:16px;height:3px;border-radius:3px;flex-shrink:0;}
.name {font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.value {margin-left:auto;font-variant-numeric:tabular-nums;font-size:13px;font-weight:600;white-space:nowrap;}
.chart-footer {display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;color:#94a3b8;font-size:11px;margin-top:14px;}
.chart-footer a {color:#94a3b8;text-decoration:none;}
@media(max-width:600px){.canvas{height:340px}.legend{grid-template-columns:1fr}.chart-toolbar{font-size:12px}}
"""
JS = """
export default function({parentElement, data}) {
  const root = parentElement.querySelector('.market-chart');
  // Streamlit also calls the renderer on data updates without unmounting.
  root._marketDispose?.();
  const host = root.querySelector('.canvas');
  const legend = root.querySelector('.legend');
  const dateLabel = root.querySelector('.chart-date');
  const L = window.LightweightCharts;
  const fmt = value => (value > 0 ? '+' : '') + (Math.abs(value) < .05 ? 0 : value).toFixed(1) + '%';
  const chart = L.createChart(host, {
    autoSize:true,
    layout:{background:{type:'solid',color:'#0F172A'},textColor:'#94A3B8',fontFamily:'Segoe UI, Microsoft JhengHei, sans-serif',fontSize:12,attributionLogo:true},
    grid:{vertLines:{visible:false},horzLines:{color:'#243147',style:2}},
    rightPriceScale:{borderColor:'#334155',scaleMargins:{top:.12,bottom:.12}},
    timeScale:{borderColor:'#334155',rightOffset:1,fixLeftEdge:true,fixRightEdge:true,timeVisible:false},
    crosshair:{mode:L.CrosshairMode.Normal,vertLine:{color:'#64748B',style:2,labelBackgroundColor:'#334155'},horzLine:{color:'#64748B',style:2,labelBackgroundColor:'#334155'}},
    localization:{locale:'zh-TW',priceFormatter:fmt},
  });
  const rows = [];
  const latest = () => {
    dateLabel.textContent = data.end + ' · ' + data.view;
    rows.forEach(row => row.value.textContent = fmt(row.points.at(-1).value));
  };
  for (const item of data.series) {
    const series = chart.addSeries(L.LineSeries, {
      color:item.color,lineWidth:2,lineStyle:0,priceLineVisible:false,lastValueVisible:false,
      crosshairMarkerRadius:4,priceFormat:{type:'custom',minMove:.1,formatter:fmt},
    });
    series.setData(item.points);
    const button = document.createElement('button');
    button.type = 'button'; button.setAttribute('aria-pressed','true');
    button.setAttribute('aria-label',item.name + ' 曲線');
    const swatch = document.createElement('span'); swatch.className='swatch';swatch.style.background=item.color;
    const name = document.createElement('span');name.className='name';name.textContent=item.name;
    const value = document.createElement('span');value.className='value';value.style.color=item.color;
    button.append(swatch,name,value);legend.append(button);
    const row = {series,button,value,points:item.points,visible:true};rows.push(row);
    button.onclick = () => {row.visible=!row.visible;series.applyOptions({visible:row.visible});button.setAttribute('aria-pressed',String(row.visible));};
  }
  rows[0]?.series.createPriceLine({price:0,color:'#64748B',lineWidth:1,lineStyle:2,axisLabelVisible:false});
  chart.timeScale().fitContent();latest();
  chart.subscribeCrosshairMove(param => {
    if (!param.time || !param.point || param.point.x<0 || param.point.y<0) {latest();return;}
    const t = param.time;
    dateLabel.textContent = (typeof t==='string' ? t : `${t.year}-${String(t.month).padStart(2,'0')}-${String(t.day).padStart(2,'0')}`) + ' · ' + data.view;
    rows.forEach(row => {const point=param.seriesData.get(row.series);row.value.textContent=point ? fmt(point.value) : '—';});
  });
  root.querySelector('.fit').onclick=()=>{chart.timeScale().fitContent();chart.priceScale('right').applyOptions({autoScale:true});};
  root.querySelector('.show-all').onclick=()=>{rows.forEach(row=>{row.visible=true;row.series.applyOptions({visible:true});row.button.setAttribute('aria-pressed','true');});latest();};
  let disposed = false;
  const cleanup = () => {
    if (disposed) return;
    disposed = true;
    chart.remove();
    if (root._marketDispose === cleanup) {legend.replaceChildren();delete root._marketDispose;}
  };
  root._marketDispose = cleanup;
  return cleanup;
}
"""

_vendor = (Path(__file__).parent / "vendor/lightweight-charts-5.0.9.js").read_text(encoding="utf-8")
_component = st.components.v2.component("taiwan_lightweight_chart", html=HTML, css=CSS, js=_vendor + "\n" + JS)


def render_chart(frame, labels, colors, view):
    series = [dict(name=labels[s], color=colors[s], points=[dict(time=t.strftime("%Y-%m-%d"), value=float(v)) for t, v in frame[s].items()]) for s in frame.columns]
    return _component(data=dict(series=series, end=frame.index[-1].strftime("%Y-%m-%d"), view=view), key="performance_chart", width="stretch", height="content")
