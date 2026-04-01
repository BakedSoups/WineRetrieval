import json
import sqlite3
from pathlib import Path

import pandas as pd


def _parse_json(value, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def load_all_vintages(db_path):
    db_path = Path(db_path)
    connection = sqlite3.connect(db_path)
    try:
        vintages = pd.read_sql_query("SELECT * FROM vintages", connection)
    finally:
        connection.close()

    if vintages.empty:
        return vintages

    vintages["wine_flavors"] = vintages["wine_flavors_json"].apply(lambda value: _parse_json(value, []))
    vintages["style_food_pairings"] = vintages["style_food_pairings_json"].apply(lambda value: _parse_json(value, []))
    vintages["style_grapes_composition"] = vintages["style_grapes_composition_json"].apply(lambda value: _parse_json(value, []))
    return vintages
