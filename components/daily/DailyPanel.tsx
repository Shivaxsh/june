"use client";
import { useEffect, useRef, useState } from "react";
import {
  addGoal, authorizeGoogle, changeGoal, configureGoogle, getBriefing, getPlaylists, itemText, itemTime, readGoogleClient, revokeGoogle,
  searchPlaces, SECTION_KINDS, SECTION_WORDS, setConnection, updateSettings,
  type Briefing, type Goal, type PlaceOption, type Playlist, type SectionKind,
} from "@/lib/daily";
import { CONNECTION_WORDS, isConflict, proposePlan, type Capability, type Connection } from "@/lib/integrations";
import PlanCard from "../integrations/PlanCard";
import type { Integrations } from "../integrations/useIntegrations";
import type { Daily } from "./useDaily";

const KIND_WORDS: Record<SectionKind, string> = { weather: "Weather", calendar: "Calendar", goals: "Goals" };
const message = (failure: unknown, fallback: string) => failure instanceof Error ? failure.message : fallback;

/** One guarded async action at a time per panel, with its own error line. */
function useRun() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const inFlight = useRef(false);
  async function run(work: () => Promise<void>, fallback = "June could not reach the daily assistant.") {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError("");
    try { await work(); } catch (failure) { setError(message(failure, fallback)); } finally { inFlight.current = false; setBusy(false); }
  }
  return { busy, error, setError, run };
}

/** Open-Meteo's free data is CC BY 4.0: credit it wherever its data is shown or used. */
function WeatherCredit() {
  return <p className="plan-step-meta weather-credit">Weather data by <a href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">Open-Meteo.com</a></p>;
}

function ConnectionLine({ connection }: { connection?: Connection }) {
  if (!connection) return <p className="handsfree-note">Checking this service…</p>;
  return <p className="plan-step-meta">{CONNECTION_WORDS[connection.state]} · {connection.message}</p>;
}

/**
 * Systems → Daily. The briefing is built by the server from structured data; each source
 * reports its own state, so a missing one is named rather than guessed. Outside services
 * are enabled only by a click, after their exact hosts are shown.
 */
export default function DailyPanel({ daily, integrations, onHear, onAnnounce }: {
  daily: Daily; integrations: Integrations; onHear(text: string): void; onAnnounce(text: string): void;
}) {
  const { settings, goals } = daily;
  const connection = (id: string) => integrations.connections?.find(c => c.id === id);
  const byId = new Map((integrations.capabilities ?? []).map(c => [c.id, c] as [string, Capability]));
  const weather = connection("open-meteo"), google = connection("google"), music = connection("apple-music"), appleCalendar = connection("apple-calendar");
  // Weather is usable once the person enabled it; "connected" arrives only after the first successful read.
  const weatherOn = !!weather && (weather.enabled === true || weather.state === "connected");
  const zone = settings?.weather.place?.timeZone;
  const hour = new Date().getHours();
  const part = hour < 5 || hour >= 18 ? "evening" : hour < 12 ? "morning" : "afternoon";

  // Briefing
  const brief = useRun();
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  // Weather
  const weatherRun = useRun();
  const [query, setQuery] = useState("");
  const [places, setPlaces] = useState<PlaceOption[] | null>(null);
  // Google
  const calendarRun = useRun();
  const googleRun = useRun();
  const [awaitingGoogle, setAwaitingGoogle] = useState(false);
  // Goals
  const goalRun = useRun();
  const [draft, setDraft] = useState("");
  // Music
  const musicRun = useRun();
  const [playlists, setPlaylists] = useState<Playlist[] | null>(null);
  const [musicPlan, setMusicPlan] = useState<string | null>(null);

  // While Google consent is open in another tab, follow the connection until it settles.
  useEffect(() => {
    if (!awaitingGoogle) return;
    if (google?.state === "connected") { setAwaitingGoogle(false); onAnnounce("Google Calendar connected, read-only."); return; }
    const timer = setInterval(() => void integrations.refresh(), 3000);
    const stop = setTimeout(() => setAwaitingGoogle(false), 5 * 60 * 1000);
    return () => { clearInterval(timer); clearTimeout(stop); };
  }, [awaitingGoogle, google?.state, integrations, onAnnounce]);

  async function saveSettings(change: Parameters<typeof updateSettings>[1], announce: string, run: ReturnType<typeof useRun>) {
    if (!settings) return;
    await run.run(async () => {
      try { const reply = await updateSettings(settings, change); daily.putSettings(reply.settings); onAnnounce(announce); }
      catch (failure) { if (isConflict(failure)) { void daily.refresh(); throw new Error("Settings changed somewhere else. June refreshed them; try again."); } throw failure; }
    });
  }

  function connectGoogle() {
    // Open the tab inside the click so the browser allows it; navigate once the URL is known.
    const tab = window.open("about:blank", "_blank");
    void googleRun.run(async () => {
      try {
        const reply = await authorizeGoogle();
        if (!tab) throw new Error("Your browser blocked the Google sign-in tab. Allow pop-ups for June and try again.");
        tab.opener = null; tab.location.href = reply.authUrl;
        setAwaitingGoogle(true);
        onAnnounce("Google sign-in opened in a new tab. June asks only to read your calendar events.");
      } catch (failure) { tab?.close(); throw failure; }
    });
  }

  const activeGoals = (goals ?? []).filter(g => g.status === "active");
  const doneGoals = (goals ?? []).filter(g => g.status === "done").slice(0, 5);
  const plan = musicPlan ? integrations.plans.find(p => p.id === musicPlan) : undefined;

  return <section className="timers-panel daily-panel" aria-label="Daily">
    <span className="eyebrow">Daily · your briefing, goals and focus</span>
    <h2>Good <em>{part}.</em></h2>
    <p>Ask for a briefing any time: weather for your chosen city, today&apos;s calendar and your goals. Each part says plainly when it is not set up or could not load.</p>
    {daily.error && <p className="error-notice" role="alert">{daily.error} <button type="button" className="quiet-button" onClick={() => void daily.refresh()}>Retry</button></p>}

    <div className="integration-group" aria-label="Briefing">
      <div className="integration-request">
        <button type="button" className="quiet-button" disabled={brief.busy} onClick={() => void brief.run(async () => { const reply = await getBriefing(); setBriefing(reply.briefing); onAnnounce("Briefing ready."); })}>Brief me</button>
        {briefing && <button type="button" className="quiet-button" onClick={() => onHear(briefing.spoken)}>Hear briefing</button>}
      </div>
      {brief.busy && <p role="status" className="handsfree-note">Preparing your briefing…</p>}
      {brief.error && <p className="error-notice" role="alert">{brief.error}</p>}
      {briefing && <div className="briefing">
        {briefing.sections.map(section => <section key={section.kind} className={`briefing-section is-${section.status}`} aria-label={section.title}>
          <div className="plan-step-head"><strong>{section.title}</strong>{section.status !== "ok" && <span>{SECTION_WORDS[section.status]}</span>}</div>
          {section.message && <p className="plan-step-meta">{section.message}</p>}
          {section.items.length > 0 && <ul>{section.items.map((item, i) => <li key={i}>{(item.at !== undefined || item.allDay) && <time>{itemTime(item, section.kind === "weather" ? zone : undefined)}</time>}<span>{itemText(item)}</span></li>)}</ul>}
          {section.kind === "weather" && section.status === "ok" && <WeatherCredit />}
        </section>)}
      </div>}
      {settings && <div className="reminder-repeat" role="group" aria-label="Include in briefing">{SECTION_KINDS.map(kind => {
        const on = settings.briefing.sections.includes(kind);
        return <button key={kind} type="button" className="quiet-button" aria-pressed={on} disabled={brief.busy}
          onClick={() => void saveSettings({ briefing: { sections: on ? settings.briefing.sections.filter(k => k !== kind) : SECTION_KINDS.filter(k => k === kind || settings.briefing.sections.includes(k)) } }, `${KIND_WORDS[kind]} ${on ? "removed from" : "added to"} the briefing.`, brief)}>{KIND_WORDS[kind]}</button>;
      })}</div>}
    </div>

    <div className="integration-group" aria-label="Weather">
      <h3>Weather</h3>
      <ConnectionLine connection={weather} />
      {weather && !weatherOn && <div className="plan-actions">
        {weather.hosts.length
          ? <p className="handsfree-note">Enabling lets June contact {weather.hosts.join(" and ")}. Only the city you choose is sent; your location is never read.</p>
          : <p className="handsfree-note">June has not listed which services weather would contact, so it cannot be enabled yet.</p>}
        <div className="timer-buttons"><button type="button" className="quiet-button" disabled={weatherRun.busy || !weather.hosts.length}
          onClick={() => void weatherRun.run(async () => { await setConnection("open-meteo", true); await integrations.refresh(); onAnnounce("Weather enabled."); })}>Enable weather</button></div>
      </div>}
      {weatherOn && <>
        <p className="handsfree-note">{settings?.weather.place ? `City: ${settings.weather.place.name}${settings.weather.place.region ? `, ${settings.weather.place.region}` : ""}, ${settings.weather.place.country}` : "No city chosen yet."}</p>
        <form className="timer-form" onSubmit={event => { event.preventDefault(); void weatherRun.run(async () => { setPlaces((await searchPlaces(query)).places); }); }}>
          <label className="timer-name">City<input type="text" value={query} maxLength={80} placeholder="Kanpur, Lisbon…" onChange={e => setQuery(e.target.value)} /></label>
          <button type="submit" className="quiet-button" disabled={weatherRun.busy || query.trim().length < 2}>Find city</button>
        </form>
        {places && (places.length ? <ul className="integration-list" aria-label="Matching cities">{places.map(place => <li key={place.id}>
          <div className="plan-step-head"><strong>{place.name}</strong><span>{[place.region, place.country].filter(Boolean).join(", ")}</span></div>
          <div className="timer-buttons"><button type="button" className="quiet-button" disabled={weatherRun.busy}
            onClick={() => void saveSettings({ weather: { placeId: place.id } }, `Weather city set to ${place.name}.`, weatherRun).then(() => setPlaces(null))}>Use {place.name}</button></div>
        </li>)}</ul> : <p className="handsfree-note">No matching city found.</p>)}
        {settings && <div className="reminder-repeat" role="group" aria-label="Units">{(["metric", "imperial"] as const).map(units =>
          <button key={units} type="button" className="quiet-button" aria-pressed={settings.weather.units === units} disabled={weatherRun.busy}
            onClick={() => void saveSettings({ weather: { units } }, `Weather units set to ${units === "metric" ? "Celsius" : "Fahrenheit"}.`, weatherRun)}>{units === "metric" ? "°C" : "°F"}</button>)}</div>}
        <div className="timer-buttons"><button type="button" className="quiet-button" disabled={weatherRun.busy}
          onClick={() => void weatherRun.run(async () => { await setConnection("open-meteo", false); await integrations.refresh(); onAnnounce("Weather turned off. June will not contact the weather service."); })}>Turn off weather</button></div>
        <WeatherCredit />
      </>}
      {weatherRun.error && <p className="error-notice" role="alert">{weatherRun.error}</p>}
    </div>

    <div className="integration-group" aria-label="Calendar">
      <h3>Apple Calendar</h3>
      <ConnectionLine connection={appleCalendar} />
      {appleCalendar && !appleCalendar.enabled && <div className="plan-actions">
        <p className="handsfree-note">macOS will ask whether June Calendar may access your calendars. June reads your events when you ask, and adds an event only after you approve its card. It never changes or deletes events, and everything stays on this Mac.</p>
        <div className="timer-buttons"><button type="button" className="quiet-button" disabled={calendarRun.busy}
          onClick={() => void calendarRun.run(async () => { await setConnection("apple-calendar", true); await integrations.refresh(); onAnnounce("June can now read your calendar for briefings."); })}>Allow June to read Calendar</button></div>
      </div>}
      {appleCalendar?.enabled && <div className="timer-buttons"><button type="button" className="quiet-button" disabled={calendarRun.busy}
        onClick={() => void calendarRun.run(async () => { await setConnection("apple-calendar", false); await integrations.refresh(); onAnnounce("June will no longer read your calendar."); })}>Stop June reading Calendar</button></div>}
      {calendarRun.error && <p className="error-notice" role="alert">{calendarRun.error}</p>}
      <details className="integration-group">
      <summary>Use Google Calendar instead (advanced)</summary>
      <ConnectionLine connection={google} />
      {google?.state === "not-configured" && <div className="plan-actions">
        <p className="handsfree-note">One-time setup: in Google Cloud, create an OAuth client of type “Desktop app” and download its JSON. Choose that file here; June keeps the client id and secret in your Mac&apos;s Keychain, not in this browser.</p>
        <label className="document-upload">Google OAuth client JSON<input type="file" accept="application/json,.json" disabled={googleRun.busy}
          onChange={event => { const file = event.target.files?.[0]; event.target.value = ""; if (!file) return;
            void googleRun.run(async () => {
              if (file.size > 20000) throw new Error("That file is too large to be a Google OAuth client JSON.");
              await configureGoogle(readGoogleClient(await file.text())); await integrations.refresh(); onAnnounce("Google client saved to the Keychain. Next, connect your calendar.");
            }); }} /></label>
      </div>}
      {google && ["needs-consent", "expired", "revoked", "error"].includes(google.state) && <div className="plan-actions">
        <p className="handsfree-note">June asks Google only to read your calendar events (primary calendar first). Google may show an “unverified app” notice for your own client. While the app is in testing, access can expire after about 7 days; June will then ask you to reconnect.</p>
        <div className="timer-buttons"><button type="button" className="quiet-button" disabled={googleRun.busy || awaitingGoogle} onClick={connectGoogle}>{google.state === "needs-consent" ? "Connect Google Calendar" : "Reconnect Google Calendar"}</button></div>
        {awaitingGoogle && <p role="status" className="handsfree-note">Waiting for you to finish in the Google tab…</p>}
      </div>}
      {google?.state === "connected" && <div className="timer-buttons"><button type="button" className="quiet-button" disabled={googleRun.busy}
        onClick={() => void googleRun.run(async () => { await revokeGoogle(); await integrations.refresh(); onAnnounce("Google Calendar disconnected. June removed its access."); })}>Disconnect Google</button></div>}
      {googleRun.error && <p className="error-notice" role="alert">{googleRun.error}</p>}
      </details>
    </div>

    <div className="integration-group" aria-label="Goals">
      <h3>Goals</h3>
      <form className="timer-form" onSubmit={event => { event.preventDefault(); void goalRun.run(async () => { const reply = await addGoal(draft); daily.putGoal(reply.goal); setDraft(""); onAnnounce("Goal added."); }); }}>
        <label className="timer-name">New goal<input type="text" value={draft} maxLength={200} placeholder="Finish the Phase 8 plan…" onChange={e => setDraft(e.target.value)} /></label>
        <button type="submit" className="quiet-button" disabled={goalRun.busy || !draft.trim()}>Add goal</button>
      </form>
      {goals === null ? <p className="handsfree-note">Loading goals…</p> : activeGoals.length === 0 ? <p className="handsfree-note">No active goals.</p> :
        <ul className="integration-list">{activeGoals.map(goal => <GoalRow key={goal.id} goal={goal} daily={daily} onAnnounce={onAnnounce} />)}</ul>}
      {doneGoals.length > 0 && <details><summary>Recently done ({doneGoals.length})</summary>
        <ul className="integration-list">{doneGoals.map(goal => <GoalRow key={goal.id} goal={goal} daily={daily} onAnnounce={onAnnounce} />)}</ul></details>}
      {goalRun.error && <p className="error-notice" role="alert">{goalRun.error}</p>}
    </div>

    <div className="integration-group" aria-label="Music">
      <h3>Apple Music</h3>
      <ConnectionLine connection={music} />
      {music && music.state !== "connected" && <div className="plan-actions">
        <p className="handsfree-note">macOS will ask whether June may control the Music app. June only lists your playlists and plays the one you choose; nothing leaves this Mac.</p>
        <div className="timer-buttons"><button type="button" className="quiet-button" disabled={musicRun.busy}
          onClick={() => void musicRun.run(async () => { await setConnection("apple-music", true); await integrations.refresh(); onAnnounce("Music control requested. Answer the macOS prompt if one appears."); })}>Allow June to control Music</button></div>
      </div>}
      {music?.state === "connected" && <>
        <p className="handsfree-note">{settings?.music.playlist ? `Focus playlist: ${settings.music.playlist.name}` : "No playlist chosen yet."}</p>
        <div className="timer-buttons">
          <button type="button" className="quiet-button" disabled={musicRun.busy} onClick={() => void musicRun.run(async () => {
            try { setPlaylists((await getPlaylists()).playlists); }
            catch (failure) { if (failure instanceof Error && "code" in failure && failure.code === "automation-permission") throw new Error("June is not allowed to control Music. Open System Settings → Privacy & Security → Automation and allow June Music to control Music, then try again."); throw failure; }
          })}>Choose playlist</button>
          {settings?.music.playlist && <button type="button" className="quiet-button" disabled={musicRun.busy}
            onClick={() => void musicRun.run(async () => { const reply = await proposePlan("play-playlist"); integrations.upsert(reply.plan, reply.serverNow); setMusicPlan(reply.plan.id); onAnnounce(`Plan to play ${settings.music.playlist!.name} is ready for review.`); })}>Play {settings.music.playlist.name}</button>}
          {settings?.music.playlist && <button type="button" className="quiet-button" disabled={musicRun.busy}
            onClick={() => void musicRun.run(async () => { const reply = await proposePlan("focus-session"); integrations.upsert(reply.plan, reply.serverNow); setMusicPlan(reply.plan.id); onAnnounce("Focus session plan is ready for review."); })}>Start focus session</button>}
        </div>
        <div className="timer-buttons" role="group" aria-label="Playback">{(["previous", "pause", "resume", "next"] as const).map(op =>
          <button key={op} type="button" className="quiet-button" disabled={musicRun.busy}
            onClick={() => void musicRun.run(async () => { const reply = await proposePlan("music-control", undefined, undefined, { op }); integrations.upsert(reply.plan, reply.serverNow); setMusicPlan(reply.plan.id); onAnnounce(reply.plan.status === "proposed" ? "Music control is ready for review." : "Music control sent."); })}>{op[0].toUpperCase() + op.slice(1)}</button>)}</div>
        <p className="handsfree-note">By voice or chat: “next song”, “pause the music”, “play Imagine Dragons”, “play the album Evolve”. June plays only what is in your own Music library.</p>
        {playlists && (playlists.length ? <ul className="integration-list" aria-label="Playlists">{playlists.slice(0, 50).map(p => <li key={p.id}>
          <div className="plan-step-head"><strong>{p.name}</strong>{settings?.music.playlist?.id === p.id && <span>Chosen</span>}</div>
          <div className="timer-buttons"><button type="button" className="quiet-button" disabled={musicRun.busy || settings?.music.playlist?.id === p.id}
            onClick={() => void saveSettings({ music: { playlistId: p.id } }, `Focus playlist set to ${p.name}.`, musicRun).then(() => setPlaylists(null))}>Use this playlist</button></div>
        </li>)}</ul> : <p className="handsfree-note">No playlists of your own were found in your Music library. If your playlist is from Apple Music, open it in the Music app and choose Add to Library (or the + button), then click Choose playlist again.</p>)}
        <div className="timer-buttons"><button type="button" className="quiet-button" disabled={musicRun.busy}
          onClick={() => void musicRun.run(async () => { await setConnection("apple-music", false); await integrations.refresh(); onAnnounce("June will no longer control Music."); })}>Stop June controlling Music</button></div>
      </>}
      {plan && <PlanCard plan={plan} capabilities={byId} serverNow={integrations.serverNow} receivedAt={integrations.receivedAt}
        onChange={integrations.upsert} onRefresh={() => void integrations.refreshPlans()} onAnnounce={onAnnounce} />}
      {musicRun.error && <p className="error-notice" role="alert">{musicRun.error}</p>}
    </div>
  </section>;
}

/** A goal. Edits are bound to the copy opened; a newer copy never rebinds the draft. */
function GoalRow({ goal, daily, onAnnounce }: { goal: Goal; daily: Daily; onAnnounce(text: string): void }) {
  const run = useRun();
  const [base, setBase] = useState<Goal | null>(null);
  const [value, setValue] = useState("");
  async function act(kind: "update" | "complete" | "reopen" | "delete", from: Goal) {
    await run.run(async () => {
      try {
        const reply = await changeGoal(from, kind, kind === "update" ? value : undefined);
        if (reply.deleted) daily.dropGoal(from.id); else daily.putGoal(reply.goal);
        setBase(null);
        onAnnounce(kind === "delete" ? "Goal deleted." : kind === "complete" ? "Goal marked done." : kind === "reopen" ? "Goal reopened." : "Goal updated.");
      } catch (failure) {
        if (isConflict(failure)) { setBase(null); void daily.refresh(); throw new Error("This goal changed somewhere else. June refreshed it; try again."); }
        throw failure;
      }
    });
  }
  return <li className={`goal is-${goal.status}`}>
    {base ? <form className="timer-form" onSubmit={event => { event.preventDefault(); void act("update", base); }}>
      {goal.revision !== base.revision && <p className="error-notice" role="status">This goal changed since you started editing. Saving will be refused; choose Keep as is to see the latest.</p>}
      <label className="timer-name">Goal<input type="text" value={value} maxLength={200} onChange={e => setValue(e.target.value)} /></label>
      <div className="timer-buttons">
        <button type="submit" className="quiet-button" disabled={run.busy || !value.trim() || value.trim() === base.text}>Save goal</button>
        <button type="button" className="quiet-button" disabled={run.busy} onClick={() => setBase(null)}>Keep as is</button>
      </div>
    </form> : <>
      <p>{goal.text}</p>
      <div className="timer-buttons">
        {goal.status === "active" ? <>
          <button type="button" className="quiet-button" disabled={run.busy} onClick={() => void act("complete", goal)}>Done</button>
          <button type="button" className="quiet-button" disabled={run.busy} onClick={() => { setBase(goal); setValue(goal.text); }}>Edit</button>
        </> : <button type="button" className="quiet-button" disabled={run.busy} onClick={() => void act("reopen", goal)}>Reopen</button>}
        <button type="button" className="quiet-button" disabled={run.busy} onClick={() => void act("delete", goal)}>Delete <span className="sr-only">{goal.text}</span></button>
      </div>
    </>}
    {run.error && <p className="error-notice" role="alert">{run.error}</p>}
  </li>;
}
