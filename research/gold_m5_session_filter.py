import json
import numpy as np
import pandas as pd
import gold_m5_discovery_spike as g
import gold_m5_campaign as c

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
c.g.URLS=g.URLS
SPEC=g.Spec('BRK','med','vwap','8R','both',12.0)

def base(x): return g.sig(x,SPEC,g.contexts(x),g.gates(x))

def session_masks(x):
    mins=x.index.hour*60+x.index.minute
    ss={'A':mins<480,'L':(mins>=480)&(mins<870),'N':mins>=870}
    return {k:pd.Series(v,index=x.index) for k,v in ss.items()}

def single(x,L,S,start,end): return g.met(*g.simulate(x,L,S,SPEC,start,end))

def main():
    x=g.prep();L,S=base(x);sm=session_masks(x);cells=[]
    for sess,m in sm.items():
      for d in ['L','S']:
        ll=(L&m) if d=='L' else pd.Series(False,index=x.index)
        ss=(S&m) if d=='S' else pd.Series(False,index=x.index)
        tr=single(x,ll,ss,g.START,g.TRAIN_END);va=single(x,ll,ss,g.TRAIN_END,g.VAL_END)
        cells.append({'cell':sess+d,'train':tr,'val':va})
    keep=[]
    for z in cells:
        tr,va=z['train'],z['val']
        if tr and va and tr['n']>=30 and va['n']>=15 and tr['avgR']>0 and va['avgR']>0 and tr['pf']>1.05 and va['pf']>1.05:
            keep.append(z['cell'])
    FL=pd.Series(False,index=x.index);FS=pd.Series(False,index=x.index)
    for cell in keep:
        sess,di=cell[0],cell[1];m=sm[sess]
        if di=='L':FL|=L&m
        else:FS|=S&m
    combos=[]
    for be in [1.,2.]:
      for tp in [8.,10.]:
        tr=c.simulate(x,FL,FS,g.START,g.TRAIN_END,be,4,tp);va=c.simulate(x,FL,FS,g.TRAIN_END,g.VAL_END,be,4,tp)
        if tr and va:
            score=tr['ret']-1.1*tr['dd']+.7*va['ret']-.8*va['dd'];combos.append((score,be,tp,tr,va))
    combos.sort(reverse=True,key=lambda z:z[0]);out=[]
    for score,be,tp,tr,va in combos:
        ho=c.simulate(x,FL,FS,g.VAL_END,g.END,be,4,tp);full=c.simulate(x,FL,FS,g.START,g.END,be,4,tp)
        out.append({'beR':be,'targetR':tp,'score':score,'train':tr,'val':va,'holdout':ho,'full':full})
    print('RESULT_JSON_START');print(json.dumps({'cells':cells,'frozen_keep':keep,'results':out,'risk_pct':.36,'selection':'cells screened with single-position 8R on train+validation only; campaign tested after freeze','limitations':['M1 OHLC->M5','0.08R cost per lot','one unprotected lot max','no news/DXY']},default=float));print('RESULT_JSON_END')
if __name__=='__main__':main()
