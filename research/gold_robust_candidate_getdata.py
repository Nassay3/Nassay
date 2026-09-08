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
START=pd.Timestamp('2026-07-23',tz='UTC'); END=pd.Timestamp('2026-09-05',tz='UTC')

def bounds(idx,a,b):
 z=np.flatnonzero(np.asarray((idx>=a)&(idx<b)));return int(z[0]),int(z[-1])

def main():
 z=pd.read_csv(LOCAL).rename(columns={'datetime':'time','volume':'tick_volume'});z['time']=pd.to_datetime(z.time,utc=True)
 z=z[['time','open','high','low','close','tick_volume']].dropna().sort_values('time');p='/tmp/getdata_norm.csv';z.to_csv(p,index=False)
 g.URLS=[p];m.g.URLS=g.URLS;vp.g.URLS=g.URLS;vw.g.URLS=g.URLS;vc.g.URLS=g.URLS;s.g.URLS=g.URLS;g.END=END
 x,arr=s.build();b=bounds(x.index,START,END)
 # Frozen robust candidate selected only from historical Train+Validation base+stress grid.
 af,be,ml,tp,mh=.65,1.75,2,32.,216
 out={}
 for name,cost,slip in [('BASE_SPREAD_PROXY08',.08,0.),('STRESS15_05',.15,.05)]:
  out[name]=s.pack(s.sim_stress(*arr,b[0],b[1],af,be,ml,tp,mh,cost,slip,1,1))
 print('RESULT_JSON_START');print(json.dumps({'candidate':{'atr_floor':af,'beR':be,'max_lots':ml,'targetR':tp,'hold_hours':18,'fresh_signal_add':True},'feed':'GetData independent XAUUSD M1 sample','window':[str(START),str(END)],'selection':'No tuning on GetData; candidate frozen from historical Train+Validation robust grid','results':out,'limitations':['OHLC not bid/ask tick sequence','GetData has already appeared in prior research and is validation, not pristine holdout','stress costs are hypothetical and Dukascopy tick test is preferred for execution realism']},default=float));print('RESULT_JSON_END')
if __name__=='__main__':main()
