import os

SEARCH_TERM = "playlist"
CONTEXT = 10

for root, _, files in os.walk("."):
    for filename in files:
        if not filename.endswith(".py"):
            continue

        path = os.path.join(root, filename)

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            for i, line in enumerate(lines):
                if SEARCH_TERM in line:
                    start = max(i - CONTEXT, 0)
                    end = min(i + CONTEXT + 1, len(lines))

                    print("=" * 80)
                    print(f"{path}:{i + 1}")
                    print("-" * 80)

                    for lineno in range(start, end):
                        prefix = ">>>" if lineno == i else "   "
                        print(f"{prefix} {lineno + 1:5}: {lines[lineno].rstrip()}")

        except Exception as e:
            print(f"Could not read {path}: {e}")
