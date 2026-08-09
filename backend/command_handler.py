import os
import webbrowser
import pyautogui
import subprocess
import time

from vision import (
    click_text,
    click_first,
    click_second,
)

from file_control import (
    open_file,
    open_folder,
    delete_file,
    copy_file,
    move_file,
)

# -------- CONTEXT --------

last_search = ""
last_folder = ""
last_file = ""
last_copied = ""


def run_command(cmd):

    global last_search
    global last_folder
    global last_file
    global last_copied

    cmd = cmd.lower().strip()

    try:

        # ---------- CLICK FIRST ----------
        if "click first" in cmd:

            click_first()

            return "Click first"

        # ---------- CLICK SECOND ----------
        if "click second" in cmd:

            click_second()

            return "Click second"

        # ---------- CLICK WORD ----------
        if "click" in cmd:

            word = cmd.replace("click", "").strip()

            if word:

                ok = click_text(word)

                if ok:
                    return "Clicked " + word

            pyautogui.click()

            return "Click"

        # ---------- OPEN FILE ----------
        if "open file" in cmd:

            name = cmd.replace("open file", "").strip()

            ok = open_file(name)

            if ok:
                last_file = name
                return "Opening file"

            return "File not found"

        # ---------- OPEN FOLDER ----------
        if "open folder" in cmd:

            name = cmd.replace("open folder", "").strip()

            ok = open_folder(name)

            if ok:
                last_folder = name
                return "Opening folder"

            return "Folder not found"

        # ---------- DELETE FILE ----------
        if "delete file" in cmd:

            name = cmd.replace("delete file", "").strip()

            ok = delete_file(name)

            if ok:
                return "Deleted"

            return "File not found"

        # ---------- COPY FILE ----------
        if "copy file" in cmd:

            name = cmd.replace("copy file", "").strip()

            path = copy_file(name)

            if path:
                last_copied = path
                return "Copied"

            return "File not found"

        # ---------- MOVE FILE ----------
        if "move file" in cmd:

            parts = cmd.replace("move file", "").strip()

            if "to" in parts:

                name, dest = parts.split("to")

                ok = move_file(
                    name.strip(),
                    dest.strip()
                )

                if ok:
                    return "Moved"

            return "Move failed"

        # ---------- OPEN CHROME ----------
        if "open chrome" in cmd:

            webbrowser.open("https://google.com")

            time.sleep(2)

            return "Opening chrome"

        # ---------- SEARCH ----------
        if "search" in cmd:

            query = cmd.replace("search", "").strip()

            last_search = query

            pyautogui.hotkey("ctrl", "l")

            time.sleep(1)

            pyautogui.write(
                f"https://www.google.com/search?q={query}"
            )

            pyautogui.press("enter")

            return "Searching " + query

        # ---------- TYPE ----------
        if "type" in cmd:

            text = cmd.replace("type", "").strip()

            pyautogui.write(text)

            return "Typing"

        # ---------- SEND ----------
        if "send" in cmd:

            pyautogui.press("enter")

            return "Send"

        # ---------- SCROLL ----------
        if "scroll down" in cmd:

            pyautogui.scroll(-500)

        if "scroll up" in cmd:

            pyautogui.scroll(500)

        # ---------- DOWNLOADS ----------
        if "open downloads" in cmd:

            path = os.path.expanduser("~\\Downloads")

            subprocess.Popen(
                f'explorer "{path}"'
            )

            last_folder = "downloads"

            return "Opening downloads"

        return ""

    except Exception as e:

        print("Error:", e)

        return "error"