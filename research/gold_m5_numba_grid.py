import json, math, itertools
import numpy as np
import pandas as pd
from numba import njit
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
m.g.URLS=g.URLS
RISK=g.RISK; COST=g.COST_R

@njit(cache=True)
def sim_numba(o,h,l,c,atr,slo3,shi3,slo6,shi6,sigL,sigS,first,last,atr_floor,swing_n,beR,maxlots,tpR,maxhold):
    dirs=np.zeros(6,np.int8); ent=np.zeros(6); stops=np.zeros(6); risks=np.zeros(6); rcs=np.zeros(6); targets=np.zeros(6); opened=np.zeros(6,np.int64); prot=np.zeros(6,np.uint8)
    nlot=0; pending_d=0; pending_i=-1; cdir=0; bal=1.0; peak=1.0; dd=0.0; nclosed=0; wins=0; pos=0.0; neg=0.0; rtot=0.0
    for i in range(max(first,30),min(last,len(o)-2)+1):
        if pending_d!=0:
            av=atr[pending_i]; e=o[i]
            if av>0 and np.isfinite(av):
                if swing_n==3: sw=slo3[pending_i] if pending_d==1 else shi3[pending_i]
                else: sw=slo6[pending_i] if pending_d==1 else shi6[pending_i]
                if pending_d==1:
                    st=min(sw-.1*av,e-atr_floor*av); rrisk=e-st
                else:
                    st=max(sw+.1*av,e+atr_floor*av); rrisk=st-e
                if rrisk>0 and rrisk/e<=.012 and nlot<maxlots:
                    dirs[nlot]=pending_d;ent[nlot]=e;stops[nlot]=st;risks[nlot]=rrisk;rcs[nlot]=bal*RISK;targets[nlot]=e+pending_d*tpR*rrisk;opened[nlot]=i;prot[nlot]=0;nlot+=1
                    if cdir==0:cdir=pending_d
            pending_d=0;pending_i=-1
        newn=0
        for k in range(nlot):
            d=dirs[k]; closed=False; rr=0.0
            if (d==1 and l[i]<=stops[k]) or (d==-1 and h[i]>=stops[k]):
                rr=d*(stops[k]-ent[k])/risks[k]-COST;closed=True
            elif (d==1 and h[i]>=targets[k]) or (d==-1 and l[i]<=targets[k]):
                rr=tpR-COST;closed=True
            elif i-opened[k]>=maxhold:
                rr=d*(c[i]-ent[k])/risks[k]-COST;closed=True
            if closed:
                bal+=rcs[k]*rr;nclosed+=1;rtot+=rr
                if rr>0:wins+=1;pos+=rr
                elif rr<0:neg-=rr
            else:
                cr=d*(c[i]-ent[k])/risks[k]
                if prot[k]==0 and cr>=beR:
                    stops[k]=ent[k];prot[k]=1
                if newn!=k:
                    dirs[newn]=dirs[k];ent[newn]=ent[k];stops[newn]=stops[k];risks[newn]=risks[k];rcs[newn]=rcs[k];targets[newn]=targets[k];opened[newn]=opened[k];prot[newn]=prot[k]
                newn+=1
        nlot=newn
        if nlot==0:cdir=0
        eq=bal
        allprot=True
        for k in range(nlot):
            eq+=rcs[k]*dirs[k]*(c[i]-ent[k])/risks[k]
            if prot[k]==0:allprot=False
        if eq>peak:peak=eq
        curdd=(peak-eq)/peak if peak>0 else 0.0
        if curdd>dd:dd=curdd
        if pending_d==0:
            if cdir==0:
                if sigL[i] and not sigS[i]:pending_d=1;pending_i=i
                elif sigS[i] and not sigL[i]:pending_d=-1;pending_i=i
            elif nlot<maxlots and allprot:
                if cdir==1 and sigL[i]:pending_d=1;pending_i=i
                elif cdir==-1 and sigS[i]:pending_d=-1;pending_i=i
    for k in range(nlot):
        rr=dirs[k]*(c[last]-ent[k])/risks[k]-COST;bal+=rcs[k]*rr;nclosed+=1;rtot+=rr
        if rr>0:wins+=1;pos+=rr
        elif rr<0:neg-=rr
    pf=pos/neg if neg>0 else 99.0
    wr=100.0*wins/nclosed if nclosed>0 else 0.0
    avg=rtot/nclosed if nclosed>0 else 0.0
    return nclosed,(bal-1)*100.0,wr,pf,avg,rtot,dd*100.0

def pack(v):
    return {'lots':int(v[0]),'ret':float(v[1]),'wr':float(v[2]),'pf':float(v[3]),'avgR':float(v[4]),'R_total':float(v[5]),'dd':float(v[6])}

def main():
    x=g.prep();ed=m.build_edges(x);L=(ed['BRK'][0]|ed['EXP'][0]).fillna(False);S=(ed['BRK'][1]|ed['EXP'][1]).fillna(False);both=L&S;L=L&~both;S=S&~both
    o=x.open.to_numpy(float);h=x.high.to_numpy(float);lo=x.low.to_numpy(float);c=x.close.to_numpy(float);atr=x.atr14.to_numpy(float);sl=L.to_numpy(np.bool_);ss=S.to_numpy(np.bool_)
    slo3=x.low.rolling(4,min_periods=1).min().to_numpy(float);shi3=x.high.rolling(4,min_periods=1).max().to_numpy(float);slo6=x.low.rolling(7,min_periods=1).min().to_numpy(float);shi6=x.high.rolling(7,min_periods=1).max().to_numpy(float)
    idx=x.index
    def bounds(a,b):
        ids=np.flatnonzero(np.asarray((idx>=a)&(idx<b)));return int(ids[0]),int(ids[-1])
    trb=bounds(g.START,g.TRAIN_END);vab=bounds(g.TRAIN_END,g.VAL_END);hob=bounds(g.VAL_END,g.END);fullb=bounds(g.START,g.END)
    # warm JIT
    sim_numba(o,h,lo,c,atr,slo3,shi3,slo6,shi6,sl,ss,trb[0],min(trb[0]+1000,trb[1]),.85,6,1.,4,10.,144)
    grid=list(itertools.product([.50,.65,.85,1.0],[3,6],[.50,.75,1.0],[4,6],[8.,10.,12.,15.],[144,288,576]))
    rows=[]
    for af,sn,be,ml,tp,mh in grid:
        tr=pack(sim_numba(o,h,lo,c,atr,slo3,shi3,slo6,shi6,sl,ss,trb[0],trb[1],af,sn,be,ml,tp,mh))
        va=pack(sim_numba(o,h,lo,c,atr,slo3,shi3,slo6,shi6,sl,ss,vab[0],vab[1],af,sn,be,ml,tp,mh))
        if tr['lots']<400 or va['lots']<120 or tr['ret']<=0 or va['ret']<=0 or tr['pf']<1.10 or va['pf']<1.08:continue
        # robustness first: reward both periods, penalize worst drawdown and huge instability.
        stability=abs(tr['avgR']-va['avgR'])*100
        score=tr['ret']-1.1*tr['dd']+.8*va['ret']-1.0*va['dd']-stability
        rows.append((score,af,sn,be,ml,tp,mh,tr,va))
    rows.sort(reverse=True,key=lambda z:z[0])
    out=[]
    for score,af,sn,be,ml,tp,mh,tr,va in rows[:5]:
        ho=pack(sim_numba(o,h,lo,c,atr,slo3,shi3,slo6,shi6,sl,ss,hob[0],hob[1],af,sn,be,ml,tp,mh))
        full=pack(sim_numba(o,h,lo,c,atr,slo3,shi3,slo6,shi6,sl,ss,fullb[0],fullb[1],af,sn,be,ml,tp,mh))
        out.append({'atr_floor':af,'swing_n':sn,'beR':be,'max_lots':ml,'targetR':tp,'max_hold_hours':mh*5/60,'score':score,'train':tr,'val':va,'holdout':ho,'full':full})
    print('RESULT_JSON_START')
    print(json.dumps({'risk_pct':.36,'signal':'BRK+EXP frozen','grid_size':len(grid),'selection':'all tuning uses train+validation; untouched holdout only top five','current_baseline':{'atr_floor':.85,'swing_n':6,'beR':1.,'max_lots':4,'targetR':10.,'max_hold_hours':12},'results':out,'target_1000_R':math.log(11)/RISK,'limitations':['M1 OHLC resampled to M5','0.08R cost per lot','one unprotected lot max','BE on close','parameter grid creates selection risk; holdout is final arbiter']},default=float))
    print('RESULT_JSON_END')
if __name__=='__main__':main()
