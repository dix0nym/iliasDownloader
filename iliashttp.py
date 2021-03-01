import json
import re
from pathlib import Path
from types import SimpleNamespace as Namespace

import requests
from bs4 import BeautifulSoup

units = {"B": 1, "KB": 2**10, "MB": 2**20, "GB": 2**30, "TB": 2**40}


def parse_size(size):
    size = size.upper().replace('BYTES', 'B').replace(".", '').replace(',', '.')
    if not re.match(r' ', size):
        size = re.sub(r'([KMGT]?B)', r' \1', size)
    number, unit = [string.strip() for string in size.split()]
    return int(float(number)*units[unit])

def sizeof_fmt(num,):
    for unit in units.keys():
        if abs(num) < 1024.0:
            return "%3.1f%s" % (num, unit)
        num /= 1024.0
    return "%.1f%s" % (num, 'PB')

class IliasClient():

    def __init__(self, baseurl, username, password):
        self.baseurl = baseurl
        self.session = requests.Session()
        self.session.headers.update({'user-agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.113 Safari/537.36"})
        self.loggedin = self.login(username, password)

    def login(self, username, password):
        self.session.get(self.baseurl + "login.php?client_id=HS-ALBSIG&lang=de")
        url = self.baseurl + "ilias.php?lang=de&client_id=HS-ALBSIG&cmd=post&cmdClass=ilstartupgui&cmdNode=zb&baseClass=ilStartUpGUI&rtoken="
        print(url)
        payload = {'username': username, 'password': password,
                   'cmd[doStandardAuthentication]': 'Anmelden'}
        header = {"origin": "https://elearning.hs-albsig.de", "referer": "https://elearning.hs-albsig.de/login.php?client_id=HS-ALBSIG&lang=de"}
        r = self.session.post(url, data=payload, headers=header)
        r = self.session.get("https://elearning.hs-albsig.de/ilias.php?baseClass=ilPersonalDesktopGUI&cmd=jumpToSelectedItems")      
        with open('tmp.html', 'w+', encoding='utf-8') as f:
            f.write(r.text)
        return "logout.php" in r.text

    def getCourses(self):
        if not self.loggedin:
            return None
        url = self.baseurl + "ilias.php?baseClass=ilPersonalDesktopGUI&cmd=jumpToMemberships"
        soup = self.getSoup(url)
        courseElems = soup.select('a.il_ContainerItemTitle')
        return [{'title': elem.text, 'url': elem['href']} for elem in courseElems]

    def parseTree(self, url, path=""):
        soup = self.getSoup(url)
        rows = soup.select('div.il_ContainerListItem')
        files = []
        for r in rows:
            titleElem = r.select_one(
                'h4.il_ContainerItemTitle > a.il_ContainerItemTitle')
            if not titleElem:
                continue
            title = titleElem.text.rstrip()
            refUrl = titleElem["href"]
            properties = r.select(
                "div.ilListItemSection.il_ItemProperties > span.il_ItemProperty")
            # 0 = extension, 1 = size, 2 = upload/mod-date
            if len(properties) >= 3:
                ext = properties[0].text.strip()
                size = properties[1].text.strip()
                size = properties[2].text.strip() if size == "" and len(properties) == 4 and ext == "Dateiendung fehlt" else size
                ext = "" if ext == "Dateiendung fehlt" else ext
                # print("{}PROPS".format(len(properties)), path, title, ext, size)
                files.append({'name': title, 'ext': ext, 'size': parse_size(
                    size), 'url': refUrl, 'path': path})
            elif len(properties) == 0 and "cmd=view" in refUrl:
                # print("FOLDER: '{}' - '{}'".format(title, url))
                files.extend(self.parseTree(refUrl, path=path + "/" + title))
        return files

    def getFilesCourse(self, title, url):
        return self.parseTree(url, path=title)

    def logout(self):
        self.session.get(self.baseurl + 'logout.php')
        self.loggedin = False

    def download(self, url, fname, path):
        with self.session.get(url, stream=True) as r:
            if r.status_code != 200:
                print("\t\t- download of {} failed with {}".format(url, r.status_code))
                return
            path = path.joinpath(fname)
            with path.open('wb+') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

    def getFileProperties(self, url):
        r = self.session.head(url)
        if r.status_code != 200:
            print("failed to get header-only {} with {}".format(url, r.status_code))
            return None
        contentdis = r.headers['content-disposition']
        name = re.findall('filename="(.+)"', contentdis)[0]
        size = r.headers['content-length'] if 'content-length' in r.headers else -1
        return {"name": name, "size": int(size)}

    def getSoup(self, url):
        if not self.loggedin:
            return None
        url = self.baseurl + url if not url.startswith(self.baseurl) else url
        source = self.session.get(url)
        return BeautifulSoup(source.text, 'lxml')


def main():
    config_path = Path("config.json")
    if not config_path.exists():
        exit("couldnt find needed config.json")
    config = json.load(config_path.open(
        'r'), object_hook=lambda d: Namespace(**d))
    print("[+] config loaded")
    output = Path(config.path)
    print(f"[+] output-path: {config.path}")
    ic = IliasClient("https://elearning.hs-albsig.de/",
                     config.username, config.password)
    courses = ic.getCourses()
    if not courses:
        print("[+] found no courses => exit")
        exit()
    print(f"[+] found {len(courses)} courses")
    for course in courses:
        print(f"\t* {course['title']}")
        files = ic.getFilesCourse(course['title'], course['url'])
        for f in files:
            path = Path(output, f['path'])
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
            props = ic.getFileProperties(f['url'])
            fpath = path.joinpath(props['name'])
            if fpath.exists():
                if props['size'] == -1:
                    print(f"\t\t+ {props['name']} - conflict, size=? ⟶ downloading as tmpfile (?B)")
                    tmpfile = path.joinpath("tmpfile")
                    ic.download(f['url'], "tmpfile", path)
                    if tmpfile.stat().st_size == fpath.stat().st_size:
                        tmpfile.unlink()
                    else:
                        tmpfile.replace(fpath)
                elif props['size'] != fpath.stat().st_size:
                    print(f"\t\t+ {props['name']} - outdated ⟶ downloading ({sizeof_fmt(props['size'])})")
                    ic.download(f['url'], props['name'], path)
            else:
                print(f"\t\t+ {props['name']} - new file ⟶ downloading ({sizeof_fmt(props['size'])})")
                ic.download(f['url'], props['name'], path)
    print("[+] done")
    ic.logout()
    print("[+] logged out")


if __name__ == "__main__":
    main()
