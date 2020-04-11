# -*- coding: utf8 -*-
import os


def get_xpack_templates_dir(path):
    paths = []
    walk_path = os.path.join(path, 'apps')
    for dirpath, dirnames, filenames in os.walk(walk_path):
        if 'template' in dirpath:
            paths.append(dirpath)
    return paths
