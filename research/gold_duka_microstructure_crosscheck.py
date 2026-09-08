import json
import numpy as np
import pandas as pd

import gold_duka_winner_crosscheck as w
import gold_quality_duka_bidask_corrected as corr
from gold_duka_microfeatures import compute_features

# Frozen management selected before 2025.
d=w.d


def prior_minute_features(sig,exe):
    f=compute_features(exe)
    ens=pd.DatetimeIndex(exe.time).as_unit('ns').asi8
    dns=pd.DatetimeIndex(sig.index+pd.Timedelta(minutes=5)).as_unit('ns').asi8
    pos=np.searchsorted(ens,dns)-1  # strictly previous completed M1 bar before executable entry minute
    good=(pos>=0)&(pos<len(ens))
    out=pd.DataFrame(index=sig.index,columns=f.columns,dtype=float)
    gi=np.flatnonzero(good)
    out.iloc[gi]=f.iloc[pos[good]].to_numpy(float)
    return out


def variants(sig,feat):
    baseL=sig.sigL.astype(bool);baseS=sig.sigS.astype(bool)
    sr=feat.spread_ratio;m5=feat.mom5;p=feat.pressure5
    defs={
      'NONE':(pd.Series(True,index=sig.index),pd.Series(True,index=sig.index)),
      # Methodological winner selected on pre-2025 only in Numba ablation.
      'SPR_LE125':((sr<=1.25).fillna(False),(sr<=1.25).fillna(False)),
      # Quality candidates were promoted pre-2025 but their 2025+ outcome is already exposed; exploratory only.
      'PRESS0':((p>0).fillna(False),(p<0).fillna(False)),
      'M5_PRESS_SPR125':(((m5>0)&(p>0)&(sr<=1.25)).fillna(False),((m5<0)&(p<0)&(sr<=1.25)).fillna(False)),
    }
    out={}
    for name,(ql,qs) in defs.items():
        z=sig.copy();z['sigL']=(baseL&ql);z['sigS']=(baseS&qs);out[name]=z
    return out


def main():
    sig=w.build_winner_signals();exe,ediag=d.load_execution();feat=prior_minute_features(sig,exe)
    vv=variants(sig,feat);report={}
    for vn,z in vv.items():
        splits={}
        for name,a,b in d.SPLITS:
            q=corr.sim_segment_corrected(z,exe,a,b);splits[name]=q
            print(vn,name,json.dumps(q,default=float),flush=True)
        report[vn]=splits
    print('RESULT_JSON_START')
    print(json.dumps({
      'base':'DUKA_EXEC_BRK_DWREL_POCMOM25','engine':'independent pure-Python corrected-distance BID/ASK',
      'microfeature_timing':'Strict prior completed Dukascopy M1 bar before executable entry minute',
      'variants':{'SPR_LE125':'pre-2025 methodological winner','PRESS0':'exploratory; holdout already exposed','M5_PRESS_SPR125':'exploratory; holdout already exposed'},
      'execution_data':ediag,'results':report,
      'decision_rule':'Do not promote a filter unless sign-stable and materially better after +0.05R/+0.10R stress; simplicity wins ties.'},default=float))
    print('RESULT_JSON_END')

if __name__=='__main__':main()
