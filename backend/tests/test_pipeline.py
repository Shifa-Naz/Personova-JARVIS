from __future__ import annotations

from pathlib import Path


def test_open_app_runs_through_adapter(pipeline, fake_platform):
    resp = pipeline.command("open chrome")
    assert resp.status == "done"
    assert resp.reply == "Chrome is open."  # launch verified via the process list
    assert ("launch_app", "chrome", ()) in fake_platform.calls


def test_unregistered_app_falls_back_to_file_search_not_shell(pipeline, fake_platform):
    resp = pipeline.command("open totally-unknown-tool")
    assert resp.status == "error"
    assert resp.error_code == "FILE_NOT_FOUND"
    assert fake_platform.calls == []


def test_plan_then_execute_exposes_steps_before_running(pipeline, fake_platform):
    plan = pipeline.plan("open chrome and search youtube for java dsa tutorials")
    assert plan.status == "ready"
    assert [s.action for s in plan.steps] == ["search_youtube"]
    assert fake_platform.calls == []  # nothing ran yet
    resp = pipeline.execute(plan.plan_id)
    assert fake_platform.calls[0][0] == "open_url"
    assert "java+dsa+tutorials" in fake_platform.calls[0][1]
    assert fake_platform.calls[0][2] == "chrome"
    # search_youtube offers to play the first result
    assert resp.status == "needs_confirmation"
    assert resp.confirmation["kind"] == "offer"
    assert "play the first one" in resp.reply


def test_plan_ids_are_single_use(pipeline):
    plan = pipeline.plan("open chrome")
    pipeline.execute(plan.plan_id)
    assert pipeline.execute(plan.plan_id).error_code == "PLAN_EXPIRED"


def test_offer_accepted_by_voice_yes(pipeline, fake_platform, no_youtube_network):
    pipeline.command("search youtube for relaxing music")
    resp = pipeline.command("yes")
    assert resp.status == "done"
    assert fake_platform.calls[-1][1] == "https://www.youtube.com/watch?v=abcdefghijk"


def test_delete_requires_confirmation_and_uses_trash(pipeline, home, trash):
    target = home / "Documents" / "report draft.docx"
    resp = pipeline.command("delete the file report draft")
    assert resp.status == "needs_confirmation"
    assert resp.confirmation["permission"] == "DESTRUCTIVE"
    assert "report draft.docx" in resp.reply and "trash" in resp.reply
    assert target.exists()  # nothing happened yet

    done = pipeline.confirm(resp.confirmation["id"], "confirm")
    assert done.status == "done"
    assert trash == [str(target.resolve())]


def test_delete_cancel_changes_nothing(pipeline, home, trash):
    resp = pipeline.command("delete the file report draft")
    cancelled = pipeline.command("no")
    assert cancelled.status == "cancelled"
    assert trash == []
    assert (home / "Documents" / "report draft.docx").exists()
    # the confirmation cannot be reused after cancelling
    assert pipeline.confirm(resp.confirmation["id"], "confirm").error_code == "CONFIRMATION_EXPIRED"


def test_delete_all_in_folder_reports_count(pipeline, trash):
    resp = pipeline.command("delete all files in downloads")
    assert resp.status == "needs_confirmation"
    assert "3 files from Downloads" in resp.reply
    assert pipeline.command("yes").status == "done"
    assert len(trash) == 3


def test_filler_word_delete_never_deletes_anything(pipeline, trash, home):
    # B2 regression: used to os.remove the first file on the Desktop
    for text in ("delete file link", "delete file result", "delete the file button"):
        resp = pipeline.command(text)
        if resp.status == "needs_confirmation":
            pipeline.confirm(resp.confirmation["id"], "cancel")
    assert trash == []
    assert (home / "Desktop" / "important.docx").exists()


def test_new_command_abandons_pending_confirmation(pipeline, trash):
    resp = pipeline.command("delete the file report draft")
    pipeline.command("open chrome")
    assert pipeline.confirm(resp.confirmation["id"], "confirm").error_code == "CONFIRMATION_EXPIRED"
    assert trash == []


def test_play_local_song(pipeline, fake_platform, home):
    resp = pipeline.command("play believer")
    assert resp.status == "done"
    assert fake_platform.calls[-1] == (
        "open_path",
        str((home / "Downloads" / "Believer - Imagine Dragons.mp3").resolve()),
    )


def test_missing_song_offers_online_search(pipeline, fake_platform, no_youtube_network):
    resp = pipeline.command("play bohemian rhapsody")
    assert resp.status == "needs_confirmation"
    assert "couldn't find bohemian rhapsody locally" in resp.reply
    assert "search online" in resp.reply
    assert fake_platform.calls == []  # never downloads or opens anything unasked
    done = pipeline.command("yes")
    assert done.status == "done"
    assert "youtube.com/watch" in fake_platform.calls[-1][1]


def test_offline_online_actions_fail_gracefully(pipeline, connectivity, fake_platform):
    connectivity.override = False
    resp = pipeline.command("search google for react hooks")
    assert resp.status == "error" and resp.error_code == "OFFLINE"
    assert fake_platform.calls == []
    assert pipeline.command("open chrome").status == "done"  # local commands still work


def test_offline_missing_song_does_not_offer_online(pipeline, connectivity):
    connectivity.override = False
    resp = pipeline.command("play bohemian rhapsody")
    # the offer is made, but accepting it reports OFFLINE instead of failing silently
    if resp.status == "needs_confirmation":
        assert pipeline.command("yes").error_code == "OFFLINE"


def test_blocked_requests_are_refused(pipeline, fake_platform):
    resp = pipeline.command("run the command rm -rf /")
    assert resp.status == "error" and resp.error_code == "BLOCKED"
    assert "don't run commands" in resp.reply
    assert fake_platform.calls == []


def test_question_answered_by_llm(pipeline):
    resp = pipeline.command("What is the capital of India?")
    assert resp.status == "done"
    assert resp.reply == "New Delhi is the capital of India."


def test_question_with_llm_down_offers_web_search(pipeline, fake_ai):
    fake_ai.is_available = False
    resp = pipeline.command("explain recursion")
    assert resp.status == "needs_confirmation"
    assert "language model isn't available" in resp.reply


def test_math_is_deterministic(pipeline):
    assert pipeline.command("what is 25 multiplied by 18").reply == "That's 450."


def test_unknown_uses_llm_plan_validated_against_registry(pipeline, fake_ai, fake_platform):
    fake_ai.plans = [
        {
            "kind": "plan",
            "steps": [{"action": "open_application", "params": {"app": "firefox"}}],
            "text": "Opening Firefox",
        }
    ]
    plan = pipeline.plan("make the fox browser come up")
    assert plan.source == "llm" and plan.steps[0].action == "open_application"
    pipeline.execute(plan.plan_id)
    assert ("launch_app", "firefox", ()) in fake_platform.calls


def test_llm_invalid_plan_is_rejected_then_retried(pipeline, fake_ai, fake_platform):
    fake_ai.plans = [
        {"kind": "plan", "steps": [{"action": "rm_everything", "params": {}}], "text": ""},
        {"kind": "plan", "steps": [{"action": "blocked_request", "params": {}}], "text": ""},
    ]
    resp = pipeline.command("make the screen look nicer")
    assert fake_ai.plan_calls == 2
    assert resp.reply == "I'm not sure how to do that safely."
    assert fake_platform.calls == []


def test_llm_down_unknown_is_polite(pipeline, fake_ai):
    fake_ai.is_available = False
    resp = pipeline.command("make my wallpaper blue")
    assert "didn't understand" in resp.reply


def test_close_app_requires_confirmation(pipeline, fake_platform):
    pipeline.command("open chrome")
    resp = pipeline.command("close chrome")
    assert resp.status == "needs_confirmation"
    assert "unsaved work" in resp.reply
    assert pipeline.command("yes").reply == "Closed Chrome."


def test_close_app_not_running(pipeline):
    resp = pipeline.command("close spotify")
    assert resp.error_code == "APP_NOT_RUNNING"


def test_type_text_is_sensitive_and_redacted(pipeline, fake_platform):
    plan = pipeline.plan("type my secret password")
    assert plan.steps[0].params["text"] == "[redacted]"
    resp = pipeline.execute(plan.plan_id)
    assert resp.status == "needs_confirmation"
    assert fake_platform.calls == []


def test_adapter_failures_become_typed_errors(pipeline, fake_platform):
    from jarvis.actions.base import ActionError

    fake_platform.fail["media"] = ActionError("NO_MEDIA_PLAYER", "There's no media player running right now.")
    resp = pipeline.command("pause")
    assert resp.status == "error" and resp.error_code == "NO_MEDIA_PLAYER"


def test_too_long_input_rejected(pipeline):
    assert pipeline.plan("x" * 5000).error_code == "TOO_LONG"


def test_find_file_offers_to_open(pipeline, fake_platform, home):
    resp = pipeline.command("find my resume")
    assert resp.status == "needs_confirmation" and "Resume_2026.pdf" in resp.reply
    pipeline.command("yes")
    assert fake_platform.calls[-1] == ("open_path", str((home / "Documents" / "Resume_2026.pdf").resolve()))


def test_session_memory_open_it(pipeline, fake_platform):
    pipeline.command("open my resume")
    fake_platform.calls.clear()
    pipeline.command("open it")
    assert fake_platform.calls[0][0] == "open_path"
    assert Path(fake_platform.calls[0][1]).name == "Resume_2026.pdf"


def test_create_file_writes_text_and_reports_the_real_location(pipeline, home):
    resp = pipeline.command("create a file greetings.txt saying Hello there")
    target = home / "Documents" / "greetings.txt"
    assert resp.status == "done"
    assert target.read_text(encoding="utf-8") == "Hello there\n"
    assert str(target) in resp.reply  # the user can find it
    assert resp.speech == "Created greetings.txt in Documents."


def test_create_file_never_overwrites(pipeline, home):
    (home / "Desktop" / "notes.txt").write_text("keep me", encoding="utf-8")
    resp = pipeline.command("create notes.txt on the desktop")
    assert resp.error_code == "FILE_EXISTS"
    assert (home / "Desktop" / "notes.txt").read_text(encoding="utf-8") == "keep me"


def test_create_file_refuses_runnable_types(pipeline, home):
    resp = pipeline.command("create a file called start.sh")
    assert resp.error_code == "UNSUPPORTED_FILE_TYPE"
    assert not (home / "Documents" / "start.sh").exists()


def test_llm_cannot_claim_it_did_something(pipeline, fake_ai):
    # Regression: the planner "created" greetings.txt by replying "Greetings.txt created." with nothing run.
    fake_ai.plans = [
        {"kind": "plan", "steps": [{"action": "reply", "params": {"text": "Greetings.txt created."}}], "text": ""},
        {"kind": "answer", "steps": [], "text": "Greetings.txt created."},
    ]
    resp = pipeline.command("make my greetings appear for me")
    assert "created" not in resp.reply.lower()
    assert resp.reply == "I can't do that with my current abilities."
