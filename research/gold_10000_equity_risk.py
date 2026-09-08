import json, math, itertools
import numpy as np
import pandas as pd
from numba import njit
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m
import gold_m5_volume_profile_ablation as vp
import gold_m5_vwap_ladder_ablation as vw
import gold_m5_vwap_consensus_ablation as vc

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
m.g.URLS=g.URLS;vp.g.URLS=g.URLS;vw.g.URLS=g.URLS;vc.g.URLS=g.URLS
RISK=g.RISK;COST=g.COST_R

@njit(cache=True)
def sim_equity(o,h,l,c,atr,slo,shi,sigL,sigS,first,last,af,beR,maxlots,tpR,maxhold):
    dirs=np.zeros(8,np.int8);ent=np.zeros(8);stops=np.zeros(8);risks=np.zeros(8);rcs=np.zeros(8);targets=np.zeros(8);opened=np.zeros(8,np.int64);prot=np.zeros(8,np.uint8)
    nlot=0;pdn=0;pdi=-1;padd=0;cdir=0;lastadd=-999;bal=1.;peak=1.;dd=0.;nclosed=0;wins=0;pos=0.;neg=0.;rtot=0.;campaigns=0;adds=0
    for i in range(max(first,30),min(last,len(o)-2)+1):
        if pdn!=0:
            av=atr[pdi];e=o[i]
            if av>0 and np.isfinite(av):
                sw=slo[pdi] if pdn==1 else shi[pdi]
                if pdn==1:st=min(sw-.1*av,e-af*av);rrisk=e-st
                else:st=max(sw+.1*av,e+af*av);rrisk=st-e
                if rrisk>0 and rrisk/e<=.012 and nlot<maxlots:
                    # Exact user rule: fresh risk = 0.36% of CURRENT mark-to-market equity at entry open.
                    eqopen=bal
                    for q in range(nlot):eqopen+=rcs[q]*dirs[q]*(e-ent[q])/risks[q]
                    rc=max(0.0,eqopen)*RISK
                    dirs[nlot]=pdn;ent[nlot]=e;stops[nlot]=st;risks[nlot]=rrisk;rcs[nlot]=rc;targets[nlot]=e+pdn*tpR*rrisk;opened[nlot]=i;prot[nlot]=0;nlot+=1
                    if padd==1:adds+=1
                    else:campaigns+=1
                    cdir=pdn;lastadd=i
            pdn=0;pdi=-1;padd=0
        newn=0
        for k in range(nlot):
            d=dirs[k];closed=False;rr=0.
            if (d==1 and l[i]<=stops[k]) or (d==-1 and h[i]>=stops[k]):rr=d*(stops[k]-ent[k])/risks[k]-COST;closed=True
            elif (d==1 and h[i]>=targets[k]) or (d==-1 and l[i]<=targets[k]):rr=tpR-COST;closed=True
            elif i-opened[k]>=maxhold:rr=d*(c[i]-ent[k])/risks[k]-COST;closed=True
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
            elif nlot<maxlots and allprot and i>lastadd:
                # Risk recycling: no second fresh-risk lot until every older live lot is at BE.
                pdn=cdir;pdi=i;padd=1
    for k in range(nlot):
        rr=dirs[k]*(c[last]-ent[k])/risks[k]-COST;bal+=rcs[k]*rr;nclosed+=1;rtot+=rr
        if rr>0:wins+=1;pos+=rr
        elif rr<0:neg-=rr
    return nclosed,campaigns,adds,(bal-1)*100.,100.*wins/nclosed if nclosed else 0.,pos/neg if neg else 99.,rtot/nclosed if nclosed else 0.,rtot,dd*100.

def pack(v):return {'lots':int(v[0]),'campaigns':int(v[1]),'adds':int(v[2]),'ret':float(v[3]),'wr':float(v[4]),'pf':float(v[5]),'avgR':float(v[6]),'R_total':float(v[7]),'dd':float(v[8])}
def bounds(idx,a,b):
    z=np.flatnonzero(np.asarray((idx>=a)&(idx<b)));return int(z[0]),int(z[-1])
def score(tr,va):
    if tr['ret']<=0 or va['ret']<=0 or tr['pf']<1.10 or va['pf']<1.10:return -1e9
    return math.log1p(tr['ret']/100)+1.45*math.log1p(va['ret']/100)-.018*tr['dd']-.028*va['dd']-1.75*abs(tr['avgR']-va['avgR'])

def main():
    x=g.prep();idx=x.index;ed=m.build_edges(x);names=('BRK','EXP','PULL','FRACTAL')
    L=pd.Series(False,index=idx);S=L.copy()
    for nm in names:L|=ed[nm][0];S|=ed[nm][1]
    clash=L&S;L&=~clash;S&=~clash
    o=x.open.to_numpy(float);h=x.high.to_numpy(float);lo=x.low.to_numpy(float);c=x.close.to_numpy(float);atr=x.atr14.to_numpy(float);vol=x.tick_volume.to_numpy(float)
    slo=x.low.rolling(7,min_periods=1).min().to_numpy(float);shi=x.high.rolling(7,min_periods=1).max().to_numpy(float)
    poc,_,_=vp.profile_levels(h,lo,c,vol,288,32,3,.70);ok=np.isfinite(poc);f=vw.vwap_ladder(x,3,True);wL,wS=vc.mk_masks(x,f)['WEEK_PLUS_ANY']
    L=(L&wL&pd.Series(ok&(c>poc),index=idx)).to_numpy(np.bool_);S=(S&wS&pd.Series(ok&(c<poc),index=idx)).to_numpy(np.bool_)
    arr=(o,h,lo,c,atr,slo,shi,L,S)
    trb=bounds(idx,g.START,g.TRAIN_END);vab=bounds(idx,g.TRAIN_END,g.VAL_END);hob=bounds(idx,g.VAL_END,g.END);fullb=bounds(idx,g.START,g.END)
    # Warm JIT
    sim_equity(*arr,trb[0],min(trb[0]+1000,trb[1]),.575,1.25,3,28.,144)
    # Small plateau only; architecture and edges are frozen.
    grid=list(itertools.product([.55,.575,.60,.625],[1.20,1.25,1.30],[2,3,4],[24.,25.,26.,27.,28.,29.,30.],[120,144,180]))
    rows=[]
    for af,be,ml,tp,mh in grid:
        tr=pack(sim_equity(*arr,trb[0],trb[1],af,be,ml,tp,mh));va=pack(sim_equity(*arr,vab[0],vab[1],af,be,ml,tp,mh));s=score(tr,va)
        if s>-1e8:rows.append((s,af,be,ml,tp,mh,tr,va))
    rows.sort(reverse=True,key=lambda z:z[0]);prom=[]
    for s,af,be,ml,tp,mh,tr,va in rows[:30]:
        ho=pack(sim_equity(*arr,hob[0],hob[1],af,be,ml,tp,mh));full=pack(sim_equity(*arr,fullb[0],fullb[1],af,be,ml,tp,mh))
        prom.append({'score':s,'atr_floor':af,'beR':be,'max_lots':ml,'targetR':tp,'hold_hours':mh*5/60,'train':tr,'val':va,'holdout':ho,'full':full,'over_10000':full['ret']>=10000})
    above=[z for z in prom if z['full']['ret']>=10000]
    print('RESULT_JSON_START');print(json.dumps({'risk_rule':'Each new lot risks exactly 0.36% of mark-to-market current equity at its entry; older live lots must all be at BE first','grid_size':len(grid),'selection':'Train+Validation only; Holdout/Full revealed top30','promoted':prom,'count_over_10000_top30':len(above),'best_full_top30':max(prom,key=lambda z:z['full']['ret']) if prom else None,'best_score':prom[0] if prom else None,'limitations':['This corrects prior balance-based under-sizing; it can materially increase compounding in trending campaigns','OHLC M5, not bid/ask ticks; 0.08R modeled cost','auto sequential adds do not require fresh BRK/EXP/PULL/FRACTAL signal','final candidate still requires external forward check']},default=float));print('RESULT_JSON_END')
if __name__=='__main__':main()
