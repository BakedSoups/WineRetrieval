import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt


DB_PATH = Path(__file__).resolve().parents[1] / "wine_flavor.db"
OUTPUT_PATH = Path(__file__).resolve().parent / "review_count_histogram.png"
FIZZINESS_OUTPUT_PATH = Path(__file__).resolve().parent / "fizziness_histogram.png"
TOP_N = 25


def ascii_histogram(values, bin_edges):
    total = len(values)
    if total == 0:
        print("No values to plot.")
        return

    counts = []
    for left, right in zip(bin_edges[:-1], bin_edges[1:]):
        if right == bin_edges[-1]:
            count = sum(left <= value <= right for value in values)
        else:
            count = sum(left <= value < right for value in values)
        counts.append(count)

    peak = max(counts) if counts else 1
    print("\nReview Count Histogram")
    for left, right, count in zip(bin_edges[:-1], bin_edges[1:], counts):
        bar_length = int((count / peak) * 40) if peak else 0
        bar = "#" * bar_length
        label = f"{left:>5} - {right:<5}"
        print(f"{label} | {bar} {count}")


def main():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"SQLite database not found at {DB_PATH}")

    connection = sqlite3.connect(DB_PATH)
    try:
        rows = connection.execute(
            """
            SELECT wine_id, wine_name, winery_name, vintage_year, COALESCE(ratings_count, 0) AS review_count, taste_fizziness
            FROM wines
            ORDER BY review_count DESC, wine_id ASC
            """
        ).fetchall()
    finally:
        connection.close()

    review_counts = [int(row[4]) for row in rows]
    fizziness_values = [float(row[5]) for row in rows if row[5] is not None]
    zero_count = sum(count == 0 for count in review_counts)

    print(f"Database: {DB_PATH}")
    print(f"Total wines: {len(rows)}")
    print(f"Wines with 0 reviews: {zero_count}")
    if rows:
        print(f"Max review count: {max(review_counts)}")

    bin_edges = [0, 1, 5, 10, 25, 50, 100, 250, 500, 1000, 5000, 10000]
    ascii_histogram(review_counts, bin_edges)

    print(f"\nTop {TOP_N} wines by review count")
    for wine_id, wine_name, winery_name, vintage_year, review_count, _ in rows[:TOP_N]:
        print(
            f"{int(review_count):>6} | "
            f"{wine_id} | "
            f"{winery_name or ''} | "
            f"{wine_name or ''} | "
            f"{vintage_year or ''}"
        )

    print(f"\nBottom {TOP_N} wines by review count")
    for wine_id, wine_name, winery_name, vintage_year, review_count, _ in rows[-TOP_N:]:
        print(
            f"{int(review_count):>6} | "
            f"{wine_id} | "
            f"{winery_name or ''} | "
            f"{wine_name or ''} | "
            f"{vintage_year or ''}"
        )

    if review_counts:
        plt.figure(figsize=(10, 6))
        plt.hist(review_counts, bins=30, color="#3b82f6", edgecolor="black")
        plt.title("Wine Review Count Distribution")
        plt.xlabel("Review Count")
        plt.ylabel("Number of Wines")
        plt.tight_layout()
        plt.savefig(OUTPUT_PATH, dpi=150)
        plt.close()
        print(f"\nSaved histogram to {OUTPUT_PATH}")

    if fizziness_values:
        plt.figure(figsize=(10, 6))
        plt.hist(fizziness_values, bins=20, color="#10b981", edgecolor="black")
        plt.title("Wine Fizziness Distribution")
        plt.xlabel("Fizziness")
        plt.ylabel("Number of Wines")
        plt.tight_layout()
        plt.savefig(FIZZINESS_OUTPUT_PATH, dpi=150)
        plt.close()
        print(f"Saved histogram to {FIZZINESS_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
