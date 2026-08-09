def split_steps(text):

    text = text.lower()

    separators = [
        "and",
        "then",
        ",",
    ]

    steps = [text]

    for s in separators:

        new_steps = []

        for step in steps:
            parts = step.split(s)

            for p in parts:
                p = p.strip()

                if p:
                    new_steps.append(p)

        steps = new_steps

    return steps