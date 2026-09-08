import json,itertools
import numpy as np
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m
import gold_m5_numba_sequential as s

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv'];m.g.URLS=g.URLS

def bounds(idx,a,b):
    ids=np.flatnonzero(np.asarray((idx>=a)&(idx<b)));return int(ids[0]),int(ids[-1])
def main():
    x=g.prep();ed=m.build_edges(x);L=(ed['BRK'][0]|ed['EXP'][0]).fillna(False);S=(ed['BRK'][1]|ed['EXP'][1]).fillna(False);z=L&S;L&=~z;S&=~z
    args=(x.open.to_numpy(float),x.high.to_numpy(float),x.low.to_numpy(float),x.close.to_numpy(float),x.atr14.to_numpy(float),x.low.rolling(7,min_periods=1).min().to_numpy(float),x.high.rolling(7,min_periods=1).max().to_numpy(float),L.to_numpy(np.bool_),S.to_numpy(np.bool_))
    idx=x.index;trb=bounds(idx,g.START,g.TRAIN_END);vab=bounds(idx,g.TRAIN_END,g.VAL_END);hob=bounds(idx,g.VAL_END,g.END);fullb=bounds(idx,g.START,g.END)
    s.sim(*args,trb[0],min(trb[0]+1000,trb[1]),.85,1.25,4,15.,144)
    grid=list(itertools.product([.75,.85,.95],[1.10,1.25,1.40],[3,4,5],[15.,18.,20.,24.],[144,216]))
    rows=[]
    for af,be,ml,tp,mh in grid:
        tr=s.pack(s.sim(*args,trb[0],trb[1],af,be,ml,tp,mh));va=s.pack(s.sim(*args,vab[0],vab[1],af,be,ml,tp,mh))
        if tr['ret']<=0 or va['ret']<=0 or tr['pf']<1.08 or va['pf']<1.10:continue
        score=tr['ret']-1.6*tr['dd']+.85*va['ret']-1.3*va['dd']-60*abs(tr['avgR']-va['avgR'])
        rows.append((score,af,be,ml,tp,mh,tr,va))
    rows.sort(reverse=True,key=lambda z:z[0]);out=[]
    for score,af,be,ml,tp,mh,tr,va in rows[:5]:
        ho=s.pack(s.sim(*args,hob[0],hob[1],af,be,ml,tp,mh));full=s.pack(s.sim(*args,fullb[0],fullb[1],af,be,ml,tp,mh))
        out.append({'atr_floor':af,'beR':be,'max_lots':ml,'targetR':tp,'max_hold_hours':mh*5/60,'score':score,'train':tr,'val':va,'holdout':ho,'full':full,'historical_1000_reached':full['ret']>=1000})
    print('RESULT_JSON_START');print(json.dumps({'risk_pct':.36,'family':'Sequential BRK+EXP, one unprotected lot max','grid_size':len(grid),'selection':'local grid selected on train+validation only; holdout/full exposed only top5','coarse_winner':{'atr_floor':.85,'beR':1.25,'max_lots':4,'targetR':15,'hold_hours':12,'full_return_pct':684.6508},'results':out,'warning':'Any +1000% historical result still requires independent forward validation; GetData is not used in selection.'},default=float));print('RESULT_JSON_END')
if __name__=='__main__':main()
