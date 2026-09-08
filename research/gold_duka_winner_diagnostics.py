import json, math
import numpy as np
import pandas as pd
import gold_duka_numba_rebuild as r

# Frozen winner. NO parameter selection/tuning in this file.
BE=4.0; MAXLOTS=2; TP=10.0; HOLD_MIN=24*60
EXTRA_LABELS=['spread_only','plus_002R','plus_005R']


def winner_signals(sig):
    for en,vn,pn,L,S in r.masks(sig):
        if en=='BRK' and vn=='DW_REL_PRICE2' and pn=='POCMOM25':
            return L,S
    raise RuntimeError('Frozen winner mask not found')


def run_period(arr,decision_id,L,S,rp,exe,a,b):
    z=np.flatnonzero(np.asarray((pd.DatetimeIndex(exe.time)>=a)&(pd.DatetimeIndex(exe.time)<b)))
    if len(z)<2:return None
    v,ca,ad,mo=r.sim_m1(*arr,decision_id,L,S,rp,int(z[0]),int(z[-1]),BE,MAXLOTS,TP,HOLD_MIN)
    return {EXTRA_LABELS[i]:r.pack(v,ca,ad,mo,i) for i in range(3)}


def side_masks(L,S,side):
    if side=='BOTH':return L.copy(),S.copy()
    if side=='LONG':return L.copy(),np.zeros_like(S)
    if side=='SHORT':return np.zeros_like(L),S.copy()
    raise ValueError(side)


def main():
    sig,exe,arr,decision_id,riskL,riskS,ediag=r.prep()
    L,S=winner_signals(sig)
    rp=np.where(L,riskL,np.where(S,riskS,.01))
    start=pd.Timestamp('2021-09-08',tz='UTC');end=r.d.END

    # Direction attribution on full sample and untouched 2025+ period. No tuning.
    directions={}
    for side in ('BOTH','LONG','SHORT'):
        l,s=side_masks(L,S,side);rr=np.where(l,riskL,np.where(s,riskS,.01))
        directions[side]={
          'FULL':run_period(arr,decision_id,l,s,rr,exe,start,end),
          'HOLDOUT_2025PLUS':run_period(arr,decision_id,l,s,rr,exe,pd.Timestamp('2025-01-01',tz='UTC'),end)
        }

    # Calendar-year diagnostics. These reset equity and flatten at period boundaries, so they are diagnostic,
    # not a replacement for the continuous full-period equity curve.
    years={}
    for y in range(2021,2027):
        a=max(start,pd.Timestamp(f'{y}-01-01',tz='UTC'));b=min(end,pd.Timestamp(f'{y+1}-01-01',tz='UTC'))
        if a>=b:continue
        years[str(y)]={}
        for side in ('BOTH','LONG','SHORT'):
            l,s=side_masks(L,S,side);rr=np.where(l,riskL,np.where(s,riskS,.01))
            years[str(y)][side]=run_period(arr,decision_id,l,s,rr,exe,a,b)

    # Monthly fixed-winner diagnostics under conservative +0.05R extra cost.
    # Equity is reset and open trades flattened at each month end; max hold is only 24h, so boundary distortion is limited
    # but explicitly acknowledged.
    months=[]
    cur=pd.Timestamp(start.year,start.month,1,tz='UTC')
    if cur<start:cur=(cur+pd.offsets.MonthBegin(1))
    while cur<end:
        nxt=cur+pd.offsets.MonthBegin(1)
        a=max(start,cur);b=min(end,nxt)
        q=run_period(arr,decision_id,L,S,rp,exe,a,b)
        if q and q['plus_005R']['lots']>0:
            m=q['plus_005R'].copy();m['month']=cur.strftime('%Y-%m');months.append(m)
        cur=nxt

    rets=np.array([m['ret']/100. for m in months],float)
    pfs=np.array([m['pf'] for m in months],float)
    monthly_summary={
      'n_months':len(months),'positive_months_pct':float(100*np.mean(rets>0)) if len(rets) else 0,
      'median_return_pct':float(100*np.median(rets)) if len(rets) else 0,
      'mean_return_pct':float(100*np.mean(rets)) if len(rets) else 0,
      'p10_return_pct':float(100*np.percentile(rets,10)) if len(rets) else 0,
      'worst_month_pct':float(100*np.min(rets)) if len(rets) else 0,
      'best_month_pct':float(100*np.max(rets)) if len(rets) else 0,
      'months_over_10pct':int(np.sum(rets>.10)),'months_over_20pct':int(np.sum(rets>.20)),'months_over_100pct':int(np.sum(rets>1.0)),
      'median_pf':float(np.median(pfs)) if len(pfs) else 0,
    }

    # 3-month moving-block bootstrap of conservative monthly returns. This is sequence-risk diagnostics, not forecasting.
    rng=np.random.default_rng(20260909);N=10000;n=len(rets);block=3
    finals=np.empty(N);maxdds=np.empty(N)
    if n>=block:
        starts=np.arange(n-block+1)
        for k in range(N):
            seq=[]
            while len(seq)<n:
                j=int(rng.choice(starts));seq.extend(rets[j:j+block].tolist())
            seq=np.array(seq[:n]);eq=1.;peak=1.;md=0.
            for x in seq:
                eq*=max(1e-9,1+x);peak=max(peak,eq);md=max(md,(peak-eq)/peak)
            finals[k]=(eq-1)*100;maxdds[k]=md*100
        mc={
          'paths':N,'block_months':block,
          'final_return_p05_pct':float(np.percentile(finals,5)),'final_return_median_pct':float(np.median(finals)),'final_return_p95_pct':float(np.percentile(finals,95)),
          'maxdd_median_pct':float(np.median(maxdds)),'maxdd_p95_pct':float(np.percentile(maxdds,95)),
          'prob_final_loss_pct':float(100*np.mean(finals<0)),'prob_maxdd_over_30_pct':float(100*np.mean(maxdds>30)),
          'warning':'Bootstrap resamples observed monthly returns; it is not an independent market simulation and cannot capture unseen regimes.'
        }
    else:mc={}

    # Addition contribution: same frozen entry signal, same exits, but maxlots=1 vs maxlots=2.
    z=np.flatnonzero(np.asarray((pd.DatetimeIndex(exe.time)>=start)&(pd.DatetimeIndex(exe.time)<end)))
    noadd_v,ca,ad,mo=r.sim_m1(*arr,decision_id,L,S,rp,int(z[0]),int(z[-1]),BE,1,TP,HOLD_MIN)
    add_ablation={'MAX1_NO_ADDS':{EXTRA_LABELS[i]:r.pack(noadd_v,ca,ad,mo,i) for i in range(3)},'MAX2_FROZEN':directions['BOTH']['FULL']}

    print('RESULT_JSON_START')
    print(json.dumps({
      'candidate':'DUKA_EXEC_BRK_DWREL_POCMOM25','params':{'atr_floor_geometry':.8,'beR':BE,'maxlots':MAXLOTS,'tpR':TP,'hold_hours':24,'risk_pct_fresh':.36},
      'execution':'Dukascopy M1 bid/ask variable spread; +0/.02/.05R extra costs in parallel','execution_data':ediag,
      'directions':directions,'calendar_years':years,'monthly_plus005R':months,'monthly_summary_plus005R':monthly_summary,
      'monte_carlo_monthly_block_plus005R':mc,'addition_ablation':add_ablation,
      'methodology_notes':['No parameter changed based on 2025+ in this diagnostic','Calendar-year/monthly cells flatten at boundaries and reset equity; use them for regime consistency, not continuous compounded return','Monte Carlo is moving-block bootstrap of observed monthly returns, not a new out-of-sample test']},default=float))
    print('RESULT_JSON_END')

if __name__=='__main__':main()
