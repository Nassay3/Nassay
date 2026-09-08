import json, math
from dataclasses import dataclass
import numpy as np
import pandas as pd
import gold_m5_discovery_spike as g

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']

@dataclass
class Lot:
    direction:int; entry:float; stop:float; risk:float; risk_cash:float; target:float; opened_i:int; protected:bool=False; edge:str=''

def build_edges(x):
    ctx=g.contexts(x); gates=g.gates(x)
    specs={
        'BRK': g.Spec('BRK','med','vwap','5R','both',12.0),
        'PULL': g.Spec('PULL','med','none','3R','both',0.0),
        'EXP': g.Spec('EXP','mtf','flow','5R','long',1.5),
        'FRACTAL': g.Spec('FRACTAL','med','vwap','5R','both',0.0),
    }
    out={}
    for k,s in specs.items(): out[k]=g.sig(x,s,ctx,gates)
    return out

def stop_for(x,i,d,entry):
    av=float(x.atr14.iloc[i])
    if not np.isfinite(av) or av<=0:return None
    if d==1:
        swing=min(float(x.low.iloc[i]),float(x.swinglo6.iloc[i])); stop=min(swing-.1*av,entry-.85*av); risk=entry-stop
    else:
        swing=max(float(x.high.iloc[i]),float(x.swinghi6.iloc[i])); stop=max(swing+.1*av,entry+.85*av); risk=stop-entry
    if not np.isfinite(risk) or risk<=0 or risk/entry>.012:return None
    return stop,risk

def select_signal(edges, names, i, campaign_dir=0):
    longs=[]; shorts=[]
    for nm in names:
        L,S=edges[nm]
        if bool(L.iloc[i]): longs.append(nm)
        if bool(S.iloc[i]): shorts.append(nm)
    if campaign_dir==1:
        return (1,longs[0]) if longs else None
    if campaign_dir==-1:
        return (-1,shorts[0]) if shorts else None
    if longs and shorts: return None
    if longs:return (1,longs[0])
    if shorts:return (-1,shorts[0])
    return None

def simulate(x,edges,names,start,end,be_r,max_lots,target_r,max_hold=144):
    valid=np.flatnonzero(np.asarray((x.index>=start)&(x.index<end)))
    if not len(valid):return None
    first,last=int(valid[0]),int(valid[-1]); bal=1.; peak=1.; maxdd=0.; lots=[]; pending=None; cdir=0
    closed=[]; durs=[]; adds=0; campaigns=0; edge_counts={k:0 for k in names}
    for i in range(max(first,30),min(last,len(x)-2)+1):
        if pending is not None:
            d,si,edge=pending; entry=float(x.open.iloc[i]); sr=stop_for(x,si,d,entry)
            if sr is not None:
                stop,risk=sr; rc=bal*g.RISK; target=entry+d*target_r*risk
                lots.append(Lot(d,entry,stop,risk,rc,target,i,False,edge)); edge_counts[edge]+=1
                if cdir!=0:adds+=1
                if cdir==0:cdir=d;campaigns+=1
            pending=None
        hi=float(x.high.iloc[i]); lo=float(x.low.iloc[i]); close=float(x.close.iloc[i]); surv=[]
        for lot in lots:
            stophit=lo<=lot.stop if lot.direction==1 else hi>=lot.stop
            if stophit:
                r=lot.direction*(lot.stop-lot.entry)/lot.risk-g.COST_R; bal+=lot.risk_cash*r; closed.append(r); durs.append((i-lot.opened_i)*5/60); continue
            tphit=hi>=lot.target if lot.direction==1 else lo<=lot.target
            if tphit:
                r=target_r-g.COST_R; bal+=lot.risk_cash*r; closed.append(r); durs.append((i-lot.opened_i)*5/60); continue
            if i-lot.opened_i>=max_hold:
                r=lot.direction*(close-lot.entry)/lot.risk-g.COST_R; bal+=lot.risk_cash*r; closed.append(r); durs.append((i-lot.opened_i)*5/60); continue
            cr=lot.direction*(close-lot.entry)/lot.risk
            if (not lot.protected) and cr>=be_r:
                lot.stop=lot.entry; lot.protected=True
            surv.append(lot)
        lots=surv
        if not lots:cdir=0
        eq=bal
        for lot in lots:eq+=lot.risk_cash*(lot.direction*(close-lot.entry)/lot.risk)
        peak=max(peak,eq);maxdd=max(maxdd,(peak-eq)/peak if peak>0 else 0)
        can_add=len(lots)<max_lots and all(z.protected for z in lots)
        if cdir==0:
            s=select_signal(edges,names,i,0)
            if s:pending=(s[0],i,s[1])
        elif can_add:
            s=select_signal(edges,names,i,cdir)
            if s:pending=(s[0],i,s[1])
    close=float(x.close.iloc[last])
    for lot in lots:
        r=lot.direction*(close-lot.entry)/lot.risk-g.COST_R;bal+=lot.risk_cash*r;closed.append(r);durs.append((last-lot.opened_i)*5/60)
    if not closed:return None
    a=np.asarray(closed,float);pos=a[a>0].sum();neg=-a[a<0].sum()
    return {'n_lots':len(a),'campaigns':campaigns,'adds':adds,'ret':(bal-1)*100,'wr':(a>0).mean()*100,'pf':pos/neg if neg else 99,'avgR':a.mean(),'dd':maxdd*100,'avgH':float(np.mean(durs)),'medH':float(np.median(durs)),'R_total':float(a.sum()),'edge_counts':edge_counts}

def main():
    x=g.prep(); ed=build_edges(x)
    combos=[('BRK',),('BRK','PULL'),('BRK','EXP'),('BRK','PULL','EXP'),('BRK','FRACTAL'),('BRK','PULL','EXP','FRACTAL')]
    rows=[]
    for names in combos:
      for be in [1.,2.]:
       for ml in [4,6]:
        for tp in [5.,8.,10.]:
            tr=simulate(x,ed,names,g.START,g.TRAIN_END,be,ml,tp);va=simulate(x,ed,names,g.TRAIN_END,g.VAL_END,be,ml,tp)
            if not tr or not va:continue
            score=tr['ret']-1.1*tr['dd']+.7*va['ret']-.8*va['dd']
            rows.append((score,names,be,ml,tp,tr,va))
    rows.sort(reverse=True,key=lambda z:z[0])
    promoted=[]
    for score,names,be,ml,tp,tr,va in rows:
        if va['ret']>0 and va['pf']>=1.08:
            ho=simulate(x,ed,names,g.VAL_END,g.END,be,ml,tp);full=simulate(x,ed,names,g.START,g.END,be,ml,tp)
            promoted.append({'edges':list(names),'beR':be,'max_lots':ml,'targetR':tp,'score':score,'train':tr,'val':va,'holdout':ho,'full':full})
    print('RESULT_JSON_START')
    print(json.dumps({'risk_pct':.36,'selection':'train+validation only; holdout untouched until ranking frozen','promoted':promoted[:12],'target_1000':{'required_5y_cagr_pct':(11**.2-1)*100,'approx_required_R':math.log(11)/g.RISK},'limitations':['M1 OHLC->M5, not bid/ask ticks','at most one unprotected lot at a time','BE activates only on close','0.08R cost per lot','news/DXY/profile deferred']},default=float))
    print('RESULT_JSON_END')
if __name__=='__main__':main()
