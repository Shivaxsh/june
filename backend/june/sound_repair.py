"""One fixed repair for a stuck Mac sound service: restart coreaudiod.

When macOS's sound service gets stuck, nothing on the Mac is audible (June, Music, system sounds)
although every app reports that it is playing. Only an administrator can restart the service, so
macOS itself asks for the person's password; June never sees or stores it. The command is fixed.
"""
import asyncio
from contextlib import suppress

OSASCRIPT = '/usr/bin/osascript'
SCRIPT = ('do shell script "/usr/bin/killall coreaudiod" with prompt '
          '"June needs to restart your Mac’s sound service to bring the sound back." with administrator privileges')


async def restart_sound_service(spawn=asyncio.create_subprocess_exec):
    """'restarted', 'cancelled' (the person closed the prompt) or 'failed'."""
    process = None
    try:
        process = await spawn(OSASCRIPT, '-e', SCRIPT, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        _, error = await asyncio.wait_for(process.communicate(), 150)
    except (OSError, TimeoutError):
        return 'failed'
    finally:
        if process is not None and process.returncode is None:
            process.kill()
            with suppress(ProcessLookupError): await process.wait()
    if process.returncode == 0:
        return 'restarted'
    return 'cancelled' if b'-128' in (error or b'') else 'failed'
