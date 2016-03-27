#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask
from playhouse.flask_utils import FlaskDB
import getpass

if getpass.getuser() == 'finalize':  # local  environment
    UPLOAD_FOLDER = '/home/finalize/Workspace/pycharm/biu/files'
else:
    UPLOAD_FOLDER = '/srv/www/biu/files'  # in remote server

ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'zip', 'rar', 'rmvb'}
SECRET_KEY = '6+WyIHq+lAFE8FzT4kGYl3xM+Qia1+yYy3K0wRfMblE='

DATABASE = {
    'name': 'biu',
    'user': 'root',
    'passwd': '19961020',
    'host': 'localhost',
    'port': 3306,
    'engine': 'playhouse.pool.PooledMySQLDatabase',
    'max_connections': 32,
    'stale_timeout': 10,
}

app = Flask(__name__)
app.config.from_object(__name__)

app.debug = True

db = FlaskDB(app)
