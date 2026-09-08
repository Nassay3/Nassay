import json, math
from dataclasses import dataclass
import numpy as np
import pandas as pd
import gold_m5_discovery_spike as g

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']

@dataclass
class Lot:
    direction:int; entry:float; stop:float; risk:float; risk_cash:float; target:float; opened_i:int; protected:bool=False

def base_signal(x):
    s=g.Spec('BRK','med','vwap','5R','both',12.0)
    return s,g.sig(x,s,g.contexts(x),g.gates(x))

def stop_for(x,i,direction,entry):
    av=float(x.atr14.iloc[i])
    if not np.isfinite(av) or av<=0:return None
    if direction==1:
        swing=min(float(x.low.iloc[i]),float(x.swinglo6.iloc[i])); stop=min(swing-.1*av,entry-.85*av); risk=entry-stop
    else:
        swing=max(float(x.high.iloc[i]),float(x.swinghi6.iloc[i])); stop=max(swing+.1*av,entry+.85*av); risk=stop-entry
    if not np.isfinite(risk) or risk<=0 or risk/entry>.012:return None
    return stop,risk

def simulate(x,L,S,start,end,be_r,max_lots,target_r,max_hold=144):
    valid=np.flatnonzero(np.asarray((x.index>=start)&(x.index<end)))
    if not len(valid):return None
    first,last=int(valid[0]),int(valid[-1]); balance=1.0; peak=1.0; maxdd=0.0; lots=[]; pending=None; campaign_dir=0
    closed=[]; durations=[]; adds=0; campaigns=0
    for i in range(max(first,30),min(last,len(x)-2)+1):
        # Fill signal from prior close at this bar open.
        if pending is not None:
            d,signal_i=pending; entry=float(x.open.iloc[i]); sr=stop_for(x,signal_i,d,entry)
            if sr is not None:
                stop,risk=sr; risk_cash=balance*g.RISK; target=entry+d*target_r*risk; lots.append(Lot(d,entry,stop,risk,risk_cash,target,i,False)); adds += 1 if campaign_dir!=0 else 0
                if campaign_dir==0: campaign_dir=d; campaigns+=1
            pending=None
        hi=float(x.high.iloc[i]); lo=float(x.low.iloc[i]); close=float(x.close.iloc[i]); survivors=[]
        for lot in lots:
            # Conservative: stop takes precedence over target on an ambiguous bar.
            stophit=lo<=lot.stop if lot.direction==1 else hi>=lot.stop
            if stophit:
                r=lot.direction*(lot.stop-lot.entry)/lot.risk-g.COST_R; balance+=lot.risk_cash*r; closed.append(r); durations.append((i-lot.opened_i)*5/60); continue
            tphit=hi>=lot.target if lot.direction==1 else lo<=lot.target
            if tphit:
                r=target_r-g.COST_R; balance+=lot.risk_cash*r; closed.append(r); durations.append((i-lot.opened_i)*5/60); continue
            if i-lot.opened_i>=max_hold:
                r=lot.direction*(close-lot.entry)/lot.risk-g.COST_R; balance+=lot.risk_cash*r; closed.append(r); durations.append((i-lot.opened_i)*5/60); continue
            # Move to BE only on bar close, so no optimistic intrabar ordering.
            cr=lot.direction*(close-lot.entry)/lot.risk
            if (not lot.protected) and cr>=be_r:
                lot.stop=lot.entry; lot.protected=True
            survivors.append(lot)
        lots=survivors
        if not lots: campaign_dir=0
        # Mark-to-market equity and drawdown.
        equity=balance
        for lot in lots: equity += lot.risk_cash*(lot.direction*(close-lot.entry)/lot.risk)
        peak=max(peak,equity); maxdd=max(maxdd,(peak-equity)/peak if peak>0 else 0)
        # Schedule next entry only if no current lot remains at initial risk.
        can_add=(len(lots)<max_lots and all(z.protected for z in lots))
        if campaign_dir==0:
            if bool(L.iloc[i]): pending=(1,i)
            elif bool(S.iloc[i]): pending=(-1,i)
        elif can_add:
            if campaign_dir==1 and bool(L.iloc[i]): pending=(1,i)
            elif campaign_dir==-1 and bool(S.iloc[i]): pending=(-1,i)
    # Flatten remaining at end.
    close=float(x.close.iloc[last])
    for lot in lots:
        r=lot.direction*(close-lot.entry)/lot.risk-g.COST_R; balance+=lot.risk_cash*r; closed.append(r); durations.append((last-lot.opened_i)*5/60)
    if not closed:return None
    a=np.array(closed,float); pos=a[a>0].sum(); neg=-a[a<0].sum()
    return {'n_lots':len(a),'campaigns':campaigns,'adds':adds,'ret':(balance-1)*100,'wr':(a>0).mean()*100,'pf':pos/neg if neg else 99,'avgR':a.mean(),'dd':maxdd*100,'avgH':float(np.mean(durations)),'medH':float(np.median(durations)),'R_total':float(a.sum())}

def main():
    x=g.prep(); _,(L,S)=base_signal(x); rows=[]
    for be in [1.0,2.0]:
        for ml in [2,3,4]:
            for tp in [5.0,8.0,10.0]:
                tr=simulate(x,L,S,g.START,g.TRAIN_END,be,ml,tp); va=simulate(x,L,S,g.TRAIN_END,g.VAL_END,be,ml,tp)
                if not tr or not va:continue
                score=tr['ret']-1.2*tr['dd']+.5*va['ret']-.8*va['dd']; rows.append((score,be,ml,tp,tr,va))
    rows.sort(reverse=True,key=lambda z:z[0]); out=[]
    for score,be,ml,tp,tr,va in rows:
        if va['ret']>0 and va['pf']>=1.05:
            ho=simulate(x,L,S,g.VAL_END,g.END,be,ml,tp); full=simulate(x,L,S,g.START,g.END,be,ml,tp)
            out.append({'beR':be,'max_lots':ml,'targetR':tp,'score':score,'train':tr,'val':va,'holdout':ho,'full':full})
    print('RESULT_JSON_START'); print(json.dumps({'risk_pct':.36,'base_signal':'BRK|med|vwap|both|12','selection':'train+validation only; holdout untouched until ranking frozen','results':out[:10],'target_1000':{'required_5y_cagr_pct':(11**.2-1)*100,'approx_required_R':math.log(11)/g.RISK},'limitations':['M1 OHLC->M5, not bid/ask ticks','BE activates only on close (conservative)','at most one unprotected lot at a time','0.08R cost per lot','news/DXY/profile not included']},default=float)); print('RESULT_JSON_END')
if __name__=='__main__':main()
