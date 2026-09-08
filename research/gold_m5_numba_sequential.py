import json, math, itertools
import numpy as np
import pandas as pd
from numba import njit
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
m.g.URLS=g.URLS
RISK=g.RISK;COST=g.COST_R

@njit(cache=True)
def sim(o,h,l,c,atr,slo6,shi6,sigL,sigS,first,last,atr_floor,beR,maxlots,tpR,maxhold):
    dirs=np.zeros(8,np.int8);ent=np.zeros(8);stops=np.zeros(8);risks=np.zeros(8);rcs=np.zeros(8);targets=np.zeros(8);opened=np.zeros(8,np.int64);prot=np.zeros(8,np.uint8)
    nlot=0;pending_d=0;pending_i=-1;pending_add=0;cdir=0;last_add=-999
    bal=1.;peak=1.;dd=0.;nclosed=0;wins=0;pos=0.;neg=0.;rtot=0.;campaigns=0;adds=0
    for i in range(max(first,30),min(last,len(o)-2)+1):
        if pending_d!=0:
            av=atr[pending_i];e=o[i]
            if av>0 and np.isfinite(av):
                sw=slo6[pending_i] if pending_d==1 else shi6[pending_i]
                if pending_d==1: st=min(sw-.1*av,e-atr_floor*av);rrisk=e-st
                else: st=max(sw+.1*av,e+atr_floor*av);rrisk=st-e
                if rrisk>0 and rrisk/e<=.012 and nlot<maxlots:
                    dirs[nlot]=pending_d;ent[nlot]=e;stops[nlot]=st;risks[nlot]=rrisk;rcs[nlot]=bal*RISK;targets[nlot]=e+pending_d*tpR*rrisk;opened[nlot]=i;prot[nlot]=0;nlot+=1
                    if pending_add==1:adds+=1
                    else:campaigns+=1
                    cdir=pending_d;last_add=i
            pending_d=0;pending_i=-1;pending_add=0
        newn=0
        for k in range(nlot):
            d=dirs[k];closed=False;rr=0.
            if (d==1 and l[i]<=stops[k]) or (d==-1 and h[i]>=stops[k]): rr=d*(stops[k]-ent[k])/risks[k]-COST;closed=True
            elif (d==1 and h[i]>=targets[k]) or (d==-1 and l[i]<=targets[k]): rr=tpR-COST;closed=True
            elif i-opened[k]>=maxhold: rr=d*(c[i]-ent[k])/risks[k]-COST;closed=True
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
        if pending_d==0:
            if cdir==0:
                if sigL[i] and not sigS[i]:pending_d=1;pending_i=i;pending_add=0
                elif sigS[i] and not sigL[i]:pending_d=-1;pending_i=i;pending_add=0
            elif nlot<maxlots and allprot and i>last_add:
                pending_d=cdir;pending_i=i;pending_add=1
    for k in range(nlot):
        rr=dirs[k]*(c[last]-ent[k])/risks[k]-COST;bal+=rcs[k]*rr;nclosed+=1;rtot+=rr
        if rr>0:wins+=1;pos+=rr
        elif rr<0:neg-=rr
    return nclosed,campaigns,adds,(bal-1)*100,100*wins/nclosed if nclosed else 0,pos/neg if neg else 99,rtot/nclosed if nclosed else 0,rtot,dd*100

def pack(v):return {'lots':int(v[0]),'campaigns':int(v[1]),'adds':int(v[2]),'ret':float(v[3]),'wr':float(v[4]),'pf':float(v[5]),'avgR':float(v[6]),'R_total':float(v[7]),'dd':float(v[8])}
def bounds(idx,a,b):
    ids=np.flatnonzero(np.asarray((idx>=a)&(idx<b)));return int(ids[0]),int(ids[-1])

def main():
    x=g.prep();ed=m.build_edges(x);L=(ed['BRK'][0]|ed['EXP'][0]).fillna(False);S=(ed['BRK'][1]|ed['EXP'][1]).fillna(False);z=L&S;L&=~z;S&=~z
    o=x.open.to_numpy(float);h=x.high.to_numpy(float);lo=x.low.to_numpy(float);c=x.close.to_numpy(float);atr=x.atr14.to_numpy(float);slo6=x.low.rolling(7,min_periods=1).min().to_numpy(float);shi6=x.high.rolling(7,min_periods=1).max().to_numpy(float);sl=L.to_numpy(np.bool_);ss=S.to_numpy(np.bool_)
    idx=x.index;trb=bounds(idx,g.START,g.TRAIN_END);vab=bounds(idx,g.TRAIN_END,g.VAL_END);hob=bounds(idx,g.VAL_END,g.END);fullb=bounds(idx,g.START,g.END)
    args=(o,h,lo,c,atr,slo6,shi6,sl,ss)
    sim(*args,trb[0],min(trb[0]+1000,trb[1]),1.,1.,4,10.,144)
    grid=list(itertools.product([.85,1.0],[.75,1.0,1.25],[4,6],[10.,12.,15.],[144,288]))
    rows=[]
    for af,be,ml,tp,mh in grid:
        tr=pack(sim(*args,trb[0],trb[1],af,be,ml,tp,mh));va=pack(sim(*args,vab[0],vab[1],af,be,ml,tp,mh))
        if tr['ret']<=0 or va['ret']<=0 or tr['pf']<1.05 or va['pf']<1.08:continue
        # Penalize drawdown aggressively; this is intentionally an aggressive family.
        score=tr['ret']-1.5*tr['dd']+.8*va['ret']-1.2*va['dd']-50*abs(tr['avgR']-va['avgR'])
        rows.append((score,af,be,ml,tp,mh,tr,va))
    rows.sort(reverse=True,key=lambda z:z[0]);out=[]
    for score,af,be,ml,tp,mh,tr,va in rows[:5]:
        ho=pack(sim(*args,hob[0],hob[1],af,be,ml,tp,mh));full=pack(sim(*args,fullb[0],fullb[1],af,be,ml,tp,mh))
        out.append({'atr_floor':af,'beR':be,'max_lots':ml,'targetR':tp,'max_hold_hours':mh*5/60,'score':score,'train':tr,'val':va,'holdout':ho,'full':full})
    print('RESULT_JSON_START');print(json.dumps({'risk_pct':.36,'signal':'BRK+EXP starts campaign','rule':'immediate sequential add only after every existing lot protected; at most one unprotected lot','grid_size':len(grid),'selection':'train+validation only; holdout top5','results':out,'target_1000_R':math.log(11)/RISK,'limitations':['aggressive pyramiding can create very large drawdowns','M1 OHLC->M5','0.08R cost/lot','BE on close','no news/DXY filter']},default=float));print('RESULT_JSON_END')
if __name__=='__main__':main()
