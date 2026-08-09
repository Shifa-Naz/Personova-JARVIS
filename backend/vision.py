import pyautogui
import pytesseract
import cv2
import numpy as np
import threading
import time

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

last_screen_text = ""
vision_running = False


def capture_screen():

    screenshot = pyautogui.screenshot()

    img = np.array(screenshot)

    img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    return img


def read_text(img):

    text = pytesseract.image_to_string(img)

    return text


def vision_loop():

    global last_screen_text
    global vision_running

    vision_running = True

    while vision_running:

        try:

            img = capture_screen()

            text = read_text(img)

            last_screen_text = text

        except Exception as e:
            print("Vision error:", e)

        time.sleep(1)


def start_vision():

    t = threading.Thread(
        target=vision_loop,
        daemon=True
    )

    t.start()


def find_word_positions():

    screenshot = pyautogui.screenshot()

    img = np.array(screenshot)

    data = pytesseract.image_to_data(
        img,
        output_type=pytesseract.Output.DICT
    )

    results = []

    for i, txt in enumerate(data["text"]):

        if txt.strip() == "":
            continue

        x = data["left"][i]
        y = data["top"][i]
        w = data["width"][i]
        h = data["height"][i]

        results.append({
            "text": txt.lower(),
            "pos": (x + w // 2, y + h // 2)
        })

    return results


def click_text(word):

    word = word.lower()

    words = find_word_positions()

    # try exact
    for w in words:
        if word in w["text"]:
            pyautogui.click(w["pos"])
            return True

    # try split words
    parts = word.split()

    for p in parts:
        for w in words:
            if p in w["text"]:
                pyautogui.click(w["pos"])
                return True

    # try domain
    if ".com" in word:

        for w in words:
            if ".com" in w["text"]:
                pyautogui.click(w["pos"])
                return True

    return False


def click_first():

    w, h = pyautogui.size()

    pyautogui.click(w // 2, 300)


def click_second():

    w, h = pyautogui.size()

    pyautogui.click(w // 2, 400)