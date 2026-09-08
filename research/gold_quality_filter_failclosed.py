import json, math, itertools
import numpy as np
import pandas as pd

import gold_m5_discovery_spike as g
import gold_m5_multiedge as m
import gold_m5_volume_profile_ablation as vp
import gold_m5_vwap_ladder_ablation as vw
import gold_m5_vwap_consensus_ablation as vc
import gold_champion_execution_stress as s

HIST_URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
GETDATA='/tmp/XAUUSD.csv'
EXT_START=pd.Timestamp('2026-07-23',tz='UTC')
EXT_END=pd.Timestamp('2026-09-05',tz='UTC')
FOLDS=[
 ('ERA1',pd.Timestamp('2021-09-08',tz='UTC'),pd.Timestamp('2023-01-01',tz='UTC')),
 ('ERA2',pd.Timestamp('2023-01-01',tz='UTC'),pd.Timestamp('2024-01-01',tz='UTC')),
 ('ERA3',pd.Timestamp('2024-01-01',tz='UTC'),pd.Timestamp('2025-01-01',tz='UTC')),
]
# Freeze exit/risk management to the best multi-era robust plateau point before this quality-filter search.
PARAMS={'atr_floor':0.80,'beR':2.25,'max_lots':3,'targetR':28.0,'hold_bars':216}
COSTS=[('BASE08',.08,0.),('STRESS15_05',.15,.05)]
EDGESETS=[
 ('BRK',),('EXP',),('PULL',),
 ('BRK','EXP'),('BRK','PULL'),('EXP','PULL'),('BRK','EXP','PULL')
]
VWAPS=['WEEK_PLUS_ANY','STRICT2','W_REL2_PRICE2','DW_REL_PRICE2','REL2_PRICE2','NINE6']
PROFILES=['POC','VA_OUT','POC_NEAR_1ATR','POC_MOMENTUM_025ATR']


def bounds(idx,a,b):
    z=np.flatnonzero(np.asarray((idx>=a)&(idx<b)))
    return int(z[0]),int(z[-1])


def set_urls(urls,end=None):
    g.URLS=list(urls); m.g.URLS=g.URLS; vp.g.URLS=g.URLS; vw.g.URLS=g.URLS; vc.g.URLS=g.URLS; s.g.URLS=g.URLS
    if end is not None: g.END=end


def base_arrays(x):
    o=x.open.to_numpy(float);h=x.high.to_numpy(float);lo=x.low.to_numpy(float);c=x.close.to_numpy(float)
    atr=x.atr14.to_numpy(float);vol=x.tick_volume.to_numpy(float)
    slo=x.low.rolling(7,min_periods=1).min().to_numpy(float);shi=x.high.rolling(7,min_periods=1).max().to_numpy(float)
    return o,h,lo,c,atr,vol,slo,shi


def profile_masks(x,h,lo,c,atr,vol):
    poc,vah,val=vp.profile_levels(h,lo,c,vol,288,32,3,.70)
    ok=np.isfinite(poc)&np.isfinite(vah)&np.isfinite(val)&np.isfinite(atr)&(atr>0)
    out={}
    out['POC']=(ok&(c>poc),ok&(c<poc))
    out['VA_OUT']=(ok&(c>vah),ok&(c<val))
    out['POC_NEAR_1ATR']=(ok&(c>poc)&((c-poc)<=1.0*atr),ok&(c<poc)&((poc-c)<=1.0*atr))
    out['POC_MOMENTUM_025ATR']=(ok&(c>poc)&((c-poc)>=.25*atr),ok&(c<poc)&((poc-c)>=.25*atr))
    return {k:(pd.Series(a,index=x.index),pd.Series(b,index=x.index)) for k,(a,b) in out.items()}


def build_context(x):
    idx=x.index; ed=m.build_edges(x)
    o,h,lo,c,atr,vol,slo,shi=base_arrays(x)
    em={nm:(ed[nm][0].fillna(False),ed[nm][1].fillna(False)) for nm in ('BRK','EXP','PULL')}
    f=vw.vwap_ladder(x,3,True); vm=vc.mk_masks(x,f)
    pm=profile_masks(x,h,lo,c,atr,vol)
    return idx,(o,h,lo,c,atr,slo,shi),em,vm,pm


def signal_for(idx,em,vm,pm,edges,vwap_name,profile_name):
    L=pd.Series(False,index=idx);S=pd.Series(False,index=idx)
    for e in edges:
        L|=em[e][0];S|=em[e][1]
    clash=L&S;L&=~clash;S&=~clash
    vL,vS=vm[vwap_name]; pL,pS=pm[profile_name]
    L=(L&vL&pL).fillna(False);S=(S&vS&pS).fillna(False)
    return L.to_numpy(np.bool_),S.to_numpy(np.bool_)


def run_cell(arr,L,S,b,cost,slip):
    af=PARAMS['atr_floor'];be=PARAMS['beR'];ml=PARAMS['max_lots'];tp=PARAMS['targetR'];mh=PARAMS['hold_bars']
    return s.pack(s.sim_stress(*arr,L,S,b[0],b[1],af,be,ml,tp,mh,cost,slip,1,1))


def score_config(cells):
    # Fail closed: every era must remain meaningfully positive under both base and stress.
    for q in cells:
        if q['lots'] < 80 or q['ret'] <= 0 or q['pf'] <= 1.05 or q['avgR'] <= 0:
            return -1e12
    logs=[math.log1p(q['ret']/100.) for q in cells]
    worst=min(logs);mean=sum(logs)/len(logs);dds=[q['dd'] for q in cells]
    # Robustness first: weakest regime dominates; then mean; DD penalty.
    return 2.5*worst + mean - .02*max(dds) - .006*sum(dds)/len(dds)


def historical_select():
    set_urls(HIST_URLS,pd.Timestamp('2026-07-23',tz='UTC'))
    x=g.prep();idx,arr,em,vm,pm=build_context(x)
    folds=[(nm,bounds(idx,a,b)) for nm,a,b in FOLDS]
    hold=bounds(idx,pd.Timestamp('2025-01-01',tz='UTC'),g.END)
    full=bounds(idx,g.START,g.END)
    rows=[]
    # Warm JIT once.
    L0,S0=signal_for(idx,em,vm,pm,('BRK','EXP','PULL'),'WEEK_PLUS_ANY','POC')
    b0=folds[0][1];run_cell(arr,L0,S0,(b0[0],min(b0[0]+1000,b0[1])),.08,0.)
    for edges,vn,pn in itertools.product(EDGESETS,VWAPS,PROFILES):
        L,S=signal_for(idx,em,vm,pm,edges,vn,pn)
        details={};cells=[]
        for nm,b in folds:
            base=run_cell(arr,L,S,b,.08,0.);stress=run_cell(arr,L,S,b,.15,.05)
            details[nm]={'base':base,'stress':stress};cells.extend([base,stress])
        sc=score_config(cells)
        rows.append((sc,edges,vn,pn,details,int(L.sum()+S.sum())))
        print('SCREEN', '+'.join(edges),vn,pn,'score',round(sc,5),flush=True)
    rows.sort(reverse=True,key=lambda z:z[0])
    qualified=[r for r in rows if r[0]>-1e11]
    if not qualified:
        return {'error':'NO_QUALIFIED_CONFIGURATION','grid_size':len(rows)},None
    win=qualified[0]
    sc,edges,vn,pn,details,nsig=win
    L,S=signal_for(idx,em,vm,pm,edges,vn,pn)
    holdres={nm:run_cell(arr,L,S,hold,cost,slip) for nm,cost,slip in COSTS}
    fullres={nm:run_cell(arr,L,S,full,cost,slip) for nm,cost,slip in COSTS}
    top=[]
    for r in qualified[:10]:
        top.append({'score':r[0],'edges':list(r[1]),'vwap':r[2],'profile':r[3],'eras':r[4],'signals':r[5]})
    selected={'edges':edges,'vwap':vn,'profile':pn}
    report={
      'grid_size':len(rows),'qualified':len(qualified),'selection_data':'ONLY ERA1/ERA2/ERA3 before 2025, base+stress',
      'frozen_params':PARAMS,'risk_rule':'0.36% current MTM equity per fresh lot; fresh signal required for every add; prior lots protected before add',
      'selected':{'score':sc,'edges':list(edges),'vwap':vn,'profile':pn,'eras':details,'signals':nsig},
      'holdout_2025_to_2026_07_22':holdres,'full_historical':fullres,'top10_pre2025':top,
      'guardrail':'2025+ holdout is reported after selection and is NOT used to replace the pre-2025 winner.'
    }
    return report,selected


def external_eval(selected):
    z=pd.read_csv(GETDATA).rename(columns={'datetime':'time','volume':'tick_volume'})
    z['time']=pd.to_datetime(z.time,utc=True)
    z=z[['time','open','high','low','close','tick_volume']].dropna().sort_values('time')
    p='/tmp/getdata_quality_norm.csv';z.to_csv(p,index=False)
    set_urls([p],EXT_END)
    x=g.prep();idx,arr,em,vm,pm=build_context(x)
    b=bounds(idx,EXT_START,EXT_END)
    L,S=signal_for(idx,em,vm,pm,tuple(selected['edges']),selected['vwap'],selected['profile'])
    out={nm:run_cell(arr,L,S,b,cost,slip) for nm,cost,slip in COSTS}
    return {
      'feed':'GetData XAUUSD M1','window':[str(EXT_START),str(EXT_END)],'frozen_selected':selected,
      'results':out,'selection_guardrail':'No GetData metric was available to or used by historical_select().',
      'limitations':['OHLC M1/M5 replay, not bid/ask tick execution','GetData has been used in prior research, so it is corroborating external evidence, not pristine holdout']
    }


def main():
    hist,selected=historical_select()
    ext=None if selected is None else external_eval(selected)
    print('RESULT_JSON_START')
    print(json.dumps({'historical':hist,'external':ext},default=float))
    print('RESULT_JSON_END')

if __name__=='__main__': main()
