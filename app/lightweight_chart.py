"""Inline Streamlit v2 chart with a locally bundled Lightweight Charts library."""
from pathlib import Path
import streamlit as st

HTML = """
<section class="market-chart">
  <div class="chart-toolbar"><div><span class="eyebrow">PERFORMANCE / </span><span class="chart-date"></span></div>
    <div class="actions"><button class="fit" type="button">重設縮放</button><button class="show-all" type="button">顯示全部</button></div></div>
  <div class="canvas" role="img" aria-label="多檔歷史漲跌幅互動圖表"></div>
  <div class="legend" aria-label="標的數值與曲線開關"></div>
  <div class="chart-footer"><span>電腦：拖曳平移、滾輪縮放。手機：左右拖曳、雙指縮放、長按查看數值。游標點旁顯示當天漲跌幅與收盤價，右側座標顯示各線最新值，點圖例開關曲線。</span><a href="https://www.tradingview.com/" target="_blank" rel="noopener noreferrer">TradingView Lightweight Charts™</a></div>
</section>
"""
CSS = """
.market-chart {container-type:inline-size;font-family:var(--st-font),sans-serif;color:var(--st-text-color);width:100%;}
.chart-toolbar {display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:6px 0 16px;font-size:13px;}
.eyebrow {color:#94a3b8;font-size:11px;letter-spacing:1.5px;}
.chart-date {font-variant-numeric:tabular-nums;}
.actions {display:flex;gap:8px;}
button {font:inherit;cursor:pointer;color:inherit;}
.actions button {border:1px solid var(--st-border-color);background:transparent;border-radius:6px;padding:10px 12px;min-height:44px;font-size:12px;}
button:hover {background:var(--st-secondary-background-color);}
button:focus-visible {outline:2px solid var(--st-primary-color);outline-offset:2px;}
.canvas {height:410px;width:100%;border-radius:8px;overflow:hidden;position:relative;}
.tag {position:absolute;z-index:3;pointer-events:none;display:none;padding:1px 6px;border-radius:4px;background:rgba(15,23,42,.82);font-size:11px;line-height:16px;font-weight:600;white-space:nowrap;font-variant-numeric:tabular-nums;}
.tag .px {color:#CBD5E1;font-weight:400;margin-left:5px;}
.axis {position:absolute;z-index:2;pointer-events:none;display:none;box-sizing:border-box;padding:1px 5px;border-radius:2px;color:#0F172A;font-size:11px;line-height:16px;font-weight:600;white-space:nowrap;font-variant-numeric:tabular-nums;}
.axis .px {font-weight:400;margin-left:5px;}
.axis .nm {font-weight:400;margin-left:5px;}
.legend {display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:8px;margin-top:18px;}
.legend button {display:flex;align-items:center;gap:8px;padding:10px 12px;min-width:0;min-height:44px;border:1px solid var(--st-border-color);border-radius:7px;background:transparent;text-align:left;}
.legend button[aria-pressed="false"] {opacity:.4;}
.swatch {width:16px;height:3px;border-radius:3px;flex-shrink:0;}
.name {font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.value {margin-left:auto;font-variant-numeric:tabular-nums;font-size:13px;font-weight:600;white-space:nowrap;}
.price {font-variant-numeric:tabular-nums;font-size:12px;opacity:.75;white-space:nowrap;}
.chart-footer {display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;color:#94a3b8;font-size:11px;margin-top:14px;}
.chart-footer a {color:#94a3b8;text-decoration:none;}
@container(max-width:600px){.canvas{height:320px}.legend{grid-template-columns:minmax(0,1fr)}.chart-toolbar{font-size:12px}.name{white-space:normal;overflow-wrap:anywhere}.actions{width:100%}.actions button{flex:1}.eyebrow{display:none}}
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
  // A close, not a return: two decimals is how Taiwan quotes most ETFs, and a price in the
  // thousands loses nothing by dropping them.
  const money = value => value.toLocaleString('zh-TW',{minimumFractionDigits:value>=1000?0:2,maximumFractionDigits:value>=1000?0:2});
  const blank = () => '';
  const day = t => typeof t==='string' ? t : `${t.year}-${String(t.month).padStart(2,'0')}-${String(t.day).padStart(2,'0')}`;
  const slashed = t => {
    const [y,m,d] = (typeof t==='number' ? new Date(t*1000).toISOString().slice(0,10) : day(t)).split('-');
    return `${y}/${+m}/${+d}`;
  };
  const chart = L.createChart(host, {
    autoSize:true,
    handleScroll:{mouseWheel:true,pressedMouseMove:true,horzTouchDrag:true,vertTouchDrag:false},
    handleScale:{mouseWheel:true,pinch:true},
    layout:{background:{type:'solid',color:'#0F172A'},textColor:'#94A3B8',fontFamily:'Segoe UI, Microsoft JhengHei, sans-serif',fontSize:12,attributionLogo:true},
    grid:{vertLines:{visible:false},horzLines:{color:'#243147',style:2}},
    // The axis carries each line's latest reading instead of a 10% grid, so its own labels are
    // blanked and it keeps room for the widest reading.
    rightPriceScale:{borderColor:'#334155',scaleMargins:{top:.12,bottom:.12},minimumWidth:96},
    timeScale:{borderColor:'#334155',rightOffset:1,fixLeftEdge:true,fixRightEdge:true,timeVisible:false},
    crosshair:{mode:L.CrosshairMode.Normal,vertLine:{color:'#64748B',style:2,labelBackgroundColor:'#334155'},horzLine:{color:'#64748B',style:2,labelVisible:false}},
    // The crosshair's date as people here write one, 2026/5/15, rather than the library's
    // zh-TW default of 15 5月 '26.
    localization:{locale:'zh-TW',priceFormatter:blank,timeFormatter:slashed},
  });
  // Two readings. Beside each point under the cursor, so a reading never needs a glance down
  // to the legend; and on the right axis, each line's latest, at that line's height. Both
  // blind to the pointer so neither can steal the hover.
  const rows = [];
  // Centred on their lines, then pushed apart where two lines run close, then pulled back
  // inside the canvas from the bottom up. `items` is [{el, y}] sorted by y.
  const stack = items => {
    if (!items.length) return [];
    const H=host.clientHeight, h=items[0].el.offsetHeight+2;
    const ys = items.map(s => s.y-h/2);
    for (let i=1;i<ys.length;i++) ys[i]=Math.max(ys[i],ys[i-1]+h);
    ys[ys.length-1]=Math.min(ys[ys.length-1],H-h);
    for (let i=ys.length-2;i>=0;i--) ys[i]=Math.min(ys[i],ys[i+1]-h);
    return ys.map(y => Math.max(0,y));
  };
  const reading = (el, v, close) => {
    el.replaceChildren(fmt(v));
    if (close != null) {const px=document.createElement('span');px.className='px';px.textContent=money(close);el.append(px);}
    el.style.display='block';
  };
  const latest = () => {
    dateLabel.textContent = data.end + ' · ' + data.view;
    rows.forEach(row => {row.value.textContent = fmt(row.points.at(-1).value);if (row.price) row.price.textContent = money(row.prices[data.end] ?? NaN);});
  };
  for (const item of data.series) {
    const series = chart.addSeries(L.LineSeries, {
      color:item.line ?? item.color,lineWidth:item.width ?? 2,lineStyle:0,priceLineVisible:false,lastValueVisible:false,
      crosshairMarkerRadius:4,priceFormat:{type:'custom',minMove:.1,formatter:blank},
    });
    series.setData(item.points);
    const button = document.createElement('button');
    button.type = 'button'; button.setAttribute('aria-pressed','true');
    button.setAttribute('aria-label',item.name + ' 曲線');
    const swatch = document.createElement('span'); swatch.className='swatch';swatch.style.background=item.color;
    const name = document.createElement('span');name.className='name';name.textContent=item.name;
    const value = document.createElement('span');value.className='value';value.style.color=item.color;
    button.append(swatch,name,value);
    // The blend has no price of its own, so it keeps the reading alone.
    let price = null;
    if (item.prices) {price=document.createElement('span');price.className='price';button.append(price);}
    legend.append(button);
    const tag = document.createElement('div');tag.className='tag';tag.style.color=item.color;host.append(tag);
    const axis = document.createElement('div');axis.className='axis';axis.style.background=item.color;host.append(axis);
    const row = {series,button,value,price,prices:item.prices,points:item.points,visible:true,tag,axis,name:item.name};rows.push(row);
    button.onclick = () => {row.visible=!row.visible;series.applyOptions({visible:row.visible});button.setAttribute('aria-pressed',String(row.visible));placeAxis();};
  }
  const hideTags = () => rows.forEach(row => row.tag.style.display='none');
  // The latest point's height moves whenever the view is panned, zoomed or resized; the
  // second frame is the one after the chart has redrawn its scale.
  const placeAxis = () => requestAnimationFrame(() => requestAnimationFrame(() => {
    if (disposed) return;
    rows.forEach(row => row.axis.style.display='none');
    const items = rows.filter(row => row.visible).map(row => {
      const last = row.points.at(-1);
      reading(row.axis, last.value, row.prices ? row.prices[data.end] : null);
      if (data.axis_names) {const nm=document.createElement('span');nm.className='nm';nm.textContent=row.name;row.axis.append(nm);}
      return {el: row.axis, y: row.series.priceToCoordinate(last.value)};
    }).filter(s => s.y != null).sort((a,b) => a.y-b.y);
    // Each tag fills the axis column from its border, as the axis's own labels do. A reading
    // too wide for the column widens the axis instead of spilling into the plot, then the
    // tags are placed again on the redrawn scale.
    rows.forEach(row => row.axis.style.width='auto');
    const scale=chart.priceScale('right'), axisWidth=scale.width();
    const widest=Math.max(0,...items.map(s => s.el.offsetWidth));
    if (widest > axisWidth) {scale.applyOptions({minimumWidth:Math.ceil(widest)+2});placeAxis();return;}
    const left=host.clientWidth-axisWidth;
    stack(items).forEach((y,i) => {const el=items[i].el;el.style.left=left+'px';el.style.width=axisWidth+'px';el.style.top=y+'px';});
  }));
  rows[0]?.series.createPriceLine({price:0,color:'#64748B',lineWidth:1,lineStyle:2,axisLabelVisible:false});
  chart.timeScale().fitContent();latest();
  chart.timeScale().subscribeVisibleLogicalRangeChange(placeAxis);
  const resized = new ResizeObserver(placeAxis);resized.observe(host);
  chart.subscribeCrosshairMove(param => {
    if (!param.time || !param.point || param.point.x<0 || param.point.y<0) {hideTags();latest();return;}
    const t = day(param.time);
    dateLabel.textContent = t + ' · ' + data.view;
    rows.forEach(row => {
      const point=param.seriesData.get(row.series);row.value.textContent=point ? fmt(point.value) : '—';
      if (row.price) row.price.textContent = row.prices[t] == null ? '—' : money(row.prices[t]);
    });
    hideTags();
    const items = rows.filter(row => row.visible && param.seriesData.get(row.series)).map(row => {
      const v = param.seriesData.get(row.series).value;
      reading(row.tag, v, row.prices ? row.prices[t] : null);
      return {el: row.tag, y: row.series.priceToCoordinate(v) ?? param.point.y};
    }).sort((a,b) => a.y-b.y);
    if (!items.length) return;
    // One side for all of them, so the tags read as a column: right of the cursor unless
    // that would run into the axis readings, then left.
    const gap=10, plot=host.clientWidth-chart.priceScale('right').width();
    const widest=Math.max(...items.map(s => s.el.offsetWidth));
    const x = param.point.x+gap+widest > plot ? Math.max(0,param.point.x-gap-widest) : param.point.x+gap;
    stack(items).forEach((y,i) => {items[i].el.style.left=x+'px';items[i].el.style.top=y+'px';});
  });
  root.querySelector('.fit').onclick=()=>{chart.timeScale().fitContent();chart.priceScale('right').applyOptions({autoScale:true});placeAxis();};
  root.querySelector('.show-all').onclick=()=>{rows.forEach(row=>{row.visible=true;row.series.applyOptions({visible:true});row.button.setAttribute('aria-pressed','true');});latest();placeAxis();};
  let disposed = false;
  const cleanup = () => {
    if (disposed) return;
    disposed = true;
    resized.disconnect();
    chart.remove();
    // The readings live on the host, not inside the chart, so chart.remove() leaves them;
    // every redraw would otherwise stack a fresh set over the old ones.
    rows.forEach(row => {row.tag.remove();row.axis.remove();});
    if (root._marketDispose === cleanup) {legend.replaceChildren();delete root._marketDispose;}
  };
  root._marketDispose = cleanup;
  return cleanup;
}
"""

_vendor = (Path(__file__).parent / "vendor/lightweight-charts-5.0.9.js").read_text(encoding="utf-8")
_component = st.components.v2.component("taiwan_lightweight_chart", html=HTML, css=CSS, js=_vendor + "\n" + JS)


# Holding colours and the blend's live together so the reserved one cannot drift back
# into the rotation. Slot 9 was #F5F7FA; a holding there was indistinguishable from the
# blend, and slots go by catalogue position, so four holdings were enough to collide.
COLORS = ["#3B9EFF", "#FF922B", "#D0A2FF", "#FFE14A", "#FF5263", "#35E0CE",
          "#C0ED55", "#FF80CB", "#7C5CFF", "#BCA383", "#90A4C2", "#00C853"]
BLEND_COLOR = "#FFFFFF"


def fade(color, alpha=0.42):
    """Hex to rgba. The holdings recede on the canvas while keeping their identity in the
    legend, where the swatch and the reading still carry the full colour."""
    value = color.lstrip("#")
    red, green, blue = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({red},{green},{blue},{alpha})"


def chart_series(frame, labels, colors, emphasis=None, closes=None):
    """`emphasis` names the one column that is not a holding.

    With a blend on the chart the holdings are its parts, so they are drawn back and it is
    drawn forward. Without one, nothing is subordinate and every line keeps full strength.

    `closes` is the day's quote shown beside the reading -- unadjusted, whatever basis the
    line is drawn on, since an adjusted price was never traded. A column it lacks (the blend)
    shows no price rather than a made-up one.
    """
    def quotes(s):
        if closes is None or s not in closes:
            return None
        return {t.strftime("%Y-%m-%d"): float(v) for t, v in closes[s].dropna().items()}
    return [dict(name=labels[s], color=colors[s], prices=quotes(s),
                 line=colors[s] if emphasis is None or s == emphasis else fade(colors[s]),
                 width=3 if s == emphasis else 2,
                 points=[dict(time=t.strftime("%Y-%m-%d"), value=float(v)) for t, v in frame[s].items()])
            for s in frame.columns]


def render_chart(frame, labels, colors, view, emphasis=None, key="performance_chart", closes=None,
                 axis_names=False):
    """`key` must differ per chart: two of these on one page share a component registry.

    `axis_names` puts each line's name on its axis reading. The configurations need it: they
    have no ticker to recognise them by and a dozen can share the column, so colour alone
    leaves the reader matching swatches against the legend below."""
    series = chart_series(frame, labels, colors, emphasis, closes)
    return _component(data=dict(series=series, end=frame.index[-1].strftime("%Y-%m-%d"), view=view,
                                axis_names=axis_names), key=key, width="stretch", height="content")
