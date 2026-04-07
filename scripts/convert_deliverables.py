"""Convert JSON deliverable files to readable markdown."""
import json
import os
import sys


def json_to_md(obj, depth=0):
    if depth >= 6:
        return str(obj)
    h = "#" * min(depth + 2, 6)
    if isinstance(obj, dict):
        lines = []
        for k, v in obj.items():
            if k in ("agent_id", "status", "confidence", "version", "date"):
                continue
            label = k.replace("_", " ").title()
            if isinstance(v, dict):
                lines.append("{} {}".format(h, label))
                lines.append("")
                lines.append(json_to_md(v, depth + 1))
                lines.append("")
            elif isinstance(v, list):
                lines.append("{} {}".format(h, label))
                lines.append("")
                for item in v:
                    if isinstance(item, dict):
                        parts = [
                            "{}: {}".format(ik, iv)
                            for ik, iv in item.items()
                            if not isinstance(iv, (dict, list))
                        ]
                        lines.append("- " + "; ".join(parts))
                    else:
                        lines.append("- {}".format(item))
                lines.append("")
            else:
                lines.append("**{}**: {}".format(label, v))
        return "\n".join(lines)
    elif isinstance(obj, list):
        return "\n".join("- {}".format(item) for item in obj)
    return str(obj)


def repair_json(s):
    opens = 0
    brackets = 0
    in_string = False
    escape = False
    for c in s:
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            opens += 1
        elif c == "}":
            opens -= 1
        elif c == "[":
            brackets += 1
        elif c == "]":
            brackets -= 1
    s = s.rstrip()
    # Close open string
    if in_string:
        s += '"'
    # Remove trailing punctuation
    while s and s[-1] in (",", ":"):
        s = s[:-1].rstrip()
    if brackets > 0:
        s += "]" * brackets
    if opens > 0:
        s += "}" * opens
    return s


base = "/root/ag.flow/projects/performances-trainer/team1/main/1:discovery"
for agent in ["Architect", "ux_designer"]:
    fpath = os.path.join(base, agent, "response.md")
    if not os.path.isfile(fpath):
        print("SKIP", fpath)
        continue
    content = open(fpath, encoding="utf-8").read()
    # Skip already-converted files (no JSON block)
    if '```json' not in content and '"deliverables"' not in content:
        print("ALREADY MD", fpath)
        continue
    idx = content.find("{")
    if idx < 0:
        print("NO {", fpath)
        continue
    json_str = content[idx:]
    # Try to parse, repair if needed
    for attempt in range(3):
        try:
            data = json.loads(json_str)
            break
        except json.JSONDecodeError as e:
            if attempt == 0:
                json_str = repair_json(json_str)
            elif attempt == 1:
                # Truncate at last valid line
                lines = json_str.split("\n")
                while lines:
                    test = repair_json("\n".join(lines))
                    try:
                        data = json.loads(test)
                        json_str = test
                        break
                    except json.JSONDecodeError:
                        lines.pop()
                else:
                    print("BROKEN", fpath, str(e)[:80])
                    break
                break
            else:
                print("BROKEN", fpath, str(e)[:80])
                break
    else:
        continue

    deliverables = data.get("deliverables", {})
    if not deliverables:
        print("NO DELIVERABLES", fpath)
        continue
    d_key = list(deliverables.keys())[0]
    d_val = deliverables[d_key]
    title = d_val.get("title") or d_val.get("titre", d_key)
    md = "# {}\n\n{}".format(title, json_to_md(d_val, depth=1))
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(md)
    print("OK", fpath, len(md), "chars")
