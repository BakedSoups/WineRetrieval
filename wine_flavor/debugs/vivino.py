def pull_wine_flavors(wine_row):
    lines = [f"\nWine: {wine_row['wine_name']}"]

    for flavor_group in wine_row["wine_flavors"]:
        lines.append(f"  Group: {flavor_group['group']} (group count={flavor_group.get('count')})")
        for keyword in flavor_group.get("primary_keywords") or []:
            lines.append(f"    Primary: {keyword.get('name')} count={keyword.get('count')}")
        for keyword in flavor_group.get("secondary_keywords") or []:
            lines.append(f"    Secondary: {keyword.get('name')} count={keyword.get('count')}")

    return "\n".join(lines)


def print_wine_flavors(wines, limit=5):
    for _, wine_row in wines.head(limit).iterrows():
        print(pull_wine_flavors(wine_row))
