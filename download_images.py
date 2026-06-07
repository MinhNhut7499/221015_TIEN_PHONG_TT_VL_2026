from icrawler.builtin import BingImageCrawler
from ddgs import DDGS
import requests
import os
import time

ROOT_DIR = r"D:\Study\Thesis\raw_images"


def clean_name(text):
    return text.replace(" ", "_").replace("/", "_")


def is_valid_image(keyword):
    blacklist = [
        "interior", "inside", "room",
        "floor plan", "blueprint", "diagram",
        "drawing", "sketch", "plan"
    ]
    keyword = keyword.lower()
    return not any(word in keyword for word in blacklist)


def download_duckduckgo(keyword, folder, remaining):

    headers = {"User-Agent": "Mozilla/5.0"}
    count = 0

    try:
        with DDGS() as ddgs:
            results = ddgs.images(keyword, max_results=remaining)

            for r in results:
                try:
                    url = r["image"]
                    response = requests.get(url, headers=headers, timeout=10)

                    if response.status_code == 200:
                        filename = f"ddg_{clean_name(keyword)}_{count}.jpg"
                        path = os.path.join(folder, filename)

                        with open(path, "wb") as f:
                            f.write(response.content)

                        count += 1

                        if count >= remaining:
                            break

                except:
                    pass

                time.sleep(0.3)

    except:
        print("DDG blocked:", keyword)


def count_images(folder):
    return len([f for f in os.listdir(folder) if f.endswith(".jpg")])


styles = {
    "brutalism": [
        "brutalist building exterior",
        "brutalist architecture concrete",
        "brutalist facade",
        "brutalist government building"
    ],
    "high_tech": [
        "high tech architecture exterior",
        "richard rogers building exterior",
        "norman foster architecture exterior",
        "high tech glass steel building"
    ],
    "neoclassical": [
        "neoclassical building exterior",
        "neoclassical facade columns",
        "government neoclassical architecture",
        "classical revival building exterior"
    ]
}


MAX_PER_FOLDER = 100

for style, keywords in styles.items():

    folder = os.path.join(ROOT_DIR, style)
    os.makedirs(folder, exist_ok=True)

    print(f"\n===== {style} =====")

    crawler = BingImageCrawler(storage={"root_dir": folder})

    for keyword in keywords:

        if not is_valid_image(keyword):
            continue

        current_count = count_images(folder)
        remaining = MAX_PER_FOLDER - current_count

        if remaining <= 0:
            print("Enough images, skip.")
            break

        print(f"Searching: {keyword} | Need: {remaining}")

        # Bing
        crawler.crawl(
            keyword=keyword + " exterior building",
            max_num=remaining,
            min_size=(400, 400)
        )

        time.sleep(3)

        # DuckDuckGo bổ sung
        current_count = count_images(folder)
        remaining = MAX_PER_FOLDER - current_count

        if remaining > 0:
            download_duckduckgo(keyword, folder, remaining)

        time.sleep(5)

print("Done.")