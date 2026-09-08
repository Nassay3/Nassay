import json, math
from dataclasses import dataclass
import numpy as np
import pandas as pd
import gold_m5_discovery_spike as g

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
COST=.10
@dataclass
class Lot:
    d:int; entry:float; stop:float; risk:float; rc:float; opened:int; protected:bool=False; rem:float=1.; realized:float=0.; hit2:bool=False; hit4:bool=False; best:float=0.
def signal(x):
    s=g.Spec('BRK','med','vwap','5R','both',12.0);return g.sig(x,s,g.contexts(x),g.gates(x))
def stop_for(x,i,d,entry):
    av=float(x.atr14.iloc[i]);
    if not np.isfinite(av) or av<=0:return None
    if d==1:swing=min(float(x.low.iloc[i]),float(x.swinglo6.iloc[i]));st=min(swing-.1*av,entry-.85*av);r=entry-st
    else:swing=max(float(x.high.iloc[i]),float(x.swinghi6.iloc[i]));st=max(swing+.1*av,entry+.85*av);r=st-entry
    if not np.isfinite(r) or r<=0 or r/entry>.012:return None
    return st,r
def simulate(x,L,S,start,end,beR,trail,capR,max_hold,max_lots=4):
    ids=np.flatnonzero(np.asarray((x.index>=start)&(x.index<end)))
    if not len(ids):return None
    first,last=int(ids[0]),int(ids[-1]);bal=1.;peak=1.;dd=0.;lots=[];pending=None;cdir=0;closed=[];durs=[];adds=0;campaigns=0
    for i in range(max(first,30),min(last,len(x)-2)+1):
        if pending:
            d,si=pending;ent=float(x.open.iloc[i]);sr=stop_for(x,si,d,ent)
            if sr:
                st,r=sr;lots.append(Lot(d,ent,st,r,bal*g.RISK,i,False,1.,0.,False,False,ent));adds+=1 if cdir else 0
                if not cdir:cdir=d;campaigns+=1
            pending=None
        hi=float(x.high.iloc[i]);lo=float(x.low.iloc[i]);cl=float(x.close.iloc[i]);surv=[]
        for z in lots:
            active=z.stop
            if z.hit4:
                if trail=='R2':active=max(active,z.entry,z.best-2*z.risk) if z.d==1 else min(active,z.entry,z.best+2*z.risk)
                elif trail=='VWMA84':tv=float(x.vwma84.iloc[i-1]);active=max(active,z.entry,tv) if z.d==1 else min(active,z.entry,tv)
                elif trail=='M15VWMA21':
                    tv=float(x.m15_vwma21.iloc[i-1]);
                    if np.isfinite(tv):active=max(active,z.entry,tv) if z.d==1 else min(active,z.entry,tv)
                else:
                    tv=float(x.m15_vwma175.iloc[i-1]);
                    if np.isfinite(tv):active=max(active,z.entry,tv) if z.d==1 else min(active,z.entry,tv)
            stophit=lo<=active if z.d==1 else hi>=active
            if stophit:
                rr=z.realized+z.rem*z.d*(active-z.entry)/z.risk-COST;bal+=z.rc*(z.rem*z.d*(active-z.entry)/z.risk-COST);closed.append(rr);durs.append((i-z.opened)*5/60);continue
            fav=(hi-z.entry)/z.risk if z.d==1 else (z.entry-lo)/z.risk
            if (not z.hit2) and fav>=2:gain=.4;bal+=z.rc*gain;z.realized+=gain;z.rem-=.2;z.hit2=True
            if (not z.hit4) and fav>=4:gain=.8;bal+=z.rc*gain;z.realized+=gain;z.rem-=.2;z.hit4=True
            if capR and fav>=capR:
                gain=z.rem*capR;bal+=z.rc*(gain-COST);z.realized+=gain-COST;closed.append(z.realized);durs.append((i-z.opened)*5/60);continue
            if i-z.opened>=max_hold:
                rr=z.rem*z.d*(cl-z.entry)/z.risk;bal+=z.rc*(rr-COST);z.realized+=rr-COST;closed.append(z.realized);durs.append((i-z.opened)*5/60);continue
            cr=z.d*(cl-z.entry)/z.risk
            if (not z.protected) and cr>=beR:z.stop=z.entry;z.protected=True
            z.best=max(z.best,hi) if z.d==1 else min(z.best,lo);surv.append(z)
        lots=surv
        if not lots:cdir=0
        eq=bal
        for z in lots:eq+=z.rc*z.rem*(z.d*(cl-z.entry)/z.risk)
        peak=max(peak,eq);dd=max(dd,(peak-eq)/peak if peak>0 else 0)
        can_add=len(lots)<max_lots and all(z.protected for z in lots)
        if cdir==0:
            if bool(L.iloc[i]):pending=(1,i)
            elif bool(S.iloc[i]):pending=(-1,i)
        elif can_add:
            if cdir==1 and bool(L.iloc[i]):pending=(1,i)
            elif cdir==-1 and bool(S.iloc[i]):pending=(-1,i)
    cl=float(x.close.iloc[last])
    for z in lots:
        rr=z.rem*z.d*(cl-z.entry)/z.risk;bal+=z.rc*(rr-COST);z.realized+=rr-COST;closed.append(z.realized);durs.append((last-z.opened)*5/60)
    if not closed:return None
    a=np.asarray(closed,float);pos=a[a>0].sum();neg=-a[a<0].sum();return {'lots':len(a),'campaigns':campaigns,'adds':adds,'ret':(bal-1)*100,'wr':(a>0).mean()*100,'pf':pos/neg if neg else 99,'avgR':a.mean(),'R_total':a.sum(),'dd':dd*100,'avgH':float(np.mean(durs)),'medH':float(np.median(durs))}
def sc(tr,va):return tr['ret']-1.1*tr['dd']+.7*va['ret']-.8*va['dd']
def main():
    x=g.prep();L,S=signal(x)
    # Stage 1: choose trail family with one fixed neutral configuration.
    trows=[]
    for trl in ['R2','VWMA84','M15VWMA21','M15VWMA175']:
        tr=simulate(x,L,S,g.START,g.TRAIN_END,2.,trl,16.,288);va=simulate(x,L,S,g.TRAIN_END,g.VAL_END,2.,trl,16.,288)
        if tr and va:trows.append((sc(tr,va),trl,tr,va))
    trows.sort(reverse=True,key=lambda z:z[0]);best_trail=trows[0][1]
    # Stage 2: tune only BE/cap/hold for the frozen trail family.
    rows=[]
    for be in [1.,2.]:
      for cap in [12.,16.]:
       for mh in [144,288]:
        tr=simulate(x,L,S,g.START,g.TRAIN_END,be,best_trail,cap,mh);va=simulate(x,L,S,g.TRAIN_END,g.VAL_END,be,best_trail,cap,mh)
        if tr and va:rows.append((sc(tr,va),be,cap,mh,tr,va))
    rows.sort(reverse=True,key=lambda z:z[0]);out=[]
    for score,be,cap,mh,tr,va in rows:
        if va['ret']>0 and va['pf']>=1.08:
            ho=simulate(x,L,S,g.VAL_END,g.END,be,best_trail,cap,mh);full=simulate(x,L,S,g.START,g.END,be,best_trail,cap,mh)
            out.append({'beR':be,'trail':best_trail,'capR':cap,'max_hold_bars':mh,'score':score,'train':tr,'val':va,'holdout':ho,'full':full})
    print('RESULT_JSON_START');print(json.dumps({'risk_pct':.36,'partials':'20%@2R + 20%@4R + 60% runner','trail_screen':[{'trail':a[1],'score':a[0],'train':a[2],'val':a[3]} for a in trows],'frozen_trail':best_trail,'selection':'two-stage train+validation only','results':out,'target_1000_R':math.log(11)/g.RISK,'limitations':['M1 OHLC->M5','0.10R cost/lot','one unprotected lot max','prior-bar trailing values','no news/DXY']},default=float));print('RESULT_JSON_END')
if __name__=='__main__':main()
