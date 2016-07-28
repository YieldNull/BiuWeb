#!/usr/bin/env python
# -*- coding: utf-8 -*-


"""


Created By YieldNull at 7/28/16
"""
import os
import shutil
from app import UPLOAD_FOLDER
from views import version_filename

from unittest import TestCase


class Test(TestCase):
    uid = "testuid"
    folder = os.path.join(UPLOAD_FOLDER, uid)

    filename = "file"
    file0 = os.path.join(folder, filename)
    file1 = os.path.join(folder, filename + '(1)')
    file2 = os.path.join(folder, filename + '(2)')

    def setUp(self):
        os.mkdir(self.folder)
        open(self.file0, 'w').close()
        open(self.file1, 'w').close()
        open(self.file2, 'w').close()

    def tearDown(self):
        shutil.rmtree(self.folder)

    def test_version_filename(self):
        self.assertEqual("file(3)", version_filename(self.uid, self.filename))
