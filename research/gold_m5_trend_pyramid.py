import json, math
from dataclasses import dataclass
import numpy as np
import pandas as pd
import gold_m5_discovery_spike as g

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']

@dataclass
class Lot:
    d:int;entry:float;stop:float;risk:float;rc:float;target:float;opened:int;protected:bool=False

def base_signal(x):
    s=g.Spec('BRK','med','vwap','5R','both',12.0)
    return g.sig(x,s,g.contexts(x),g.gates(x))

def stop_for(x,i,d,e):
    av=float(x.atr14.iloc[i])
    if not np.isfinite(av) or av<=0:return None
    if d==1:
        sw=min(float(x.low.iloc[i]),float(x.swinglo6.iloc[i]));st=min(sw-.1*av,e-.85*av);r=e-st
    else:
        sw=max(float(x.high.iloc[i]),float(x.swinghi6.iloc[i]));st=max(sw+.1*av,e+.85*av);r=st-e
    if not np.isfinite(r) or r<=0 or r/e>.012:return None
    return st,r

def simulate(x,L,S,start,end,beR,maxlots,tpR,maxhold=288):
    ids=np.flatnonzero(np.asarray((x.index>=start)&(x.index<end)))
    if not len(ids):return None
    first,last=int(ids[0]),int(ids[-1]);bal=1.;peak=1.;dd=0.;lots=[];pending=None;cdir=0;closed=[];durs=[];campaigns=0;adds=0;last_add_i=-999
    for i in range(max(first,30),min(last,len(x)-2)+1):
        if pending is not None:
            d,si,is_add=pending;e=float(x.open.iloc[i]);sr=stop_for(x,si,d,e)
            if sr:
                st,r=sr;lots.append(Lot(d,e,st,r,bal*g.RISK,e+d*tpR*r,i,False))
                if is_add:adds+=1
                else:campaigns+=1
                cdir=d;last_add_i=i
            pending=None
        hi=float(x.high.iloc[i]);lo=float(x.low.iloc[i]);cl=float(x.close.iloc[i]);surv=[]
        for z in lots:
            if (lo<=z.stop if z.d==1 else hi>=z.stop):
                rr=z.d*(z.stop-z.entry)/z.risk-g.COST_R;bal+=z.rc*rr;closed.append(rr);durs.append((i-z.opened)*5/60);continue
            if (hi>=z.target if z.d==1 else lo<=z.target):
                rr=tpR-g.COST_R;bal+=z.rc*rr;closed.append(rr);durs.append((i-z.opened)*5/60);continue
            if i-z.opened>=maxhold:
                rr=z.d*(cl-z.entry)/z.risk-g.COST_R;bal+=z.rc*rr;closed.append(rr);durs.append((i-z.opened)*5/60);continue
            if (not z.protected) and z.d*(cl-z.entry)/z.risk>=beR:
                z.stop=z.entry;z.protected=True
            surv.append(z)
        lots=surv
        if not lots:cdir=0
        eq=bal+sum(z.rc*z.d*(cl-z.entry)/z.risk for z in lots);peak=max(peak,eq);dd=max(dd,(peak-eq)/peak if peak>0 else 0)
        if pending is None:
            if cdir==0:
                if bool(L.iloc[i]):pending=(1,i,False)
                elif bool(S.iloc[i]):pending=(-1,i,False)
            elif len(lots)<maxlots and all(z.protected for z in lots) and i>last_add_i:
                pending=(cdir,i,True)
    cl=float(x.close.iloc[last])
    for z in lots:
        rr=z.d*(cl-z.entry)/z.risk-g.COST_R;bal+=z.rc*rr;closed.append(rr);durs.append((last-z.opened)*5/60)
    if not closed:return None
    a=np.asarray(closed,float);pos=a[a>0].sum();neg=-a[a<0].sum()
    return {'lots':len(a),'campaigns':campaigns,'adds':adds,'ret':(bal-1)*100,'wr':(a>0).mean()*100,'pf':pos/neg if neg else 99,'avgR':a.mean(),'R_total':a.sum(),'dd':dd*100,'avgH':float(np.mean(durs)),'medH':float(np.median(durs))}

def main():
    x=g.prep();L,S=base_signal(x);rows=[]
    candidates=[(be,ml,tp) for be in [1.,1.5] for ml in [4,6] for tp in [10.,12.]]
    for be,ml,tp in candidates:
        tr=simulate(x,L,S,g.START,g.TRAIN_END,be,ml,tp);va=simulate(x,L,S,g.TRAIN_END,g.VAL_END,be,ml,tp)
        if tr and va:
            score=tr['ret']-1.1*tr['dd']+.7*va['ret']-.8*va['dd'];rows.append((score,be,ml,tp,tr,va))
    rows.sort(reverse=True,key=lambda z:z[0]);out=[]
    for score,be,ml,tp,tr,va in rows[:4]:
        if va['ret']>0 and va['pf']>=1.08:
            ho=simulate(x,L,S,g.VAL_END,g.END,be,ml,tp);full=simulate(x,L,S,g.START,g.END,be,ml,tp);out.append({'beR':be,'max_lots':ml,'targetR':tp,'score':score,'train':tr,'val':va,'holdout':ho,'full':full})
    print('RESULT_JSON_START');print(json.dumps({'risk_pct':.36,'rule':'sequential add immediately after all existing lots protected; at most one unprotected lot','selection':'progressive 8-combo train+validation screen; holdout only top four','results':out,'target_1000_R':math.log(11)/g.RISK,'limitations':['M1 OHLC->M5','0.08R cost/lot','BE on close only','no news/DXY']},default=float));print('RESULT_JSON_END')
if __name__=='__main__':main()
