import json, math
import numpy as np
import pandas as pd

import gold_duka_numba_rebuild as r
import gold_duka_winner_crosscheck as w
from gold_duka_microfeatures import compute_features

# Frozen execution-aware winner. No management tuning in this experiment.
BE=4.0; MAXLOTS=2; TPR=10.0; HOLD_MIN=24*60
FOLDS=r.FOLDS
HOLD=r.HOLD


def aligned_features(sig, exe):
    f=compute_features(exe)
    ens=pd.DatetimeIndex(exe.time).as_unit('ns').asi8
    dns=pd.DatetimeIndex(sig.index+pd.Timedelta(minutes=5)).as_unit('ns').asi8
    pos=np.searchsorted(ens,dns)
    good=(pos>=0)&(pos<len(ens))
    good &= np.where(good,ens[np.minimum(pos,len(ens)-1)]==dns,False)
    out=pd.DataFrame(index=sig.index,columns=f.columns,dtype=float)
    gi=np.flatnonzero(good)
    out.iloc[gi]=f.iloc[pos[good]].to_numpy(float)
    return out


def quality_masks(f):
    one=pd.Series(True,index=f.index)
    sr=f.spread_ratio
    m1=f.mom1;m5=f.mom5;m15=f.mom15;p=f.pressure5;clv=f.clv5;rx=f.range_exp5
    def ds(long_cond,short_cond): return (long_cond.fillna(False),short_cond.fillna(False))
    return {
      'NONE':(one,one),
      'SPR_LE100':ds(sr<=1.00,sr<=1.00),
      'SPR_LE125':ds(sr<=1.25,sr<=1.25),
      'SPR_LE150':ds(sr<=1.50,sr<=1.50),
      'MOM1':ds(m1>0,m1<0),
      'MOM5':ds(m5>0,m5<0),
      'MOM15':ds(m15>0,m15<0),
      'MOM5_15':ds((m5>0)&(m15>0),(m5<0)&(m15<0)),
      'PRESS0':ds(p>0,p<0),
      'PRESS20':ds(p>=.20,p<=-.20),
      'CLV0':ds(clv>0,clv<0),
      'RANGE_GE08':ds(rx>=.80,rx>=.80),
      'RANGE_08_20':ds((rx>=.80)&(rx<=2.0),(rx>=.80)&(rx<=2.0)),
      'M5_PRESS':ds((m5>0)&(p>0),(m5<0)&(p<0)),
      'M5_CLV':ds((m5>0)&(clv>0),(m5<0)&(clv<0)),
      'M15_PRESS':ds((m15>0)&(p>0),(m15<0)&(p<0)),
      'M5_15_SPR125':ds((m5>0)&(m15>0)&(sr<=1.25),(m5<0)&(m15<0)&(sr<=1.25)),
      'M5_PRESS_SPR125':ds((m5>0)&(p>0)&(sr<=1.25),(m5<0)&(p<0)&(sr<=1.25)),
      'M5_CLV_SPR125':ds((m5>0)&(clv>0)&(sr<=1.25),(m5<0)&(clv<0)&(sr<=1.25)),
      'M5_15_PRESS':ds((m5>0)&(m15>0)&(p>0),(m5<0)&(m15<0)&(p<0)),
      'M5_15_CLV':ds((m5>0)&(m15>0)&(clv>0),(m5<0)&(m15<0)&(clv<0)),
      'M5_15_PRESS_SPR125':ds((m5>0)&(m15>0)&(p>0)&(sr<=1.25),(m5<0)&(m15<0)&(p<0)&(sr<=1.25)),
      'M5_PRESS_RANGE':ds((m5>0)&(p>0)&(rx>=.8)&(rx<=2.0),(m5<0)&(p<0)&(rx>=.8)&(rx<=2.0)),
    }


def score(cells):
    # Must survive every pre-2025 era at both variable spread-only and +0.05R extra.
    for q in cells:
        if q['ret']<=0 or q['pf']<=1.05 or q['avgR']<=0 or q['lots']<80:return -1e12
    lg=[math.log1p(q['ret']/100) for q in cells]
    d=[q['dd'] for q in cells]
    pf=[q['pf'] for q in cells]
    return 2.5*min(lg)+sum(lg)/len(lg)+.15*min(pf)-.018*max(d)-.004*np.mean(d)


def main():
    # Use exact frozen winner signal construction; only add execution-feed quality masks.
    sig=w.build_winner_signals()
    exe,ediag=w.d.load_execution(); exe=exe.reset_index(drop=True)
    feats=aligned_features(sig,exe); qm=quality_masks(feats)

    ens=pd.DatetimeIndex(exe.time).as_unit('ns').asi8
    dns=pd.DatetimeIndex(sig.index+pd.Timedelta(minutes=5)).as_unit('ns').asi8
    pos=np.searchsorted(ens,dns);valid=(pos>=0)&(pos<len(ens));valid &= np.where(valid,ens[np.minimum(pos,len(ens)-1)]==dns,False)
    decision_id=np.full(len(exe),-1,np.int64);decision_id[pos[valid]]=np.flatnonzero(valid)
    arr=tuple(exe[c].to_numpy(float) for c in ['open_bid','high_bid','low_bid','close_bid','open_ask','high_ask','low_ask','close_ask'])

    es=sig.next_open_signal.to_numpy(float);av=sig.atr14.to_numpy(float);sl=sig.slo7.to_numpy(float);sh=sig.shi7.to_numpy(float)
    riskL=(es-np.minimum(sl-.1*av,es-.8*av))/es
    riskS=(np.maximum(sh+.1*av,es+.8*av)-es)/es
    baseL=sig.sigL.to_numpy(bool);baseS=sig.sigS.to_numpy(bool)
    folds=[(nm,r.interval(exe,a,b)) for nm,a,b in FOLDS]
    hold=r.interval(exe,HOLD[1],HOLD[2]);full=r.interval(exe,FOLDS[0][1],w.d.END)

    # Numba engine scenarios: index 0=spread-only, index2=+0.05R extra.
    rows=[];cache={}
    # warm compile
    bb=folds[0][1];rp=np.where(baseL,riskL,np.where(baseS,riskS,.01))
    r.sim_m1(*arr,decision_id,baseL,baseS,rp,bb[0],min(bb[0]+1000,bb[1]),BE,MAXLOTS,TPR,HOLD_MIN)
    for name,(qL,qS) in qm.items():
        L=baseL&qL.to_numpy(bool);S=baseS&qS.to_numpy(bool)
        rp=np.where(L,riskL,np.where(S,riskS,.01))
        cells=[];details={}
        for fn,b in folds:
            v,ca,ad,mo=r.sim_m1(*arr,decision_id,L,S,rp,b[0],b[1],BE,MAXLOTS,TPR,HOLD_MIN)
            q0=r.pack(v,ca,ad,mo,0);q5=r.pack(v,ca,ad,mo,2);cells.extend([q0,q5]);details[fn]={'spread_only':q0,'plus_005R':q5}
        sc=score(cells);rows.append((sc,name,L,S,rp,details));cache[name]=(L,S,rp)
        print('SCREEN',name,'score',round(sc,4),*[f"{fn}:{details[fn]['plus_005R']['ret']:.2f}/{details[fn]['plus_005R']['pf']:.3f}" for fn,_ in folds],flush=True)
    rows.sort(reverse=True,key=lambda x:x[0]);qual=[x for x in rows if x[0]>-1e11]
    print('QUALIFIED',len(qual),flush=True)
    # Reveal holdout only baseline + top five selected pre-2025.
    picks=[]
    base=[x for x in rows if x[1]=='NONE'][0];picks.append(base)
    for x in qual:
        if x[1]!='NONE' and len(picks)<6:picks.append(x)
    promoted=[]
    for sc,name,L,S,rp,details in picks:
        vh,ca,ad,mo=r.sim_m1(*arr,decision_id,L,S,rp,hold[0],hold[1],BE,MAXLOTS,TPR,HOLD_MIN)
        vf,caf,adf,mof=r.sim_m1(*arr,decision_id,L,S,rp,full[0],full[1],BE,MAXLOTS,TPR,HOLD_MIN)
        promoted.append({'name':name,'score':sc,'eras':details,
          'holdout_2025plus':{'spread_only':r.pack(vh,ca,ad,mo,0),'plus_005R':r.pack(vh,ca,ad,mo,2)},
          'full':{'spread_only':r.pack(vf,caf,adf,mof,0),'plus_005R':r.pack(vf,caf,adf,mof,2)}})
    print('RESULT_JSON_START')
    print(json.dumps({'base_candidate':'DUKA_EXEC_BRK_DWREL_POCMOM25','management':{'BE_R':BE,'max_lots':MAXLOTS,'TP_R':TPR,'hold_hours':24,'risk_pct_per_fresh':.36},
      'microfeatures':['spread_ratio/change','mid momentum 1/5/15m','5m close-location','5m candle-pressure proxy','5m range expansion'],
      'honesty':'All added features are Dukascopy BID/ASK price/execution features; no CVD/TPS/volume/order-book claims.',
      'causality':'Feature at M1 row t uses <=t only; signal is then filled on the next M1 open by the simulator.',
      'selection':'Pre-2025 ERA1/2/3 only; every era must have positive return, PF>1.05, avgR>0 at spread-only and +0.05R. Holdout exposed only baseline + top5.',
      'execution_data':ediag,'qualified':len(qual),'ranking':[{'name':x[1],'score':x[0],'eras':x[5]} for x in rows], 'promoted':promoted},default=float))
    print('RESULT_JSON_END')

if __name__=='__main__':main()
