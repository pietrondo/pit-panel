import requests

def get_cve():
    res = requests.get('https://cve.circl.lu/api/last')
    print(res.status_code)
    # print(res.json()[:2])

get_cve()
