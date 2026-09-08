import json, math, itertools
import numpy as np
import pandas as pd
from numba import njit

import gold_quality_duka_bidask as qsel
import gold_quality_duka_bidask_corrected as corr

d=qsel.d

# Strictly pre-2025 selection. 2025+ is not touched until final winner is frozen.
FOLDS=[
 ('ERA1',pd.Timestamp('2021-09-08',tz='UTC'),pd.Timestamp('2023-01-01',tz='UTC')),
 ('ERA2',pd.Timestamp('2023-01-01',tz='UTC'),pd.Timestamp('2024-01-01',tz='UTC')),
 ('ERA3',pd.Timestamp('2024-01-01',tz='UTC'),pd.Timestamp('2025-01-01',tz='UTC')),
]
HOLD=('HOLDOUT_2025PLUS',pd.Timestamp('2025-01-01',tz='UTC'),d.END)
EXTRA=np.array([0.0,.02,.05],dtype=np.float64)
RISK=.0036

@njit(cache=True)
def sim_m1(ob,hb,lb,cb,oa,ha,la,ca,decision_id,sigL,sigS,riskpct,first,last,beR,maxlots,tpR,maxhold_min):
    ns=3
    bal=np.ones(ns); peak=np.ones(ns); dd=np.zeros(ns); wins=np.zeros(ns,np.int64); pos=np.zeros(ns); neg=np.zeros(ns); rtot=np.zeros(ns)
    dirs=np.zeros(4,np.int8); ent=np.zeros(4); stops=np.zeros(4); risks=np.zeros(4); targets=np.zeros(4); rc=np.zeros((4,ns)); opened=np.zeros(4,np.int64); prot=np.zeros(4,np.uint8)
    n=0; cdir=0; campaigns=0; adds=0; closed=0; maxopen=0
    pending=0; pending_add=0; pending_riskpct=0.0
    for i in range(first,last+1):
        # Fill a signal decided at the prior completed M5 boundary at this M1 open.
        if pending!=0:
            e=oa[i] if pending==1 else ob[i]
            rrisk=e*pending_riskpct
            if rrisk>0 and rrisk/e<=.012 and n<maxlots:
                st=e-pending*rrisk; tg=e+pending*tpR*rrisk
                # MTM current equity on executable sides.
                for sj in range(ns):
                    eq=bal[sj]
                    for k in range(n):
                        px=ob[i] if dirs[k]==1 else oa[i]
                        eq += rc[k,sj]*(dirs[k]*(px-ent[k])/risks[k])
                    cash=max(0.0,eq)*RISK
                    rc[n,sj]=cash
                dirs[n]=pending;ent[n]=e;stops[n]=st;risks[n]=rrisk;targets[n]=tg;opened[n]=i;prot[n]=0;n+=1
                if pending_add==1:adds+=1
                else:campaigns+=1
                cdir=pending
                if n>maxopen:maxopen=n
            pending=0;pending_add=0

        # Intraminute executable-side exits; conservative stop-first.
        newn=0
        for k in range(n):
            raw=1e100
            if dirs[k]==1:
                if lb[i]<=stops[k]:
                    fill=ob[i] if ob[i]<=stops[k] else stops[k];raw=(fill-ent[k])/risks[k]
                elif hb[i]>=targets[k]:raw=tpR
            else:
                if ha[i]>=stops[k]:
                    fill=oa[i] if oa[i]>=stops[k] else stops[k];raw=(ent[k]-fill)/risks[k]
                elif la[i]<=targets[k]:raw=tpR
            if raw==1e100 and i-opened[k]>=maxhold_min:
                px=cb[i] if dirs[k]==1 else ca[i];raw=dirs[k]*(px-ent[k])/risks[k]
            if raw!=1e100:
                closed+=1
                for sj in range(ns):
                    rr=raw-EXTRA[sj];bal[sj]+=rc[k,sj]*rr;rtot[sj]+=rr
                    if rr>0:wins[sj]+=1;pos[sj]+=rr
                    elif rr<0:neg[sj]-=rr
            else:
                if newn!=k:
                    dirs[newn]=dirs[k];ent[newn]=ent[k];stops[newn]=stops[k];risks[newn]=risks[k];targets[newn]=targets[k];opened[newn]=opened[k];prot[newn]=prot[k]
                    for sj in range(ns):rc[newn,sj]=rc[k,sj]
                newn+=1
        n=newn
        if n==0:cdir=0

        # At exact completed-M5 decision minutes, protect positions and possibly queue next-M1 entry.
        j=decision_id[i]
        if j>=0:
            allprot=n>0
            for k in range(n):
                px=cb[i] if dirs[k]==1 else ca[i]
                cr=dirs[k]*(px-ent[k])/risks[k]
                if prot[k]==0 and cr>=beR:
                    stops[k]=ent[k];prot[k]=1
                if prot[k]==0:allprot=False
            if cdir==0:
                if sigL[j] and not sigS[j]:pending=1;pending_add=0;pending_riskpct=riskpct[j]
                elif sigS[j] and not sigL[j]:pending=-1;pending_add=0;pending_riskpct=riskpct[j]
            elif n<maxlots and allprot:
                # Every add requires a fresh same-direction signal.
                if cdir==1 and sigL[j] and not sigS[j]:pending=1;pending_add=1;pending_riskpct=riskpct[j]
                elif cdir==-1 and sigS[j] and not sigL[j]:pending=-1;pending_add=1;pending_riskpct=riskpct[j]

        # conservative adverse-side DD mark
        for sj in range(ns):
            eq=bal[sj]
            for k in range(n):
                px=lb[i] if dirs[k]==1 else ha[i]
                eq += rc[k,sj]*(dirs[k]*(px-ent[k])/risks[k])
            if eq>peak[sj]:peak[sj]=eq
            cur=(peak[sj]-eq)/peak[sj] if peak[sj]>0 else 0.
            if cur>dd[sj]:dd[sj]=cur

    # Liquidate at segment end executable close.
    for k in range(n):
        px=cb[last] if dirs[k]==1 else ca[last];raw=dirs[k]*(px-ent[k])/risks[k];closed+=1
        for sj in range(ns):
            rr=raw-EXTRA[sj];bal[sj]+=rc[k,sj]*rr;rtot[sj]+=rr
            if rr>0:wins[sj]+=1;pos[sj]+=rr
            elif rr<0:neg[sj]-=rr
    out=np.zeros((ns,7))
    for sj in range(ns):
        out[sj,0]=(bal[sj]-1)*100
        out[sj,1]=100*wins[sj]/closed if closed else 0
        out[sj,2]=pos[sj]/neg[sj] if neg[sj]>0 else 99
        out[sj,3]=rtot[sj]/closed if closed else 0
        out[sj,4]=rtot[sj]
        out[sj,5]=dd[sj]*100
        out[sj,6]=closed
    return out,campaigns,adds,maxopen


def pack(v,campaigns,adds,maxopen,ix):
    q=v[ix]
    return {'ret':float(q[0]),'wr':float(q[1]),'pf':float(q[2]),'avgR':float(q[3]),'R_total':float(q[4]),'dd':float(q[5]),'lots':int(q[6]),'campaigns':int(campaigns),'adds':int(adds),'max_open':int(maxopen)}


def prep():
    sig=corr.build_signals_corrected();exe,ediag=d.load_execution()
    # Build execution arrays and map each M5 completion to its exact M1 row.
    exe=exe.reset_index(drop=True)
    times=pd.DatetimeIndex(exe.time).as_unit('ns')
    ns=times.asi8
    decision_time=pd.DatetimeIndex(sig.index+pd.Timedelta(minutes=5)).as_unit('ns').asi8
    pos=np.searchsorted(ns,decision_time)
    valid=(pos>=0)&(pos<len(ns))
    valid &= np.where(valid,ns[np.minimum(pos,len(ns)-1)]==decision_time,False)
    decision_id=np.full(len(exe),-1,np.int64)
    decision_id[pos[valid]]=np.flatnonzero(valid)
    # structural risk percent from signal source, translated proportionally to executable entry by simulator
    es=sig.next_open_signal.to_numpy(float);av=sig.atr14.to_numpy(float);sl=sig.slo7.to_numpy(float);sh=sig.shi7.to_numpy(float)
    # base risk distance differs by direction; keep both arrays later. Most masks direction-specific.
    riskL=(es-np.minimum(sl-.1*av,es-.8*av))/es
    riskS=(np.maximum(sh+.1*av,es+.8*av)-es)/es
    arrays=tuple(exe[c].to_numpy(float) for c in ['open_bid','high_bid','low_bid','close_bid','open_ask','high_ask','low_ask','close_ask'])
    return sig,exe,arrays,decision_id,riskL,riskS,ediag


def masks(sig):
    idx=sig.index;x=sig
    ed=d.m.build_edges(x)
    # Note build_edges expects the prepared columns already present in sig.
    edge_sets=[('PULL',),('EXP',),('BRK',),('EXP','PULL'),('BRK','PULL'),('BRK','EXP'),('BRK','EXP','PULL')]
    f=d.vw.vwap_ladder(x,3,True);vm=d.vc.mk_masks(x,f)
    c=x.close.to_numpy(float);h=x.high.to_numpy(float);lo=x.low.to_numpy(float);vol=x.tick_volume.to_numpy(float);atr=x.atr14.to_numpy(float)
    poc,vah,val=d.vp.profile_levels(h,lo,c,vol,288,32,3,.70);ok=np.isfinite(poc)&np.isfinite(atr)&(atr>0)
    profiles={
      'NONE':(pd.Series(True,index=idx),pd.Series(True,index=idx)),
      'POC':(pd.Series(ok&(c>poc),index=idx),pd.Series(ok&(c<poc),index=idx)),
      'POCMOM25':(pd.Series(ok&(c>poc)&((c-poc)>=.25*atr),index=idx),pd.Series(ok&(c<poc)&((poc-c)>=.25*atr),index=idx)),
      'VAOUT':(pd.Series(ok&(c>vah),index=idx),pd.Series(ok&(c<val),index=idx)),
    }
    vwaps=['WEEK_PLUS_ANY','W_REL2_PRICE2','DW_REL_PRICE2','STRICT2','REL2_PRICE2','NINE6']
    out=[]
    for edges in edge_sets:
      baseL=pd.Series(False,index=idx);baseS=pd.Series(False,index=idx)
      for e in edges:baseL|=ed[e][0].fillna(False);baseS|=ed[e][1].fillna(False)
      clash=baseL&baseS;baseL&=~clash;baseS&=~clash
      for vn in vwaps:
        vL,vS=vm[vn]
        for pn,(pL,pS) in profiles.items():
          L=(baseL&vL&pL).fillna(False).to_numpy(np.bool_);S=(baseS&vS&pS).fillna(False).to_numpy(np.bool_)
          out.append(('+'.join(edges),vn,pn,L,S))
    return out


def interval(exe,a,b):
    t=pd.DatetimeIndex(exe.time);z=np.flatnonzero(np.asarray((t>=a)&(t<b)));return int(z[0]),int(z[-1])


def robust_score(cells):
    # Require positive under spread-only and +0.02R extra in all 3 eras.
    for q in cells:
        if q['ret']<=0 or q['pf']<=1.05 or q['avgR']<=0 or q['lots']<70:return -1e12
    lg=[math.log1p(q['ret']/100) for q in cells];dds=[q['dd'] for q in cells]
    return 2.5*min(lg)+sum(lg)/len(lg)-.018*max(dds)-.005*np.mean(dds)


def main():
    sig,exe,arr,decision_id,riskL,riskS,ediag=prep();cfgs=masks(sig)
    folds=[(nm,interval(exe,a,b)) for nm,a,b in FOLDS]
    hold=interval(exe,HOLD[1],HOLD[2]);full=interval(exe,FOLDS[0][1],d.END)
    # First stage: execution-aware signal/filter quality, deliberately wide stop and no pyramiding.
    stage=[]
    # warm compile
    nm,vn,pn,L,S=cfgs[0];rp=np.where(L,riskL,np.where(S,riskS,.01));b=folds[0][1]
    sim_m1(*arr,decision_id,L,S,rp,b[0],min(b[0]+1000,b[1]),4.,1,12.,1440)
    for ci,(en,vn,pn,L,S) in enumerate(cfgs):
        rp=np.where(L,riskL,np.where(S,riskS,.01))
        cells=[];det={}
        for fn,b in folds:
            v,ca,ad,mo=sim_m1(*arr,decision_id,L,S,rp,b[0],b[1],4.,1,12.,1440)
            q0=pack(v,ca,ad,mo,0);q2=pack(v,ca,ad,mo,1);cells.extend([q0,q2]);det[fn]={'spread_only':q0,'plus_002R':q2}
        sc=robust_score(cells);stage.append((sc,en,vn,pn,L,S,det))
        if ci%30==0:print('STAGE1',ci,'/',len(cfgs),en,vn,pn,round(sc,4),flush=True)
    stage.sort(reverse=True,key=lambda z:z[0]);qual=[r for r in stage if r[0]>-1e11]
    print('STAGE1_QUALIFIED',len(qual),flush=True)
    # If nothing passes strict gate, still take top 6 finite scores based on soft score for diagnosis.
    top=qual[:6]
    if not top:
        def soft(r):
            # score from reported cells, allowing negatives only for diagnostic Stage2; never call it qualified
            cells=[]
            for v in r[6].values():cells.extend([v['spread_only'],v['plus_002R']])
            lg=[math.copysign(math.log1p(abs(q['ret'])/100),q['ret']) for q in cells]
            return 2*min(lg)+sum(lg)/len(lg)-.015*max(q['dd'] for q in cells)
        top=sorted(stage,key=soft,reverse=True)[:6]
    # Stage2: small economically-motivated management grid on only six pre-2025 signal structures.
    params=list(itertools.product([2.5,4.0,6.0],[1,2],[6.,10.,14.,20.],[12,24,36])) # BE,maxlots,TP,holdh
    rows=[]
    for rank,r in enumerate(top):
        _,en,vn,pn,L,S,_=r;rp=np.where(L,riskL,np.where(S,riskS,.01))
        for be,ml,tp,hh in params:
            cells=[];det={}
            for fn,b in folds:
                v,ca,ad,mo=sim_m1(*arr,decision_id,L,S,rp,b[0],b[1],be,ml,tp,int(hh*60))
                q0=pack(v,ca,ad,mo,0);q2=pack(v,ca,ad,mo,1);cells.extend([q0,q2]);det[fn]={'spread_only':q0,'plus_002R':q2}
            sc=robust_score(cells);rows.append((sc,en,vn,pn,be,ml,tp,hh,L,S,rp,det))
        print('STAGE2_SIGNAL',rank+1,'/',len(top),en,vn,pn,flush=True)
    rows.sort(reverse=True,key=lambda z:z[0]);qualified=[r for r in rows if r[0]>-1e11]
    report={'execution_source':'Dukascopy M1 bid/ask, variable spread implicit','execution_data':ediag,'selection':'ERA1/2/3 pre-2025 only; strict gate each era positive PF>1.05 at spread-only and +0.02R extra','stage1_qualified':len(qual),'stage2_qualified':len(qualified),'stage1_top':[{'score':r[0],'edges':r[1],'vwap':r[2],'profile':r[3],'eras':r[6]} for r in stage[:10]]}
    if not qualified:
        report['decision']='REJECT_ALL_TESTED_EXECUTION_AWARE_CONFIGS'
        report['best_diagnostic_stage2']=[{'score':r[0],'edges':r[1],'vwap':r[2],'profile':r[3],'beR':r[4],'maxlots':r[5],'tpR':r[6],'holdh':r[7],'eras':r[11]} for r in rows[:10]]
    else:
        w=qualified[0];_,en,vn,pn,be,ml,tp,hh,L,S,rp,det=w
        vh,ca,ad,mo=sim_m1(*arr,decision_id,L,S,rp,hold[0],hold[1],be,ml,tp,int(hh*60));vf,cf,af,mo2=sim_m1(*arr,decision_id,L,S,rp,full[0],full[1],be,ml,tp,int(hh*60))
        report['winner']={'score':w[0],'edges':en,'vwap':vn,'profile':pn,'beR':be,'maxlots':ml,'tpR':tp,'holdh':hh,'eras':det,
          'holdout_2025plus':{'spread_only':pack(vh,ca,ad,mo,0),'plus_002R':pack(vh,ca,ad,mo,1),'plus_005R':pack(vh,ca,ad,mo,2)},
          'full':{'spread_only':pack(vf,cf,af,mo2,0),'plus_002R':pack(vf,cf,af,mo2,1),'plus_005R':pack(vf,cf,af,mo2,2)}}
        report['decision']='WINNER_FROZEN_BEFORE_HOLDOUT'
    print('RESULT_JSON_START');print(json.dumps(report,default=float));print('RESULT_JSON_END')

if __name__=='__main__':main()
