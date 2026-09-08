import json, math
import numpy as np
import pandas as pd
import gold_m5_discovery_spike as g

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
RISK=g.RISK; COST=.08
# Article times are MSK (UTC+3): XAUUSD 10:00-23:45 MSK => 07:00-20:45 UTC.
START_MIN=7*60; END_MIN=20*60+45

def daily_atr_map(x):
    d=x[['open','high','low','close']].resample('1D',label='left',closed='left').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna()
    pc=d.close.shift(1);tr=pd.concat([(d.high-d.low).abs(),(d.high-pc).abs(),(d.low-pc).abs()],axis=1).max(axis=1)
    atr=tr.rolling(14,min_periods=14).mean().shift(1)
    return {k.date():float(v) for k,v in atr.dropna().items()}

def fractal_levels(day):
    upper=None; lower=None
    for i in range(4,len(day)):
        j=i-2
        if day.index[j].hour*60+day.index[j].minute<START_MIN: continue
        h=float(day.high.iloc[j]); l=float(day.low.iloc[j])
        hs=day.high.iloc[j-2:j+3].to_numpy(float); ls=day.low.iloc[j-2:j+3].to_numpy(float)
        if upper is None and h>=np.max(hs)-1e-12: upper=(i,h)
        if lower is None and l<=np.min(ls)+1e-12: lower=(i,l)
        if upper is not None and lower is not None: break
    return upper,lower

def gates(x,mode,i,d):
    if mode=='BASE': return True
    vw_l=(x.h1_close.iloc[i]>x.h1_vwma84.iloc[i]) and (x.h1_vwma84.iloc[i]>x.h1_vwma175.iloc[i])
    vw_s=(x.h1_close.iloc[i]<x.h1_vwma84.iloc[i]) and (x.h1_vwma84.iloc[i]<x.h1_vwma175.iloc[i])
    vp_l=(x.close.iloc[i]>x.sess_vwap.iloc[i]>x.sess_prior.iloc[i]) and (x.close.iloc[i]>x.day_vwap.iloc[i]>x.day_prior.iloc[i]) and (x.close.iloc[i]>x.week_vwap.iloc[i]>x.week_prior.iloc[i])
    vp_s=(x.close.iloc[i]<x.sess_vwap.iloc[i]<x.sess_prior.iloc[i]) and (x.close.iloc[i]<x.day_vwap.iloc[i]<x.day_prior.iloc[i]) and (x.close.iloc[i]<x.week_vwap.iloc[i]<x.week_prior.iloc[i])
    if mode=='VWMA': return vw_l if d==1 else vw_s
    if mode=='VWAP': return vp_l if d==1 else vp_s
    return (vw_l and vp_l) if d==1 else (vw_s and vp_s)

def simulate(x,start,end,mode,hedged):
    xx=x[(x.index>=start)&(x.index<end)].copy(); amap=daily_atr_map(x)
    bal=1.;peak=1.;dd=0.;rs=[];durs=[];days=0
    for date,day in xx.groupby(xx.index.date):
        sess=day[((day.index.hour*60+day.index.minute)>=START_MIN)&((day.index.hour*60+day.index.minute)<=END_MIN)]
        if len(sess)<8 or date not in amap or not np.isfinite(amap[date]): continue
        days+=1; up,dn=fractal_levels(sess); used={1:False,-1:False}; active={1:None,-1:None}; pending={1:False,-1:False}
        for k in range(len(sess)):
            ts=sess.index[k];gi=x.index.get_indexer([ts])[0]
            if gi<0:continue
            # Next-open fills, one per direction. In one-active mode, suppress fill if opposite is still active.
            for d in [1,-1]:
                if pending[d] and active[d] is None and (hedged or active[-d] is None):
                    entry=float(x.open.iloc[gi]);dist=.25*amap[date]
                    if dist>0 and np.isfinite(dist):active[d]={'d':d,'entry':entry,'stop':entry-d*dist,'tp':entry+d*6*dist,'risk':dist,'open_i':gi,'risk_cash':bal*RISK}
                    pending[d]=False
            hi=float(x.high.iloc[gi]);lo=float(x.low.iloc[gi])
            for d in [1,-1]:
                z=active[d]
                if z is None:continue
                stophit=lo<=z['stop'] if d==1 else hi>=z['stop'];tphit=hi>=z['tp'] if d==1 else lo<=z['tp']
                if stophit:
                    r=-1-COST;bal+=z['risk_cash']*r;rs.append(r);durs.append((gi-z['open_i'])*5/60);active[d]=None
                elif tphit:
                    r=6-COST;bal+=z['risk_cash']*r;rs.append(r);durs.append((gi-z['open_i'])*5/60);active[d]=None
            if k<len(sess)-1:
                c=float(sess.close.iloc[k]);pc=float(sess.close.iloc[k-1]) if k>0 else c
                can_long=hedged or active[-1] is None
                can_short=hedged or active[1] is None
                if up is not None and k>=up[0] and (not used[1]) and (not pending[1]) and can_long and pc<=up[1] and c>up[1] and gates(x,mode,gi,1):
                    pending[1]=True;used[1]=True
                if dn is not None and k>=dn[0] and (not used[-1]) and (not pending[-1]) and can_short and pc>=dn[1] and c<dn[1] and gates(x,mode,gi,-1):
                    pending[-1]=True;used[-1]=True
            eq=bal
            for d in [1,-1]:
                z=active[d]
                if z is not None:eq+=z['risk_cash']*(d*(float(x.close.iloc[gi])-z['entry'])/z['risk'])
            peak=max(peak,eq);dd=max(dd,(peak-eq)/peak if peak>0 else 0)
        gi=x.index.get_indexer([sess.index[-1]])[0]
        for d in [1,-1]:
            z=active[d]
            if z is not None:
                r=d*(float(x.close.iloc[gi])-z['entry'])/z['risk']-COST;bal+=z['risk_cash']*r;rs.append(r);durs.append((gi-z['open_i'])*5/60)
    if not rs:return None
    a=np.array(rs,float);pos=a[a>0].sum();neg=-a[a<0].sum()
    return {'trades':len(a),'days':days,'ret':(bal-1)*100,'wr':float((a>0).mean()*100),'pf':float(pos/neg if neg else 99),'avgR':float(a.mean()),'R_total':float(a.sum()),'dd':dd*100,'avgH':float(np.mean(durs)),'medH':float(np.median(durs))}

def main():
    x=g.prep();out=[]
    for hedged in [False,True]:
      for mode in ['BASE','VWMA','VWAP','VWMA_VWAP']:
        tr=simulate(x,g.START,g.TRAIN_END,mode,hedged);va=simulate(x,g.TRAIN_END,g.VAL_END,mode,hedged);ho=simulate(x,g.VAL_END,g.END,mode,hedged);full=simulate(x,g.START,g.END,mode,hedged)
        out.append({'execution':'HEDGED' if hedged else 'ONE_ACTIVE','mode':mode,'train':tr,'val':va,'holdout':ho,'full':full})
    print('RESULT_JSON_START');print(json.dumps({'risk_pct':.36,'session':'07:00-20:45 UTC, converted from article 10:00-23:45 MSK','entry':'confirmed 5-bar fractal breakout on M5 close, next bar open (conservative vs article tick trigger)','stop':'25% prior completed D1 ATR14','target':'6R','attempts':'max one long + one short per session','results':out,'target_1000_R':math.log(11)/RISK,'limitations':['article triggers intrabar on bid and fills market/ask; this test confirms M5 close then enters next open','M1 OHLC->M5 not bid/ask ticks','0.08R cost/trade','HEDGED mode can have two simultaneous 0.36% trades']},default=float));print('RESULT_JSON_END')
if __name__=='__main__':main()
