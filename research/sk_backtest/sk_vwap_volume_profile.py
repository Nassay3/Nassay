from __future__ import annotations
import io, os, zipfile, math, itertools, json, warnings
from pathlib import Path
import numpy as np, pandas as pd, requests
warnings.filterwarnings('ignore')

SYMBOLS=os.getenv('SYMBOLS','BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,LINKUSDT,ARBUSDT,OPUSDT').split(',')
START=os.getenv('START','2022-01'); END=os.getenv('END','2024-12')
TFS={'15m':'15min','1h':'1h','4h':'4h','12h':'12h','1d':'1D'}
ROWS=[24,50,100,150]; VAS=[.68,.70,.80]
OUT=Path('artifacts/sk_vwap_volume_profile'); OUT.mkdir(parents=True,exist_ok=True)
FEE=float(os.getenv('FEE','0.001')); SLIP=float(os.getenv('SLIP','0.0005'))

def months(a,b):
    p=pd.period_range(a,b,freq='M'); return [str(x) for x in p]

def load_1m(sym):
    parts=[]
    for m in months(START,END):
        url=f'https://data.binance.vision/data/spot/monthly/klines/{sym}/1m/{sym}-1m-{m}.zip'
        r=requests.get(url,timeout=60)
        if r.status_code!=200: continue
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            raw=pd.read_csv(z.open(z.namelist()[0]),header=None,usecols=range(6))
        raw.columns=['ts','open','high','low','close','volume']
        x=pd.to_numeric(raw.ts,errors='coerce')
        unit=np.where(x>1e16,'ns',np.where(x>1e13,'us',np.where(x>1e11,'ms','s')))
        dt=pd.Series(pd.NaT,index=raw.index,dtype='datetime64[ns, UTC]')
        for u in ('ns','us','ms','s'):
            mask=unit==u
            if mask.any(): dt.loc[mask]=pd.to_datetime(x[mask],unit=u,utc=True,errors='coerce')
        raw['ts']=dt
        for c in ['open','high','low','close','volume']: raw[c]=pd.to_numeric(raw[c],errors='coerce')
        parts.append(raw.dropna())
    if not parts: return pd.DataFrame()
    return pd.concat(parts).drop_duplicates('ts').sort_values('ts').set_index('ts')

def resample(d,rule):
    o=d.open.resample(rule).first(); h=d.high.resample(rule).max(); l=d.low.resample(rule).min(); c=d.close.resample(rule).last(); v=d.volume.resample(rule).sum()
    q=pd.concat([o,h,l,c,v],axis=1).dropna(); q.columns=['open','high','low','close','volume']; return q

def atr(d,n=14):
    pc=d.close.shift(); tr=pd.concat([(d.high-d.low),(d.high-pc).abs(),(d.low-pc).abs()],axis=1).max(axis=1)
    return tr.rolling(n,min_periods=n).mean()

def pivots(d,k=2,atr_mult=.65):
    hi=d.high; lo=d.low; a=atr(d)
    ph=(hi==hi.rolling(2*k+1,center=True).max()); pl=(lo==lo.rolling(2*k+1,center=True).min())
    pts=[]
    for i in np.where((ph|pl).fillna(False))[0]:
        typ='H' if ph.iloc[i] else 'L'; price=hi.iloc[i] if typ=='H' else lo.iloc[i]
        if not pts: pts.append([i,typ,price]); continue
        if typ==pts[-1][1]:
            if (typ=='H' and price>pts[-1][2]) or (typ=='L' and price<pts[-1][2]): pts[-1]=[i,typ,price]
        elif abs(price-pts[-1][2]) >= (a.iloc[i] if np.isfinite(a.iloc[i]) else 0)*atr_mult: pts.append([i,typ,price])
    return pts

def sequences(d):
    p=pivots(d); ev=[]
    for j in range(len(p)-2):
        p0,p1,p2=p[j:j+3]
        if p0[1]=='L' and p1[1]=='H' and p2[1]=='L' and p2[2]>p0[2]:
            i0,ia,ib=p0[0],p1[0],p2[0]; A=p1[2]; B=p2[2]; zero=p0[2]
            future=np.where(d.high.iloc[ib+1:].to_numpy()>=A)[0]
            if len(future):
                act=ib+1+future[0]; ev.append(dict(i0=i0,ia=ia,ib=ib,act=act,zero=zero,A=A,B=B,dir=1))
    return ev

def profile(seg,rows,va):
    if len(seg)<5: return None
    lo=float(seg.low.min()); hi=float(seg.high.max())
    if hi<=lo:return None
    edges=np.linspace(lo,hi,rows+1); vol=np.zeros(rows)
    for r in seg.itertuples():
        a=max(0,min(rows-1,np.searchsorted(edges,r.low,side='right')-1)); b=max(0,min(rows-1,np.searchsorted(edges,r.high,side='right')-1))
        if b<a:a,b=b,a
        vol[a:b+1]+=r.volume/(b-a+1)
    centers=(edges[:-1]+edges[1:])/2; ip=int(np.argmax(vol)); poc=centers[ip]
    order=np.argsort(vol)[::-1]; target=vol.sum()*va; chosen=[]; s=0
    for x in order:
        chosen.append(x); s+=vol[x]
        if s>=target:break
    val=centers[min(chosen)]; vah=centers[max(chosen)]
    q1=vol[:rows//3].sum(); q2=vol[rows//3:2*rows//3].sum(); q3=vol[2*rows//3:].sum(); total=vol.sum()+1e-12
    if q3/total>.48: shape='P'
    elif q1/total>.48: shape='b'
    elif q2/total>.48: shape='D'
    elif q1/total>.32 and q3/total>.32: shape='B'
    elif max(q1,q2,q3)/total<.42: shape='D'
    else: shape='L'
    hvn=centers[vol>=.7*vol[ip]]; lvn=centers[vol<=.2*vol[ip]]
    return dict(poc=poc,vah=vah,val=val,shape=shape,hvn_near=float(hvn[np.argmin(abs(hvn-seg.close.iloc[-1]))]) if len(hvn) else np.nan,lvn_near=float(lvn[np.argmin(abs(lvn-seg.close.iloc[-1]))]) if len(lvn) else np.nan)

def add_vwaps(d):
    x=d.copy(); pv=((x.high+x.low+x.close)/3)*x.volume
    for name,key in [('D',x.index.floor('D')),('W',x.index.to_period('W').start_time.tz_localize('UTC')),('M',x.index.to_period('M').start_time.tz_localize('UTC'))]:
        x[f'vwap_{name}']=pv.groupby(key).cumsum()/x.volume.groupby(key).cumsum()
    hour=x.index.hour
    sess=np.select([(hour>=0)&(hour<8),(hour>=8)&(hour<13),(hour>=13)&(hour<21)],['asia','london','ny'],default='off')
    g=pd.Series(x.index.floor('D').astype(str)+'_'+sess,index=x.index)
    x['vwap_session']=pv.groupby(g).cumsum()/x.volume.groupby(g).cumsum()
    return x

def outcome(d,e):
    entry=e['A']*(1+SLIP); stop=e['B']*(1-SLIP); risk=entry-stop
    if risk<=0:return None
    t1=entry+1.618*risk; t2=entry+2*risk; end=min(len(d),e['act']+120)
    ret=-1.0; hit2=0; bars=end-e['act']
    for k in range(e['act']+1,end):
        if d.low.iloc[k]<=stop: ret=-1; bars=k-e['act']; break
        if d.high.iloc[k]>=t2: hit2=1
        if d.high.iloc[k]>=t1: ret=1.618; bars=k-e['act']; break
    ret-=((2*FEE+2*SLIP)*entry/risk)
    return ret,hit2,bars

def run_symbol(sym):
    base=load_1m(sym)
    if base.empty:return []
    frames={tf:add_vwaps(resample(base,r)) for tf,r in TFS.items()}
    seq={tf:sequences(frames[tf]) for tf in TFS}
    rows=[]; pairs=[('1d','4h'),('12h','4h'),('4h','1h'),('4h','15m'),('1h','15m')]
    for ptf,ctf in pairs:
        pdx=frames[ptf]; cdx=frames[ctf]
        for pe in seq[ptf]:
            pb=pdx.index[pe['ib']]; pact=pdx.index[pe['act']]
            children=[ce for ce in seq[ctf] if cdx.index[ce['ib']]>=pb and cdx.index[ce['act']]<=pact]
            for ce in children:
                out=outcome(cdx,ce)
                if out is None: continue
                ix=ce['act']; price=ce['A']; rec=dict(symbol=sym,parent_tf=ptf,child_tf=ctf,parent_BC_start=pb,entry_time=cdx.index[ix],R=out[0],hit2=out[1],bars=out[2])
                for col in ['vwap_D','vwap_W','vwap_M','vwap_session']:
                    v=float(cdx[col].iloc[ix]); rec[f'above_{col}']=price>v; rec[f'dist_{col}']=(price-v)/price
                for nm,start in [('c0',ce['i0']),('cA',ce['ia']),('cB',ce['ib'])]:
                    sg=cdx.iloc[start:ix+1]; av=float(((sg.high+sg.low+sg.close)/3*sg.volume).sum()/sg.volume.sum()); rec[f'above_avwap_{nm}']=price>av; rec[f'dist_avwap_{nm}']=(price-av)/price
                pseg=pdx.iloc[pe['i0']:pe['act']+1]
                for n in ROWS:
                    for va in VAS:
                        vp=profile(pseg,n,va)
                        if not vp:continue
                        pre=f'vp_{n}_{int(va*100)}'; rec[f'{pre}_shape']=vp['shape']; rec[f'{pre}_above_poc']=price>vp['poc']; rec[f'{pre}_inside_va']=vp['val']<=price<=vp['vah']; rec[f'{pre}_above_vah']=price>vp['vah']; rec[f'{pre}_below_val']=price<vp['val']; rec[f'{pre}_dist_poc']=(price-vp['poc'])/price
                rows.append(rec)
    return rows

def metrics(g):
    n=len(g); wins=(g.R>0).sum(); pos=g.loc[g.R>0,'R'].sum(); neg=-g.loc[g.R<=0,'R'].sum()
    return pd.Series(dict(n=n,win_rate=wins/n if n else np.nan,expectancy=g.R.mean(),profit_factor=pos/neg if neg else np.inf,median_R=g.R.median()))

allrows=[]
for s in SYMBOLS:
    print('RUN',s,flush=True); allrows.extend(run_symbol(s))
ev=pd.DataFrame(allrows); ev.to_parquet(OUT/'events.parquet',index=False); ev.to_csv(OUT/'events.csv',index=False)
base=metrics(ev).to_dict() if len(ev) else {}; json.dump(base,open(OUT/'summary.json','w'),indent=2)
rank=[]
if len(ev):
    feats=[c for c in ev.columns if c.startswith(('above_','vp_')) and (ev[c].dtype==bool or ev[c].dtype=='object')]
    for f in feats:
        vals=ev[f].dropna().unique()[:20]
        for v in vals:
            g=ev[ev[f]==v]
            if len(g)>=50: rank.append({'feature':f,'value':str(v),**metrics(g).to_dict()})
    b=[c for c in feats if ev[c].dtype==bool]
    for a,b2 in itertools.combinations(b,2):
        g=ev[ev[a]&ev[b2]]
        if len(g)>=75: rank.append({'feature':a+' & '+b2,'value':'True',**metrics(g).to_dict()})
r=pd.DataFrame(rank).sort_values(['expectancy','profit_factor'],ascending=False); r.to_csv(OUT/'feature_ranking.csv',index=False)
if len(ev):
    ev['year']=pd.to_datetime(ev.entry_time,utc=True).dt.year
    wf=ev.groupby(['year','parent_tf','child_tf']).apply(metrics).reset_index(); wf.to_csv(OUT/'walk_forward.csv',index=False)
print(json.dumps(base,indent=2))
