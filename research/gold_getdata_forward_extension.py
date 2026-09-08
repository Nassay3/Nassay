import json
import numpy as np
import pandas as pd
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m
import gold_m5_volume_profile_ablation as vp
import gold_m5_vwap_ladder_ablation as vw
import gold_m5_vwap_consensus_ablation as vc

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


def bounds(idx,a,b):
    ids=np.flatnonzero(np.asarray((idx>=a)&(idx<b)))
    if len(ids)<20: raise RuntimeError('forward window has insufficient bars')
    return int(ids[0]),int(ids[-1])


def pack(v): return vp.pack(v)


def main():
    path=prepare_feed()
    # Freeze all strategy logic before inspecting the forward results.
    g.URLS=[path];m.g.URLS=g.URLS;vp.g.URLS=g.URLS;vw.g.URLS=g.URLS;vc.g.URLS=g.URLS
    g.END=EXT_END
    x=g.prep();idx=x.index
    ed=m.build_edges(x)
    rawL=(ed['BRK'][0]|ed['EXP'][0]).fillna(False);rawS=(ed['BRK'][1]|ed['EXP'][1]).fillna(False)
    conf=rawL&rawS;rawL&=~conf;rawS&=~conf

    o=x.open.to_numpy(float);h=x.high.to_numpy(float);lo=x.low.to_numpy(float);c=x.close.to_numpy(float)
    atr=x.atr14.to_numpy(float);vol=x.tick_volume.to_numpy(float)
    slo=x.low.rolling(7,min_periods=1).min().to_numpy(float);shi=x.high.rolling(7,min_periods=1).max().to_numpy(float)

    # Same historical causal profile: previous 24h M5 bars, 32 bins, tick-volume weighted HLC3, refresh every 15m.
    poc,_,_=vp.profile_levels(h,lo,c,vol,288,32,3,.70)
    ok=np.isfinite(poc)
    pocL=pd.Series(ok&(c>poc),index=idx);pocS=pd.Series(ok&(c<poc),index=idx)

    # Same VWAP architecture selected historically: Riyadh +3 anchor, prior same-type session close.
    fields=vw.vwap_ladder(x,3,True)
    wL,wS=vc.mk_masks(x,fields)['WEEK_PLUS_ANY']
    L=(rawL&pocL&wL).to_numpy(np.bool_);S=(rawS&pocS&wS).to_numpy(np.bool_)
    ones=np.ones(len(x),dtype=np.bool_)
    arr=(o,h,lo,c,atr,slo,shi,L,S,ones,ones)
    bd=bounds(idx,EXT_START,EXT_END)

    finalists={
      'ROBUST_AF065_TP18':(.65,1.25,4,18.,144),
      'RETURN_AF065_TP20':(.65,1.25,4,20.,144),
      'NEIGHBOR_AF070_TP19':(.70,1.25,4,19.,144),
      'NEIGHBOR_AF070_TP20':(.70,1.25,4,20.,144),
    }
    out={}
    for name,(af,be,ml,tp,hold) in finalists.items():
        out[name]=pack(vp.sim_profile(*arr,bd[0],bd[1],af,be,ml,tp,hold))
        out[name]['params']={'atr_floor':af,'beR':be,'maxlots':ml,'tpR':tp,'hold_hours':hold*5/60}
        print('FORWARD',name,out[name],flush=True)

    mask=(idx>=EXT_START)&(idx<EXT_END)
    diagnostics={
      'raw_BRK_long':int(ed['BRK'][0][mask].sum()),'raw_BRK_short':int(ed['BRK'][1][mask].sum()),
      'raw_EXP_long':int(ed['EXP'][0][mask].sum()),'raw_EXP_short':int(ed['EXP'][1][mask].sum()),
      'after_POC_VWAP_long':int(np.asarray(L)[mask].sum()),'after_POC_VWAP_short':int(np.asarray(S)[mask].sum()),
    }
    print('RESULT_JSON_START')
    print(json.dumps({
      'risk_pct_per_unprotected_entry':.36,
      'feed':'GetData free XAUUSD M1 sample',
      'feed_range':[str(idx.min()),str(idx.max())],
      'forward_window':[str(EXT_START),str(EXT_END)],
      'selection':'ZERO selection/tuning on GetData; all four finalist parameter sets and POC/VWAP logic were frozen on the historical source first',
      'entry':'BRK+EXP + causal 24h POC_GATE + Riyadh UTC+3 same-type-session VWAP WEEK_PLUS_ANY',
      'week_plus_any':'strict weekly alignment AND (strict daily OR strict session alignment); strict long = price > current VWAP > prior completed VWAP close and price > prior close; short exact inverse',
      'results':out,
      'diagnostics':diagnostics,
      'limitations':['different broker/mid-quote feed than training source','tick volume proxy, not COMEX traded volume','M1 OHLC resampled to M5','short forward window ~6 weeks','fixed 0.08R cost proxy; no full broker bid/ask/slippage model']
    },default=float))
    print('RESULT_JSON_END')
if __name__=='__main__':main()
