import requests

url = "https://api.iplayacl.com/api/v1/player-compare-stats"

payload = {
    "playerIDs": [142125],
    "bucketID": 11
}

headers = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "origin": "https://app.iplayacl.com",
    "referer": "https://app.iplayacl.com/",
    "user-agent": "Mozilla/5.0",
    "x-app-version": "14.1.0"
}

r = requests.post(
    url,
    json=payload,
    headers=headers
)

print(r.status_code)
print(r.json())