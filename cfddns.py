import requests
import socket
import sys
import os

CF_GLOBAL_KEY = os.environ.get("CF_GLOBAL_KEY")
CF_EMAIL = os.environ.get("CF_EMAIL")

auth = {"X-Auth-Email": CF_EMAIL, "X-Auth-Key": CF_GLOBAL_KEY, "Content-Type": "application/json"}


def update_dns(domain, new_ip):
    for i in list_zones():
        if domain.endswith(i[1]):
            zone = i[0]
    if not zone:
        print("ERROR DOMAIN NOT FOUND")

    if create_domain(zone, domain, new_ip):
        print(f"RECORD {domain} -> {new_ip} CREATED")
        return

    list_api = f"https://api.cloudflare.com/client/v4/zones/{zone}/dns_records?name="
    edit_api = f"https://api.cloudflare.com/client/v4/zones/{zone}/dns_records"
    dns_info = {"type": "A", "name": domain, "ttl": 3600, "proxied": False}

    try:
        old_ip = socket.gethostbyname(dns_info["name"])
    except socket.gaierror:
        old_ip = None

    if old_ip == new_ip:
        print(f"RECORD {dns_info['name']} = {old_ip} NOT CHANGED")
    else:
        dns_id = requests.get(f"{list_api}{domain}", headers=auth).json()["result"][0]["id"]
        dns_info["content"] = new_ip
        upd = requests.put(f"{edit_api}/{dns_id}", headers=auth, json=dns_info).json()
        dn_name = upd["result"]["name"]
        dn_type = upd["result"]["type"]
        dn_content = upd["result"]["content"]
        print(f"RECORD {dn_name} {dn_type} {dn_content} UPDATED")


def list_zones():
    api_url = "https://api.cloudflare.com/client/v4/zones"
    resp = requests.get(api_url, headers=auth).json()
    return [(z["id"], z["name"]) for z in resp["result"]]


def list_domains(zid):
    api_url = f"https://api.cloudflare.com/client/v4/zones/{zid}/dns_records"
    resp = requests.get(api_url, headers=auth).json()
    return resp["result"]


def create_domain(zone, domain, ip=None):
    existing = [i["name"] for i in list_domains(zone)]
    if domain not in existing:
        create_record(domain, zone, ip)
        return True
    else:
        return False


def create_record(sub, zid, ip="1.1.1.1", record="A"):
    api_url = f"https://api.cloudflare.com/client/v4/zones/{zid}/dns_records"
    data = {"content": ip, "name": sub, "proxied": False, "type": record, "comment": "", "ttl": 3600}
    res_txt = requests.post(api_url, headers=auth, json=data).text
    print(res_txt)
    return res_txt


if __name__ == "__main__":
    TARGET_DOMAIN = sys.argv[1]
    TARGET_ADDR = requests.get("https://ping.api.morgan.kr").json()["info"]["client"]
    print(f"UPDATE {TARGET_DOMAIN} <- {TARGET_ADDR}")
    update_dns(TARGET_DOMAIN, TARGET_ADDR)
