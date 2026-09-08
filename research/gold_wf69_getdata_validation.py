import json
import numpy as np
import pandas as pd
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m
import gold_m5_volume_profile_ablation as vp
import gold_m5_vwap_ladder_ablation as vw
import gold_m5_vwap_consensus_ablation as vc
import gold_champion_execution_stress as s

LOCAL='/tmp/XAUUSD.csv'
START=pd.Timestamp('2026-07-23',tz='UTC')
END=pd.Timestamp('2026-09-05',tz='UTC')
EDGES=('BRK','EXP','PULL')
PARAMS={'atr_floor':0.80,'beR':2.25,'max_lots':3,'targetR':28.0,'hold_bars':216}

def bounds(idx,a,b):
    z=np.flatnonzero(np.asarray((idx>=a)&(idx<b)))
    return int(z[0]),int(z[-1])

def main():
    z=pd.read_csv(LOCAL).rename(columns={'datetime':'time','volume':'tick_volume'})
    z['time']=pd.to_datetime(z.time,utc=True)
    z=z[['time','open','high','low','close','tick_volume']].dropna().sort_values('time')
    p='/tmp/getdata_norm.csv'; z.to_csv(p,index=False)
    g.URLS=[p]; m.g.URLS=g.URLS; vp.g.URLS=g.URLS; vw.g.URLS=g.URLS; vc.g.URLS=g.URLS; s.g.URLS=g.URLS; g.END=END
    x=g.prep(); idx=x.index; ed=m.build_edges(x)
    L=pd.Series(False,index=idx); S=pd.Series(False,index=idx)
    for nm in EDGES:
        L|=ed[nm][0]; S|=ed[nm][1]
    clash=L&S; L&=~clash; S&=~clash
    o=x.open.to_numpy(float); h=x.high.to_numpy(float); lo=x.low.to_numpy(float); c=x.close.to_numpy(float); atr=x.atr14.to_numpy(float); vol=x.tick_volume.to_numpy(float)
    slo=x.low.rolling(7,min_periods=1).min().to_numpy(float); shi=x.high.rolling(7,min_periods=1).max().to_numpy(float)
    poc,_,_=vp.profile_levels(h,lo,c,vol,288,32,3,.70)
    ok=np.isfinite(poc)
    f=vw.vwap_ladder(x,3,True); wL,wS=vc.mk_masks(x,f)['WEEK_PLUS_ANY']
    L=(L&wL&pd.Series(ok&(c>poc),index=idx)).to_numpy(np.bool_)
    S=(S&wS&pd.Series(ok&(c<poc),index=idx)).to_numpy(np.bool_)
    arr=(o,h,lo,c,atr,slo,shi,L,S); b=bounds(idx,START,END)
    af=PARAMS['atr_floor']; be=PARAMS['beR']; ml=PARAMS['max_lots']; tp=PARAMS['targetR']; mh=PARAMS['hold_bars']
    levels=[('BASE08',.08,0.0),('STRESS15_05',.15,.05),('HARD24_10',.24,.10),('EXTREME32_15',.32,.15)]
    out={}
    for name,cost,slip in levels:
        out[name]=s.pack(s.sim_stress(*arr,b[0],b[1],af,be,ml,tp,mh,cost,slip,1,1))
    payload={
      'candidate':'WF69_FROZEN',
      'edges':list(EDGES),
      'params':{'atr_floor':af,'beR':be,'max_lots':ml,'targetR':tp,'hold_hours':18.0,'fresh_signal_add':True},
      'selection':'Frozen before this GetData run from multi-era pre-2025 base+stress ranking; absolutely no GetData retuning',
      'risk_rule':'0.36% of current mark-to-market equity per fresh risky lot; prior live lots must be protected before a new fresh-risk add',
      'filters':'causal 24h activity POC + Riyadh WEEK_PLUS_ANY VWAP consensus',
      'feed':'GetData XAUUSD M1 reused external validation sample',
      'window':[str(START),str(END)],
      'results':out,
      'limitations':['M1 OHLC resampled to M5, not true bid/ask tick sequence','tick volume/profile is an activity proxy, not COMEX traded volume','GetData has been used previously and is validation evidence rather than a pristine holdout','cost/slippage are stress models in R units rather than broker-observed variable execution','true bid/ask tick validation remains decisive']
    }
    print('RESULT_JSON_START'); print(json.dumps(payload,default=float)); print('RESULT_JSON_END')

if __name__=='__main__': main()
