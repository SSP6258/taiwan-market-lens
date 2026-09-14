"""Reproducible retirement study. Units: TWD ten-thousands. Not app code."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True)

def download():
    symbols = ['^TWII', 'QQQ', 'LQD', 'VCLT', 'SHY', 'BIL', 'SPY', 'EFA', 'EEM', 'VT', 'TWD=X']
    for s in symbols:
        p = DATA / (s.replace('^','').replace('=','_') + '.csv')
        if p.exists():
            continue
        h = yf.Ticker(s).history(start='2003-01-01', end='2026-09-01', auto_adjust=False)
        if h.empty:
            raise RuntimeError('No history: ' + s)
        h.index = h.index.tz_localize(None)
        h.to_csv(p)
        print(s, len(h), str(h.index[0]), str(h.index[-1]), flush=True)

def read(s):
    return pd.read_csv(DATA / (s.replace('^','').replace('=','_') + '.csv'), index_col=0, parse_dates=True)

def monthly():
    # Independently observed month-end closes; no daily cross-market forward fill.
    fx = read('TWD=X')['Close']; fx = fx.where(fx.between(20,40)).resample('ME').last()
    tw = read('^TWII')['Close'].dropna()
    daily = tw.pct_change().dropna()
    twtr = (1 + daily + .035/252).cumprod()
    lev = (1 + 2*(daily + .035/252) - .015/252).cumprod()
    out = pd.DataFrame({'tw':twtr.resample('ME').last().pct_change(fill_method=None),
                        'lev':lev.resample('ME').last().pct_change(fill_method=None)})
    for s in ['QQQ','LQD','VCLT','SHY','BIL','SPY','EFA','EEM','VT']:
        px = read(s)['Adj Close'].resample('ME').last()
        out[s] = (px*fx).pct_change(fill_method=None)
    # Pre-VT proxy is monthly rebalanced 60/30/10, explicitly synthetic.
    synth = .6*out.SPY+.3*out.EFA+.1*out.EEM
    out['world'] = out.VT.combine_first(synth)
    out['short'] = out.BIL.combine_first(out.SHY)
    out['long'] = out.VCLT.combine_first(out.LQD)
    result = out[['tw','QQQ','LQD','lev','world','short','long']].dropna()
    gaps = result.index.to_period('M').astype(int).to_series().diff().ne(1).cumsum().to_numpy()
    result = max((g for _,g in result.groupby(gaps)), key=len)
    assert not result.isna().any().any()
    assert (result.index.to_period('M').astype(int).to_series().diff().dropna()==1).all()
    assert result.abs().max().max()<.7
    result.to_csv(ROOT/'monthly_returns.csv')
    return result

def simulate(r, interest=.03, inflation=0, payout=.0627, yield_mode=False, collateral_discount=False):
    """r[path,month,7]. Annual withdrawals at start; monthly return and interest.
    Dividend cash is subtracted from total-return wealth: never counted twice.
    Unconstrained diagnostic paths continue after thresholds; these are NOT executable loans.
    """
    n, months, _ = r.shape
    a = np.tile([600.,600.,1500.,300.],(n,1)); b = np.tile([2700.,300.],(n,1))
    debt = np.zeros((n,2)); maxltv=np.zeros((n,2)); first=np.full((n,2),np.nan)
    history=[]; peak=np.full((n,2),3000.); dd=np.zeros((n,2)); peakdebt=debt.copy()
    for m in range(months):
        if m%12==0:
            spending=150*(1+inflation)**(m//12)
            cash1=np.minimum(a[:,2], (a[:,2] if yield_mode else 1500)*payout)
            a[:,2]-=cash1
            transfer=.04*b[:,0]; b[:,0]-=transfer; b[:,1]+=transfer
            cash5=.25*b[:,1]; b[:,1]-=cash5
            cash=np.column_stack([cash1,cash5]); shortfall=spending-cash
            debt+=np.maximum(shortfall,0)
            surplus=np.maximum(-shortfall,0); repay=np.minimum(debt,surplus)
            debt-=repay; surplus-=repay
            a[:,2]+=surplus[:,0]; b[:,1]+=surplus[:,1]
            if m==0:
                assert np.allclose(a.sum(1)-debt[:,0],2850)
                assert np.allclose(b.sum(1)-debt[:,1],2850)
        # Check immediately after cash movements AND month-end marks.
        for stage in range(2):
            if stage:
                a*=1+r[:,m,:4]; b*=1+r[:,m,4:6]
                debt*=(1+interest)**(1/12)
            gross=np.column_stack([a.sum(1),b.sum(1)])
            collateral=gross.copy()
            if collateral_discount:
                collateral[:,0]-=a[:,3]
            ltv=debt/np.maximum(collateral,1e-12)
            maxltv=np.maximum(maxltv,ltv)
            hit=(ltv>=.5)&np.isnan(first); first[hit]=(m+1)/12
            net=gross-debt; peak=np.maximum(peak,net); dd=np.minimum(dd,net/peak-1)
            peakdebt=np.maximum(peakdebt,debt)
        if n==1:
            history.append([m+1,*gross[0],*debt[0],*net[0],*ltv[0]])
    stats=[]
    for j in range(2):
        safe=maxltv[:,j]<.5
        stats.append({'strategy':1 if j==0 else 5,'cross50_pct':float(100*np.mean(~safe)),
            'cross60_pct':float(100*np.mean(maxltv[:,j]>=.6)),
            'cross70_pct':float(100*np.mean(maxltv[:,j]>=.7)),
            'net_nonpositive_pct':float(100*np.mean(dd[:,j]<=-1)),
            'median_peak_ltv_pct':float(100*np.median(maxltv[:,j])),
            'p95_peak_ltv_pct':float(100*np.quantile(maxltv[:,j],.95)),
            'median_final_net_unconstrained':float(np.median(net[:,j])),
            'p05_final_net_unconstrained':float(np.quantile(net[:,j],.05)),
            'median_final_net_never_cross50':float(np.median(net[safe,j])) if safe.any() else None,
            'median_peak_debt':float(np.median(peakdebt[:,j])),
            'median_first_cross_year_if_cross':float(np.nanmedian(first[:,j])) if (~safe).any() else None})
    return stats, history

def bootstrap(arr, n=4000, years=40, block=12):
    rng=np.random.default_rng(9142026)
    chunks=int(np.ceil(years*12/block))
    starts=rng.integers(0,len(arr)-block+1,size=(n,chunks))
    idx=(starts[:,:,None]+np.arange(block)).reshape(n,-1)[:,:years*12]
    return arr[idx]

def main():
    download(); df=monthly(); arr=df.to_numpy()
    print('WINDOW',df.index[0],df.index[-1],len(df),flush=True)
    summary={'window':[str(df.index[0].date()),str(df.index[-1].date())], 'months':len(df),
        'geometric_returns':dict(zip(df.columns,((1+df).prod()**(12/len(df))-1).round(6))), 'runs':{}}
    for start in [0, int(np.searchsorted(df.index,pd.Timestamp('2007-10-01')))]:
        stats,h=simulate(arr[None,start:,:]); key='history_'+str(df.index[start].date())
        summary['runs'][key]=stats
        pd.DataFrame(h,columns=['month','gross1','gross5','debt1','debt5','net1','net5','ltv1','ltv5']).to_csv(ROOT/(key+'.csv'),index=False)
    paths=bootstrap(arr)
    cases=[('base',{}),('interest5',{'interest':.05}),('inflation2',{'inflation':.02}),
           ('dividend4.5',{'payout':.045}),('variable_dividend6.27',{'yield_mode':True}),
           ('exclude_leveraged_collateral',{'collateral_discount':True})]
    for name,kw in cases:
        summary['runs'][name]=simulate(paths,**kw)[0]
        print(name,summary['runs'][name],flush=True)
    longpaths=paths.copy(); longpaths[:,:,2]=longpaths[:,:,6]
    summary['runs']['long_bond_proxy']=simulate(longpaths)[0]
    # Conservative scenario: subtract 3 percentage points of annual log returns from ALL stock legs.
    low=paths.copy()
    for col,drag in [(0,.03),(1,.03),(3,.06),(4,.03)]:
        low[:,:,col]=(1+low[:,:,col])*np.exp(-drag/12)-1
    summary['runs']['equities_minus3pp']=simulate(low)[0]
    summary['runs']['block24']=simulate(bootstrap(arr,block=24))[0]
    # Actual VT + VCLT era, no synthetic world or short-duration LQD for corporate leg.
    recent=df.loc['2010-01-01':].copy(); recent['LQD']=recent['long']
    summary['runs']['since2010_long_bonds']=simulate(bootstrap(recent.to_numpy()))[0]
    # Remove the sample's Taiwan/Nasdaq outperformance while retaining monthly shocks.
    logmeans=np.log1p(arr).mean(axis=0)*12
    neutral=paths.copy()
    for col in [0,1,4]:
        drag=logmeans[col]-np.log1p(.08)
        neutral[:,:,col]=(1+paths[:,:,col])*np.exp(-drag/12)-1
        if col==0:
            neutral[:,:,3]=(1+paths[:,:,3])*np.exp(-2*drag/12)-1
    summary['runs']['equities_equal8']=simulate(neutral)[0]
    summary['runs']['equities_equal8_inflation2']=simulate(neutral,inflation=.02)[0]
    summary['runs']['equities_equal8_interest5']=simulate(neutral,interest=.05)[0]
    neutral_long=neutral.copy(); neutral_long[:,:,2]=neutral_long[:,:,6]
    summary['runs']['equities_equal8_long_bond']=simulate(neutral_long)[0]
    summary['runs']['equities_equal8_variable_dividend']=simulate(neutral,yield_mode=True)[0]
    summary['runs']['equities_equal8_dividend4.5']=simulate(neutral,payout=.045)[0]
    summary['runs']['horizon30']=simulate(bootstrap(arr,years=30))[0]
    for target in [.09,.10,.11,.12]:
        advantage=neutral.copy()
        delta=np.log1p(target)-np.log1p(.08)
        for col,mult in [(0,1),(1,1),(3,2)]:
            advantage[:,:,col]=(1+advantage[:,:,col])*np.exp(mult*delta/12)-1
        summary['runs']['tw_qqq_target_'+str(target)]=simulate(advantage)[0]
    (ROOT/'results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    pd.DataFrame([dict(scenario=k,**s) for k,v in summary['runs'].items() for s in v]).to_csv(ROOT/'summary.csv',index=False)
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':
    main()




