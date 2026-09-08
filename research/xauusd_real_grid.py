#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math
from dataclasses import dataclass, asdict
from pathlib import Path
import numpy as np
import pandas as pd

RISK = 0.0036
VW = (21,48,84,175,480,840)
ZP = (21,48,84,175,480)
TFS = (15,30,45,60)
TRAIN_START = pd.Timestamp('2021-09-01', tz='UTC')
TRAIN_END = pd.Timestamp('2024-01-01', tz='UTC')
VALID_END = pd.Timestamp('2025-01-01', tz='UTC')
BASE_SPREAD_USD = 0.10

@dataclass(frozen=True)
class SigCfg:
    tf:int; setup:str; trend:str; vwap:str; zthr:float; zslow:str

@dataclass(frozen=True)
class ExitCfg:
    atr_mult:float; management:str

def read_data(path:Path)->pd.DataFrame:
    df=pd.read_csv(path)
    df.columns=[str(c).strip().lower().replace('<','').replace('>','') for c in df.columns]
    if 'time' not in df.columns and 'date' in df.columns:
        if 'time.1' in df.columns:
            df['time']=pd.to_datetime(df['date'].astype(str)+' '+df['time.1'].astype(str),utc=True,errors='coerce')
        else:
            df['time']=pd.to_datetime(df['date'],utc=True,errors='coerce')
    else:
        df['time']=pd.to_datetime(df['time'],utc=True,errors='coerce')
    ren={}
    for c in df.columns:
        lc=c.lower()
        if lc in ('tickvol','tick_volume','tickvolume'): ren[c]='volume'
    df=df.rename(columns=ren)
    if 'volume' not in df.columns:
        if 'vol' in df.columns: df['volume']=df['vol']
        else: raise ValueError('No tick volume column')
    req=['time','open','high','low','close','volume']
    for c in req:
        if c!='time': df[c]=pd.to_numeric(df[c],errors='coerce')
    df=df.dropna(subset=req).drop_duplicates('time').sort_values('time').reset_index(drop=True)
    df=df[(df.time>=pd.Timestamp('2020-01-01',tz='UTC'))].copy()
    return df

def safe_div(a,b): return a/b.replace(0,np.nan)

def resample(base:pd.DataFrame,tf:int)->pd.DataFrame:
    if tf==15: return base[['time','open','high','low','close','volume']].copy()
    need=tf//15
    x=base.set_index('time')
    r=x.resample(f'{tf}min',label='left',closed='left',origin='start_day').agg(
        open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),volume=('volume','sum'),n=('close','count'))
    r=r[r.n==need].drop(columns='n').dropna().reset_index()
    return r

def add_feat(df:pd.DataFrame)->pd.DataFrame:
    x=df.copy(); c=x.close.astype(float); v=x.volume.astype(float)
    for n in VW:
        x[f'vwma{n}']=safe_div((c*v).rolling(n,min_periods=n).sum(),v.rolling(n,min_periods=n).sum())
    for n in ZP:
        sd=c.rolling(n,min_periods=n).std(ddof=0)
        x[f'z{n}']=(c-x[f'vwma{n}'])/sd.replace(0,np.nan)
    pc=c.shift(1)
    tr=pd.concat([(x.high-x.low),(x.high-pc).abs(),(x.low-pc).abs()],axis=1).max(axis=1)
    x['atr14']=tr.rolling(14,min_periods=14).mean()
    vm=v.rolling(30,min_periods=30).mean(); vs=v.rolling(30,min_periods=30).std(ddof=0)
    x['rvol']=v/vm.replace(0,np.nan); x['vol_z']=(v-vm)/vs.replace(0,np.nan)
    x['body_atr']=(x.close-x.open).abs()/x.atr14.replace(0,np.nan)
    x['swing12']=x.low.rolling(12,min_periods=12).min()
    x['ph3']=x.high.shift(1).rolling(3,min_periods=3).max()
    x['ph12']=x.high.shift(1).rolling(12,min_periods=12).max()
    x['touch48']=(x.low<=x.vwma48*1.002)
    x['touch84']=(x.low<=x.vwma84*1.002)
    x['deep_touch']=(x.low<=x.vwma84*1.002)&(x.close>=x.vwma175*0.997)
    x['recent_shallow']=(x.touch48|x.touch84).shift(1).rolling(8,min_periods=1).max().fillna(0).astype(bool)
    x['recent_deep']=x.deep_touch.shift(1).rolling(12,min_periods=1).max().fillna(0).astype(bool)
    return x

def period_vwap(tp,pvvol,key):
    pv=tp*pvvol
    cur=pv.groupby(key).cumsum()/pvvol.groupby(key).cumsum().replace(0,np.nan)
    tmp=pd.DataFrame({'k':key,'v':cur})
    fin=tmp.groupby('k',sort=True).v.last()
    prev=key.map(fin.shift(1))
    return cur,prev

def vwap_context(base:pd.DataFrame)->pd.DataFrame:
    x=base.copy(); tp=(x.high+x.low+x.close)/3.0; vol=x.volume.astype(float)
    daynum=(x.time.astype('int64')//86_400_000_000_000).astype(np.int64)
    week=((daynum+3)//7).astype(np.int64)
    minute=x.time.dt.hour*60+x.time.dt.minute
    sess=np.where(minute<480,0,np.where(minute<870,1,2)).astype(np.int64)
    sid=daynum*3+sess
    x['d_vwap'],x['prev_d_vwap']=period_vwap(tp,vol,pd.Series(daynum,index=x.index))
    x['w_vwap'],x['prev_w_vwap']=period_vwap(tp,vol,pd.Series(week,index=x.index))
    x['s_vwap'],x['prev_s_vwap']=period_vwap(tp,vol,pd.Series(sid,index=x.index))
    x['session']=np.where(sess==0,'ASIA',np.where(sess==1,'LONDON','NEW_YORK'))
    x['ctx_time']=x.time+pd.Timedelta(minutes=15)
    return x[['ctx_time','d_vwap','prev_d_vwap','w_vwap','prev_w_vwap','s_vwap','prev_s_vwap','session']]

def attach_context(frame:pd.DataFrame,tf:int,vctx:pd.DataFrame,frames:dict[int,pd.DataFrame])->pd.DataFrame:
    x=frame.copy(); x['signal_time']=x.time+pd.to_timedelta(tf,unit='m')
    x=pd.merge_asof(x.sort_values('signal_time'),vctx.sort_values('ctx_time'),left_on='signal_time',right_on='ctx_time',direction='backward')
    htf=60 if tf<=30 else 240
    h=frames[htf].copy(); h['htf_time']=h.time+pd.to_timedelta(htf,unit='m')
    cols=['htf_time','close','vwma48','vwma84','vwma175','vwma480','z48','z84']
    h=h[cols].rename(columns={c:f'htf_{c}' for c in cols if c!='htf_time'})
    x=pd.merge_asof(x.sort_values('signal_time'),h.sort_values('htf_time'),left_on='signal_time',right_on='htf_time',direction='backward')
    return x.reset_index(drop=True)

def trend_gate(x,mode):
    if mode=='CORE':
        return (x.close>x.vwma21)&(x.vwma48>x.vwma84)&(x.vwma84>x.vwma175)&(x.vwma175>x.vwma480)&(x.vwma480>x.vwma840)
    return (x.close>x.vwma21)&(x.vwma21>x.vwma48)&(x.vwma48>x.vwma84)&(x.vwma84>x.vwma175)&(x.vwma175>x.vwma480)&(x.vwma480>x.vwma840)

def htf_gate(x):
    return (x.htf_close>x.htf_vwma175)&(x.htf_vwma48>x.htf_vwma84)&(x.htf_vwma84>x.htf_vwma175)&(x.htf_z48>0)&(x.htf_z84>-0.5)

def vw_gate(x,mode):
    if mode=='NONE': return pd.Series(True,index=x.index)
    d=(x.close>x.d_vwap)&(x.d_vwap>x.prev_d_vwap)&(x.close>x.prev_d_vwap)
    w=(x.close>x.w_vwap)&(x.w_vwap>x.prev_w_vwap)&(x.close>x.prev_w_vwap)
    if mode=='DW': return d&w
    s=(x.close>x.s_vwap)&(x.s_vwap>x.prev_s_vwap)&(x.close>x.prev_s_vwap)
    if mode=='DWS': return d&w&s
    return d&w&s&(x.s_vwap>x.d_vwap)&(x.d_vwap>x.w_vwap)

def zslow_gate(x,mode):
    if mode=='NONE': return pd.Series(True,index=x.index)
    if mode=='Z175': return x.z175>0
    if mode=='Z480': return x.z480>0
    return (x.z175>0)&(x.z480>0)

def setup_gate(x,setup,zthr):
    bull=(x.close>x.open)&(x.body_atr>=0.12); act=(x.rvol>=0.90)|(x.vol_z>=-0.25)
    if setup=='SHALLOW': return x.recent_shallow&(x.close>x.vwma21)&(x.close>x.ph3)&(x.z21>=zthr)&(x.z48>0)&bull&act
    if setup=='DEEP': return x.recent_deep&(x.close>x.vwma21)&(x.close>x.ph3)&(x.z48>=zthr)&(x.z84>0)&bull&act
    return (x.close>x.ph12)&(x.z21>=zthr)&(x.z48>=max(.25,.6*zthr))&(x.body_atr>=.20)&bull&((x.rvol>=1)|(x.vol_z>=0))

def signal(x,cfg):
    s=trend_gate(x,cfg.trend)&htf_gate(x)&vw_gate(x,cfg.vwap)&zslow_gate(x,cfg.zslow)&setup_gate(x,cfg.setup,cfg.zthr)
    return s.fillna(False)

def exits(man):
    if man=='2R': return [2.0],[1.0]
    if man=='3R': return [3.0],[1.0]
    if man=='4R': return [4.0],[1.0]
    if man=='FIB': return [1.618,2.0,2.618],[.55,.30,.15]
    if man=='EXT': return [1.5,2.5,4.0],[.55,.30,.15]
    raise ValueError(man)

def simulate(x,sig,ex:ExitCfg,spread=BASE_SPREAD_USD):
    idx=np.flatnonzero(sig.to_numpy(bool)); out=[]; blocked=-1; tg,w=exits(ex.management)
    max_hold=max(16,int(24*60/int(x.attrs['tf'])))
    for i in idx:
        if i<=blocked or i+1>=len(x): continue
        entry_i=i+1; entry=float(x.open.iat[entry_i])+spread
        atr=float(x.atr14.iat[i]); swing=float(x.swing12.iat[i])
        if not np.isfinite(entry+atr+swing) or atr<=0: continue
        stop=min(swing-.10*atr,entry-ex.atr_mult*atr); rd=entry-stop
        if rd<=0 or rd<.50*atr or rd>5*atr: continue
        end=min(len(x)-1,entry_i+max_hold)
        rem=1.0; pnl=0.0; active=stop; hit=[False]*len(tg); reason='TIME'; jx=end
        for j in range(entry_i,end+1):
            lo=float(x.low.iat[j]); hi=float(x.high.iat[j])
            if lo<=active:
                pnl+=rem*(active-entry)/rd; rem=0; reason='STOP' if not any(hit) else 'MANAGED_STOP'; jx=j; break
            for k,r in enumerate(tg):
                if not hit[k] and hi>=entry+r*rd:
                    pnl+=w[k]*r; rem-=w[k]; hit[k]=True
                    if len(tg)>1:
                        if k==0: active=max(active,entry)
                        elif k==1: active=max(active,entry+tg[0]*rd)
                    if rem<=1e-12: rem=0; reason='TARGET'; jx=j
                    break
            if rem<=1e-12: break
        if rem>1e-12:
            pnl+=rem*(float(x.close.iat[jx])-entry)/rd
        out.append({'signal_time':x.signal_time.iat[i],'entry_time':x.time.iat[entry_i],'exit_time':x.time.iat[jx],'pnl_r':pnl,'entry':entry,'stop':stop,'risk_points':rd,'bars':jx-entry_i+1,'exit_reason':reason,'session':x.session.iat[i]})
        blocked=jx
    return pd.DataFrame(out)

def metrics(t):
    if t.empty: return {'n':0,'win':np.nan,'exp_r':np.nan,'pf':np.nan,'dd_pct':np.nan,'ret_pct':np.nan,'avg_hold_h':np.nan}
    r=t.pnl_r.to_numpy(float); eq=[1.0]
    for z in r: eq.append(eq[-1]*max(1e-9,1+RISK*z))
    eq=np.asarray(eq); pk=np.maximum.accumulate(eq); dd=eq/pk-1
    gp=r[r>0].sum(); gl=-r[r<0].sum()
    hold=(pd.to_datetime(t.exit_time,utc=True)-pd.to_datetime(t.entry_time,utc=True)).dt.total_seconds()/3600
    return {'n':int(len(r)),'win':float(np.mean(r>0)),'exp_r':float(np.mean(r)),'pf':float(gp/gl) if gl>0 else 99.0,'dd_pct':float(-dd.min()*100),'ret_pct':float((eq[-1]-1)*100),'avg_hold_h':float(hold.mean())}

def cut(t,a,b=None):
    if t.empty:return t
    z=pd.to_datetime(t.entry_time,utc=True); m=z>=a
    if b is not None:m&=z<b
    return t[m].copy()

def three(t): return metrics(cut(t,TRAIN_START,TRAIN_END)),metrics(cut(t,TRAIN_END,VALID_END)),metrics(cut(t,VALID_END))

def score(a,b):
    if a['n']<40 or b['n']<12 or a['exp_r']<=0 or b['exp_r']<=0 or a['pf']<=1.05 or b['pf']<=1.05:return -1e9
    return 2*min(a['exp_r'],b['exp_r'])+.25*(min(a['pf'],b['pf'],3)-1)+.02*min(b['ret_pct']/max(b['dd_pct'],1),5)+.004*math.sqrt(b['n'])

def configs():
    return [SigCfg(tf,se,tr,vw,z,zs) for tf in TFS for se in ('SHALLOW','DEEP','BREAKOUT') for tr in ('CORE','FULL') for vw in ('NONE','DW','DWS','LADDER') for z in (.5,.875,1.25) for zs in ('NONE','Z175','Z480','BOTH')]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--data',type=Path,required=True); ap.add_argument('--out',type=Path,default=Path('xau_results')); args=ap.parse_args(); args.out.mkdir(parents=True,exist_ok=True)
    raw=read_data(args.data); data_end=raw.time.max(); vctx=vwap_context(raw)
    baseframes={tf:add_feat(resample(raw,tf)) for tf in (15,30,45,60,240)}
    frames={}
    for tf in TFS:
        x=attach_context(baseframes[tf],tf,vctx,baseframes); x.attrs['tf']=tf; frames[tf]=x
    rows=[]; sigcache={}; baseex=ExitCfg(2.0,'3R'); cs=configs(); print('DATA',len(raw),raw.time.min(),data_end,'GRID',len(cs),flush=True)
    for q,cfg in enumerate(cs,1):
        s=signal(frames[cfg.tf],cfg); sigcache[cfg]=s; t=simulate(frames[cfg.tf],s,baseex)
        a,b,o=three(t); rows.append({**asdict(cfg),'score':score(a,b),**{f'train_{k}':v for k,v in a.items()},**{f'valid_{k}':v for k,v in b.items()},**{f'oos_{k}':v for k,v in o.items()}})
        if q%100==0: print(q,'/',len(cs),flush=True)
    g=pd.DataFrame(rows).sort_values(['score','valid_exp_r','valid_pf'],ascending=False); g.to_csv(args.out/'stage1.csv',index=False)
    eligible=g[g.score>-1e8].head(12); diag=False
    if eligible.empty: eligible=g.head(12); diag=True
    rows2=[]; trades={}
    for _,r in eligible.iterrows():
        cfg=SigCfg(int(r.tf),str(r.setup),str(r.trend),str(r.vwap),float(r.zthr),str(r.zslow)); s=sigcache[cfg]
        for am in (1.5,2.0,2.5,3.0):
            for man in ('2R','3R','4R','FIB','EXT'):
                ex=ExitCfg(am,man); t=simulate(frames[cfg.tf],s,ex); a,b,o=three(t); key=f'{cfg.tf}-{cfg.setup}-{cfg.trend}-{cfg.vwap}-z{cfg.zthr}-{cfg.zslow}-a{am}-{man}'; trades[key]=t
                rows2.append({'key':key,**asdict(cfg),**asdict(ex),'score':score(a,b),**{f'train_{k}':v for k,v in a.items()},**{f'valid_{k}':v for k,v in b.items()},**{f'oos_{k}':v for k,v in o.items()}})
    g2=pd.DataFrame(rows2).sort_values(['score','valid_exp_r','valid_pf'],ascending=False); g2.to_csv(args.out/'stage2.csv',index=False)
    dep=g2[g2.score>-1e8]; selected=dep.iloc[0] if len(dep) else g2.iloc[0]; key=str(selected.key); seltr=trades[key]; seltr.to_csv(args.out/'selected_trades.csv',index=False)
    ab=[]
    for vw in ('NONE','DW','DWS','LADDER'):
        for zs in ('NONE','Z175','Z480','BOTH'):
            cfg=SigCfg(int(selected.tf),str(selected.setup),str(selected.trend),vw,float(selected.zthr),zs); ex=ExitCfg(float(selected.atr_mult),str(selected.management)); t=simulate(frames[cfg.tf],signal(frames[cfg.tf],cfg),ex); a,b,o=three(t)
            ab.append({'vwap':vw,'zslow':zs,'score':score(a,b),**{f'train_{k}':v for k,v in a.items()},**{f'valid_{k}':v for k,v in b.items()},**{f'oos_{k}':v for k,v in o.items()}})
    pd.DataFrame(ab).to_csv(args.out/'vwap_z_ablation.csv',index=False)
    sens=[]
    cfg=SigCfg(int(selected.tf),str(selected.setup),str(selected.trend),str(selected.vwap),float(selected.zthr),str(selected.zslow)); ex=ExitCfg(float(selected.atr_mult),str(selected.management)); ss=signal(frames[cfg.tf],cfg)
    for sp in (.07,.10,.15,.30):
        t=simulate(frames[cfg.tf],ss,ex,spread=sp); a,b,o=three(t); sens.append({'spread_usd':sp,**{f'train_{k}':v for k,v in a.items()},**{f'valid_{k}':v for k,v in b.items()},**{f'oos_{k}':v for k,v in o.items()}})
    pd.DataFrame(sens).to_csv(args.out/'spread_sensitivity.csv',index=False)
    yearly=[]
    if not seltr.empty:
        yy=pd.to_datetime(seltr.entry_time,utc=True).dt.year
        for y in sorted(yy.unique()): yearly.append({'year':int(y),**metrics(seltr[yy==y])})
    pd.DataFrame(yearly).to_csv(args.out/'yearly.csv',index=False)
    sess=[]
    for sname in ('ASIA','LONDON','NEW_YORK'):
        q=seltr[seltr.session==sname] if not seltr.empty else seltr; sess.append({'session':sname,**metrics(q)})
    pd.DataFrame(sess).to_csv(args.out/'sessions.csv',index=False)
    summary={'status':'FAILED_VALIDATION_DIAGNOSTIC_ONLY' if diag or len(dep)==0 else 'VALIDATED_TRAIN_VALIDATION','source':'simom1/XAUUSD-history MT5 UTC M15 tick-volume','coverage':{'rows':len(raw),'start':str(raw.time.min()),'end':str(data_end)},'risk_per_trade':RISK,'selection_periods':{'train':[str(TRAIN_START),str(TRAIN_END)],'validation':[str(TRAIN_END),str(VALID_END)],'oos':[str(VALID_END),str(data_end)]},'grid_stage1':len(cs),'execution_model':{'entry':'next bar open + fixed spread sensitivity','base_spread_usd':BASE_SPREAD_USD,'same_bar_conflict':'stop-first','commission':'none','historical_bid_ask':'not in this dataset'},'vwap_rules':{'DW':'price > current D VWAP > prior-day VWAP close; same for week','DWS':'DW + current session VWAP > previous completed session VWAP close','LADDER':'DWS + session VWAP > daily VWAP > weekly VWAP'},'selected':selected.to_dict(),'selected_all':metrics(seltr)}
    (args.out/'summary.json').write_text(json.dumps(summary,indent=2,default=str),encoding='utf-8'); print(json.dumps(summary,indent=2,default=str),flush=True)
if __name__=='__main__': main()
