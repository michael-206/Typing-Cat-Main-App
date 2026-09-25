import requests
import time
import json

BASE_URL = "https://chenlaoshi.ca/typing_cat3/loadConfig.php?config=CME{level}Lesson{lesson}{part}"

OUTPUT_FILE = "all_vocab.txt"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

PARTS = ["A", "B", "C", "D"]

def fetch_config(level, lesson, part):
    url = BASE_URL.format(level=level, lesson=lesson, part=part)
    try:
        response = requests.get(url, headers=HEADERS, timeout=5)
        if response.status_code == 200 and response.text.strip():
            return response.text
    except requests.RequestException:
        pass
    return None

def extract_vocab(json_text):
    try:
        data = json.loads(json_text)
        words = data.get("words", [])
        
        vocab = []
        for word in words:
            q = word.get("question", "")
            a = word.get("answer", "")
            
            if q == a and q.strip():
                vocab.append(q)

        return vocab

    except json.JSONDecodeError:
        return []

def main():
    level = 1

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out_file:

        while True:
            lesson = 1
            level_has_data = False

            while True:
                lesson_has_data = False

                for part in PARTS:
                    content = fetch_config(level, lesson, part)

                    if content:
                        vocab = extract_vocab(content)

                        if vocab:
                            line = f"cme{level}, lesson{lesson}{part}: " + "，".join(vocab)
                            out_file.write(line + "\n")
                            print(f"Saved: {line}")

                        level_has_data = True
                        lesson_has_data = True
                        time.sleep(0.2)

                    # If no content → just skip this part (no break anymore)

                if not lesson_has_data:
                    print(f"No more lessons in Level {level}")
                    break

                lesson += 1

            if not level_has_data:
                print(f"No more levels. Stopping at Level {level}")
                break

            level += 1


if __name__ == "__main__":
    main()