import json
import numpy as np
import pandas as pd
from numba import njit
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m
import gold_m5_volume_profile_ablation as vp
import gold_m5_vwap_ladder_ablation as vw
import gold_m5_vwap_consensus_ablation as vc

# Research branch only. Main historical public source.
g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
m.g.URLS=g.URLS; vp.g.URLS=g.URLS; vw.g.URLS=g.URLS; vc.g.URLS=g.URLS
RISK=.0036

@njit(cache=True)
def sim_stress(o,h,l,c,atr,slo,shi,sigL,sigS,first,last,af,beR,maxlots,tpR,maxhold,costR,stop_slipR,require_fresh_add,min_gap):
    dirs=np.zeros(8,np.int8);ent=np.zeros(8);stops=np.zeros(8);risks=np.zeros(8);rcs=np.zeros(8);targets=np.zeros(8);opened=np.zeros(8,np.int64);prot=np.zeros(8,np.uint8)
    nlot=0;pdn=0;pdi=-1;padd=0;cdir=0;lastadd=-999;bal=1.;peak=1.;dd=0.;nclosed=0;wins=0;pos=0.;neg=0.;rtot=0.;campaigns=0;adds=0;max_open=0
    for i in range(max(first,30),min(last,len(o)-2)+1):
        if pdn!=0:
            av=atr[pdi]; e=o[i]
            if av>0 and np.isfinite(av):
                sw=slo[pdi] if pdn==1 else shi[pdi]
                if pdn==1: st=min(sw-.1*av,e-af*av); rrisk=e-st
                else: st=max(sw+.1*av,e+af*av); rrisk=st-e
                if rrisk>0 and rrisk/e<=.012 and nlot<maxlots:
                    eqopen=bal
                    for q in range(nlot): eqopen+=rcs[q]*dirs[q]*(e-ent[q])/risks[q]
                    rc=max(0.0,eqopen)*RISK
                    dirs[nlot]=pdn; ent[nlot]=e; stops[nlot]=st; risks[nlot]=rrisk; rcs[nlot]=rc; targets[nlot]=e+pdn*tpR*rrisk; opened[nlot]=i; prot[nlot]=0; nlot+=1
                    if padd==1: adds+=1
                    else: campaigns+=1
                    cdir=pdn; lastadd=i
                    if nlot>max_open:max_open=nlot
            pdn=0;pdi=-1;padd=0
        newn=0
        for k in range(nlot):
            d=dirs[k];closed=False;rr=0.
            if (d==1 and l[i]<=stops[k]) or (d==-1 and h[i]>=stops[k]):
                rr=d*(stops[k]-ent[k])/risks[k]-costR-stop_slipR; closed=True
            elif (d==1 and h[i]>=targets[k]) or (d==-1 and l[i]<=targets[k]):
                rr=tpR-costR; closed=True
            elif i-opened[k]>=maxhold:
                rr=d*(c[i]-ent[k])/risks[k]-costR; closed=True
            if closed:
                bal+=rcs[k]*rr;nclosed+=1;rtot+=rr
                if rr>0:wins+=1;pos+=rr
                elif rr<0:neg-=rr
            else:
                cr=d*(c[i]-ent[k])/risks[k]
                if prot[k]==0 and cr>=beR:stops[k]=ent[k];prot[k]=1
                if newn!=k:
                    dirs[newn]=dirs[k];ent[newn]=ent[k];stops[newn]=stops[k];risks[newn]=risks[k];rcs[newn]=rcs[k];targets[newn]=targets[k];opened[newn]=opened[k];prot[newn]=prot[k]
                newn+=1
        nlot=newn
        if nlot==0:cdir=0
        eq=bal;allprot=True
        for k in range(nlot):
            eq+=rcs[k]*dirs[k]*(c[i]-ent[k])/risks[k]
            if prot[k]==0:allprot=False
        if eq>peak:peak=eq
        cur=(peak-eq)/peak if peak>0 else 0.
        if cur>dd:dd=cur
        if pdn==0:
            if cdir==0:
                if sigL[i] and not sigS[i]:pdn=1;pdi=i;padd=0
                elif sigS[i] and not sigL[i]:pdn=-1;pdi=i;padd=0
            elif nlot<maxlots and allprot and i-lastadd>=min_gap:
                if require_fresh_add==0:
                    pdn=cdir;pdi=i;padd=1
                else:
                    if cdir==1 and sigL[i] and not sigS[i]:pdn=1;pdi=i;padd=1
                    elif cdir==-1 and sigS[i] and not sigL[i]:pdn=-1;pdi=i;padd=1
    for k in range(nlot):
        rr=dirs[k]*(c[last]-ent[k])/risks[k]-costR
        bal+=rcs[k]*rr;nclosed+=1;rtot+=rr
        if rr>0:wins+=1;pos+=rr
        elif rr<0:neg-=rr
    return nclosed,campaigns,adds,(bal-1)*100.,100.*wins/nclosed if nclosed else 0.,pos/neg if neg else 99.,rtot/nclosed if nclosed else 0.,rtot,dd*100.,max_open

def pack(v):
    return {'lots':int(v[0]),'campaigns':int(v[1]),'adds':int(v[2]),'ret':float(v[3]),'wr':float(v[4]),'pf':float(v[5]),'avgR':float(v[6]),'R_total':float(v[7]),'dd':float(v[8]),'max_open':int(v[9])}

def bounds(idx,a,b):
    z=np.flatnonzero(np.asarray((idx>=a)&(idx<b)));return int(z[0]),int(z[-1])

def build():
    x=g.prep();idx=x.index;ed=m.build_edges(x);names=('BRK','EXP','PULL','FRACTAL')
    L=pd.Series(False,index=idx);S=pd.Series(False,index=idx)
    for nm in names:L|=ed[nm][0];S|=ed[nm][1]
    clash=L&S;L&=~clash;S&=~clash
    o=x.open.to_numpy(float);h=x.high.to_numpy(float);lo=x.low.to_numpy(float);c=x.close.to_numpy(float);atr=x.atr14.to_numpy(float);vol=x.tick_volume.to_numpy(float)
    slo=x.low.rolling(7,min_periods=1).min().to_numpy(float);shi=x.high.rolling(7,min_periods=1).max().to_numpy(float)
    poc,_,_=vp.profile_levels(h,lo,c,vol,288,32,3,.70);ok=np.isfinite(poc)
    f=vw.vwap_ladder(x,3,True);wL,wS=vc.mk_masks(x,f)['WEEK_PLUS_ANY']
    L=(L&wL&pd.Series(ok&(c>poc),index=idx)).to_numpy(np.bool_);S=(S&wS&pd.Series(ok&(c<poc),index=idx)).to_numpy(np.bool_)
    return x,(o,h,lo,c,atr,slo,shi,L,S)

def main():
    x,arr=build();idx=x.index
    bounds_map={'TRAIN':bounds(idx,g.START,g.TRAIN_END),'VAL':bounds(idx,g.TRAIN_END,g.VAL_END),'HOLDOUT':bounds(idx,g.VAL_END,g.END),'FULL':bounds(idx,g.START,g.END)}
    candidates={'A_METHOD':(.60,1.25,3,26.,144),'B_HIST':(.575,1.25,3,28.,144)}
    scenarios=[
      ('BASE_AUTO',.08,0.,0,1),
      ('AUTO_COST15',.15,0.,0,1),('AUTO_COST25',.25,0.,0,1),('AUTO_COST40',.40,0.,0,1),
      ('AUTO_C15_SLIP05',.15,.05,0,1),('AUTO_C25_SLIP10',.25,.10,0,1),('AUTO_C40_SLIP20',.40,.20,0,1),
      ('AUTO_GAP15_C15S05',.15,.05,0,3),('AUTO_GAP30_C15S05',.15,.05,0,6),
      ('FRESH_BASE',.08,0.,1,1),('FRESH_C15S05',.15,.05,1,1),('FRESH_C25S10',.25,.10,1,1)
    ]
    # warm
    q=bounds_map['TRAIN'];sim_stress(*arr,q[0],min(q[0]+1000,q[1]),.60,1.25,3,26.,144,.08,0.,0,1)
    out={}
    for cn,p in candidates.items():
        af,be,ml,tp,mh=p; out[cn]={}
        for sn,cost,slip,fresh,gap in scenarios:
            sm={}
            for split,b in bounds_map.items():sm[split]=pack(sim_stress(*arr,b[0],b[1],af,be,ml,tp,mh,cost,slip,fresh,gap))
            out[cn][sn]={'costR':cost,'stop_slipR':slip,'require_fresh_add':bool(fresh),'min_add_gap_min':gap*5,'metrics':sm}
    print('RESULT_JSON_START')
    print(json.dumps({'risk_rule':'0.36% current MTM equity per fresh lot; prior lots protected before add','purpose':'Execution/pyramiding fragility stress. Parameters frozen; no tuning.','candidates':out,'interpretation_guardrails':['Fresh-add scenarios isolate whether edge survives when every pyramid addition needs a same-direction UNION4 alpha signal','Stop-first ordering remains conservative when stop and target share one M5 bar','stop_slipR is applied to every stop/BE stop in addition to closing costR','This is still OHLC stress, not true tick replay']},default=float))
    print('RESULT_JSON_END')
if __name__=='__main__':main()
