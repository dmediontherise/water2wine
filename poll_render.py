import urllib.request, json, time, sys

url = "https://youtube-converter-api-zy86.onrender.com/api/info?url=https://youtu.be/3eabL2_MyjA"
print("Polling Render for new deployment...")
sys.stdout.flush()

for attempt in range(40):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Origin": "https://dmediontherise.github.io"})
        res = urllib.request.urlopen(req, timeout=30)
        data = json.loads(res.read().decode())
        if "title" in data:
            print("")
            print("SUCCESS on attempt %d!" % (attempt+1))
            print("Title: %s" % data["title"])
            print("Duration: %s" % data.get("duration_formatted", "N/A"))
            print("Channel: %s" % data.get("channel", "N/A"))
            print("Formats: %d" % len(data.get("formats", [])))
            sys.exit(0)
        else:
            print("[%d] Got response but no title" % (attempt+1))
    except Exception as e:
        err_str = str(e)
        if hasattr(e, "read"):
            try:
                err_str = e.read().decode()[:150]
            except:
                pass
        print("[%d] %s" % (attempt+1, err_str[:120]))
    sys.stdout.flush()
    time.sleep(15)

print("Timed out after 10 minutes.")
sys.exit(1)
