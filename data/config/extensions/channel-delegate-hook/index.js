import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

const execFileAsync = promisify(execFile);

const RUN_PY = "/home/node/openclaw-mauro/scripts/run-finanzas-py.sh";
const DELEGATE = "/home/node/openclaw-mauro/scripts/channel_delegate.py";
const CHANNEL_PROVIDERS = new Set(["whatsapp", "telegram"]);

function resolveConfig(api) {
  const cfg = api.pluginConfig ?? {};
  return {
    agentId: typeof cfg.agentId === "string" && cfg.agentId.trim() ? cfg.agentId.trim() : "main",
    timeoutMs: typeof cfg.timeoutMs === "number" && cfg.timeoutMs > 0 ? cfg.timeoutMs : 120_000,
  };
}

function shouldHandle(ctx, agentId) {
  if (ctx.agentId !== agentId) {
    return false;
  }
  if (ctx.trigger && ctx.trigger !== "user") {
    return false;
  }
  const provider = String(ctx.messageProvider ?? "").toLowerCase();
  if (CHANNEL_PROVIDERS.has(provider)) {
    return true;
  }
  const sessionKey = String(ctx.sessionKey ?? "").toLowerCase();
  return sessionKey.includes(":whatsapp:") || sessionKey.includes(":telegram:");
}

function looksLikeMediaBody(body) {
  return /\[image\]|\[photo\]|\[media\]|\[audio\]|📷|🖼|🎤/i.test(body);
}

async function runChannelDelegate(text, hasMedia, timeoutMs) {
  const args = [DELEGATE, "--text", text, "--json"];
  if (hasMedia) {
    args.push("--has-media");
  }
  try {
    const { stdout } = await execFileAsync(RUN_PY, args, {
      timeout: timeoutMs,
      maxBuffer: 10 * 1024 * 1024,
    });
    return JSON.parse(stdout);
  } catch (err) {
    if (err && typeof err === "object" && "code" in err && err.code === 2) {
      const raw = String(err.stdout ?? "").trim();
      if (raw) {
        try {
          return JSON.parse(raw);
        } catch {
          return { status: "delegate_miss" };
        }
      }
      return { status: "delegate_miss" };
    }
    throw err;
  }
}

export default definePluginEntry({
  id: "channel-delegate-hook",
  name: "Channel Delegate Hook",
  register(api) {
    const { agentId, timeoutMs } = resolveConfig(api);

    api.on(
      "before_agent_reply",
      async (event, ctx) => {
        if (!shouldHandle(ctx, agentId)) {
          return undefined;
        }
        const text = String(event.cleanedBody ?? "").trim();
        if (!text) {
          return undefined;
        }
        try {
          const result = await runChannelDelegate(text, looksLikeMediaBody(text), timeoutMs);
          const status = result?.status;
          const replyText = String(result.whatsapp_reply ?? result.reply ?? "").trim();
          const blocked = status === "delegate_miss" || status === "skip" || status === "error";
          if (replyText && !blocked) {
            api.logger.info(
              `channel-delegate-hook: handled status=${status ?? "implicit"} agent=${result.agent ?? "?"} session=${ctx.sessionKey ?? "?"}`,
            );
            return { handled: true, reply: { text: replyText } };
          }
          return undefined;
        } catch (err) {
          const message = err instanceof Error ? err.message : String(err);
          api.logger.warn(`channel-delegate-hook failed: ${message}`);
          return undefined;
        }
      },
      { priority: 200, timeoutMs },
    );
  },
});
