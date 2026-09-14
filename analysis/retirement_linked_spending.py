"""Same dynamic consumption for both strategies, set by retirement 5. Amounts in TWD 10,000."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from retirement_compare import bootstrap
ROOT=Path(__file__).resolve().parent

def simulate_linked(r, interest=.03, payout=.0627, yield_mode=False, real_inflation=.02):
    n,months,_=r.shape
    a=np.tile([600.,600.,1500.,300.],(n,1)); b=np.tile([2700.,300.],(n,1))
    debt=np.zeros(n); maxltv=np.zeros(n); peakdebt=np.zeros(n)
    peak=np.full((n,2),3000.); maxdd=np.zeros((n,2)); first=np.full(n,np.nan)
    incomes=[]; annual=[]; history=[]
    for m in range(months):
        if m%12==0:
            cash1=np.minimum(a[:,2],(a[:,2] if yield_mode else 1500)*payout)
            a[:,2]-=cash1
            tr=.04*b[:,0]; b[:,0]-=tr; b[:,1]+=tr
            spending=.25*b[:,1]; b[:,1]-=spending
            gap=spending-cash1
            added=np.maximum(gap,0); surplus=np.maximum(-gap,0)
            repay=np.minimum(debt,surplus); debt+=added-repay; a[:,2]+=surplus-repay
            incomes.append(spending.copy())
            if n==1: annual.append([m//12+1,spending[0],cash1[0],added[0],repay[0],debt[0]])
            if m==0:
                assert np.allclose(a.sum(1)-debt,3000-spending)
                assert np.allclose(b.sum(1),3000-spending)
        for stage in range(2):
            if stage:
                a*=1+r[:,m,:4]; b*=1+r[:,m,4:6]; debt*=(1+interest)**(1/12)
            ltv=debt/np.maximum(a.sum(1),1e-12)
            maxltv=np.maximum(maxltv,ltv); peakdebt=np.maximum(peakdebt,debt)
            hit=(ltv>=.5)&np.isnan(first); first[hit]=(m+1)/12
            net=np.column_stack([a.sum(1)-debt,b.sum(1)])
            peak=np.maximum(peak,net); maxdd=np.minimum(maxdd,net/peak-1)
        if n==1: history.append([m+1,a.sum(),b.sum(),debt[0],net[0,0],net[0,1],ltv[0]])
    income=np.asarray(incomes)
    real=income/((1+real_inflation)**np.arange(len(income)))[:,None]
    mins=real.min(axis=0); safe=maxltv<.5
    changes=real[1:]/real[:-1]-1
    stats={'cross50_ret1_pct':float((~safe).mean()*100),
        'cross60_ret1_pct':float((maxltv>=.6).mean()*100),'cross70_ret1_pct':float((maxltv>=.7).mean()*100),
        'cross50_ret5_pct':0.,'peak_debt_ret5':0.,
        'median_peak_ltv_ret1_pct':float(np.median(maxltv)*100),
        'median_peak_debt_ret1':float(np.median(peakdebt)),
        'median_first_cross_year':float(np.nanmedian(first)) if (~safe).any() else None,
        'final_ret1_debtfree_pct':float((debt<1e-8).mean()*100),
        'ret1_wealth_gt_ret5_and_never_cross50_pct':float(((net[:,0]>net[:,1])&safe).mean()*100),
        'median_final_net_unconstrained':np.median(net,axis=0).tolist(),
        'median_final_net_both_on_ret1_safe_paths':np.median(net[safe],axis=0).tolist() if safe.any() else None,
        'median_max_net_drawdown_pct':(np.median(maxdd,axis=0)*100).tolist(),
        'real_spending_min_p05':float(np.quantile(mins,.05)),
        'real_spending_min_median':float(np.median(mins)),
        'ever_real_spending_below75_pct':float((mins<75).mean()*100),
        'ever_real_spending_below100_pct':float((mins<100).mean()*100),
        'worst_real_annual_income_change_p05_pct':float(np.quantile(changes.min(axis=0),.05)*100) if len(changes) else None,
        'income_years':{str(y):{'nominal_p05_median_p95':np.quantile(income[y-1],[.05,.5,.95]).tolist(),
                             'real_p05_median_p95':np.quantile(real[y-1],[.05,.5,.95]).tolist()}
                        for y in [1,5,10,20,30,40] if y<=len(income)}}
    return stats,history,annual

def main():
    df=pd.read_csv(ROOT/'monthly_returns.csv',index_col=0,parse_dates=True); arr=df.to_numpy()
    paths=bootstrap(arr); means=np.log1p(arr).mean(0)*12
    neutral=paths.copy()
    for col in [0,1,4]:
        drag=means[col]-np.log1p(.08)
        neutral[:,:,col]=(1+paths[:,:,col])*np.exp(-drag/12)-1
        if col==0: neutral[:,:,3]=(1+paths[:,:,3])*np.exp(-2*drag/12)-1
    runs={}
    for name,p,kw in [('historical_bootstrap',paths,{}),('equal8',neutral,{}),
                      ('equal8_interest5',neutral,{'interest':.05}),
                      ('equal8_variable_dividend',neutral,{'yield_mode':True}),
                      ('equal8_dividend4.5',neutral,{'payout':.045}),
                      ('block24',bootstrap(arr,block=24),{})]:
        runs[name]=simulate_linked(p,**kw)[0]
    lng=neutral.copy(); lng[:,:,2]=lng[:,:,6]
    runs['equal8_longbond']=simulate_linked(lng)[0]
    low=neutral.copy()
    for col,mult in [(0,1),(1,1),(3,2),(4,1)]:
        low[:,:,col]=(1+low[:,:,col])*np.exp(mult*(np.log1p(.05)-np.log1p(.08))/12)-1
    runs['equal5']=simulate_linked(low)[0]
    for start in [0,int(np.searchsorted(df.index,pd.Timestamp('2007-10-01')))]:
        key='history_'+str(df.index[start].date()); s,h,a=simulate_linked(arr[None,start:,:]);runs[key]=s
        pd.DataFrame(h,columns=['month','gross1','gross5','debt1','net1','net5','ltv1']).to_csv(ROOT/('linked_'+key+'.csv'),index=False)
        pd.DataFrame(a,columns=['year','shared_spending','dividend1','new_debt1','repay1','debt1_before_interest']).to_csv(ROOT/('linked_'+key+'_annual.csv'),index=False)
    summary={'scenario':'Both consume retirement5 annual withdrawal; retirement5 never borrows',
             'seed':9142026,'paths':4000,'years':40,'window':[str(df.index[0].date()),str(df.index[-1].date())],
             'deflator_only':.02,'runs':runs}
    (ROOT/'linked_results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__': main()

