import base64
from termcolor import colored
import json
import zlib
from pathlib import Path
from types import SimpleNamespace as Namespace
from lxml import etree

from zeep import Client, xsd


def loadConfig():
    config_path = Path("config.json")
    if not config_path.exists():
        exit("couldnt find needed config.json")
    return json.load(config_path.open('r'), object_hook=lambda d: Namespace(**d))

def printlogo():
    print(r"  ___ _ _             ____                      _                 _           ")
    print(r" |_ _| (_) __ _ ___  |  _ \  _____      ___ __ | | ___   __ _  __| | ___ _ __ ")
    print(r"  | || | |/ _` / __| | | | |/ _ \ \ /\ / / '_ \| |/ _ \ / _` |/ _` |/ _ \ '__|")
    print(r"  | || | | (_| \__ \ | |_| | (_) \ V  V /| | | | | (_) | (_| | (_| |  __/ |   ")
    print(r" |___|_|_|\__,_|___/ |____/ \___/ \_/\_/ |_| |_|_|\___/ \__,_|\__,_|\___|_|   ")
    print("\n")

def getRoles(parser, roles):
    parsed = etree.fromstring(roles.encode('utf-8'), parser=parser)
    return [t.text.split("_")[-1] for t in parsed.findall('Object/Title') if "crs_member" in t.text]

def getIntValue(tree, selector):
    value = tree.find(selector).text
    return int(value) if value.isdigit() else value

def parseCourse(parser, course):
    parsed = etree.fromstring(course.encode('utf-8'), parser=parser)
    objs = parsed.findall('Object')
    course = {'title': '', 'id': 0, "files": []}
    for obj in objs:
        if obj.get('type') == 'crs':
            course['title'] = obj.find('Title').text
            course['id'] = obj.find('References').get('ref_id')
        elif obj.get('type') == 'file':
            refs = obj.find('References')
            fileSize = getIntValue(obj, "Properties/Property[@name='fileSize']")
            version = getIntValue(obj, "Properties/Property[@name='fileVersion']")
            path = buildPath(course['id'], refs.findall('Path/Element'))
            f = {'id': refs.get('ref_id'), 'title': obj.find('Title').text, 'fileSize': fileSize, 'version': version, "path": path}
            course['files'].append(f)
    return course

def buildPath(cid, paths):
    path = []
    for p in paths[::-1]:
        path.insert(0, p.text)
        if p.get('ref_id') == cid:
            break
    return "/".join(path)

def downloadFiles(client, sid, parser, output, files):
    count = 0
    failcount = 0
    new_files = 0
    for f in files:
        path = Path(output, f['path'], f['title'])
        if not path.exists() or path.stat().st_size != f['fileSize']:
            # does not exists
            new_files += 1
            # ATTACH_MODE: NO = 0; ENCODED = 1; ZLIB_ENCODED = 2; GZIP_ENCODED = 3; COPY = 4;
            with client.settings(xml_huge_tree=True):
                response = client.service.getFileXML(sid, f['id'], 2)

            root = etree.fromstring(response.encode('utf-8'), parser=parser)
            latestVersion = root.find("Versions/Version[@version='{}']".format(f['version']))
            # filename = responseDict['File']['Filename']
            if latestVersion is not None and hasattr(latestVersion, 'text'):
                assert latestVersion.get('text') == latestVersion.text
                data = latestVersion.text
                decoded = base64.decodebytes(data.encode('utf-8'))
                decompressed = zlib.decompress(decoded)
                if not path.parent.exists():
                    path.parent.mkdir(parents=True, exist_ok=True)
                with path.open('wb+') as f:
                    f.write(decompressed)
                count += 1
            else:
                failcount += 1
    return new_files, count, failcount


def main():
    printlogo()
    parser = etree.XMLParser(huge_tree=True)
    config = loadConfig()
    client = Client(config.server)
    sid = client.service.loginLDAP(config.client_id, config.username, config.password)
    print("[+] logged in as {} -> sid={}".format(config.username, sid))
    user_id = client.service.getUserIdBySid(sid=sid)
    print("[+] user_id = {}".format(user_id))
    roles = getRoles(parser, client.service.getUserRoles(sid=sid, user_id=user_id))
    output = Path(config.path)
    print("[+] output-path: {}".format(config.path))

    if not output.exists():
        output.mkdir(parents=True, exist_ok=True)

    print("[+] found {} course".format(len(roles)))

    for role in roles:
        tree = client.service.getXMLTree(sid=sid, ref_id=role, types=xsd.SkipValue, user_id=user_id)
        k = parseCourse(parser, tree)
        new_files, count, failcount = downloadFiles(client, sid, parser, output, k['files'])
        formatted_counts = "{}/{}/{}".format(colored(count, 'green'), colored(failcount, 'red'), new_files)
        print("\t* {}: {}".format(k['title'], formatted_counts if new_files else "no new files"))
    print("[+] done")
    client.service.logout(sid)
    print("[+] logged out")

if __name__ == "__main__":
    main()
