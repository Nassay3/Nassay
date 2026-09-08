import json
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

import gold_duka_numba_rebuild as r
import gold_bls_news_blackout as bls

BE=4.0;MAXLOTS=2;TP=10.0;HOLD_MIN=24*60
ET=ZoneInfo('America/New_York')

# Official FOMC scheduled decision dates (second day of regular meetings) from Federal Reserve calendar.
FOMC_DATES=[
'2021-09-22','2021-11-03','2021-12-15',
'2022-01-26','2022-03-16','2022-05-04','2022-06-15','2022-07-27','2022-09-21','2022-11-02','2022-12-14',
'2023-02-01','2023-03-22','2023-05-03','2023-06-14','2023-07-26','2023-09-20','2023-11-01','2023-12-13',
'2024-01-31','2024-03-20','2024-05-01','2024-06-12','2024-07-31','2024-09-18','2024-11-07','2024-12-18',
'2025-01-29','2025-03-19','2025-05-07','2025-06-18','2025-07-30','2025-09-17','2025-10-29','2025-12-10',
'2026-01-28','2026-03-18','2026-04-29','2026-06-17','2026-07-29']

def fomc_events():
    out=[]
    for ds in FOMC_DATES:
        d=pd.Timestamp(ds)
        local=datetime(d.year,d.month,d.day,14,0,tzinfo=ET)
        out.append(('FOMC',pd.Timestamp(local).tz_convert('UTC')))
    return out

def winner_signals(sig):
    for en,vn,pn,L,S in r.masks(sig):
        if en=='BRK' and vn=='DW_REL_PRICE2' and pn=='POCMOM25':return L,S
    raise RuntimeError('winner missing')

def allowed(index,events,pre,post,kinds):
    a=np.ones(len(index),dtype=np.bool_)
    for kind,t in events:
        if kind not in kinds:continue
        z=np.asarray((index>=t-pd.Timedelta(minutes=pre))&(index<=t+pd.Timedelta(minutes=post)))
        a[z]=False
    return a

def interval(exe,a,b):
    t=pd.DatetimeIndex(exe.time);z=np.flatnonzero(np.asarray((t>=a)&(t<b)));return int(z[0]),int(z[-1])

def run(arr,decision,L,S,rp,b):
    v,ca,ad,mo=r.sim_m1(*arr,decision,L,S,rp,b[0],b[1],BE,MAXLOTS,TP,HOLD_MIN)
    return {lab:r.pack(v,ca,ad,mo,i) for i,lab in enumerate(['spread_only','plus_002R','plus_005R'])}

def main():
    bev=bls.parse_bls();events=[(k,t) for k,t,*_ in bev]+fomc_events()
    sig,exe,arr,decision,riskL,riskS,ediag=r.prep();idx=sig.index
    L0,S0=winner_signals(sig)
    modes=[
      ('NONE',set(),0,0),
      ('NFP_CPI_30_60',{'NFP','CPI'},30,60),
      ('FOMC_30_90',{'FOMC'},30,90),
      ('ALL_30_60',{'NFP','CPI','FOMC'},30,60),
      ('ALL_60_60',{'NFP','CPI','FOMC'},60,60),
    ]
    periods={
      'PRE2025':interval(exe,pd.Timestamp('2021-09-08',tz='UTC'),pd.Timestamp('2025-01-01',tz='UTC')),
      'HOLDOUT_2025PLUS':interval(exe,pd.Timestamp('2025-01-01',tz='UTC'),r.d.END),
      'FULL':interval(exe,pd.Timestamp('2021-09-08',tz='UTC'),r.d.END),
    }
    report={}
    for name,kinds,pre,post in modes:
        if name=='NONE':allow=np.ones(len(idx),dtype=np.bool_)
        else:allow=allowed(idx,events,pre,post,kinds)
        L=L0&allow;S=S0&allow;rp=np.where(L,riskL,np.where(S,riskS,.01))
        report[name]={'blocked_signal_bars':int(np.sum(~allow)),'periods':{p:run(arr,decision,L,S,rp,b) for p,b in periods.items()}}
    print('RESULT_JSON_START')
    print(json.dumps({'candidate':'DUKA_EXEC_BRK_DWREL_POCMOM25','params':{'beR':BE,'maxlots':MAXLOTS,'tpR':TP,'hold_hours':24,'risk_pct_fresh':.36},
      'execution':'Dukascopy M1 bid/ask variable spread; additional costs 0/.02/.05R','news_events':{'BLS_count':len(bev),'FOMC_count':len(FOMC_DATES)},
      'blackouts':report,
      'methodology':['Diagnostic only: no blackout mode is selected/tuned here','Blackout suppresses new campaign signals and fresh-signal adds; existing positions remain open','FOMC statements modeled at 2:00pm America/New_York on scheduled decision dates','BLS events parsed from official yearly BLS calendars and converted America/New_York to UTC'],
      'limitations':['PCE is not included in this run; add only from an official historical BEA calendar, not inferred dates','M1 bid/ask has no intraminute tick ordering']},default=float))
    print('RESULT_JSON_END')
if __name__=='__main__':main()
