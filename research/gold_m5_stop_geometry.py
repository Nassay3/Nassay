import json, math
from dataclasses import dataclass
import numpy as np
import pandas as pd
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
m.g.URLS=g.URLS
@dataclass
class Lot:
 d:int;entry:float;stop:float;risk:float;rc:float;target:float;opened:int;protected:bool=False

def union(x):
 ed=m.build_edges(x);L=ed['BRK'][0]|ed['EXP'][0];S=ed['BRK'][1]|ed['EXP'][1];cl=L&S;return (L&~cl),(S&~cl)
def stop_for(x,i,d,e,atrm,sn):
 av=float(x.atr14.iloc[i]);
 if not np.isfinite(av) or av<=0:return None
 if d==1:
  sw=float(x.low.iloc[max(0,i-sn):i+1].min());st=min(sw-.05*av,e-atrm*av);r=e-st
 else:
  sw=float(x.high.iloc[max(0,i-sn):i+1].max());st=max(sw+.05*av,e+atrm*av);r=st-e
 if not np.isfinite(r) or r<=0 or r/e>.012:return None
 return st,r
def sim(x,L,S,start,end,atrm,sn,be=1.,ml=4,tp=10.):
 ids=np.flatnonzero(np.asarray((x.index>=start)&(x.index<end)))
 if not len(ids):return None
 first,last=int(ids[0]),int(ids[-1]);bal=1.;peak=1.;dd=0.;lots=[];pending=None;cdir=0;rs=[];adds=0;camps=0
 for i in range(max(first,20),min(last,len(x)-2)+1):
  if pending:
   d,si=pending;e=float(x.open.iloc[i]);sr=stop_for(x,si,d,e,atrm,sn)
   if sr:
    st,r=sr;lots.append(Lot(d,e,st,r,bal*g.RISK,e+d*tp*r,i,False));adds+=1 if cdir else 0
    if not cdir:camps+=1;cdir=d
   pending=None
  hi=float(x.high.iloc[i]);lo=float(x.low.iloc[i]);cl=float(x.close.iloc[i]);sv=[]
  for z in lots:
   if (lo<=z.stop if z.d==1 else hi>=z.stop):rr=z.d*(z.stop-z.entry)/z.risk-g.COST_R;bal+=z.rc*rr;rs.append(rr);continue
   if (hi>=z.target if z.d==1 else lo<=z.target):rr=tp-g.COST_R;bal+=z.rc*rr;rs.append(rr);continue
   if i-z.opened>=144:rr=z.d*(cl-z.entry)/z.risk-g.COST_R;bal+=z.rc*rr;rs.append(rr);continue
   if (not z.protected) and z.d*(cl-z.entry)/z.risk>=be:z.stop=z.entry;z.protected=True
   sv.append(z)
  lots=sv
  if not lots:cdir=0
  eq=bal+sum(z.rc*z.d*(cl-z.entry)/z.risk for z in lots);peak=max(peak,eq);dd=max(dd,(peak-eq)/peak if peak>0 else 0)
  if pending is None:
   if cdir==0:
    if bool(L.iloc[i]):pending=(1,i)
    elif bool(S.iloc[i]):pending=(-1,i)
   elif len(lots)<ml and all(z.protected for z in lots):
    if cdir==1 and bool(L.iloc[i]):pending=(1,i)
    elif cdir==-1 and bool(S.iloc[i]):pending=(-1,i)
 cl=float(x.close.iloc[last])
 for z in lots:rr=z.d*(cl-z.entry)/z.risk-g.COST_R;bal+=z.rc*rr;rs.append(rr)
 if not rs:return None
 a=np.asarray(rs,float);pos=a[a>0].sum();neg=-a[a<0].sum();return {'lots':len(a),'campaigns':camps,'adds':adds,'ret':(bal-1)*100,'wr':(a>0).mean()*100,'pf':pos/neg if neg else 99,'avgR':a.mean(),'R_total':a.sum(),'dd':dd*100}
def main():
 x=g.prep();L,S=union(x);rows=[]
 for atrm in [.50,.65,.85,1.0]:
  for sn in [3,6]:
   tr=sim(x,L,S,g.START,g.TRAIN_END,atrm,sn);va=sim(x,L,S,g.TRAIN_END,g.VAL_END,atrm,sn)
   if tr and va:score=tr['ret']-1.1*tr['dd']+.7*va['ret']-.8*va['dd'];rows.append((score,atrm,sn,tr,va))
 rows.sort(reverse=True,key=lambda z:z[0]);out=[]
 for score,a,sn,tr,va in rows:
  if va['ret']>0 and va['pf']>=1.08:
   ho=sim(x,L,S,g.VAL_END,g.END,a,sn);full=sim(x,L,S,g.START,g.END,a,sn);out.append({'atr_floor':a,'swing_n':sn,'score':score,'train':tr,'val':va,'holdout':ho,'full':full})
 print('RESULT_JSON_START');print(json.dumps({'risk_pct':.36,'signal':'BRK+EXP frozen','campaign':'BE1 max4 TP10','selection':'stop geometry selected on train+validation only','results':out,'target_1000_R':math.log(11)/g.RISK,'limitations':['M1 OHLC->M5','0.08R cost/lot','one unprotected lot max','stop=max distance of recent swing and ATR floor']},default=float));print('RESULT_JSON_END')
if __name__=='__main__':main()
