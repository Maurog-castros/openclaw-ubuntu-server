import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

const execFileAsync = promisify(execFile);

const REPO_ROOT = "/home/node/openclaw-mauro";
const RUN_WRAPPER = `${REPO_ROOT}/scripts/run-finanzas-py.sh`;
const DELEGATE = `${REPO_ROOT}/scripts/channel_delegate.py`;
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

function extractWhatsAppPeer(sessionKey, channelId, body, ctx) {
  const sk = String(sessionKey ?? "");
  const fromSession = sk.match(/:whatsapp(?::[^:\s]+)*:(\+\d{8,15})(?:$|[:\s])/i);
  if (fromSession) {
    return fromSession[1];
  }
  const ch = String(channelId ?? "").trim();
  const fromChannel = ch.match(/\+\d{8,15}/);
  if (fromChannel) {
    return fromChannel[0];
  }
  for (const key of ["peer", "from", "sender", "phone", "remoteJid"]) {
    const value = String(ctx?.[key] ?? "");
    const match = value.match(/\+\d{8,15}|(?:^|[^\d])(56\d{9,13})(?:$|[^\d])/);
    if (match) {
      return match[0].startsWith("+") ? match[0] : `+${match[1]}`;
    }
  }
  const raw = String(body ?? "");
  const fromBracket = raw.match(/\[WhatsApp\s+(\+\d{10,15})/i);
  if (fromBracket) {
    return fromBracket[1];
  }
  const fromLine = raw.match(/(\+\d{10,15}):\s/m);
  if (fromLine) {
    return fromLine[1];
  }
  const anyPhone = `${sk}\n${ch}\n${raw}`.match(/\+\d{8,15}/);
  if (anyPhone) {
    return anyPhone[0];
  }
  return "";
}

async function runChannelDelegate(text, hasMedia, timeoutMs, ctx) {
  const args = [RUN_WRAPPER, DELEGATE, "--text", text, "--json"];
  const sessionKey = String(ctx?.sessionKey ?? "");
  const peer = extractWhatsAppPeer(sessionKey, ctx?.channelId, text, ctx);
  if (sessionKey) {
    args.push("--session-key", sessionKey);
  }
  if (peer) {
    args.push("--peer", peer);
  }
  if (hasMedia) {
    args.push("--has-media");
  }
  try {
    const { stdout } = await execFileAsync("/bin/bash", args, {
      timeout: timeoutMs,
      maxBuffer: 10 * 1024 * 1024,
    });
    const result = JSON.parse(stdout);
    result._peer = peer;
    return result;
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
          const result = await runChannelDelegate(text, looksLikeMediaBody(text), timeoutMs, ctx);
          const status = result?.status;
          const replyText = String(result.whatsapp_reply ?? result.reply ?? "").trim();
          const blocked = !replyText || status === "delegate_miss" || status === "skip";
          if (!blocked) {
            api.logger.info(
              `channel-delegate-hook: handled status=${status ?? "implicit"} agent=${result.agent ?? "?"} peer=${result._peer || "?"} session=${ctx.sessionKey ?? "?"}`,
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
