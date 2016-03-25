# !/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test Server
"""

import requests
import io

uid = 'e61f2266-eff9-11e5-8264-74867a3853c6'
host = 'http://192.168.1.102/'
url_bind = host + 'bind'
url_upload = host + 'api/upload'
url_file_list = host + 'api/filelist'


def bind(what):
    req = requests.get(url_bind, params={'uid': uid, 'what': what})
    print(req.text)


def upload():
    files = [
        ('files', ('srca.cer', open('/home/finalize/Downloads/srca.cer', 'rb'), 'application/pkix-cert')),
        ('files', ('recur.png', open('/home/finalize/Downloads/recur.png', 'rb'), 'image/png')),
        ('files', ('Simple_Explorer_2.3.apk', open('/home/finalize/Downloads/Simple_Explorer_2.3.apk', 'rb'),
                   'application/vnd.android.package-archive'))
    ]
    req = requests.post(url_upload, data={'uid': uid}, files=files)
    print(req.text)


def file_list():
    res = requests.get(url_file_list, params={'uid': uid})
    return res.json()


def download():
    files = file_list()
    print(files)

    for file in files:
        res = requests.get('http://192.168.1.102' + file['url'], params={'uid': uid})

        output = io.FileIO('/home/finalize/Desktop/download/' + file['name'], 'w')
        output.write(res.content)
        output.close()
