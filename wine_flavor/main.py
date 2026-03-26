from datasource import fetch_vivino_wines

#Example of running:  fetch_vivino_wines(page=1, num_pages=3)
df = fetch_vivino_wines(num_pages=1)


print(df.head())        # first 5 rows
print(df.shape)         # (rows, cols)
print(df.columns)       # column names