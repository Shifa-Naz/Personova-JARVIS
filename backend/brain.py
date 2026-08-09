# brain.py

def get_reply(text):

    text = text.lower().strip()

    # Greetings
    if any(x in text for x in [
        "hello",
        "hi",
        "hey",
        "good morning",
        "good afternoon",
        "good evening"
    ]):
        return "Hello! How can I help you?"

    # How are you
    if "how are you" in text:
        return "I am doing great. How can I help you today?"

    # Name
    if "your name" in text or "who are you" in text:
        return "I am Jarvis, your personal AI desktop assistant."

    # Thanks
    if "thank" in text or "thanks" in text:
        return "You're welcome."

    # Help
    if "help" in text:
        return (
            "I can open applications, search the web, "
            "open files and folders, click buttons, "
            "type text, and much more."
        )

    # Bye
    if "bye" in text:
        return "Goodbye. Have a great day."

    # Unknown conversation
    return (
        "I'm still learning. "
        "I'll be able to answer that after my AI brain is upgraded."
    )