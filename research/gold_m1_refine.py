import json, math
import numpy as np
import pandas as pd
import gold_m5_discovery_spike as g

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
COST=.10

def prep_all():
    m1=g.read_all(); m1=g.core(m1,[84,175]); m5=g.prep();
    spec=g.Spec('BRK','med','vwap','5R','both',12.0); L,S=g.sig(m5,spec,g.contexts(m5),g.gates(m5));
    sigs=[]
    for ts in m5.index[(L|S)]: sigs.append((ts,1 if bool(L.loc[ts]) else -1,float(m5.loc[ts,'high']),float(m5.loc[ts,'low']),float(m5.loc[ts,'atr14'])))
    return m1,m5,sigs

def find_entry(m1,ts,d,window,swing_n):
    start=ts+pd.Timedelta(minutes=5); end=start+pd.Timedelta(minutes=window)
    z=m1[(m1.index>=start)&(m1.index<=end)]
    if len(z)<5:return None
    touched=False
    for k in range(1,len(z)-1):
        row=z.iloc[k]; prev=z.iloc[k-1]
        if not np.isfinite(row.vwma84) or not np.isfinite(row.vwma175):continue
        if d==1:
            if row.low<=row.vwma84*1.0005 and row.close>=row.vwma175*.998: touched=True
            reclaim=touched and row.close>row.vwma84 and row.vwma84>row.vwma175 and row.close>prev.high
        else:
            if row.high>=row.vwma84*.9995 and row.close<=row.vwma175*1.002: touched=True
            reclaim=touched and row.close<row.vwma84 and row.vwma84<row.vwma175 and row.close<prev.low
        if reclaim:
            ei=k+1; ent=float(z.open.iloc[ei]); atr5=float(row.atr14) if np.isfinite(row.atr14) else np.nan
            if d==1:
                sw=float(z.low.iloc[max(0,k-swing_n+1):k+1].min()); stop=sw
                if np.isfinite(row.vwma175): stop=min(stop,float(row.vwma175))
            else:
                sw=float(z.high.iloc[max(0,k-swing_n+1):k+1].max()); stop=sw
                if np.isfinite(row.vwma175): stop=max(stop,float(row.vwma175))
            risk=(ent-stop) if d==1 else (stop-ent)
            if risk<=0 or risk/ent>.006:return None
            return z.index[ei],ent,stop,risk
    return None

def simulate(m1,sigs,start,end,window,swing_n,tpR):
    bal=1.;peak=1.;dd=0.;rs=[];durs=[];p=0; filtered=[s for s in sigs if s[0]>=start and s[0]<end]
    while p<len(filtered):
        ts,d,sh,sl,a=filtered[p]; fe=find_entry(m1,ts,d,window,swing_n)
        if fe is None:p+=1;continue
        et,ent,stop,risk=fe;rc=bal*g.RISK;target=ent+d*tpR*risk
        # max hold 12h, conservative stop-first on M1 bars
        z=m1[(m1.index>=et)&(m1.index<=et+pd.Timedelta(hours=12))]
        exit_t=z.index[-1];rr=None
        for t,row in z.iterrows():
            hit_s=row.low<=stop if d==1 else row.high>=stop;hit_t=row.high>=target if d==1 else row.low<=target
            if hit_s:rr=-1-COST;exit_t=t;break
            if hit_t:rr=tpR-COST;exit_t=t;break
        if rr is None:rr=d*(float(z.close.iloc[-1])-ent)/risk-COST
        bal+=rc*rr;rs.append(rr);durs.append((exit_t-et).total_seconds()/3600)
        peak=max(peak,bal);dd=max(dd,(peak-bal)/peak if peak>0 else 0)
        # skip M5 signals occurring while position was active
        p+=1
        while p<len(filtered) and filtered[p][0]<=exit_t:p+=1
    if not rs:return None
    a=np.asarray(rs,float);pos=a[a>0].sum();neg=-a[a<0].sum()
    return {'trades':len(a),'ret':(bal-1)*100,'wr':(a>0).mean()*100,'pf':pos/neg if neg else 99,'avgR':a.mean(),'R_total':a.sum(),'dd':dd*100,'avgH':float(np.mean(durs)),'medH':float(np.median(durs))}

def main():
    m1,m5,sigs=prep_all();rows=[]
    for window in [30,60]:
      for sn in [3,5]:
       for tp in [5.,8.]:
        tr=simulate(m1,sigs,g.START,g.TRAIN_END,window,sn,tp);va=simulate(m1,sigs,g.TRAIN_END,g.VAL_END,window,sn,tp)
        if tr and va:score=tr['ret']-1.1*tr['dd']+.7*va['ret']-.8*va['dd'];rows.append((score,window,sn,tp,tr,va))
    rows.sort(reverse=True,key=lambda z:z[0]);out=[]
    for score,w,sn,tp,tr,va in rows:
        if va['ret']>0 and va['pf']>=1.08:
            ho=simulate(m1,sigs,g.VAL_END,g.END,w,sn,tp);full=simulate(m1,sigs,g.START,g.END,w,sn,tp);out.append({'window_min':w,'swing_n':sn,'targetR':tp,'score':score,'train':tr,'val':va,'holdout':ho,'full':full})
    print('RESULT_JSON_START');print(json.dumps({'risk_pct':.36,'parent_signal':'M5 BRK med+VWAP both 12-bar','entry':'M1 VWMA84/175 pullback then reclaim + previous-bar break, next M1 open','selection':'train+validation only; holdout untouched','results':out,'target_1000_R':math.log(11)/g.RISK,'limitations':['M1 OHLC not bid/ask ticks','0.10R cost/trade','one active position at a time','M1 stop uses recent swing and VWMA175']},default=float));print('RESULT_JSON_END')
if __name__=='__main__':main()
