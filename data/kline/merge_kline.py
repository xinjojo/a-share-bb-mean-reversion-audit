import pandas as pd, glob
files=sorted(glob.glob('data/kline/*.parquet'))
df=pd.concat([pd.read_parquet(f) for f in files])
df['date']=pd.to_datetime(df['date'])
df=df.sort_values(['ts_code','date']).reset_index(drop=True)
df.to_parquet('combined_daily.parquet', index=False)
print('合并完成', len(df))
