import json
import numpy as np
import pandas as pd
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m
import gold_m5_trend_pyramid as p

LOCAL='/tmp/XAUUSD.csv'
EXT_START=pd.Timestamp('2026-07-23',tz='UTC')
EXT_END=pd.Timestamp('2026-09-05',tz='UTC')

def prepare_feed():
    z=pd.read_csv(LOCAL)
    z=z.rename(columns={'datetime':'time','volume':'tick_volume'})
    z['time']=pd.to_datetime(z['time'],utc=True)
    z=z[['time','open','high','low','close','tick_volume']].dropna().sort_values('time')
    path='/tmp/getdata_norm.csv';z.to_csv(path,index=False)
    print('GETDATA_RANGE',z.time.min(),z.time.max(),'ROWS',len(z),flush=True)
    return path

def main():
    path=prepare_feed()
    g.URLS=[path]; m.g.URLS=g.URLS; p.g.URLS=g.URLS
    g.END=EXT_END
    x=g.prep()
    ed=m.build_edges(x)
    champion=m.simulate(x,ed,('BRK','EXP'),EXT_START,EXT_END,1.0,6,15.0,144)
    baseline=m.simulate(x,ed,('BRK','EXP'),EXT_START,EXT_END,1.0,4,10.0,144)
    Lb,Sb=p.base_signal(x)
    pyramid_brk=p.simulate(x,Lb,Sb,EXT_START,EXT_END,1.0,6,10.0,288)
    # Frozen sequential BRK+EXP winner selected entirely on the historical source.
    Lu=(ed['BRK'][0]|ed['EXP'][0]).fillna(False);Su=(ed['BRK'][1]|ed['EXP'][1]).fillna(False);conf=Lu&Su;Lu&=~conf;Su&=~conf
    pyramid_brk_exp=p.simulate(x,Lu,Su,EXT_START,EXT_END,1.25,4,15.0,144)
    mask=(x.index>=EXT_START)&(x.index<EXT_END)
    counts={k:{'long':int(v[0][mask].sum()),'short':int(v[1][mask].sum())} for k,v in ed.items() if k in ('BRK','EXP')}
    print('RESULT_JSON_START')
    print(json.dumps({
      'feed':'GetData free XAUUSD M1 sample',
      'feed_range':[str(x.index.min()),str(x.index.max())],
      'forward_window':[str(EXT_START),str(EXT_END)],
      'selection':'NONE on GetData; all parameters frozen before this feed was inspected',
      'champion_BRK_EXP_TP15_max6':champion,
      'baseline_BRK_EXP_TP10_max4':baseline,
      'aggressive_BRK_sequential_pyramid':pyramid_brk,
      'frozen_BRK_EXP_sequential_BE1.25_max4_TP15':pyramid_brk_exp,
      'signal_counts':counts,
      'limitations':['different broker/mid-quote feed than training source','tick volume proxy','M1 OHLC resampled to M5','short forward window ~6 weeks','no explicit spread/slippage beyond fixed R cost']
    },default=float))
    print('RESULT_JSON_END')
if __name__=='__main__':main()
