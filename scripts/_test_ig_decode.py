import json
import re
import urllib.request
from content_instagram_analyze import extract_caption_from_embed, fetch_embed_html, decode_json_string

html = fetch_embed_html("https://www.instagram.com/p/DY7vFf4Fp-z/")
cap = extract_caption_from_embed(html)
print("len", len(cap))
print("repr head", repr(cap[:40]))
print("decoded head", decode_json_string(cap[:40]) if cap[:2] == "\\" else cap[:40])

anchor = html.find("edge_media_to_caption")
chunk = html[anchor : anchor + 8000]
start = chunk.find('text\\":\\"') + len('text\\":\\"')
end = chunk.find('\\"', start)
raw = chunk[start:end]
print("raw repr", repr(raw[:30]))
print("json.loads", json.loads(f'"{raw[:30]}"'))
