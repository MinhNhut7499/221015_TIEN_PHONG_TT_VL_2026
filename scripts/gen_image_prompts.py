"""
Generate 100 image-generation prompts for Architecture-AI dataset.

Each prompt:
  - 1 main style with 5 dominant features
  - 5 secondary style accents (1 feature each, from different families)

Output:
  docs/image_gen_prompts.md        — 100 filled-in prompt texts
  docs/image_gen_ground_truth.csv  — ground-truth table for scoring
"""

import csv
import json
import random
from pathlib import Path

ROOT = Path(__file__).parent.parent
STYLES_JSON = ROOT / "chatbot" / "knowledge" / "styles.json"
OUT_MD = ROOT / "docs" / "image_gen_prompts.md"
OUT_CSV = ROOT / "docs" / "image_gen_ground_truth.csv"


def load_styles() -> dict:
    with open(STYLES_JSON, encoding="utf-8") as f:
        return json.load(f)


def get_features(style: dict, n: int = 5) -> list[str]:
    """Return n defining features, supplementing from expected_profile if short."""
    feats = list(style["defining_features"])
    if len(feats) < n:
        ep = style.get("expected_profile", {})
        for v in ep.values():
            cand = str(v)
            if cand not in feats:
                feats.append(cand)
            if len(feats) >= n:
                break
    return feats[:n]


def pick_secondaries(main_id: str, all_styles: list[dict], n: int = 5, seed: int = 0) -> list[dict]:
    """Pick n secondary styles from as many different families as possible."""
    rng = random.Random(seed)
    candidates = [s for s in all_styles if s["id"] != main_id]

    # Group by family
    by_family: dict[str, list[dict]] = {}
    for s in candidates:
        by_family.setdefault(s["parent"], []).append(s)

    main_family = next(s["parent"] for s in all_styles if s["id"] == main_id)
    # Prefer families different from main's family
    family_order = [f for f in by_family if f != main_family] + [main_family]
    rng.shuffle(family_order[:len(family_order) - 1])  # shuffle non-main families

    selected: list[dict] = []
    used_ids: set[str] = set()

    for fam in family_order:
        if len(selected) >= n:
            break
        pool = [s for s in by_family.get(fam, []) if s["id"] not in used_ids]
        if pool:
            pick = rng.choice(pool)
            selected.append(pick)
            used_ids.add(pick["id"])

    # Fill remaining slots from any remaining candidates
    remaining = [s for s in candidates if s["id"] not in used_ids]
    while len(selected) < n and remaining:
        pick = rng.choice(remaining)
        selected.append(pick)
        used_ids.add(pick["id"])
        remaining = [s for s in remaining if s["id"] not in used_ids]

    return selected[:n]


# ---------------------------------------------------------------------------
# 100 (main_style_id, building_type) pairs — each main style used exactly once
# ---------------------------------------------------------------------------
MAIN_PAIRS: list[tuple[str, str]] = [
    # --- Medieval European ---
    ("gothic",               "cathedral"),
    ("romanesque",           "cathedral"),
    ("norman",               "cathedral"),
    ("brick-gothic",         "church"),
    ("venetian-gothic",      "palace"),
    ("mudejar",              "church"),
    # --- Renaissance & Baroque ---
    ("renaissance",          "palace"),
    ("baroque",              "church"),
    ("mannerism",            "palace"),
    ("palladian",            "mansion"),
    ("rococo",               "palace"),
    ("churrigueresque",      "church"),
    ("manueline",            "church"),
    ("spanish-colonial",     "church"),
    ("dutch-colonial",       "city hall"),
    # --- Neoclassical & 19th-century Revival ---
    ("neoclassical",         "museum"),
    ("beaux-arts",           "opera house"),
    ("greek-revival",        "library"),
    ("gothic-revival",       "church"),
    ("romanesque-revival",   "church"),
    ("renaissance-revival",  "city hall"),
    ("byzantine-revival",    "church"),
    ("egyptian-revival",     "mausoleum"),
    ("moorish-revival",      "pavilion"),
    ("russian-revival",      "church"),
    ("second-empire",        "city hall"),
    ("italianate",           "mansion"),
    ("tudor-revival",        "mansion"),
    ("colonial-revival",     "government hall"),
    ("spanish-colonial-revival", "church"),
    ("mission-revival",      "church"),
    # --- European-American Vernacular ---
    ("georgian",             "mansion"),
    ("federal",              "government hall"),
    ("regency",              "opera house"),
    ("victorian-queen-anne", "city hall"),
    ("grunderzeit",          "city hall"),
    ("jacobean",             "mansion"),
    # --- Early Modern ---
    ("arts-and-crafts",      "library"),
    ("art-nouveau",          "mansion"),
    ("jugendstil-secession",  "museum"),
    ("catalan-modernisme",   "church"),
    ("prairie-school",       "mansion"),
    ("art-deco",             "skyscraper"),
    ("streamline-moderne",   "train station"),
    ("expressionism",        "museum"),
    ("amsterdam-school",     "library"),
    ("constructivism",       "government hall"),
    ("de-stijl",             "pavilion"),
    ("futurism",             "train station"),
    ("bauhaus",              "museum"),
    # --- Modern & Contemporary ---
    ("modernism",            "government hall"),
    ("mid-century-modern",   "pavilion"),
    ("brutalism",            "library"),
    ("metabolism",           "skyscraper"),
    ("organic-architecture", "museum"),
    ("googie",               "train station"),
    ("postmodernism",        "city hall"),
    ("deconstructivism",     "museum"),
    ("high-tech",            "train station"),
    ("neo-futurism",         "museum"),
    ("parametricism",        "opera house"),
    ("critical-regionalism", "museum"),
    ("minimalism",           "library"),
    ("contemporary-vernacular", "pavilion"),
    # --- Ancient ---
    ("ancient-greek",        "temple"),
    ("ancient-roman",        "government hall"),
    ("ancient-egyptian",     "mausoleum"),
    ("mesopotamian",         "temple"),
    ("achaemenid-persian",   "palace"),
    ("etruscan",             "temple"),
    # --- Late Antique / Early Medieval ---
    ("byzantine",            "cathedral"),
    ("early-christian",      "church"),
    ("carolingian",          "cathedral"),
    ("ottonian",             "cathedral"),
    ("pre-romanesque",       "church"),
    # --- Islamic ---
    ("umayyad-abbasid",      "mosque"),
    ("moorish",              "palace"),
    ("mamluk",               "mosque"),
    ("ottoman",              "mosque"),
    ("safavid-persian",      "mosque"),
    ("mughal",               "mausoleum"),
    ("indo-islamic",         "mausoleum"),
    ("fatimid",              "mosque"),
    # --- East Asian ---
    ("traditional-chinese",  "temple"),
    ("traditional-japanese", "pavilion"),
    ("japanese-buddhist-temple", "temple"),
    ("korean-hanok",         "pavilion"),
    ("tibetan",              "temple"),
    # --- South & Southeast Asian ---
    ("north-indian-temple",  "temple"),
    ("south-indian-temple",  "temple"),
    ("khmer",                "temple"),
    ("thai",                 "temple"),
    ("burmese",              "temple"),
    ("javanese-candi",       "temple"),
    ("vietnamese-traditional","pavilion"),
    # --- Indigenous Americas & Africa ---
    ("maya",                 "temple"),
    ("aztec",                "temple"),
    ("inca",                 "temple"),
    ("pueblo",               "mansion"),
    ("sudano-sahelian",      "mosque"),
]

assert len(MAIN_PAIRS) == 100, f"Expected 100 pairs, got {len(MAIN_PAIRS)}"


def build_prompt(idx: int, main: dict, btype: str, main_feats: list[str],
                 sec_data: list[tuple[str, str]]) -> str:
    mn = main["name"]
    lines = [
        f"**Prompt {idx:03d}**  *(building: {btype})*\n",
        f"Generate a photorealistic exterior photograph of a {btype}, daytime,",
        "eye-level, the entire building visible, no text or watermark, high detail.",
        f"PRIMARY STYLE = {mn}. Make ALL of these {mn} features clearly DOMINANT:",
        f"1. {main_feats[0]} ({mn})",
        f"2. {main_feats[1]} ({mn})",
        f"3. {main_feats[2]} ({mn})",
        f"4. {main_feats[3]} ({mn})",
        f"5. {main_feats[4]} ({mn})",
        "",
        "SECONDARY ACCENTS — make each one SMALL, localized, and clearly a DIFFERENT style:",
        f"6.  {sec_data[0][1]} ({sec_data[0][0]})",
        f"7.  {sec_data[1][1]} ({sec_data[1][0]})",
        f"8.  {sec_data[2][1]} ({sec_data[2][0]})",
        f"9.  {sec_data[3][1]} ({sec_data[3][0]})",
        f"10. {sec_data[4][1]} ({sec_data[4][0]})",
        "",
        f"The building must read OVERALL as {mn}.",
    ]
    return "\n".join(lines)


def main() -> None:
    data = load_styles()
    all_styles = data["styles"]
    by_id = {s["id"]: s for s in all_styles}

    prompts: list[str] = []
    gt_rows: list[list[str]] = []

    for idx, (main_id, btype) in enumerate(MAIN_PAIRS, 1):
        main = by_id[main_id]
        main_feats = get_features(main, 5)
        sec_styles = pick_secondaries(main_id, all_styles, n=5, seed=idx * 17)
        sec_data: list[tuple[str, str]] = [
            (ss["name"], ss["defining_features"][0]) for ss in sec_styles
        ]

        prompts.append(build_prompt(idx, main, btype, main_feats, sec_data))

        gt_rows.append([
            str(idx), btype, main["name"],
            main_feats[0], main["name"],
            main_feats[1], main["name"],
            main_feats[2], main["name"],
            main_feats[3], main["name"],
            main_feats[4], main["name"],
            sec_data[0][1], sec_data[0][0],
            sec_data[1][1], sec_data[1][0],
            sec_data[2][1], sec_data[2][0],
            sec_data[3][1], sec_data[3][0],
            sec_data[4][1], sec_data[4][0],
        ])

    # Write markdown
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("# Image Generation Prompts — Architecture-AI Dataset\n\n")
        f.write(
            "100 prompts for generating photorealistic architectural images covering "
            "all style families in `chatbot/knowledge/styles.json`.\n"
            "Each prompt specifies 1 dominant style (5 features) + 5 secondary accent styles (1 feature each).\n\n"
            "Companion ground-truth table: `docs/image_gen_ground_truth.csv`\n\n"
            "---\n\n"
        )
        for p in prompts:
            f.write(p)
            f.write("\n\n---\n\n")

    # Write CSV
    header = [
        "prompt_id", "building_type", "main_style",
        "ev1", "ev1_style", "ev2", "ev2_style", "ev3", "ev3_style",
        "ev4", "ev4_style", "ev5", "ev5_style",
        "ev6", "ev6_style", "ev7", "ev7_style", "ev8", "ev8_style",
        "ev9", "ev9_style", "ev10", "ev10_style",
    ]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(header)
        w.writerows(gt_rows)

    print(f"✓ {len(prompts)} prompts → {OUT_MD}")
    print(f"✓ Ground truth → {OUT_CSV}")


if __name__ == "__main__":
    main()
