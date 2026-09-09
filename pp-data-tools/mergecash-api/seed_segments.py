"""
Seed segment configs into Firestore for MergeCash v3.

Each segment defines a chapter range → single target chapter + reward + time limit.
When a player signs up, their current chapter is matched against these ranges.

Usage:
    python seed_segments.py                    # Seed from built-in defaults
    python seed_segments.py --csv segments.csv # Seed from CSV file

CSV format:
    segment_id,name,min_chapter,max_chapter,target_chapter,reward_amount,time_limit_days
    early,Early Push,1,30,50,3.00,21
    mid,Mid Push,31,60,80,5.00,14
"""
import argparse
import csv
import sys
from google.cloud import firestore

PROJECT_ID = "yotam-395120"

# Placeholder segments — replace with real values from the segment CSV
DEFAULT_SEGMENTS = {
    "early": {
        "name": "Early Push",
        "min_chapter": 1,
        "max_chapter": 30,
        "target_chapter": 50,
        "reward_amount": 3.00,
        "time_limit_days": 21,
        "is_active": True,
    },
    "mid": {
        "name": "Mid Push",
        "min_chapter": 31,
        "max_chapter": 60,
        "target_chapter": 80,
        "reward_amount": 5.00,
        "time_limit_days": 14,
        "is_active": True,
    },
    "late": {
        "name": "Late Push",
        "min_chapter": 61,
        "max_chapter": 100,
        "target_chapter": 120,
        "reward_amount": 10.00,
        "time_limit_days": 10,
        "is_active": True,
    },
    "endgame": {
        "name": "Endgame",
        "min_chapter": 101,
        "max_chapter": 135,
        "target_chapter": 135,
        "reward_amount": 15.00,
        "time_limit_days": 7,
        "is_active": True,
    },
}


def load_csv(path):
    """Load segments from CSV file."""
    segments = {}
    with open(path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            seg_id = row["segment_id"].strip()
            segments[seg_id] = {
                "name": row.get("name", seg_id).strip(),
                "min_chapter": int(row["min_chapter"]),
                "max_chapter": int(row["max_chapter"]),
                "target_chapter": int(row["target_chapter"]),
                "reward_amount": float(row["reward_amount"]),
                "time_limit_days": int(row.get("time_limit_days", 14)),
                "is_active": True,
            }
    return segments


def seed(segments):
    fs = firestore.Client(project=PROJECT_ID)

    # Deactivate all existing segments first
    for doc in fs.collection("segments").stream():
        doc.reference.update({"is_active": False})
    print("Deactivated existing segments")

    # Seed new segments
    for seg_id, data in segments.items():
        fs.collection("segments").document(seg_id).set(data)
        print(f"  Seeded: {seg_id} (ch{data['min_chapter']}-{data['max_chapter']} -> target ch{data['target_chapter']}, ${data['reward_amount']:.2f}, {data['time_limit_days']}d)")

    print(f"\nDone! {len(segments)} segments active.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed MergeCash segment configs into Firestore")
    parser.add_argument("--csv", help="Path to CSV file with segment definitions")
    args = parser.parse_args()

    if args.csv:
        segments = load_csv(args.csv)
        print(f"Loaded {len(segments)} segments from {args.csv}")
    else:
        segments = DEFAULT_SEGMENTS
        print("Using default placeholder segments")

    seed(segments)
