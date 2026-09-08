from __future__ import annotations
import json
import numpy as np
import pandas as pd

URL="https://raw.githubusercontent.com/simom1/XAUUSD-history/main/Gold-Cash/XAUUSD/XAUUSD_H1.csv"
START=pd.Timestamp("2021-09-08",tz="UTC")
END=pd.Timestamp("2026-09-08 23:59:59",tz="UTC")
WARM=START-pd.Timedelta(days=120)
RISK=0.0036
COST_R=0.05


def profile(window,bins=24,va=0.70):
    if len(window)<8:return (np.nan,np.nan,np.nan)
    lo=float(window.low.min());hi=float(window.high.max())
    if hi<=lo:return (np.nan,np.nan,np.nan)
    edges=np.linspace(lo,hi,bins+1); vv=np.zeros(bins)
    for r in window.itertuples():
        a=max(0,min(bins-1,int(np.searchsorted(edges,r.low,side='right')-1)))
        b=max(0,min(bins-1,int(np.searchsorted(edges,r.high,side='left')-1)))
        if b<a:b=a
        vv[a:b+1]+=float(r.tick_volume)/(b-a+1)
    if vv.sum()<=0:return (np.nan,np.nan,np.nan)
    p=int(np.argmax(vv)); chosen={p}; total=vv[p]; target=vv.sum()*va; l=p-1; r=p+1
    while total<target and (l>=0 or r<bins):
        lv=vv[l] if l>=0 else -1; rv=vv[r] if r<bins else -1
        if rv>lv: chosen.add(r); total+=rv; r+=1
        else: chosen.add(l); total+=lv; l-=1
    return ((edges[p]+edges[p+1])/2,edges[max(chosen)+1],edges[min(chosen)])


def add_group_vwap(x,group,prefix):
    typ=(x.high+x.low+x.close)/3; vol=x.tick_volume.clip(lower=1).astype(float); pv=typ*vol
    cur=pv.groupby(group).cumsum()/vol.groupby(group).cumsum()
    codes,_=pd.factorize(group,sort=False)
    final=cur.groupby(codes).last()
    prior=np.full(len(x),np.nan); mask=codes>0
    prior[mask]=final.iloc[codes[mask]-1].to_numpy()
    x[prefix+'_vwap']=cur; x[prefix+'_prior']=prior


def prep():
    print('DOWNLOAD',URL,flush=True)
    x=pd.read_csv(URL)
    x['time']=pd.to_datetime(x.time,utc=True)
    for c in ['open','high','low','close','tick_volume']:x[c]=pd.to_numeric(x[c],errors='coerce')
    x=x.dropna().drop_duplicates('time').sort_values('time').set_index('time')
    x=x[(x.index>=WARM)&(x.index<=END)].copy()
    typ=(x.high+x.low+x.close)/3; vol=x.tick_volume.astype(float)
    for n in [21,48,84,175,480,840]:
        x[f'vwma{n}']=(typ*vol).rolling(n,min_periods=n).sum()/vol.rolling(n,min_periods=n).sum()
    for n in [48,84]:
        sd=x.close.rolling(n,min_periods=n).std(ddof=0).replace(0,np.nan)
        x[f'z{n}']=(x.close-x[f'vwma{n}'])/sd
        x[f'z{n}_max20']=x[f'z{n}'].shift(1).rolling(20,min_periods=10).max()
        x[f'z{n}_min20']=x[f'z{n}'].shift(1).rolling(20,min_periods=10).min()
    x['range']=x.high-x.low
    x['avg_range14']=x['range'].shift(1).rolling(14,min_periods=14).mean()
    x['dv']=typ*vol; x['dvma30']=x.dv.rolling(30,min_periods=30).mean(); x['rqvol']=x.dvma30/x.dvma30.rolling(1800,min_periods=500).mean()
    day=pd.Series(x.index.strftime('%Y-%m-%d'),index=x.index)
    iso=x.index.isocalendar(); week=pd.Series(iso.year.astype(str)+'-'+iso.week.astype(str),index=x.index)
    add_group_vwap(x,day,'day'); add_group_vwap(x,week,'week')
    fpoc=np.full(len(x),np.nan);fvah=np.full(len(x),np.nan);fval=np.full(len(x),np.nan);dpoc=np.full(len(x),np.nan)
    day_start=0
    for i in range(len(x)):
        if i==0 or x.index[i].date()!=x.index[i-1].date(): day_start=i
        if i>=31:
            p,a,b=profile(x.iloc[i-31:i+1]);fpoc[i]=p;fvah[i]=a;fval[i]=b
        p,_,_=profile(x.iloc[day_start:i+1]);dpoc[i]=p
    x['fpoc']=fpoc;x['fvah']=fvah;x['fval']=fval;x['dpoc']=dpoc
    print('RANGE',x.index.min(),x.index.max(),'ROWS',len(x),flush=True)
    return x


def flags(x):
    closepos=(x.close-x.low)/x['range'].replace(0,np.nan)
    exp=x['range']>=2.0*x.avg_range14
    long_reg=(x.close>x.vwma21)&(x.vwma21>x.vwma84)&(x.vwma84>x.vwma175)&(x.vwma175>x.vwma480)
    short_reg=(x.close<x.vwma21)&(x.vwma21<x.vwma84)&(x.vwma84<x.vwma175)&(x.vwma175<x.vwma480)
    base_l=exp&long_reg&(x.close>x.open)&(closepos>=0.80)
    base_s=exp&short_reg&(x.close<x.open)&(closepos<=0.20)
    vw_l=(x.day_vwap>x.day_prior)&(x.week_vwap>x.week_prior)&(x.close>x.day_vwap)&(x.close>x.day_prior)&(x.close>x.week_vwap)&(x.close>x.week_prior)
    vw_s=(x.day_vwap<x.day_prior)&(x.week_vwap<x.week_prior)&(x.close<x.day_vwap)&(x.close<x.day_prior)&(x.close<x.week_vwap)&(x.close<x.week_prior)
    flow=(x.dv>x.dvma30)&(x.rqvol>1.0)
    zl=(x.z48>x.z48_max20)&(x.z84>x.z84_max20)&(x.z48>0)&(x.z84>0)
    zs=(x.z48<x.z48_min20)&(x.z84<x.z84_min20)&(x.z48<0)&(x.z84<0)
    pl=(x.close>x.fvah)&(x.close>x.dpoc); ps=(x.close<x.fval)&(x.close<x.dpoc)
    return {
      'VWMA_EXPANSION':(base_l,base_s),
      'PLUS_VWAP':(base_l&vw_l,base_s&vw_s),
      'PLUS_VWAP_FLOW':(base_l&vw_l&flow,base_s&vw_s&flow),
      'PLUS_VWAP_Z':(base_l&vw_l&zl,base_s&vw_s&zs),
      'PLUS_VWAP_PROFILE':(base_l&vw_l&pl,base_s&vw_s&ps),
      'FULL_AVAILABLE':(base_l&vw_l&flow&zl&pl,base_s&vw_s&flow&zs&ps),
    }


def trade_sim(x,ls,ss,style,long_only,start,end,max_hold=24):
    ix=x.index; valid=np.flatnonzero(np.asarray((ix>=start)&(ix<end)))
    if not len(valid):return [],[]
    i=max(valid[0],20); last=valid[-1]; rs=[];dur=[]
    while i<last-1:
        d=1 if bool(ls.iloc[i]) else (-1 if (not long_only and bool(ss.iloc[i])) else 0)
        if d==0:i+=1;continue
        e_i=i+1; entry=float(x.open.iloc[e_i]); ar=float(x.avg_range14.iloc[i]); riskdist=1.2*ar
        if not np.isfinite(riskdist) or riskdist<=0:i+=1;continue
        stop=entry-d*riskdist; remain=1.; realized=0.; hit4=False; best=entry; active=stop; out=None
        lastj=min(last,e_i+max_hold)
        for j in range(e_i,lastj+1):
            hi=float(x.high.iloc[j]);lo=float(x.low.iloc[j])
            if style=='trail' and hit4:
                active=max(stop,entry,best-2*riskdist) if d==1 else min(stop,entry,best+2*riskdist)
            if (lo<=active if d==1 else hi>=active):
                realized+=remain*d*(active-entry)/riskdist;remain=0;out=j;break
            fav=(hi-entry)/riskdist if d==1 else (entry-lo)/riskdist
            if style=='3R' and fav>=3:
                realized=3.;remain=0;out=j;break
            if style!='3R':
                if remain>0.80-1e-9 and fav>=2:realized+=0.4;remain-=0.2
                if remain>0.60-1e-9 and fav>=4:realized+=0.8;remain-=0.2;hit4=True
                if style=='scale6' and fav>=6:realized+=remain*6;remain=0;out=j;break
            best=max(best,hi) if d==1 else min(best,lo)
        if out is None:
            out=lastj; px=float(x.close.iloc[out]);realized+=remain*d*(px-entry)/riskdist
        rs.append(realized-COST_R);dur.append((ix[out]-ix[e_i]).total_seconds()/3600)
        i=max(i+1,out+1)
    return rs,dur


def summarize(name,side,style,rs,dur,foldrets,foldn):
    a=np.asarray(rs,float);eq=1.;peak=1.;dd=0
    for r in a:eq*=max(.001,1+RISK*r);peak=max(peak,eq);dd=max(dd,(peak-eq)/peak)
    gp=a[a>0].sum();gl=-a[a<0].sum()
    return {'name':name,'side':side,'exit':style,'trades':len(a),'win_rate':round(float((a>0).mean()*100),2),'return_pct':round((eq-1)*100,2),'max_dd_pct':round(dd*100,2),'pf':round(float(gp/gl if gl>0 else 99),3),'avg_r':round(float(a.mean()),3),'median_r':round(float(np.median(a)),3),'avg_hours':round(float(np.mean(dur)),2),'median_hours':round(float(np.median(dur)),2),'fold_returns':[round(v,2) for v in foldrets],'fold_trades':foldn}


def main():
    x=prep(); ladders=flags(x); actual_end=min(END,x.index.max()+pd.Timedelta(hours=1))
    folds=[];fs=START
    while fs<actual_end:
        fe=min(fs+pd.DateOffset(months=6),actual_end);folds.append((fs,fe));fs=fe
    results=[]
    for name,(ls,ss) in ladders.items():
      for long_only in [True,False]:
       for style in ['3R','scale6','trail']:
        rs,d=trade_sim(x,ls,ss,style,long_only,START,actual_end)
        if not rs:continue
        frs=[];fns=[]
        for a,b in folds:
            rr,dd=trade_sim(x,ls,ss,style,long_only,a,b);fns.append(len(rr));ee=1.
            for z in rr:ee*=max(.001,1+RISK*z)
            frs.append((ee-1)*100 if rr else 0.)
        results.append(summarize(name,'LONG' if long_only else 'BOTH',style,rs,d,frs,fns))
    def robust_score(r):
        if r['trades']<30:return -1e9
        med=float(np.median(r['fold_returns']));neg=sum(v<0 for v in r['fold_returns'])
        return r['return_pct']-.7*r['max_dd_pct']+3*med-2*neg
    robust=sorted(results,key=robust_score,reverse=True);raw=sorted(results,key=lambda z:z['return_pct'],reverse=True)
    out={'test_range':[str(START),str(actual_end)],'risk_per_setup_pct':0.36,'cost_R':COST_R,'source':'MT5 XAUUSD H1 tick_volume proxy','best_robust':robust[0] if robust else None,'best_raw_return':raw[0] if raw else None,'top_robust':robust[:12],'limitations':['OHLC bar backtest; conservative stop-first on ambiguous bars; no bid/ask spread beyond 0.05R cost assumption','tick_volume is activity proxy, not real traded volume','news and DXY not included in this run','profile is candle-based volume distribution, not exchange volume-at-price']}
    print('RESULT_JSON_START');print(json.dumps(out,ensure_ascii=False));print('RESULT_JSON_END')

if __name__=='__main__':main()
