#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from app import *
from models import *
from views import *

if __name__ == '__main__':
    db.database.create_tables([User, File], safe=True)
    app.run()
