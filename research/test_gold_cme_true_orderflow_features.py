import numpy as np
import pandas as pd
import gold_cme_true_orderflow_features as f


def synthetic_trades():
    idx=pd.to_datetime([
        '2026-01-02T10:00:10Z','2026-01-02T10:00:20Z','2026-01-02T10:00:40Z',
        '2026-01-02T10:01:10Z','2026-01-02T10:01:20Z'])
    # B buyer aggressor, A seller aggressor.
    return pd.DataFrame({'side':['B','B','A','A','B'],'size':[10,5,3,8,2]},index=idx)


def synthetic_book():
    idx=pd.to_datetime([
        '2026-01-02T10:00:05Z','2026-01-02T10:00:15Z','2026-01-02T10:00:30Z',
        '2026-01-02T10:01:05Z','2026-01-02T10:01:30Z'])
    d={
        'bid_px_00':[2000,2000,2000,2001,2001],
        'ask_px_00':[2001,2001,2001,2002,2002],
        'action':['A','A','C','A','C'],
        'side':['B','A','A','B','B'],
        'size':[5,2,1,4,2],
    }
    for i in range(10):
        d[f'bid_sz_{i:02d}']=[10+i,12+i,12+i,14+i,12+i]
        d[f'ask_sz_{i:02d}']=[8+i,9+i,8+i,8+i,8+i]
        d[f'bid_ct_{i:02d}']=[2,2,2,3,2]
        d[f'ask_ct_{i:02d}']=[2,2,2,2,2]
        if i>0:
            d[f'bid_px_{i:02d}']=[2000-i,2000-i,2000-i,2001-i,2001-i]
            d[f'ask_px_{i:02d}']=[2001+i,2001+i,2001+i,2002+i,2002+i]
    return pd.DataFrame(d,index=idx)


def main():
    t=f.trade_features(synthetic_trades(),'1min',1)
    first=t.loc[pd.Timestamp('2026-01-02T10:00:00Z')]
    assert first['buy_volume']==15
    assert first['sell_volume']==3
    assert first['delta']==12
    assert abs(first['buy_pressure']-15/18)<1e-12
    assert abs(first['sell_pressure']-3/18)<1e-12
    assert abs(first['aggressor_imbalance']-12/18)<1e-12
    assert first['trades']==3
    assert abs(first['tps']-3/60)<1e-12
    assert first['available_time']==pd.Timestamp('2026-01-02T10:01:00Z')

    b=f.book_features(synthetic_book(),'1min',1)
    bf=b.loc[pd.Timestamp('2026-01-02T10:00:00Z')]
    assert np.isfinite(bf['depth_imb_l1'])
    assert bf['bid_add']==5
    assert bf['ask_add']==2
    assert bf['ask_cancel']==1
    assert bf['bid_cancel']==0
    assert bf['stack_pressure']>0
    assert bf['pull_pressure']>0
    assert bf['liquidity_pressure']>0
    assert bf['available_time']==pd.Timestamp('2026-01-02T10:01:00Z')

    # Aggregation availability must be at close, never at bar start.
    t5=f.trade_features(synthetic_trades(),'5min',5)
    assert t5.iloc[0]['available_time']==t5.index[0]+pd.Timedelta(minutes=5)
    t15=f.trade_features(synthetic_trades(),'15min',15)
    assert t15.iloc[0]['available_time']==t15.index[0]+pd.Timedelta(minutes=15)
    print('PASS_TRUE_ORDERFLOW_FEATURE_TESTS')

if __name__=='__main__':main()
