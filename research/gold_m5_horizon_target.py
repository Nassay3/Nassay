import json, math
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
m.g.URLS=g.URLS

def main():
    x=g.prep();ed=m.build_edges(x);names=('BRK','EXP');rows=[]
    for tp in [10.,12.,15.]:
        for mh in [144,288,576]:
            tr=m.simulate(x,ed,names,g.START,g.TRAIN_END,1.,4,tp,mh)
            va=m.simulate(x,ed,names,g.TRAIN_END,g.VAL_END,1.,4,tp,mh)
            if tr and va:
                score=tr['ret']-1.1*tr['dd']+.7*va['ret']-.8*va['dd'];rows.append((score,tp,mh,tr,va))
    rows.sort(reverse=True,key=lambda z:z[0]);out=[]
    for score,tp,mh,tr,va in rows[:5]:
        if va['ret']>0 and va['pf']>=1.08:
            ho=m.simulate(x,ed,names,g.VAL_END,g.END,1.,4,tp,mh)
            full=m.simulate(x,ed,names,g.START,g.END,1.,4,tp,mh)
            out.append({'targetR':tp,'max_hold_bars':mh,'max_hold_hours':mh*5/60,'score':score,'train':tr,'val':va,'holdout':ho,'full':full})
    print('RESULT_JSON_START')
    print(json.dumps({'risk_pct':.36,'signal':'BRK+EXP frozen','campaign':'BE1 max4; at most one unprotected lot','selection':'TP/horizon selected on train+validation only; holdout only top five','results':out,'target_1000_R':math.log(11)/g.RISK,'limitations':['M1 OHLC->M5','0.08R cost/lot','no news/DXY','BE activates on close']},default=float))
    print('RESULT_JSON_END')
if __name__=='__main__':main()
