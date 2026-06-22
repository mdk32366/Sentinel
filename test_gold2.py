import sdmx
client = sdmx.Client('IMF_DATA')
flow = client.dataflow('IRFCL')
print(flow)