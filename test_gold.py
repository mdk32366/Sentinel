import sdmx
client = sdmx.Client('IMF_DATA')

for country in ['US', 'DE', 'IT', 'RU', 'IN', 'TR', 'GB', 'FR', 'JP', 'AU']:
    try:
        msg = client.data('IRFCL', key=f'{country}.RAFAGOLDV.M',
                          params={'startPeriod': '2024-01', 'endPeriod': '2024-06'})
        df = sdmx.to_pandas(msg)
        if len(df) > 0:
            print(f'{country}: {len(df)} obs, latest={df.values[-1]:.1f}')
        else:
            print(f'{country}: empty')
    except Exception as e:
        print(f'{country}: ERROR {str(e)[:80]}')