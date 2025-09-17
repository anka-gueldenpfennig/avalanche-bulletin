# scripts/backfill.py
import os, shutil, subprocess, sys
from pathlib import Path
from datetime import date, timedelta

def main():
    if len(sys.argv) >= 3:
        start_s, end_s = sys.argv[1], sys.argv[2]
    else:
        start_s = os.environ.get("START_DATE", "2024-12-01")
        end_s   = os.environ.get("END_DATE",   "2025-04-30")

    start = date.fromisoformat(start_s)
    end   = date.fromisoformat(end_s)
    days = (end - start).days + 1

    repo    = Path(".").resolve()
    out_dir = repo / "bulletin" / "output"
    img_src = repo / "bulletin" / "static" / "images"
    public  = repo / "public" / "history"
    out_dir.mkdir(parents=True, exist_ok=True)

    ok = 0
    for i in range(days):
        d = start + timedelta(days=i)
        out_file = out_dir / f"bulletin_{d.isoformat()}.html"
        print(f"\n=== Building {d.isoformat()} ===", flush=True)

        rc = subprocess.call([
            "python", "bulletin/ava_bulletin_signage_de.py",
            "--date", d.isoformat(),
            "--out",  str(out_file),
        ])
        if rc != 0 or not out_file.exists():
            print(f"Skip {d} (exit={rc})", file=sys.stderr, flush=True)
            continue

        day_dir = public / d.isoformat()
        (day_dir / "static" / "images").mkdir(parents=True, exist_ok=True)
        shutil.copy2(out_file, day_dir / "index.html")

        if img_src.exists():
            for p in img_src.iterdir():
                if p.is_file():
                    shutil.copy2(p, day_dir / "static" / "images" / p.name)

        ok += 1

    print(f"\nBuilt {ok}/{days} days", flush=True)

if __name__ == "__main__":
    main()
