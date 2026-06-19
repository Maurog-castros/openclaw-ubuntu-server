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

function isTelegramGroupSession(sessionKey) {
  const sk = String(sessionKey ?? "").toLowerCase();
  return sk.includes(":telegram:group:");
}

function extractDelegateText(cleanedBody, msgCtx) {
  const cleaned = String(cleanedBody ?? "").trim();
  if (cleaned) {
    return cleaned;
  }
  if (!msgCtx || typeof msgCtx !== "object") {
    return "";
  }
  for (const key of [
    "BodyForCommands",
    "CommandBody",
    "RawBody",
    "BodyStripped",
    "BodyForAgent",
    "Body",
  ]) {
    const value = String(msgCtx[key] ?? "").trim();
    if (value) {
      return value;
    }
  }
  return "";
}

function looksLikeMediaBody(body) {
  return /\[image\]|\[photo\]|\[media\]|\[audio\]|📷|🖼|🎤/i.test(body);
}

function normalizePhoneMatch(value) {
  const raw = String(value ?? "");
  const plus = raw.match(/\+\d{8,15}/);
  if (plus) {
    return plus[0];
  }
  const jid = raw.match(/(?:^|[^\d])(56\d{9,13})@/);
  if (jid) {
    return `+${jid[1]}`;
  }
  const plain = raw.match(/(?:^|[^\d])(56\d{9,13})(?:$|[^\d])/);
  if (plain) {
    return `+${plain[1]}`;
  }
  return "";
}

function extractFromObject(obj, depth = 0) {
  if (!obj || depth > 3 || typeof obj !== "object") {
    return "";
  }
  const preferred = [
    "senderE164",
    "from",
    "peer",
    "sender",
    "senderId",
    "senderJid",
    "remoteJid",
    "chatId",
    "conversationId",
    "participant",
    "channelId",
  ];
  for (const key of preferred) {
    const value = obj[key];
    const direct = normalizePhoneMatch(value);
    if (direct) {
      return direct;
    }
    if (value && typeof value === "object") {
      const nested = extractFromObject(value, depth + 1);
      if (nested) {
        return nested;
      }
    }
  }
  return "";
}

function extractTelegramPeer(ctx, event) {
  for (const source of [event, ctx]) {
    if (!source || typeof source !== "object") {
      continue;
    }
    for (const key of ["senderId", "from", "chatId", "channelId", "peer"]) {
      const value = String(source[key] ?? "");
      const match = value.match(/telegram:(\d{5,})|^(\d{5,})$/);
      if (match) {
        return `telegram:${match[1] || match[2]}`;
      }
    }
  }
  return "";
}

function extractChannelPeer(sessionKey, channelId, body, ctx, event) {
  const provider = String(ctx?.messageProvider ?? event?.messageProvider ?? "").toLowerCase();
  if (provider === "telegram") {
    const telegramPeer = extractTelegramPeer(ctx, event);
    if (telegramPeer) {
      return telegramPeer;
    }
  }
  const sk = String(sessionKey ?? "");
  const fromSession = sk.match(/:whatsapp(?::[^:\s]+)*:(\+\d{8,15})(?:$|[:\s])/i);
  if (fromSession) {
    return fromSession[1];
  }
  const fromEvent = extractFromObject(event);
  if (fromEvent) {
    return fromEvent;
  }
  const fromCtx = extractFromObject(ctx);
  if (fromCtx) {
    return fromCtx;
  }
  const fromChannel = normalizePhoneMatch(channelId);
  if (fromChannel) {
    return fromChannel;
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
  const anyPhone = normalizePhoneMatch(`${sk}\n${channelId ?? ""}\n${raw}`);
  if (anyPhone) {
    return anyPhone;
  }
  return "";
}

async function runChannelDelegate(text, hasMedia, timeoutMs, ctx, event) {
  const args = [RUN_WRAPPER, DELEGATE, "--text", text, "--json"];
  const sessionKey = String(ctx?.sessionKey ?? "");
  const peer = extractChannelPeer(sessionKey, ctx?.channelId, text, ctx, event);
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
          const result = await runChannelDelegate(text, looksLikeMediaBody(text), timeoutMs, ctx, event);
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

    api.on(
      "reply_dispatch",
      async (event, dispatchCtx) => {
        const sessionKey = String(event.sessionKey ?? event.ctx?.SessionKey ?? "");
        if (!sessionKey.toLowerCase().includes("agent:main:")) {
          return undefined;
        }
        if (!isTelegramGroupSession(sessionKey)) {
          return undefined;
        }
        if (event.sendPolicy === "deny") {
          return undefined;
        }
        const text = extractDelegateText("", event.ctx).trim();
        if (!text) {
          return undefined;
        }
        const hookCtx = {
          agentId,
          sessionKey,
          sessionId: event.ctx?.SessionId,
          messageProvider: "telegram",
          trigger: "user",
          channelId: event.originatingTo ?? event.ctx?.To,
        };
        try {
          const result = await runChannelDelegate(
            text,
            looksLikeMediaBody(text),
            timeoutMs,
            hookCtx,
            event.ctx,
          );
          const status = result?.status;
          const replyText = String(result.whatsapp_reply ?? result.reply ?? "").trim();
          const blocked = !replyText || status === "delegate_miss" || status === "skip";
          if (blocked) {
            return undefined;
          }
          await dispatchCtx.onReplyStart?.();
          dispatchCtx.dispatcher.sendFinalReply({ text: replyText });
          dispatchCtx.recordProcessed("completed");
          dispatchCtx.markIdle("channel-delegate-hook");
          api.logger.info(
            `channel-delegate-hook: reply_dispatch handled status=${status ?? "implicit"} agent=${result.agent ?? "?"} peer=${result._peer || "?"} session=${sessionKey}`,
          );
          return {
            handled: true,
            queuedFinal: true,
            counts: { tool: 0, block: 0, final: 1 },
          };
        } catch (err) {
          const message = err instanceof Error ? err.message : String(err);
          api.logger.warn(`channel-delegate-hook reply_dispatch failed: ${message}`);
          return undefined;
        }
      },
      { priority: 200, timeoutMs },
    );
  },
});
