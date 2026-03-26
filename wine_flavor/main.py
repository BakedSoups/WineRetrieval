
import datasource
import debugs
import engine
import transforms

# If you need a broader batch later, uncomment this to print back some IDs.
# datasource.print_vivino_wine_ids(num_pages=3, limit=10)

wines = datasource.fetch_vivino_wines(num_pages=1)

# get all unique flavors from wine
unique_flavors = transforms.unique_flavors(wines)

user_preferences = {
    "structure": {
        "acidity": 0.7,
        "fizziness": 0.0,
        "intensity": 0.8,
        "sweetness": 0.3,
        "tannin": 0.6,
    },
    "flavors": {
        "black cherry": 1.0,
        "plum": 0.9,
        "vanilla": 0.7,
        "oak": 0.6,
        "earthy": 0.8,
    },
}

sample_wine_vector = engine.build_wine_vector(wines.iloc[0], unique_flavors)
user_vector = engine.build_user_vector(user_preferences, unique_flavors)

debugs.print_wine_flavors(wines)

print(wines.head())
print(wines.shape)
print(wines.columns)
print(f"Sample wine vector length: {len(sample_wine_vector)}")
print(f"User vector length: {len(user_vector)}")
