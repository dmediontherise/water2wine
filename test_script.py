import urllib.request
import urllib.error
import sys

url = "http://localhost:8000/api/download?url=https://www.youtube.com/watch?v=vJoAoqZ1Sso&format=mp3&quality=192k&title=test"
try:
    print("Fetching URL:", url)
    response = urllib.request.urlopen(url)
    print("Status:", response.status)
    with open("download_test.mp3", "wb") as f:
        while True:
            chunk = response.read(16384)
            if not chunk:
                break
            f.write(chunk)
    import os
    print("Saved file size:", os.path.getsize("download_test.mp3"))
except urllib.error.HTTPError as e:
    print("Status:", e.code)
    print("Error:", e.read().decode())
except Exception as e:
    print("Exception:", e)
