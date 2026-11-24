// June's helper signing identity. A private self-signed "June Local Code Signing" certificate in the login
// keychain gives every rebuilt helper the same designated requirement (identifier + certificate), so macOS keeps
// its permissions (Full Disk Access, Automation, Screen Recording, Microphone, Calendar) across rebuilds.
// Without that certificate, helpers are signed ad hoc as before (and macOS asks again after each rebuild).
import {execFileSync} from 'node:child_process';
export const CERTIFICATE = 'June Local Code Signing';
export function signingIdentity() {
  try {
    const listed = execFileSync('/usr/bin/security', ['find-identity', '-p', 'codesigning'], {encoding: 'utf8'});
    const found = listed.split('\n').map(line => line.match(/^\s*\d+\)\s+([0-9A-F]{40})\s+"([^"]+)"/)).find(m => m && m[2] === CERTIFICATE);
    if (found) return found[1];
  } catch {}
  console.warn(`No "${CERTIFICATE}" certificate: signing ad hoc, so macOS will ask for this helper's permissions again.`);
  return '-';
}
