import os
import subprocess
import shutil

SEARCH_FOLDERS = [
    os.path.expanduser("~/Desktop"),
    os.path.expanduser("~/Downloads"),
    os.path.expanduser("~/Documents"),
    os.path.expanduser("~/Pictures"),
    os.path.expanduser("~/Videos"),
]


def find_file(name):

    name = name.lower()

    for folder in SEARCH_FOLDERS:

        for root, dirs, files in os.walk(folder):

            for f in files:

                if name in f.lower():
                    return os.path.join(root, f)

    return None


def find_folder(name):

    name = name.lower()

    for folder in SEARCH_FOLDERS:

        for root, dirs, files in os.walk(folder):

            for d in dirs:

                if name in d.lower():
                    return os.path.join(root, d)

    return None


def open_file(name):

    path = find_file(name)

    if path:
        os.startfile(path)
        return True

    return False


def open_folder(name):

    path = find_folder(name)

    if path:
        subprocess.Popen(f'explorer "{path}"')
        return True

    return False


def delete_file(name):

    path = find_file(name)

    if path:
        os.remove(path)
        return True

    return False


def copy_file(name):

    path = find_file(name)

    if not path:
        return None

    return path


def move_file(name, dest_folder):

    src = find_file(name)

    dest = find_folder(dest_folder)

    if src and dest:

        filename = os.path.basename(src)

        new_path = os.path.join(dest, filename)

        shutil.move(src, new_path)

        return True

    return False