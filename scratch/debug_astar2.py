import urllib.request
import json
req = urllib.request.Request('http://127.0.0.1:8000/api/schedule-benchmark/a_star/ENSIA_S1', method='POST')
res = urllib.request.urlopen(req)
