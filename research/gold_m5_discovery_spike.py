from __future__ import annotations
import json, math
from dataclasses import dataclass
import numpy as np
import pandas as pd

URLS=[
"https://raw.githubusercontent.com/simom1/XAUUSD-history/main/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv",
"https://raw.githubusercontent.com/simom1/XAUUSD-history/main/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv"]
START=pd.Timestamp("2021-09-08",tz="UTC"); TRAIN_END=pd.Timestamp("2024-01-01",tz="UTC")
VAL_END=pd.Timestamp("2025-01-01",tz="UTC"); END=pd.Timestamp("2026-09-03",tz="UTC")
WARMUP=START-pd.Timedelta(days=240); RISK=.0036; COST_R=.08

def read_all():
    out=[]
    for u in URLS:
        print("DOWNLOAD",u,flush=True); d=pd.read_csv(u); d["time"]=pd.to_datetime(d.time,utc=True)
        d=d[(d.time>=WARMUP)&(d.time<END)][["time","open","high","low","close","tick_volume"]].copy()
        for c in ["open","high","low","close","tick_volume"]: d[c]=pd.to_numeric(d[c],errors="coerce")
        out.append(d.dropna())
    d=pd.concat(out,ignore_index=True).drop_duplicates("time").sort_values("time").set_index("time")
    print("M1_RANGE",d.index.min(),d.index.max(),"ROWS",len(d),flush=True); return d

def rs(df,rule,frac=.8):
    g=df.resample(rule,origin="epoch",label="left",closed="left"); out=g.agg(open=("open","first"),high=("high","max"),low=("low","min"),close=("close","last"),tick_volume=("tick_volume","sum"))
    cnt=g.close.count(); exp=int(pd.Timedelta(rule)/pd.Timedelta(minutes=1)); return out[cnt>=max(1,int(exp*frac))].dropna()

def vwma(x,n):
    typ=(x.high+x.low+x.close)/3; v=x.tick_volume.clip(lower=1).astype(float)
    return (typ*v).rolling(n,min_periods=n).sum()/v.rolling(n,min_periods=n).sum()

def atr(x,n=14):
    pc=x.close.shift(1); tr=pd.concat([(x.high-x.low).abs(),(x.high-pc).abs(),(x.low-pc).abs()],axis=1).max(axis=1)
    return tr.rolling(n,min_periods=n).mean()

def core(x,periods):
    x=x.copy()
    for n in sorted(set(list(periods)+[48,84])):
        x[f"vwma{n}"]=vwma(x,n); sd=x.close.rolling(n,min_periods=n).std(ddof=0).replace(0,np.nan); x[f"z{n}"]=(x.close-x[f"vwma{n}"])/sd
    x["atr14"]=atr(x); typ=(x.high+x.low+x.close)/3; x["dv"]=typ*x.tick_volume; x["dvma30"]=x.dv.rolling(30,min_periods=30).mean(); x["rqvol"]=x.dvma30/x.dvma30.rolling(1800,min_periods=300).mean(); return x

def vwaps(x):
    x=x.copy(); typ=(x.high+x.low+x.close)/3; vol=x.tick_volume.clip(lower=1).astype(float); pv=typ*vol; idx=x.index
    day=pd.Series(idx.strftime("%Y-%m-%d"),index=idx); iso=idx.isocalendar(); week=pd.Series(iso.year.astype(str)+"-"+iso.week.astype(str),index=idx)
    mins=idx.hour*60+idx.minute; sn=np.where(mins<480,"A",np.where(mins<870,"L","N")); sess=pd.Series(idx.strftime("%Y-%m-%d")+"_"+sn,index=idx)
    def mk(group,p):
        cur=pv.groupby(group).cumsum()/vol.groupby(group).cumsum(); finals=cur.groupby(group).last(); keys=list(pd.unique(group)); mp={keys[i]:float(finals.loc[keys[i-1]]) for i in range(1,len(keys))}; x[f"{p}_vwap"]=cur; x[f"{p}_prior"]=group.map(mp).astype(float)
    mk(sess,"sess"); mk(day,"day"); mk(week,"week"); return x

def prev_levels(x):
    x=x.copy(); day=pd.Series(x.index.strftime("%Y-%m-%d"),index=x.index); da=x.groupby(day).agg(hi=("high","max"),lo=("low","min")); ks=list(da.index)
    x["pdh"]=day.map({ks[i]:float(da.iloc[i-1].hi) for i in range(1,len(ks))}).astype(float); x["pdl"]=day.map({ks[i]:float(da.iloc[i-1].lo) for i in range(1,len(ks))}).astype(float)
    mins=x.index.hour*60+x.index.minute; sn=np.where(mins<480,"A",np.where(mins<870,"L","N")); sk=pd.Series(x.index.strftime("%Y-%m-%d")+"_"+sn,index=x.index); sa=x.groupby(sk).agg(hi=("high","max"),lo=("low","min")); ss=list(sa.index)
    x["prev_sess_hi"]=sk.map({ss[i]:float(sa.iloc[i-1].hi) for i in range(1,len(ss))}).astype(float); x["prev_sess_lo"]=sk.map({ss[i]:float(sa.iloc[i-1].lo) for i in range(1,len(ss))}).astype(float); return x

def prep():
    m1=read_all(); m5=prev_levels(vwaps(core(rs(m1,"5min"),[84,175]))); m15=core(rs(m1,"15min"),[21,175,480,840]); h1=core(rs(m1,"1h"),[21,84,175,480,840]); h1["vwma84_prev6"]=h1.vwma84.shift(6)
    print("BARS",len(m5),len(m15),len(h1),flush=True)
    b=m5.copy(); b["decision_time"]=b.index+pd.Timedelta(minutes=5); b=b.reset_index().rename(columns={"time":"bar_time"})
    q15=m15.add_prefix("m15_"); q15["ctx15"]=m15.index+pd.Timedelta(minutes=15); q15=q15.reset_index(drop=True)
    q1=h1.add_prefix("h1_"); q1["ctx1"]=h1.index+pd.Timedelta(hours=1); q1=q1.reset_index(drop=True)
    b=pd.merge_asof(b.sort_values("decision_time"),q15.sort_values("ctx15"),left_on="decision_time",right_on="ctx15",direction="backward")
    b=pd.merge_asof(b.sort_values("decision_time"),q1.sort_values("ctx1"),left_on="decision_time",right_on="ctx1",direction="backward").set_index("bar_time").sort_index()
    rng=b.high-b.low; b["range_med20"]=rng.shift(1).rolling(20,min_periods=12).median(); b["rh12"]=b.high.shift(1).rolling(12,min_periods=12).max(); b["rl12"]=b.low.shift(1).rolling(12,min_periods=12).min(); b["rh24"]=b.high.shift(1).rolling(24,min_periods=24).max(); b["rl24"]=b.low.shift(1).rolling(24,min_periods=24).min(); b["swinglo6"]=b.low.shift(1).rolling(6,min_periods=4).min(); b["swinghi6"]=b.high.shift(1).rolling(6,min_periods=4).max()
    hi2=b.high.shift(2); lo2=b.low.shift(2); b["fr_hi"]=hi2.where(hi2>=b.high.rolling(5,min_periods=5).max()-1e-12).ffill(); b["fr_lo"]=lo2.where(lo2<=b.low.rolling(5,min_periods=5).min()+1e-12).ffill()
    b["z48_prev10max"]=b.z48.shift(1).rolling(10,min_periods=8).max(); b["z84_prev10max"]=b.z84.shift(1).rolling(10,min_periods=8).max(); b["z48_prev10min"]=b.z48.shift(1).rolling(10,min_periods=8).min(); b["z84_prev10min"]=b.z84.shift(1).rolling(10,min_periods=8).min(); return b

def contexts(x):
    L=(x.h1_close>x.h1_vwma84)&(x.h1_vwma84>x.h1_vwma175)&(x.h1_vwma84>x.h1_vwma84_prev6); S=(x.h1_close<x.h1_vwma84)&(x.h1_vwma84<x.h1_vwma175)&(x.h1_vwma84<x.h1_vwma84_prev6)
    mL=(x.m15_close>x.m15_vwma21)&(x.m15_vwma21>x.m15_vwma175); mS=(x.m15_close<x.m15_vwma21)&(x.m15_vwma21<x.m15_vwma175)
    return {"med":(L.fillna(False),S.fillna(False)),"mtf":((L&mL).fillna(False),(S&mS).fillna(False))}

def gates(x):
    vL=(x.close>x.sess_vwap)&(x.close>x.day_vwap)&(x.close>x.week_vwap)&(x.day_vwap>x.day_prior)&(x.week_vwap>x.week_prior); vS=(x.close<x.sess_vwap)&(x.close<x.day_vwap)&(x.close<x.week_vwap)&(x.day_vwap<x.day_prior)&(x.week_vwap<x.week_prior)
    zL=(x.z48>x.z48_prev10max)&(x.z84>x.z84_prev10max)&(x.z48>0)&(x.z84>0); zS=(x.z48<x.z48_prev10min)&(x.z84<x.z84_prev10min)&(x.z48<0)&(x.z84<0); flow=(x.dv>x.dvma30)&(x.rqvol>.9)
    return vL.fillna(False),vS.fillna(False),zL.fillna(False),zS.fillna(False),flow.fillna(False)

@dataclass(frozen=True)
class Spec: family:str; context:str; gate:str; exit:str; side:str; param:float

def sig(x,s,ctxs,gs):
    c,o,h,l=x.close,x.open,x.high,x.low; CL,CS=ctxs[s.context]; vL,vS,zL,zS,flow=gs; above=(c>x.vwma84)&(x.vwma84>x.vwma175); below=(c<x.vwma84)&(x.vwma84<x.vwma175)
    if s.family=="EXP":
        rr=(h-l)/x.range_med20; L=(rr>=s.param)&(c>o)&(((c-l)/(h-l).replace(0,np.nan))>=.78)&above; S=(rr>=s.param)&(c<o)&(((h-c)/(h-l).replace(0,np.nan))>=.78)&below
    elif s.family=="PULL":
        L=(x.low.shift(1)<=x.vwma84.shift(1)*1.001)&(x.low.shift(1)>=x.vwma175.shift(1)*.997)&(c>x.vwma84)&(c>x.high.shift(1))&(x.z48>x.z48.shift(1)); S=(x.high.shift(1)>=x.vwma84.shift(1)*.999)&(x.high.shift(1)<=x.vwma175.shift(1)*1.003)&(c<x.vwma84)&(c<x.low.shift(1))&(x.z48<x.z48.shift(1))
    elif s.family=="BRK":
        L=(c>(x.rh12 if s.param<20 else x.rh24))&above; S=(c<(x.rl12 if s.param<20 else x.rl24))&below
    elif s.family=="SWEEP":
        L=(((l<x.pdl)&(c>x.pdl))|((l<x.prev_sess_lo)&(c>x.prev_sess_lo)))&(c>o); S=(((h>x.pdh)&(c<x.pdh))|((h>x.prev_sess_hi)&(c<x.prev_sess_hi)))&(c<o)
    else:
        active=(x.index.hour>=6)&(x.index.hour<=20); L=active&(c>x.fr_hi)&(c.shift(1)<=x.fr_hi.shift(1))&above; S=active&(c<x.fr_lo)&(c.shift(1)>=x.fr_lo.shift(1))&below
    L=L&CL; S=S&CS
    if s.gate=="vwap": L&=vL; S&=vS
    elif s.gate=="z": L&=zL; S&=zS
    elif s.gate=="flow": L&=flow; S&=flow
    elif s.gate=="vwap_flow": L&=vL&flow; S&=vS&flow
    if s.side=="long": S=pd.Series(False,index=x.index)
    return L.fillna(False),S.fillna(False)

def specs():
    out=[]
    for fam,pars in [("EXP",[1.5,1.8,2.1]),("PULL",[0]),("BRK",[12,24]),("SWEEP",[0]),("FRACTAL",[0])]:
        for c in ["med","mtf"]:
            for g in ["none","vwap","z","flow","vwap_flow"]:
                for side in ["both","long"]:
                    for ex in ["3R","5R","8R","runner"]:
                        for p in pars: out.append(Spec(fam,c,g,ex,side,float(p)))
    return out

def name(s): return f"{s.family}|{s.context}|{s.gate}|{s.side}|{s.exit}|{s.param:g}"

def simulate(x,L,S,s,start,end):
    mask=np.asarray((x.index>=start)&(x.index<end)); idx=np.flatnonzero((L|S).to_numpy()&mask); rs=[]; ds=[]; p=0
    while p<len(idx):
        i=int(idx[p]);
        if i+1>=len(x): break
        direction=1 if bool(L.iloc[i]) else -1; ei=i+1; ent=float(x.open.iloc[ei]); av=float(x.atr14.iloc[i])
        if not np.isfinite(av) or av<=0: p+=1; continue
        if direction==1: swing=min(float(x.low.iloc[i]),float(x.swinglo6.iloc[i])); stop=min(swing-.1*av,ent-.85*av); risk=ent-stop
        else: swing=max(float(x.high.iloc[i]),float(x.swinghi6.iloc[i])); stop=max(swing+.1*av,ent+.85*av); risk=stop-ent
        if not np.isfinite(risk) or risk<=0 or risk/ent>.012: p+=1; continue
        rem=1.; real=0.; trail=None; endi=min(len(x)-1,ei+144); exit_i=endi
        for j in range(ei,endi+1):
            hi=float(x.high.iloc[j]); lo=float(x.low.iloc[j]); astop=stop if trail is None else (max(stop,trail) if direction==1 else min(stop,trail)); hit=lo<=astop if direction==1 else hi>=astop
            if hit: real+=rem*direction*(astop-ent)/risk; exit_i=j; rem=0; break
            if s.exit in ("3R","5R","8R"):
                t=float(s.exit[:-1]); thit=hi>=ent+t*risk if direction==1 else lo<=ent-t*risk
                if thit: real=t; rem=0; exit_i=j; break
            else:
                if rem>.8-1e-9:
                    h2=hi>=ent+2*risk if direction==1 else lo<=ent-2*risk
                    if h2: real+=.4; rem-=.2
                if rem>.6-1e-9:
                    h4=hi>=ent+4*risk if direction==1 else lo<=ent-4*risk
                    if h4: real+=.8; rem-=.2
                if rem<=.6+1e-9:
                    trail=max(ent,hi-2*risk,trail if trail is not None else ent) if direction==1 else min(ent,lo+2*risk,trail if trail is not None else ent)
            if j==endi and rem>0: real+=rem*direction*(float(x.close.iloc[j])-ent)/risk
        rs.append(real-COST_R); ds.append((x.index[exit_i]-x.index[ei]).total_seconds()/3600); p=int(np.searchsorted(idx,exit_i+1,side="left"))
    return rs,ds

def met(rs,ds):
    if not rs:return None
    a=np.array(rs,float); eq=1.; peak=1.; dd=0
    for r in a: eq*=max(1e-9,1+RISK*r); peak=max(peak,eq); dd=max(dd,(peak-eq)/peak)
    pos=a[a>0].sum(); neg=-a[a<0].sum(); return {"n":len(a),"ret":(eq-1)*100,"wr":(a>0).mean()*100,"pf":pos/neg if neg else 99,"avgR":a.mean(),"dd":dd*100,"medR":float(np.median(a)),"avgH":float(np.mean(ds)),"medH":float(np.median(ds))}

def main():
    x=prep(); ctx=contexts(x); gs=gates(x); ss=specs(); print("CANDIDATES",len(ss),flush=True); rows=[]; cache={}
    for k,s in enumerate(ss):
        L,S=sig(x,s,ctx,gs); cache[name(s)]=(L,S); tr=met(*simulate(x,L,S,s,START,TRAIN_END))
        if not tr or tr["n"]<80 or tr["pf"]<1.05 or tr["ret"]<=0: continue
        va=met(*simulate(x,L,S,s,TRAIN_END,VAL_END)); score=-999 if not va else tr["ret"]-1.2*tr["dd"]+.5*va["ret"]-.8*va["dd"]; rows.append((score,s,tr,va))
        if k%100==0: print("PROGRESS",k,flush=True)
    rows.sort(key=lambda z:z[0],reverse=True); promoted=[]; fam=set()
    for score,s,tr,va in rows:
        if va and va["n"]>=25 and va["ret"]>0 and va["pf"]>=1.08 and s.family not in fam:
            ho=met(*simulate(x,*cache[name(s)],s,VAL_END,END)); promoted.append({"spec":name(s),"train":tr,"val":va,"holdout":ho,"score":score}); fam.add(s.family)
        if len(promoted)>=5: break
    top=[]
    for score,s,tr,va in rows[:20]: top.append({"spec":name(s),"train":tr,"val":va,"holdout":met(*simulate(x,*cache[name(s)],s,VAL_END,END)),"score":score})
    best=None
    if promoted:
        sname=promoted[0]["spec"]; s=next(q for q in ss if name(q)==sname); best={"spec":sname,"full":met(*simulate(x,*cache[sname],s,START,END))}
    print("RESULT_JSON_START"); print(json.dumps({"range":[str(x.index.min()),str(x.index.max())],"splits":[str(START),str(TRAIN_END),str(VAL_END),str(END)],"risk_pct":.36,"cost_R":COST_R,"candidate_count":len(ss),"target_1000":{"multiple":11,"required_5y_cagr_pct":(11**.2-1)*100,"approx_required_net_R":math.log(11)/RISK},"promoted":promoted,"top20":top,"best_single":best,"limitations":["M1 OHLC resampled to M5, not bid/ask ticks","tick_volume proxy","news/DXY/profile intentionally deferred until after discovery","one active position at a time","0.08R cost deducted per completed trade"]},default=float)); print("RESULT_JSON_END")
if __name__=="__main__": main()
