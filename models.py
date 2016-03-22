#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from peewee import IntegerField, CharField, ForeignKeyField, BooleanField

from app import db


class User(db.Model):
    uid = CharField(primary_key=True)
    state = IntegerField()  # 相对于浏览器而言，STATE_OFFLINE, STATE_UPLOAD, STATE_DOWNLOAD


class File(db.Model):
    uid = ForeignKeyField(User)
    name = CharField()
    used = BooleanField(default=False)
    hash = CharField()  # uid+name hash
