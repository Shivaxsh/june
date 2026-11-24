// Saved project commands and the GitHub consent. Running one is always a plan (lib/integrations).
import { call, defaultHttp, IntegrationError, type Http } from "./integrations";

export type CommandKind = "run" | "server";
export type SavedCommand = { id: string; projectId: string; project: string; name: string; command: string; safe: boolean; kind: CommandKind; running: boolean };
export type CommandProject = { id: string; name: string };
export type CommandState = { githubAllowed: boolean; projects: CommandProject[]; commands: SavedCommand[] };

const ID = /^[a-f0-9]{32}$/;
const invalid = () => new IntegrationError("June returned project commands in an unexpected form.", 502, "invalid-response");
const text = (value: unknown, max: number): value is string => typeof value === "string" && value.trim().length > 0 && value.length <= max;

function parseState(data: Record<string, unknown>): CommandState {
  const { githubAllowed, projects, commands } = data;
  if (typeof githubAllowed !== "boolean" || !Array.isArray(projects) || projects.length > 10 || !Array.isArray(commands) || commands.length > 30) throw invalid();
  return {
    githubAllowed,
    projects: projects.map(p => {
      if (!p || typeof p !== "object" || !ID.test((p as CommandProject).id) || !text((p as CommandProject).name, 60)) throw invalid();
      return { id: (p as CommandProject).id, name: (p as CommandProject).name };
    }),
    commands: commands.map(c => {
      const v = c as SavedCommand;
      if (!v || typeof v !== "object" || !ID.test(v.id) || !ID.test(v.projectId) || !text(v.project, 60) || !text(v.name, 40) || !text(v.command, 500)
        || typeof v.safe !== "boolean" || typeof v.running !== "boolean" || (v.kind !== "run" && v.kind !== "server")) throw invalid();
      return { id: v.id, projectId: v.projectId, project: v.project, name: v.name, command: v.command, safe: v.safe, kind: v.kind, running: v.running };
    }),
  };
}

export async function getCommands(http: Http = defaultHttp) { return parseState(await call(http, "/api/commands")); }
/** The command text is what the person typed in this form, never anything June or a model wrote. */
export async function addCommand(value: { projectId: string; name: string; command: string; safe: boolean; kind: CommandKind }, http: Http = defaultHttp) {
  if (!ID.test(value.projectId) || !text(value.name, 40) || !text(value.command, 500) || /[\u0000-\u001f\u007f]/.test(value.command))
    throw new IntegrationError("Give the command a name and type it on one line.", 400, "invalid-input");
  return parseState(await call(http, "/api/commands", { projectId: value.projectId, name: value.name.trim(), command: value.command.trim(), safe: value.safe, kind: value.kind }));
}
export async function removeCommand(id: string, http: Http = defaultHttp) {
  if (!ID.test(id)) throw new IntegrationError("June cannot remove that command.", 400, "invalid-input");
  return parseState(await call(http, `/api/commands/${id}/remove`, {}));
}
export async function setGithub(allowed: boolean, http: Http = defaultHttp) { return parseState(await call(http, "/api/commands/github", { allowed })); }
