from __future__ import annotations
import json
import numpy as np
import pandas as pd

URL="https://raw.githubusercontent.com/simom1/XAUUSD-history/main/Gold-Cash/XAUUSD/XAUUSD_M15.csv"
START=pd.Timestamp("2021-09-08",tz="UTC")
END=pd.Timestamp("2026-09-08 23:59:59",tz="UTC")
WARM=START-pd.Timedelta(days=160)
RISK=0.0036
COST_R=0.06


def vwma(x,n):
    typ=(x.high+x.low+x.close)/3.0; v=x.tick_volume.astype(float)
    return (typ*v).rolling(n,min_periods=n).sum()/v.rolling(n,min_periods=n).sum()

def enrich(x,periods):
    y=x.copy(); prev=y.close.shift(1)
    tr=pd.concat([(y.high-y.low).abs(),(y.high-prev).abs(),(y.low-prev).abs()],axis=1).max(axis=1)
    y['atr14']=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    typ=(y.high+y.low+y.close)/3.0; v=y.tick_volume.astype(float)
    for n in sorted(set(periods+[48,84])):
        y[f'vwma{n}']=vwma(y,n)
        sd=y.close.rolling(n,min_periods=n).std(ddof=0).replace(0,np.nan)
        y[f'z{n}']=(y.close-y[f'vwma{n}'])/sd
    y['dv']=typ*v; y['dvma30']=y.dv.rolling(30,min_periods=30).mean(); y['rqvol']=y.dvma30/y.dvma30.rolling(1800,min_periods=500).mean()
    y['range']=y.high-y.low; y['avg_range14']=y['range'].shift(1).rolling(14,min_periods=14).mean()
    return y

def resample(x,rule):
    g=x.resample(rule,origin='epoch',label='left',closed='left')
    out=g.agg({'open':'first','high':'max','low':'min','close':'last','tick_volume':'sum'})
    cnt=g.close.count(); expected=int(pd.Timedelta(rule)/pd.Timedelta(minutes=15))
    return out[cnt==expected].dropna()

def add_group_vwap(x,group,prefix):
    typ=(x.high+x.low+x.close)/3.0;v=x.tick_volume.clip(lower=1).astype(float);pv=typ*v
    cur=pv.groupby(group).cumsum()/v.groupby(group).cumsum(); codes,_=pd.factorize(group,sort=False); finals=cur.groupby(codes).last()
    prior=np.full(len(x),np.nan);m=codes>0;prior[m]=finals.iloc[codes[m]-1].to_numpy();x[prefix+'_vwap']=cur;x[prefix+'_prior']=prior

def profile(window,bins=24,va=.70):
    if len(window)<8:return np.nan,np.nan,np.nan
    lo=float(window.low.min());hi=float(window.high.max())
    if hi<=lo:return np.nan,np.nan,np.nan
    edges=np.linspace(lo,hi,bins+1);vols=np.zeros(bins)
    for r in window.itertuples():
        a=max(0,min(bins-1,int(np.searchsorted(edges,r.low,side='right')-1)));b=max(0,min(bins-1,int(np.searchsorted(edges,r.high,side='left')-1)));b=max(a,b)
        vols[a:b+1]+=float(r.tick_volume)/(b-a+1)
    if vols.sum()<=0:return np.nan,np.nan,np.nan
    p=int(np.argmax(vols));chosen={p};tot=vols[p];target=vols.sum()*va;l=p-1;r=p+1
    while tot<target and (l>=0 or r<bins):
        lv=vols[l] if l>=0 else -1;rv=vols[r] if r<bins else -1
        if rv>lv:chosen.add(r);tot+=rv;r+=1
        else:chosen.add(l);tot+=lv;l-=1
    return (edges[p]+edges[p+1])/2,edges[max(chosen)+1],edges[min(chosen)]

def prep():
    print('DOWNLOAD',URL,flush=True)
    x=pd.read_csv(URL);x['time']=pd.to_datetime(x.time,utc=True)
    for c in ['open','high','low','close','tick_volume']:x[c]=pd.to_numeric(x[c],errors='coerce')
    x=x.dropna().drop_duplicates('time').sort_values('time').set_index('time');x=x[(x.index>=WARM)&(x.index<=END)].copy()
    m15=enrich(x,[21,175,480,840]);h1=enrich(resample(x,'1h'),[21,84,175,480,840])
    day=pd.Series(m15.index.strftime('%Y-%m-%d'),index=m15.index);iso=m15.index.isocalendar();week=pd.Series(iso.year.astype(str)+'-'+iso.week.astype(str),index=m15.index)
    mins=m15.index.hour*60+m15.index.minute;sess_name=np.where(mins<480,'A',np.where(mins<810,'L','N'));sess=pd.Series(m15.index.strftime('%Y-%m-%d')+'_'+sess_name,index=m15.index)
    add_group_vwap(m15,sess,'sess');add_group_vwap(m15,day,'day');add_group_vwap(m15,week,'week')
    for n in [48,84]:m15[f'z{n}_max20']=m15[f'z{n}'].shift(1).rolling(20,min_periods=10).max();m15[f'z{n}_min20']=m15[f'z{n}'].shift(1).rolling(20,min_periods=10).min()
    # causal fixed 32-bar profile + developing daily POC
    fvah=np.full(len(m15),np.nan);fval=np.full(len(m15),np.nan);dpoc=np.full(len(m15),np.nan);ds=0
    for i in range(len(m15)):
        if i==0 or m15.index[i].date()!=m15.index[i-1].date():ds=i
        if i>=31:_,fvah[i],fval[i]=profile(m15.iloc[i-31:i+1])
        dpoc[i],_,_=profile(m15.iloc[ds:i+1])
    m15['fvah']=fvah;m15['fval']=fval;m15['dpoc']=dpoc
    # attach only completed H1 context
    a=m15.copy();a['decision']=a.index+pd.Timedelta(minutes=15)
    b=h1.copy();b['available']=b.index+pd.Timedelta(hours=1);b['h1_close']=b.close;b['h1_v84']=b.vwma84;b['h1_v175']=b.vwma175;b['h1_v480']=b.vwma480;b['h1_v840']=b.vwma840
    cols=['available','h1_close','h1_v84','h1_v175','h1_v480','h1_v840']
    z=pd.merge_asof(a.reset_index().sort_values('decision'),b[cols].sort_values('available'),left_on='decision',right_on='available',direction='backward').set_index('time').sort_index()
    print('RANGE',z.index.min(),z.index.max(),'M15',len(z),'H1',len(h1),flush=True)
    return z

def signals(x):
    # Parent H1 directional location
    hl=(x.h1_close>x.h1_v84)&(x.h1_v84>x.h1_v175)&(x.h1_v175>x.h1_v480)
    hs=(x.h1_close<x.h1_v84)&(x.h1_v84<x.h1_v175)&(x.h1_v175<x.h1_v480)
    # Native 15m trend + pullback/re-acceleration
    nl=(x.close>x.vwma21)&(x.vwma21>x.vwma175)&(x.vwma175>x.vwma480)
    ns=(x.close<x.vwma21)&(x.vwma21<x.vwma175)&(x.vwma175<x.vwma480)
    prev_pull_l=(x.low.shift(1)<=x.vwma21.shift(1)*1.0025)&(x.close.shift(1)>x.vwma175.shift(1)*.997)
    prev_pull_s=(x.high.shift(1)>=x.vwma21.shift(1)*.9975)&(x.close.shift(1)<x.vwma175.shift(1)*1.003)
    cp=(x.close-x.low)/x['range'].replace(0,np.nan)
    exp=x['range']>=1.35*x.avg_range14
    trig_l=exp&(x.close>x.open)&(cp>=.72)&(x.close>x.high.shift(1))
    trig_s=exp&(x.close<x.open)&(cp<=.28)&(x.close<x.low.shift(1))
    base_l=(hl&nl&prev_pull_l&trig_l).fillna(False);base_s=(hs&ns&prev_pull_s&trig_s).fillna(False)
    vl=(x.sess_vwap>x.sess_prior)&(x.day_vwap>x.day_prior)&(x.week_vwap>x.week_prior)&(x.close>x.sess_vwap)&(x.close>x.sess_prior)&(x.close>x.day_vwap)&(x.close>x.day_prior)&(x.close>x.week_vwap)&(x.close>x.week_prior)
    vs=(x.sess_vwap<x.sess_prior)&(x.day_vwap<x.day_prior)&(x.week_vwap<x.week_prior)&(x.close<x.sess_vwap)&(x.close<x.sess_prior)&(x.close<x.day_vwap)&(x.close<x.day_prior)&(x.close<x.week_vwap)&(x.close<x.week_prior)
    flow=(x.dv>x.dvma30)&(x.rqvol>1.0)
    zl=(x.z48>x.z48_max20)&(x.z84>x.z84_max20)&(x.z48>0)&(x.z84>0);zs=(x.z48<x.z48_min20)&(x.z84<x.z84_min20)&(x.z48<0)&(x.z84<0)
    pl=(x.close>x.fvah)&(x.close>x.dpoc);ps=(x.close<x.fval)&(x.close<x.dpoc)
    return {'MTF_BASE':(base_l,base_s),'PLUS_VWAP':(base_l&vl,base_s&vs),'PLUS_VWAP_FLOW':(base_l&vl&flow,base_s&vs&flow),'PLUS_VWAP_Z':(base_l&vl&zl,base_s&vs&zs),'PLUS_VWAP_PROFILE':(base_l&vl&pl,base_s&vs&ps),'FULL_AVAILABLE':(base_l&vl&flow&zl&pl,base_s&vs&flow&zs&ps)}

def sim(x,ls,ss,style,long_only,start,end,maxhold=48):
    ix=x.index;valid=np.flatnonzero(np.asarray((ix>=start)&(ix<end)))
    if not len(valid):return [],[]
    i=max(valid[0],20);last=valid[-1];rs=[];durs=[]
    while i<last-1:
        d=1 if bool(ls.iloc[i]) else (-1 if (not long_only and bool(ss.iloc[i])) else 0)
        if not d:i+=1;continue
        ei=i+1;entry=float(x.open.iloc[ei]);atr=float(x.atr14.iloc[i])
        if d==1:
            protected=min(float(x.low.iloc[max(0,i-7):i+1].min()),float(x.vwma175.iloc[i]));stop=min(entry-1.15*atr,protected*.9975);rd=entry-stop
        else:
            protected=max(float(x.high.iloc[max(0,i-7):i+1].max()),float(x.vwma175.iloc[i]));stop=max(entry+1.15*atr,protected*1.0025);rd=stop-entry
        if not np.isfinite(rd) or rd<=0 or rd/entry>.025:i+=1;continue
        rem=1.;real=0.;hit4=False;best=entry;active=stop;out=None;lastj=min(last,ei+maxhold)
        for j in range(ei,lastj+1):
            hi=float(x.high.iloc[j]);lo=float(x.low.iloc[j])
            if style=='trail' and hit4:active=max(stop,entry,best-2*rd) if d==1 else min(stop,entry,best+2*rd)
            if (lo<=active if d==1 else hi>=active):real+=rem*d*(active-entry)/rd;rem=0;out=j;break
            fav=(hi-entry)/rd if d==1 else (entry-lo)/rd
            if style=='3R' and fav>=3:real=3.;rem=0;out=j;break
            if style!='3R':
                if rem>.80-1e-9 and fav>=2:real+=.4;rem-=.2
                if rem>.60-1e-9 and fav>=4:real+=.8;rem-=.2;hit4=True
                if style=='scale6' and fav>=6:real+=rem*6;rem=0;out=j;break
            best=max(best,hi) if d==1 else min(best,lo)
        if out is None:out=lastj;real+=rem*d*(float(x.close.iloc[out])-entry)/rd
        rs.append(real-COST_R);durs.append((ix[out]-ix[ei]).total_seconds()/3600);i=max(i+1,out+1)
    return rs,durs

def pack(name,side,style,rs,durs,foldr,foldn):
    a=np.asarray(rs,float);eq=1.;peak=1.;dd=0
    for r in a:eq*=max(.001,1+RISK*r);peak=max(peak,eq);dd=max(dd,(peak-eq)/peak)
    gp=a[a>0].sum();gl=-a[a<0].sum()
    return {'name':name,'side':side,'exit':style,'trades':len(a),'win_rate':round(float((a>0).mean()*100),2),'return_pct':round((eq-1)*100,2),'max_dd_pct':round(dd*100,2),'pf':round(float(gp/gl if gl>0 else 99),3),'avg_r':round(float(a.mean()),3),'median_r':round(float(np.median(a)),3),'avg_hours':round(float(np.mean(durs)),2),'median_hours':round(float(np.median(durs)),2),'fold_returns':[round(z,2) for z in foldr],'fold_trades':foldn}
def main():
    x=prep();ladd=signals(x);actual_start=max(START,x.index.min());actual_end=min(END,x.index.max()+pd.Timedelta(minutes=15));folds=[];fs=actual_start
    while fs<actual_end:fe=min(fs+pd.DateOffset(months=6),actual_end);folds.append((fs,fe));fs=fe
    rows=[]
    for name,(ls,ss) in ladd.items():
      for lo in [True,False]:
       for style in ['3R','scale6','trail']:
        rs,d=sim(x,ls,ss,style,lo,actual_start,actual_end)
        if not rs:continue
        fr=[];fn=[]
        for a,b in folds:
            rr,_=sim(x,ls,ss,style,lo,a,b);fn.append(len(rr));e=1.
            for z in rr:e*=max(.001,1+RISK*z)
            fr.append((e-1)*100 if rr else 0.)
        rows.append(pack(name,'LONG' if lo else 'BOTH',style,rs,d,fr,fn))
    def score(r):
        if r['trades']<50:return -1e9
        med=float(np.median(r['fold_returns']));neg=sum(z<0 for z in r['fold_returns']);return r['return_pct']-.8*r['max_dd_pct']+3*med-2*neg
    robust=sorted(rows,key=score,reverse=True);raw=sorted(rows,key=lambda r:r['return_pct'],reverse=True)
    print('RESULT_JSON_START');print(json.dumps({'range':[str(actual_start),str(actual_end)],'risk_pct':.36,'cost_R':COST_R,'best_robust':robust[0] if robust else None,'best_raw':raw[0] if raw else None,'top':[r for r in robust[:15]],'limitations':['bar OHLC not tick bid/ask','tick volume proxy','news/DXY not included','candle-based profile']},ensure_ascii=False));print('RESULT_JSON_END')
if __name__=='__main__':main()
