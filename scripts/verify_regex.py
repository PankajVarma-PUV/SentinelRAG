import re

# The new pattern: r'@([\w\- ]+(?:\.[\w\-]+)*)(?=\s|$|\?|!|[,;:])'
MENTION_PATTERN = re.compile(r'@([\w\- ]+(?:\.[\w\-]+)*)(?=\s|$|\?|!|[,;:])')

def parse_mentions(query: str) -> list:
    return MENTION_PATTERN.findall(query)

test_cases = [
    ("@cats.jpg what is this?", ["cats.jpg"]),
    ("Tell me about @data.json.", ["data.json"]),
    ("Compare @file1 and @file2.txt!", ["file1", "file2.txt"]),
    ("What is in @my-file_v1.0.txt?", ["my-file_v1.0.txt"]),
    ("Simple @mention at end of sentence.", ["mention"]),
    ("Multiple @dots.in.name.pdf test", ["dots.in.name.pdf"]),
    ("@file with space (not supported usually, but let's see)", ["file with space"]), # \w\- ] captures spaces
]

print("--- Regex Verification Results ---")
for query, expected in test_cases:
    actual = parse_mentions(query)
    status = "✅ PASS" if actual == expected else f"❌ FAIL (Actual: {actual})"
    print(f"Query: {query}\nResult: {actual} | {status}\n")
