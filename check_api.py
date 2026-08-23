import urllib.request
import json
import sys

API_KEY = 'AQ.Ab8RN6Iy4bhSIDmxO5nPmPy9dDlc-VzmaEmV3rZHgj0bcj2s5w'
url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={API_KEY}'

payload = json.dumps({
    'contents': [{'parts': [{'text': 'Say OK'}]}]
}).encode('utf-8')

req = urllib.request.Request(url, data=payload, method='POST')
req.add_header('Content-Type', 'application/json')

try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read())
        text = body['candidates'][0]['content']['parts'][0]['text']
        print(f'[OK] API hoat dong binh thuong. Phan hoi: {text.strip()}')
except urllib.error.HTTPError as e:
    code = e.code
    body = e.read().decode('utf-8', errors='replace')
    print(f'[FAIL] HTTP {code}: {body[:1000]}')
except Exception as e:
    print(f'[ERROR] {e}')
