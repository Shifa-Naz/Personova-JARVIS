from flask import Flask, request, jsonify
from flask_cors import CORS

from parser import parse_command
from step_splitter import split_steps
from planner import plan_steps
from command_handler import run_command
from brain import get_reply

from vision import start_vision


app = Flask(__name__)
CORS(app)

last_command = ""


@app.route("/")
def home():
    return "Jarvis backend running"


@app.route("/command", methods=["POST"])
def command():

    global last_command

    data = request.get_json()

    if not data:
        return jsonify({"reply": ""})

    raw = data.get("command", "")

    parsed = parse_command(raw)

    if parsed == "":
        return jsonify({"reply": ""})

    if parsed == last_command:
        return jsonify({"reply": ""})

    last_command = parsed

    steps = split_steps(parsed)

    actions = plan_steps(steps)

    print("Actions:", actions)

    reply = ""

    for act, value in actions:

        # -------- Conversation --------
        if act.startswith("chat "):

            text = act.replace("chat ", "", 1)

            reply = get_reply(text)

            continue

        # -------- Desktop Commands --------
        if value:
            cmd = f"{act} {value}"
        else:
            cmd = act

        print("Running:", cmd)

        r = run_command(cmd)

        if r:
            reply = r

    return jsonify({
        "reply": reply
    })


if __name__ == "__main__":

    start_vision()

    app.run(
        debug=True,
        use_reloader=False,
        threaded=True
    )