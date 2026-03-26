
import datasource
# grab all the wines from the first page 
wines = datasource.fetch_vivino_wines(num_pages=1)
# Example of running:  fetch_vivino_wines(page=1, num_pages=3)

# get all unique flavors from wine
unique_flavors = datasource.unique_flavors(wines) 



print(wines.head())        # first 5 rows
print(wines.shape)         # (rows, cols)
print(wines.columns)       # column names