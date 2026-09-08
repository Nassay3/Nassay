import json,re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from bs4 import BeautifulSoup
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m
import gold_m5_numba_grid as ng

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv'];m.g.URLS=g.URLS
ET=ZoneInfo('America/New_York')

def parse_bls():
    events=[]
    for year in range(2021,2027):
        p=Path(f'/tmp/bls_{year}.html')
        soup=BeautifulSoup(p.read_text(errors='ignore'),'html.parser')
        for tr in soup.find_all('tr'):
            cells=[x.get_text(' ',strip=True) for x in tr.find_all(['td','th'])]
            if len(cells)<3:continue
            release=' '.join(cells[2:])
            kind='NFP' if 'Employment Situation' in release and 'State Employment' not in release and 'Veterans' not in release else ('CPI' if 'Consumer Price Index' in release else None)
            if not kind:continue
            ds=cells[0];ts=cells[1]
            d=pd.to_datetime(ds,errors='coerce')
            if pd.isna(d):continue
            # National Employment Situation / CPI schedule is normally 08:30 ET; use table time if parseable.
            mt=re.search(r'(\d{1,2}):(\d{2})\s*(AM|PM)',ts,re.I)
            if mt:
                hh=int(mt.group(1))%12+(12 if mt.group(3).upper()=='PM' else 0);mm=int(mt.group(2))
            else: hh,mm=8,30
            local=datetime(d.year,d.month,d.day,hh,mm,tzinfo=ET);utc=pd.Timestamp(local).tz_convert('UTC')
            events.append((kind,utc,ds,ts,release))
    # Deduplicate current schedules that may repeat in navigation markup.
    uniq={ (k,t):(k,t,ds,ts,r) for k,t,ds,ts,r in events }
    out=sorted(uniq.values(),key=lambda z:z[1])
    print('BLS_EVENTS',len(out),'NFP',sum(k=='NFP' for k,*_ in out),'CPI',sum(k=='CPI' for k,*_ in out),flush=True)
    print('BLS_FIRST_LAST',out[0][:2] if out else None,out[-1][:2] if out else None,flush=True)
    return out

def arrays(x,L,S):
    return (x.open.to_numpy(float),x.high.to_numpy(float),x.low.to_numpy(float),x.close.to_numpy(float),x.atr14.to_numpy(float),x.low.rolling(4,min_periods=1).min().to_numpy(float),x.high.rolling(4,min_periods=1).max().to_numpy(float),x.low.rolling(7,min_periods=1).min().to_numpy(float),x.high.rolling(7,min_periods=1).max().to_numpy(float),L.to_numpy(np.bool_),S.to_numpy(np.bool_))
def bounds(idx,a,b):
    ids=np.flatnonzero(np.asarray((idx>=a)&(idx<b)));return int(ids[0]),int(ids[-1])
def run(arr,bd):return ng.pack(ng.sim_numba(*arr,bd[0],bd[1],1.0,6,1.0,6,15.0,144))

def allow_mask(index,events,kinds,pre,post):
    a=pd.Series(True,index=index)
    for kind,t,*_ in events:
        if kind not in kinds:continue
        a.loc[(index>=t-pd.Timedelta(minutes=pre))&(index<=t+pd.Timedelta(minutes=post))]=False
    return a

def main():
    events=parse_bls();x=g.prep();ed=m.build_edges(x);L0=(ed['BRK'][0]|ed['EXP'][0]).fillna(False);S0=(ed['BRK'][1]|ed['EXP'][1]).fillna(False);z=L0&S0;L0&=~z;S0&=~z
    modes=[('NONE',set(),0,0),('NFP_30_60',{'NFP'},30,60),('NFP_60_60',{'NFP'},60,60),('CPI_30_60',{'CPI'},30,60),('NFP_CPI_30_60',{'NFP','CPI'},30,60),('NFP_CPI_60_60',{'NFP','CPI'},60,60)]
    idx=x.index;trb=bounds(idx,g.START,g.TRAIN_END);vab=bounds(idx,g.TRAIN_END,g.VAL_END);hob=bounds(idx,g.VAL_END,g.END);fullb=bounds(idx,g.START,g.END)
    rows=[];cache={}
    for name,kinds,pre,post in modes:
        allow=pd.Series(True,index=idx) if name=='NONE' else allow_mask(idx,events,kinds,pre,post)
        L=(L0&allow).fillna(False);S=(S0&allow).fillna(False);arr=arrays(x,L,S);cache[name]=arr
        tr=run(arr,trb);va=run(arr,vab);score=tr['ret']-1.1*tr['dd']+.8*va['ret']-va['dd'];rows.append((score,name,tr,va,int((~allow).sum())))
    rows.sort(reverse=True,key=lambda z:z[0]);prom=[]
    for score,name,tr,va,blocked in rows[:2]:
        arr=cache[name];prom.append({'mode':name,'score':score,'blocked_m5_bars':blocked,'train':tr,'val':va,'holdout':run(arr,hob),'full':run(arr,fullb)})
    print('RESULT_JSON_START');print(json.dumps({'strategy':'Frozen BRK+EXP ATR1 swing6 BE1 max6 TP15 hold12h','calendar':'Official BLS yearly schedules 2021-2026; event time converted America/New_York -> UTC','selection':'blackout mode chosen on train+validation only; holdout top2','screen':[{'mode':n,'score':s,'blocked_m5_bars':b,'train':tr,'val':va} for s,n,tr,va,b in rows],'promoted':prom,'events_sample':[{'kind':k,'utc':str(t),'date_text':ds,'time_text':ts} for k,t,ds,ts,r in events[:6]],'limitations':['blackout suppresses new signals/additions only; existing positions stay open','BLS schedule pages may reflect revised historical release dates','FOMC/PCE not included in this first news ablation','M1 OHLC->M5']},default=float));print('RESULT_JSON_END')
if __name__=='__main__':main()
