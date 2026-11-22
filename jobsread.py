import json, time

j = json.load(open("/tmp/jobs.json"))["jobs"]
now = time.time()
print("任务总数:", len(j))
err = [x for x in j if x["status"] == "error"]
print("失败数:", len(err))
for x in err:
    age = (now - x["created"]) / 3600
    print(f"  - [{age:5.1f}h前] {x['label'][:34]} | {x['error'][:150]}")
for x in [y for y in j if y["status"] == "done"][:6]:
    age = (now - x["created"]) / 3600
    print(f"  ok [{age:5.1f}h前] {x['file'][:56]}")
