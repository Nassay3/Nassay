import json
import numpy as np
import pandas as pd
import yfinance as yf
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m
import gold_m5_numba_grid as ng

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
m.g.URLS=g.URLS

def dxy_context(index):
    d=yf.download('DX-Y.NYB',start='2021-07-01',end='2026-09-06',auto_adjust=False,progress=False)
    if d.empty: raise RuntimeError('DXY download returned empty')
    if isinstance(d.columns,pd.MultiIndex): d.columns=d.columns.get_level_values(0)
    close=pd.to_numeric(d['Close'],errors='coerce').dropna()
    z=pd.DataFrame({'dxy_close':close})
    z['dxy_ret1']=z.dxy_close.pct_change()
    z['dxy_sma20']=z.dxy_close.rolling(20,min_periods=20).mean()
    z['dxy_slope20']=z.dxy_sma20-z.dxy_sma20.shift(5)
    # Conservative availability: use a DXY daily bar only from the next UTC calendar day onward.
    av=pd.to_datetime(z.index).tz_localize('UTC').normalize()+pd.Timedelta(days=1)
    z=z.set_index(av).sort_index()
    left=pd.DataFrame(index=index);left['t']=index
    right=z.copy();right['available']=right.index
    q=pd.merge_asof(left.reset_index(drop=True).sort_values('t'),right.reset_index(drop=True).sort_values('available'),left_on='t',right_on='available',direction='backward')
    q.index=index
    print('DXY_RANGE',close.index.min(),close.index.max(),'ROWS',len(close),flush=True)
    return q

def arrays(x,L,S):
    o=x.open.to_numpy(float);h=x.high.to_numpy(float);lo=x.low.to_numpy(float);c=x.close.to_numpy(float);atr=x.atr14.to_numpy(float)
    slo3=x.low.rolling(4,min_periods=1).min().to_numpy(float);shi3=x.high.rolling(4,min_periods=1).max().to_numpy(float);slo6=x.low.rolling(7,min_periods=1).min().to_numpy(float);shi6=x.high.rolling(7,min_periods=1).max().to_numpy(float)
    return o,h,lo,c,atr,slo3,shi3,slo6,shi6,L.to_numpy(np.bool_),S.to_numpy(np.bool_)

def bounds(idx,a,b):
    ids=np.flatnonzero(np.asarray((idx>=a)&(idx<b)));return int(ids[0]),int(ids[-1])

def run(arr,bnd):
    return ng.pack(ng.sim_numba(*arr,bnd[0],bnd[1],1.0,6,1.0,6,15.0,144))

def main():
    x=g.prep();ed=m.build_edges(x);baseL=(ed['BRK'][0]|ed['EXP'][0]).fillna(False);baseS=(ed['BRK'][1]|ed['EXP'][1]).fillna(False);conf=baseL&baseS;baseL&=~conf;baseS&=~conf
    d=dxy_context(x.index)
    modes={
      'NONE':(pd.Series(True,index=x.index),pd.Series(True,index=x.index)),
      'RET1':((d.dxy_ret1<0).fillna(False),(d.dxy_ret1>0).fillna(False)),
      'SMA20':((d.dxy_close<d.dxy_sma20).fillna(False),(d.dxy_close>d.dxy_sma20).fillna(False)),
      'SLOPE20':((d.dxy_slope20<0).fillna(False),(d.dxy_slope20>0).fillna(False)),
      'COMBO':(((d.dxy_ret1<0)&(d.dxy_close<d.dxy_sma20)).fillna(False),((d.dxy_ret1>0)&(d.dxy_close>d.dxy_sma20)).fillna(False)),
    }
    idx=x.index;trb=bounds(idx,g.START,g.TRAIN_END);vab=bounds(idx,g.TRAIN_END,g.VAL_END);hob=bounds(idx,g.VAL_END,g.END);fullb=bounds(idx,g.START,g.END)
    rows=[];cache={}
    for name,(allowL,allowS) in modes.items():
        L=(baseL&allowL).fillna(False);S=(baseS&allowS).fillna(False);arr=arrays(x,L,S);cache[name]=arr
        tr=run(arr,trb);va=run(arr,vab);score=tr['ret']-1.1*tr['dd']+.8*va['ret']-va['dd']
        rows.append((score,name,tr,va))
    rows.sort(reverse=True,key=lambda z:z[0]);out=[]
    for score,name,tr,va in rows[:2]:
        arr=cache[name];out.append({'mode':name,'score':score,'train':tr,'val':va,'holdout':run(arr,hob),'full':run(arr,fullb)})
    print('RESULT_JSON_START');print(json.dumps({'strategy':'Frozen BRK+EXP champion: ATR1 swing6 BE1 max6 TP15 hold12h','DXY':'Yahoo Finance DX-Y.NYB; previous completed daily bar only','selection':'five DXY modes ranked on train+validation; holdout top2 only','screen':[{'mode':n,'score':s,'train':tr,'val':va} for s,n,tr,va in rows],'promoted':out,'limitations':['daily DXY only, no intraday DXY','Yahoo index feed may differ by venue','M1 gold OHLC->M5','parameter-selection risk controlled by untouched holdout']},default=float));print('RESULT_JSON_END')
if __name__=='__main__':main()
