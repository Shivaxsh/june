#!/usr/bin/env python3
"""PCM IPC regression checks; never requests microphone access.
Usage: python3 native/pcm-ipc-test.py /path/to/JuneAudio [--prepare-output]
The optional flag also starts the output-only graph and plays silent PCM.
"""
import base64
import json
import queue
import subprocess
import sys
import threading

process = subprocess.Popen([sys.argv[1]], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
messages = queue.Queue()
events = []
def read():
    for line in process.stdout:
        messages.put(json.loads(line))
threading.Thread(target=read, daemon=True).start()

def command(kind, job="segment", **fields):
    ack = f"ack-{command.sequence}"
    command.sequence += 1
    process.stdin.write(json.dumps(dict(type=kind, id=job, commandId=ack, **fields)) + "\n")
    process.stdin.flush()
    while True:
        message = messages.get(timeout=3)
        if message.get("type") == "result" and message.get("id") == ack:
            return message
        events.append(message)
command.sequence = 0

def start(job="segment", **extra):
    fields = dict(ownerId="owner", requestId="request", text="June PCM validation.", voiceId="saved-june", rate=1.0)
    fields.update(extra)
    return command("pcm-start", job, **fields)

def ok(reply):
    assert reply.get("accepted") is True and "error" not in reply, reply

def bad(reply):
    assert "error" in reply and not reply.get("accepted"), reply

try:
    ready = messages.get(timeout=5)
    assert ready["type"] == "ready"
    if "--prepare-output" in sys.argv:
        # Standard commands correlate with id even if commandId is present.
        process.stdin.write(json.dumps(dict(type="prepare-output", id="output", commandId="ignored")) + "\n")
        process.stdin.flush()
        reply = messages.get(timeout=5)
        assert reply == dict(type="result", id="output", prepared=True), reply
        ok(start("silent-playback", voiceSessionId="session", turnId=3))
        ok(command("pcm-chunk", "silent-playback", audio=base64.b64encode(bytes(8192)).decode()))
        ok(command("pcm-end", "silent-playback"))
        while not any(e.get("id") == "silent-playback" and e.get("phase") == "end" for e in events):
            event = messages.get(timeout=5)
            assert event.get("phase") not in ("error", "cancelled"), event
            events.append(event)
        played = [e for e in events if e.get("id") == "silent-playback"]
        assert any(e.get("phase") == "start" for e in played), played
        process.stdin.write(json.dumps(dict(type="status", id="after-output")) + "\n")
        process.stdin.flush()
        status = messages.get(timeout=5)
        assert status["id"] == "after-output" and status["capturing"] is False, status
        assert status["permission"] == ready["permission"], status
    ok(start(voiceSessionId="session", turnId=3))
    ok(command("pcm-chunk", audio=base64.b64encode(b"\x01").decode()))
    bad(command("pcm-end"))  # Incomplete int16 sample cancels the job.
    phases = [e for e in events if e.get("id") == "segment"]
    assert [e["phase"] for e in phases] == ["error", "cancelled"], phases
    assert all(e.get("voiceSessionId") == "session" and e.get("turnId") == 3 for e in phases)
    bad(command("pcm-chunk", audio="AA=="))  # Stale ID.
    ok(start("oversized"))
    bad(command("pcm-chunk", "oversized", audio=base64.b64encode(bytes(8193)).decode()))
    ok(start("invalid-base64"))
    bad(command("pcm-chunk", "invalid-base64", audio="%%%"))
    ok(start("cancelled"))
    process.stdin.write(json.dumps(dict(type="cancel", id="cancelled")) + "\n")
    process.stdin.flush()
    bad(command("pcm-end", "cancelled"))
    ok(start("duplicate"))
    bad(start("duplicate"))
    bad(command("pcm-end", "duplicate"))
    bad(start("mismatch", segmentId="different"))
    bad(start("bad-turn", turnId=True))
    bad(start("negative-turn", turnId=-1))
    ok(start("empty"))
    bad(command("pcm-end", "empty"))
    for job in ("a", "b", "c"):
        ok(start(job))
    bad(start("d"))
    process.stdin.write(json.dumps(dict(type="stop", ownerId="owner", requestId="request")) + "\n")
    process.stdin.flush()
    bad(command("pcm-end", "a"))
    ok(start("heartbeat"))
    # No heartbeat: queued PCM ownership must expire without starting any device.
    import time
    time.sleep(3.3)
    bad(command("pcm-end", "heartbeat"))
    print("PCM IPC checks passed (microphone unopened; output preparation: " + str("--prepare-output" in sys.argv) + ").")
finally:
    process.stdin.close()
    process.wait(timeout=5)
