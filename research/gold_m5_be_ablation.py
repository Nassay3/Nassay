import json, math
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
m.g.URLS=g.URLS

def main():
    x=g.prep();ed=m.build_edges(x);names=('BRK','EXP');rows=[]
    for be in [.50,.75,1.0]:
      for ml in [4,6]:
        tr=m.simulate(x,ed,names,g.START,g.TRAIN_END,be,ml,10.,144)
        va=m.simulate(x,ed,names,g.TRAIN_END,g.VAL_END,be,ml,10.,144)
        if tr and va:
            score=tr['ret']-1.1*tr['dd']+.7*va['ret']-.8*va['dd'];rows.append((score,be,ml,tr,va))
    rows.sort(reverse=True,key=lambda z:z[0]);out=[]
    for score,be,ml,tr,va in rows[:3]:
      if va['ret']>0 and va['pf']>=1.08:
        ho=m.simulate(x,ed,names,g.VAL_END,g.END,be,ml,10.,144)
        full=m.simulate(x,ed,names,g.START,g.END,be,ml,10.,144)
        out.append({'beR':be,'max_lots':ml,'score':score,'train':tr,'val':va,'holdout':ho,'full':full})
    print('RESULT_JSON_START');print(json.dumps({'risk_pct':.36,'signal':'BRK+EXP frozen','targetR':10,'max_hold_hours':12,'selection':'BE/max lots selected on train+validation only; holdout top3','results':out,'target_1000_R':math.log(11)/g.RISK,'limitations':['M1 OHLC->M5','0.08R cost/lot','BE activates on bar close','one unprotected lot max']},default=float));print('RESULT_JSON_END')
if __name__=='__main__':main()
