import json, math
from dataclasses import dataclass
import numpy as np
import pandas as pd
import gold_m5_discovery_spike as g

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
SCREEN_SPEC=g.Spec('BRK','med','vwap','8R','both',12.0)
@dataclass
class Lot:
    direction:int;entry:float;stop:float;risk:float;risk_cash:float;target:float;opened_i:int;protected:bool=False;edge:str=''
def build_edges(x):
    ctx=g.contexts(x);ga=g.gates(x);sp={'BRK':g.Spec('BRK','med','vwap','5R','both',12.),'PULL':g.Spec('PULL','med','none','3R','both',0.),'EXP':g.Spec('EXP','mtf','flow','5R','long',1.5),'FRACTAL':g.Spec('FRACTAL','med','vwap','5R','both',0.)}
    return {k:g.sig(x,s,ctx,ga) for k,s in sp.items()}
def union_signal(ed,names):
    L=pd.Series(False,index=next(iter(ed.values()))[0].index);S=L.copy()
    for n in names:L|=ed[n][0];S|=ed[n][1]
    clash=L&S;L&=~clash;S&=~clash;return L,S
def stop_for(x,i,d,e):
    av=float(x.atr14.iloc[i]);
    if not np.isfinite(av) or av<=0:return None
    if d==1:sw=min(float(x.low.iloc[i]),float(x.swinglo6.iloc[i]));st=min(sw-.1*av,e-.85*av);r=e-st
    else:sw=max(float(x.high.iloc[i]),float(x.swinghi6.iloc[i]));st=max(sw+.1*av,e+.85*av);r=st-e
    if not np.isfinite(r) or r<=0 or r/e>.012:return None
    return st,r
def select_signal(ed,names,i,cdir=0):
    lo=[];sh=[]
    for nm in names:
        L,S=ed[nm]
        if bool(L.iloc[i]):lo.append(nm)
        if bool(S.iloc[i]):sh.append(nm)
    if cdir==1:return (1,lo[0]) if lo else None
    if cdir==-1:return (-1,sh[0]) if sh else None
    if lo and sh:return None
    return (1,lo[0]) if lo else ((-1,sh[0]) if sh else None)
def simulate(x,ed,names,start,end,be,maxlots,tp,maxhold=144):
    ids=np.flatnonzero(np.asarray((x.index>=start)&(x.index<end)))
    if not len(ids):return None
    first,last=int(ids[0]),int(ids[-1]);bal=1.;peak=1.;dd=0.;lots=[];pending=None;cdir=0;closed=[];durs=[];adds=0;campaigns=0;ec={k:0 for k in names}
    for i in range(max(first,30),min(last,len(x)-2)+1):
        if pending:
            d,si,edge=pending;e=float(x.open.iloc[i]);sr=stop_for(x,si,d,e)
            if sr:
                st,r=sr;lots.append(Lot(d,e,st,r,bal*g.RISK,e+d*tp*r,i,False,edge));ec[edge]+=1;adds+=1 if cdir else 0
                if not cdir:cdir=d;campaigns+=1
            pending=None
        hi=float(x.high.iloc[i]);lo=float(x.low.iloc[i]);cl=float(x.close.iloc[i]);surv=[]
        for z in lots:
            if (lo<=z.stop if z.direction==1 else hi>=z.stop):rr=z.direction*(z.stop-z.entry)/z.risk-g.COST_R;bal+=z.risk_cash*rr;closed.append(rr);durs.append((i-z.opened_i)*5/60);continue
            if (hi>=z.target if z.direction==1 else lo<=z.target):rr=tp-g.COST_R;bal+=z.risk_cash*rr;closed.append(rr);durs.append((i-z.opened_i)*5/60);continue
            if i-z.opened_i>=maxhold:rr=z.direction*(cl-z.entry)/z.risk-g.COST_R;bal+=z.risk_cash*rr;closed.append(rr);durs.append((i-z.opened_i)*5/60);continue
            if (not z.protected) and z.direction*(cl-z.entry)/z.risk>=be:z.stop=z.entry;z.protected=True
            surv.append(z)
        lots=surv
        if not lots:cdir=0
        eq=bal+sum(z.risk_cash*z.direction*(cl-z.entry)/z.risk for z in lots);peak=max(peak,eq);dd=max(dd,(peak-eq)/peak if peak>0 else 0)
        can=len(lots)<maxlots and all(z.protected for z in lots)
        if cdir==0:
            s=select_signal(ed,names,i,0)
            if s:pending=(s[0],i,s[1])
        elif can:
            s=select_signal(ed,names,i,cdir)
            if s:pending=(s[0],i,s[1])
    cl=float(x.close.iloc[last])
    for z in lots:rr=z.direction*(cl-z.entry)/z.risk-g.COST_R;bal+=z.risk_cash*rr;closed.append(rr);durs.append((last-z.opened_i)*5/60)
    if not closed:return None
    a=np.asarray(closed,float);pos=a[a>0].sum();neg=-a[a<0].sum();return {'n_lots':len(a),'campaigns':campaigns,'adds':adds,'ret':(bal-1)*100,'wr':(a>0).mean()*100,'pf':pos/neg if neg else 99,'avgR':a.mean(),'dd':dd*100,'R_total':a.sum(),'avgH':float(np.mean(durs)),'medH':float(np.median(durs)),'edge_counts':ec}
def main():
    x=g.prep();ed=build_edges(x);combos=[('BRK',),('BRK','PULL'),('BRK','EXP'),('BRK','PULL','EXP'),('BRK','FRACTAL'),('BRK','PULL','EXP','FRACTAL')]
    screens=[]
    for names in combos:
        L,S=union_signal(ed,names);tr=g.met(*g.simulate(x,L,S,SCREEN_SPEC,g.START,g.TRAIN_END));va=g.met(*g.simulate(x,L,S,SCREEN_SPEC,g.TRAIN_END,g.VAL_END))
        if tr and va:s=tr['ret']-1.1*tr['dd']+.7*va['ret']-.8*va['dd'];screens.append((s,names,tr,va))
    screens.sort(reverse=True,key=lambda z:z[0]);frozen=[z for z in screens if z[2]['pf']>1.05 and z[3]['pf']>1.08 and z[3]['ret']>0][:2]
    rows=[]
    for _,names,_,_ in frozen:
      for be in [1.,2.]:
       for ml in [4,6]:
        for tp in [8.,10.]:
            tr=simulate(x,ed,names,g.START,g.TRAIN_END,be,ml,tp);va=simulate(x,ed,names,g.TRAIN_END,g.VAL_END,be,ml,tp)
            if tr and va:score=tr['ret']-1.1*tr['dd']+.7*va['ret']-.8*va['dd'];rows.append((score,names,be,ml,tp,tr,va))
    rows.sort(reverse=True,key=lambda z:z[0]);out=[]
    for score,names,be,ml,tp,tr,va in rows:
        if va['ret']>0 and va['pf']>=1.08:
            ho=simulate(x,ed,names,g.VAL_END,g.END,be,ml,tp);full=simulate(x,ed,names,g.START,g.END,be,ml,tp);out.append({'edges':list(names),'beR':be,'max_lots':ml,'targetR':tp,'score':score,'train':tr,'val':va,'holdout':ho,'full':full})
    print('RESULT_JSON_START');print(json.dumps({'risk_pct':.36,'screen':[{'edges':list(z[1]),'score':z[0],'train':z[2],'val':z[3]} for z in screens],'frozen':[list(z[1]) for z in frozen],'promoted':out,'target_1000_R':math.log(11)/g.RISK,'selection':'single-position screen on train+validation, then campaign on top two; holdout untouched','limitations':['M1 OHLC->M5','one unprotected lot max','0.08R cost/lot','no news/DXY/profile']},default=float));print('RESULT_JSON_END')
if __name__=='__main__':main()
