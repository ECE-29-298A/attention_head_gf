#!/usr/bin/env python3
"""Run ll_synth_b.sh jobs from a queue: at most 2 of mine at once, and none while a foreign
LibreLane container (another agent's harden or synthesis) is running. Appends to synth/results.tsv.
Usage: synth_queue.py <tag>[@RTLDIR] ...   (override file synth/ovr/<tag-before-'+'>.json)"""
import os, subprocess, sys, time
B = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(os.path.dirname(B), "baseline", "original_rtl")
ENV = "source /Users/samuelzhang/ttsetup/env.sh >/dev/null 2>&1; "
def n_ll():
    out = subprocess.run(["bash", "-lc", ENV + "docker ps --format '{{.Image}}'"],
                         capture_output=True, text=True).stdout.split()
    return sum("librelane" in l for l in out)
jobs = [a.split("@") for a in sys.argv[1:]]
running = {}
log = open(os.path.join(B, "synth", "results.tsv"), "a")
while jobs or running:
    for t, p in list(running.items()):
        if p.poll() is not None:
            out = p.stdout.read().strip()
            line = f"{t}\t{p.returncode}\t{out.splitlines()[-1] if out else ''}"
            print(line, flush=True); log.write(line + "\n"); log.flush()
            del running[t]
    if jobs and len(running) < 2 and n_ll() <= len(running):
        tag, *rtl = jobs.pop(0)
        rtl = rtl[0] if rtl else GOLD
        ovr = os.path.join(B, "synth", "ovr", tag.split("+")[0] + ".json")
        running[tag] = subprocess.Popen(["bash", os.path.join(B, "scripts", "ll_synth_b.sh"), rtl, tag, ovr],
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        time.sleep(10)
        continue
    time.sleep(3)
