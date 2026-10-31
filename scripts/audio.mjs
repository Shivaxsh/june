// Build a private, ad-hoc signed Mac helper. No login agent or global install.
import {existsSync} from 'node:fs';
import {spawn} from 'node:child_process';
import {readFile,mkdir,writeFile,chmod,rename} from 'node:fs/promises';
import {join} from 'node:path';
import {homedir} from 'node:os';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
if(existsSync(join(root,'.env.local')))process.loadEnvFile(join(root,'.env.local'));
const pkg=JSON.parse(await readFile(join(root,'package.json'),'utf8'));
const home=process.env.JUNE_AUDIO_HOME || join(homedir(),'Library/Application Support/June/audio');
if(process.platform!=='darwin')throw Error('June Audio currently requires macOS. Browser push-to-talk remains available.');
const bundle=join(home,'JuneAudio.app'),contents=join(bundle,'Contents'),mac=join(contents,'MacOS');
await mkdir(mac,{recursive:true,mode:0o700});await chmod(home,0o700);
function run(binary,args){return new Promise((resolve,reject)=>{const child=spawn(binary,args,{cwd:root,stdio:'inherit'});child.on('error',reject);child.on('exit',(code,signal)=>code===0?resolve():reject(Error(`June Audio command failed (${code ?? signal}).`)));});}
await writeFile(join(contents,'Info.plist'),`<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><dict><key>CFBundleIdentifier</key><string>local.june.audio</string><key>CFBundleName</key><string>June Audio</string><key>CFBundleDisplayName</key><string>June Audio</string><key>CFBundleExecutable</key><string>JuneAudio</string><key>CFBundlePackageType</key><string>APPL</string><key>CFBundleVersion</key><string>${pkg.version}</string><key>LSUIElement</key><true/><key>NSMicrophoneUsageDescription</key><string>June uses your microphone only when you enable hands-free, for local speech recognition with speaker echo processing. Audio is not uploaded or saved.</string></dict></plist>`);
console.log('Compiling June Audio with the installed Apple SDK…');
await run('/usr/bin/xcrun',['swiftc','-O',join(root,'native/JuneAudio.swift'),'-framework','AVFoundation','-framework','AppKit','-o',join(mac,'JuneAudio.next')]);
await rename(join(mac,'JuneAudio.next'),join(mac,'JuneAudio'));
await run('/usr/bin/codesign',['--force','--sign','-','--identifier','local.june.audio',bundle]);
await run(join(mac,'JuneAudio'),['--self-test']);
console.log('June Audio ready. Microphone permission is requested only after Enable hands-free.');
