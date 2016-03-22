#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import functools
import hashlib
import json
import os
import io
from time import sleep
from urllib.parse import quote

import qrcode
import uuid

from flask import request, render_template, make_response, session, send_file, url_for

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

    print(uid)

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

    interval = 0.5  # 等待时间间隔
    wait_count = 0  # 检查次数
    while True:
        if wait_count == 20:
            return text_as_js(AJAX_RETRY)

        query = User.select().where(User.uid == session['uid'])
        if query.count() == 0:
            return STATUS_403
        else:
            user = query[0]
            if user.state == STATE_OFFLINE:
                wait_count += 1
                sleep(interval)
            elif user.state == STATE_UPLOAD:
                return text_as_js(AJAX_UPLOAD)
            else:
                return text_as_js(AJAX_DOWNLOAD)


@app.route('/upload', methods=['GET', 'POST'])
@session_required
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
        return '200'  # TODO 界面，或者用AJAX上传
    else:
        return render_template('upload.html')


@app.route('/download')
@session_required
def download():
    """
    浏览器下载文件页面。
    :return:
    """
    return render_template('download.html')


@app.route('/file/<hashcode>')
@session_required
def file(hashcode):
    """
    下载指定文件，根据uid以及文件的hashcode返回对应的文件
    :param hashcode:
    :return:
    """
    return down_file(session['uid'], hashcode)


@app.route('/list')
@session_required
def file_list():
    uid = session['uid']
    interval = 0.5
    retry_count = 0

    while True:
        if retry_count == 20:
            return json.dumps([])

        files_json = get_file_list(uid)
        if len(json.loads(files_json)) == 0:
            retry_count += 1
            sleep(interval)
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

    File.update(used=True).where(File.uid == uid).execute()

    query = User.update(state=state).where(User.uid == uid)
    if query.execute() == 0:
        return STATUS_403  # uid 不合法
    else:
        return '200'


@app.route('/client/upload', methods=['POST'])
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


@app.route('/client/file/<hashcode>')
@uid_required('GET')
def android_file(hashcode):
    """
    android下载指定文件
    :param hashcode:
    :return:
    """
    uid = request.args.get('uid')
    return down_file(uid, hashcode)


@app.route('/client/list')
@uid_required('GET')
def android_file_list():
    """
    Android 获取可下载的文件列表
    :return:
    """
    uid = request.args.get('uid')
    interval = 0.5
    retry_count = 0

    while True:
        if retry_count == 20:
            return json.dumps([])

        files_json = get_file_list(uid, android=True)
        if len(json.loads(files_json)) == 0:
            retry_count += 1
            sleep(interval)
        else:
            return files_json


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
        url = url_for('file', hashcode=file.hash) if not android else url_for('android_file', hashcode=file.hash)
        file_list.append(
            {'name': file.name, 'url': url, 'size': get_file_size(uid, file.name)})

    return json.dumps(file_list)


def store_files(uid, files):
    """
    存储文件
    :param uid:
    :param files:
    :return:
    """
    File.update(used=True).where(File.used == False).execute()  # 更改状态

    for file in files:
        file.save(get_file_path(uid, file.filename))

        sha1 = hashlib.sha1()
        sha1.update((uid + file.filename).encode('utf-8'))
        File.create(uid=uid, name=file.filename, hash=sha1.hexdigest(), used=False)


def down_file(uid, hashcode):
    """
    下载指定文件
    :param uid:
    :param hashcode:
    :return:
    """
    query = File.select().where(File.uid == uid, File.hash == hashcode)
    if len(query) == 0:
        return STATUS_403

    name = query[0].name
    file_path = get_file_path(uid, name)

    # F*ck 遇到坑了，直接send_file as attachment时，使用Unicode字符会出现编码问题，进而返回为空
    # see https://github.com/mitsuhiko/flask/issues/1286
    response = make_response(send_file(file_path))
    response.headers["Content-Disposition"] = \
        "attachment; " \
        "filenane={ascii_filename};" \
        "filename*=UTF-8''{utf_filename}".format(
            ascii_filename="book.pdf",
            utf_filename=quote(name)
        )

    return response
