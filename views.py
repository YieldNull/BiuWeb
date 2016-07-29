#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import functools
import hashlib
import json
import os
import io
from time import sleep

import re
import qrcode
import uuid
import mimetypes

import urllib.parse

from flask import request, render_template, make_response, session, url_for, redirect
from app import *
from models import *

STATE_OFFLINE = 0
STATE_UPLOAD = 1
STATE_DOWNLOAD = 2

STATUS_403 = ('403 Forbidden', 403)  # 非法请求则返回403

# HTTP 长连接中的处理结果
# 以Javascript 文件形式返回给浏览器，浏览器直接执行
AJAX_RETRY = '$.getScript("/login");'
AJAX_UPLOAD = 'window.location = "/upload";'
AJAX_DOWNLOAD = 'window.location = "/download";'

POLLING_INTERVAL = 0.5
RETRY_THRESHOLD = 100


def session_required(fn):
    """
    浏览器客户端需要启用Cookie，并且`uid`必须存在于session中
    :param fn:
    :return:
    """

    @functools.wraps(fn)
    def inner(*args, **kwargs):
        if session.get('uid'):
            return fn(*args, **kwargs)
        return STATUS_403

    return inner


def login_required(fn):
    """
    浏览器客户端需要启用Cookie，并且`uid`必须存在于session中
    :param fn:
    :return:
    """

    @functools.wraps(fn)
    def inner(*args, **kwargs):
        uid = session.get('uid')
        if uid is None:
            return STATUS_403

        query = User.select().where(User.uid == uid)
        if query.count() == 0:
            return redirect(url_for('index'))

        user = query[0]
        if user.state == STATE_OFFLINE:
            return redirect(url_for('index'))

        return fn(*args, **kwargs)

    return inner


def uid_required(method):
    """
    Android客户端发起请求时，必须要附带`uid`参数
    :param method:  请求方式
    :return:
    """

    def wrapper(fn):
        @functools.wraps(fn)
        def inner(*args, **kwargs):
            if (method == 'POST' and request.form.get('uid') is None) or \
                    (method == 'GET' and request.args.get('uid') is None):
                return STATUS_403
            return fn(*args, **kwargs)

        return inner

    return wrapper


@app.route('/qrcode')
@session_required
def gen_qrcode():
    """
    二维码
    :return:
    """

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,
        border=4,
    )

    qr.add_data(session['uid'])
    qr.make(fit=True)
    img = qr.make_image()

    output = io.BytesIO()
    img.save(output)

    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'image/jpeg'
    return response


@app.route('/')
def index():
    """
    主页，若session中不存在`uid`,则创建。
    将数据库中uid对应的User状态改为offline
    :return:
    """
    if session.get('uid') is None:
        uid = str(uuid.uuid1())
        session['uid'] = uid
    else:
        uid = session['uid']

    # 更改状态
    query = User.select().where(User.uid == uid)
    if query.count() == 0:
        User.create(uid=uid, state=STATE_OFFLINE)
    else:
        User.update(state=STATE_OFFLINE).where(User.uid == uid).execute()

    return render_template('index.html')


@app.route('/login')
@session_required
def login():
    """
    浏览器AJAX检查是否与手机建立连接

    每隔一段时间读取以下数据库中User的状态，若为offline则继续等待
    否则根据状态返回相应的js文件，使浏览器进行跳转
    :return:
    """

    def text_as_js(text):
        response = make_response(text)
        response.headers['content-type'] = 'text/javascript'
        return response

    wait_count = 0  # 检查次数
    while True:
        if wait_count == RETRY_THRESHOLD:
            return text_as_js(AJAX_RETRY)

        query = User.select().where(User.uid == session['uid'])
        if query.count() == 0:
            return STATUS_403
        else:
            user = query[0]
            if user.state == STATE_OFFLINE:
                wait_count += 1
                sleep(POLLING_INTERVAL)
            elif user.state == STATE_UPLOAD:
                return text_as_js(AJAX_UPLOAD)
            else:
                return text_as_js(AJAX_DOWNLOAD)


@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    """
    浏览器上传文件
    :return:
    """
    if request.method == 'POST':
        files = request.files.getlist("file")
        if len(files) == 0:
            return STATUS_403

        uid = session['uid']
        store_files(uid, files)
        return '200 OK'  # redirect(url_for('upload'))  # TODO 界面，或者用AJAX上传
    else:
        return render_template('upload.html')


@app.route('/download')
@login_required
def download():
    """
    浏览器下载文件页面。
    :return:
    """
    return render_template('download.html')


@app.route('/download/<hashcode>')
@login_required
def file(hashcode):
    """
    下载指定文件，根据uid以及文件的hashcode返回对应的文件
    :param hashcode:
    :return:
    """
    return down_file(session['uid'], hashcode)


@app.route('/filelist')
@login_required
def file_list():
    uid = session['uid']
    retry_count = 0

    while True:
        if retry_count == RETRY_THRESHOLD:
            return json.dumps([])

        files_json = get_file_list(uid)
        if len(json.loads(files_json)) == 0:
            retry_count += 1
            sleep(POLLING_INTERVAL)
        else:
            return files_json


@app.route('/bind')
@uid_required('GET')
def bind():
    """
    Android客户端与浏览器配对。
    Android扫码后将uid以及操作（what)发送到服务器
    服务器根据what更改User对应的state，在`login`中引导浏览器跳转
    :return:
    """
    uid = request.args.get('uid')
    what = request.args.get('what')  # Android客户端想做什么

    if what is None:
        return STATUS_403

    # 网页端与Android端相反
    state = STATE_UPLOAD if what == 'download' else STATE_DOWNLOAD

    query = User.update(state=state).where(User.uid == uid)
    if query.execute() == 0:
        return STATUS_403  # uid 不合法
    else:
        return '200'


@app.route('/api/upload', methods=['POST'])
@uid_required('POST')
def android_upload():
    """
    Android上传
    :return:
    """
    files = request.files.getlist("files")

    if len(files) == 0:
        return STATUS_403

    store_files(request.form['uid'], files)
    return '200'


@app.route('/api/download/<hashcode>')
@uid_required('GET')
def android_file(hashcode):
    """
    android下载指定文件
    :param hashcode:
    :return:
    """
    uid = request.args.get('uid')
    return down_file(uid, hashcode)


@app.route('/api/filelist')
@uid_required('GET')
def android_file_list():
    """
    Android 获取可下载的文件列表
    :return:
    """
    uid = request.args.get('uid')
    retry_count = 0

    while True:
        if retry_count == RETRY_THRESHOLD:
            return json.dumps([])

        files_json = get_file_list(uid, android=True)
        if len(json.loads(files_json)) == 0:
            retry_count += 1
            sleep(POLLING_INTERVAL)
        else:
            return files_json


@app.route('/icon/<name>')
def file_icon(name):
    if not mimetypes.inited:
        mimetypes.init()

    mime, encoding = mimetypes.guess_type(name)
    filename = 'icon/{:s}.svg'.format(mime.replace('/', '-'))

    if os.path.exists('static/' + filename):
        return redirect(url_for('static', filename=filename))
    else:
        return redirect(url_for('static', filename='file.svg'))


# 以下方法Android 与浏览器共用，区别在于二者获取uid的方式不同
# Android 从 param 或 form中获取
# 浏览器从session中获取

def get_file_path(uid, filename):
    folder = os.path.join(app.config['UPLOAD_FOLDER'], uid)
    if not os.path.exists(folder):
        os.mkdir(folder)
    return os.path.join(folder, filename)


def get_file_size(uid, filename):
    """
    获取文件size
    :param uid:
    :param filename:
    :return:
    """
    path = get_file_path(uid, filename)
    return os.path.getsize(path)


def get_file_list(uid, android=False):
    """
    获取可下载的文件列表
    :param android:
    :param uid:
    :return:
    """
    query = File.select().where(File.uid == uid, File.used == False)

    file_list = []
    for file in query:
        url = url_for('file', hashcode=file.hashcode) if not android else url_for('android_file',
                                                                                  hashcode=file.hashcode)
        file_list.append({
            'uid': file.uid.uid,  # 你大爷的，没叫你自动关联啊
            'name': file.name,
            'uri': url,
            'size': get_file_size(uid, file.name)})

        # TODO 这里有一个问题啊，当用户在浏览器下载文件后，又刷新页面，结果就给刷没了。。。。
        File.update(used=True).where(File.uid == uid, File.hashcode == file.hashcode).execute()  # 更改状态

    return json.dumps(file_list)


def store_files(uid, files):
    """
    存储文件
    :param uid:
    :param files:
    :return:
    """
    for file in files:
        name = urllib.parse.unquote(file.filename)

        name = re.sub('[\\\/|:?*<>+"]', '_', name)  # 将文件名中的这些字符替换掉

        if os.path.exists(get_file_path(uid, name)):
            name = version_filename(uid, name)  # 重命名 files中的相同文件名，不然就覆盖了

        file.save(get_file_path(uid, name))

        sha1 = hashlib.sha1()
        sha1.update((uid + name + str(datetime.datetime.now())).encode('utf-8'))

        File.create(uid=uid, name=name,
                    hashcode=sha1.hexdigest(), used=False,
                    timestamp=datetime.datetime.now())


def version_filename(uid, name):
    """
    重命名已存在的文件，在后面加版本号 "(\d)"
    :param uid:
    :param name:
    :return:
    """
    pos = name.find('.')
    pos = pos if pos > 0 else len(name)

    version = 1
    name = name[:pos] + '({:d})'.format(version) + name[pos:]
    vname = list(name)

    while os.path.exists(get_file_path(uid, "".join(vname))):
        version += 1
        vname[pos + 1] = str(version)

    return "".join(vname)


def down_file(uid, hashcode):
    """
    下载指定文件
    :param uid:
    :param hashcode:
    :return:
    """
    query = File.select().where(File.uid == uid, File.hashcode == hashcode)
    if len(query) == 0:
        return STATUS_403

    name = query[0].name

    File.update(used=True).where(File.uid == uid, File.hashcode == hashcode).execute()

    return redirect('/files/{:s}/{:s}'.format(uid, name))  # 交给 nginx处理
