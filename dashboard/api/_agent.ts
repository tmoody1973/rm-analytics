/**
 * The assistant's agentic loop, built as a CopilotKit v2 "aisdk" factory so we can
 * GUARANTEE a written answer — the one thing the classic BuiltInAgent config can't.
 *
 * The bug (2026-07-29), diagnosed from prod stream instrumentation:
 *   [agent] {ok:true, ms:61119, steps:7, toolCalls:12, reasoning:21, textLen:0}
 * On hard multi-source questions the model calls many tools and then NEVER writes an
 * answer. Reproduced locally: with the real system prompt + the render_chart/render_table
 * tools present, forcing `toolChoice:"none"` (or `activeTools:[]`) on a thinking model
 * yields a reasoning block and ZERO text — the model, shown tools it may not use, stalls.
 * Simple questions work only because the model *chooses* to answer after a few tools.
 *
 * The proven fix (verified against the real Anthropic API): TWO PHASES.
 *   1. GATHER — streamText WITH tools. If the model answers on its own, we're done.
 *      A soft-deadline `prepareStep` forces it to stop calling tools so gather ends fast.
 *   2. SYNTHESIZE — if gather produced no text, make a SEPARATE streamText call with NO
 *      tools at all, feeding it everything gathered, and ask for the answer. A no-tools
 *      call can't stall on forbidden tools, so it reliably returns prose (1,600+ chars in
 *      the repro that produced 0 under toolChoice:"none").
 *
 * Reasoning parts are stripped from the stream (CopilotKit's converter mishandles the
 * @ai-sdk/anthropic reasoning lifecycle, #3323). The two phases are stitched into one
 * fullStream: gather's terminal `finish` is dropped (the converter treats `finish` as
 * end-of-stream), so exactly one `finish` — the final phase's — reaches CopilotKit.
 */
import { streamText, stepCountIs, type ToolChoice, type ToolSet } from "ai";
import {
  resolveModel,
  convertMessagesToVercelAISDKMessages,
  convertToolDefinitionsToVercelAITools,
  convertToolsToVercelAITools,
  type ToolDefinition,
} from "@copilotkit/runtime/v2";

/** Backstop on the gather tool loop. Time is the real limit (below). */
export const MAX_STEPS = 15;
/** Force gather to stop calling tools at ~45s, leaving room for the synthesis call. */
export const SOFT_DEADLINE_MS = 45_000;
/** Hard abort before Vercel's 120s wall, so WE stop the run, not an ungraceful kill. */
export const HARD_ABORT_MS = 110_000;

/** System prompt for the synthesis call: no persona bloat, no render emphasis, no tools. */
export const SYNTHESIS_SYSTEM =
  "You are the Radio Milwaukee data analyst, and you are out of time. You have NO tools " +
  "available now (no SQL, no chart/table rendering). Using ONLY the data already returned " +
  "in the conversation above, write the best answer you can for the user RIGHT NOW, in " +
  "clear plain prose. Lead with the bottom line, then support it with the figures you have. " +
  "If you couldn't gather everything, give what you have and name the gap in one line. " +
  "Do not write tool calls or code. An answer in words is required.";

export const SYNTHESIS_USER =
  "Answer my question now, in prose, using only the data already gathered above.";

/**
 * Should gather stop calling tools? True once the step ceiling or the time budget is
 * spent. Pure and unit-tested (test/agent-loop.test.ts) so CI guards it without a live call.
 */
export function shouldFinalize(
  stepNumber: number,
  elapsedMs: number,
  { maxSteps, softMs }: { maxSteps: number; softMs: number },
): boolean {
  return stepNumber >= maxSteps - 1 || elapsedMs >= softMs;
}

export interface BuildAgentStreamOptions {
  /** "anthropic:claude-sonnet-5" (colon form resolveModel accepts). */
  model: string;
  /** Server-authoritative system prompt. */
  systemPrompt: string;
  /** Server-side tools with `execute` (get_metric, query_sql, …). */
  serverTools: ToolDefinition[];
  /** Composed run + deadline signal. */
  abortSignal: AbortSignal;
  /** Injectable clock for tests. */
  now?: () => number;
  /** Override the soft deadline (tests). */
  softDeadlineMs?: number;
  /** Override the step ceiling (tests). */
  maxSteps?: number;
}

const isReasoning = (t: unknown): boolean => typeof t === "string" && t.startsWith("reasoning");

/**
 * Build one agent turn. Returns `{ fullStream }` — all CopilotKit's factory consumes.
 */
export function buildAgentStream(input: any, opts: BuildAgentStreamOptions) {
  const now = opts.now ?? (() => Date.now());
  const softMs = opts.softDeadlineMs ?? SOFT_DEADLINE_MS;
  const maxSteps = opts.maxSteps ?? MAX_STEPS;
  const model = resolveModel(opts.model);

  // useAgentContext() data arrives on input.context — append to the system prompt, as the
  // classic agent does, so "what am I looking at?" grounding is preserved.
  let system = opts.systemPrompt;
  if (input?.context && input.context.length > 0) {
    const parts = [opts.systemPrompt, "\n## Context from the application\n"];
    for (const ctx of input.context) parts.push(`${ctx.description}:\n${ctx.value}\n`);
    system = parts.join("");
  }

  // Passed via streamText's `system` param (not unshifted into messages) — cleaner, and it
  // silences the AI SDK "system message in messages is a prompt-injection risk" warning.
  const convo = convertMessagesToVercelAISDKMessages(input?.messages ?? [], {
    forwardSystemMessages: false,
  });

  const tools: ToolSet = {
    ...convertToolsToVercelAITools(input?.tools ?? []),          // client tools (render_chart/table)
    ...convertToolDefinitionsToVercelAITools(opts.serverTools),  // server tools (with execute)
  };

  return { fullStream: runTwoPhase({ model, system, convo, tools, abortSignal: opts.abortSignal, now, softMs, maxSteps }) };
}

async function* runTwoPhase(args: {
  model: ReturnType<typeof resolveModel>;
  system: string;
  convo: any[];
  tools: ToolSet;
  abortSignal: AbortSignal;
  now: () => number;
  softMs: number;
  maxSteps: number;
}): AsyncIterable<unknown> {
  const { model, system, convo, tools, abortSignal, now, softMs, maxSteps } = args;
  const startedAt = now();
  let textLen = 0, toolCalls = 0, synthLen = 0;
  let phase: "gather" | "synth" = "gather";

  const gather = streamText({
    model,
    system,
    messages: convo,
    tools,
    stopWhen: stepCountIs(maxSteps),
    abortSignal,
    // Stop gathering when the budget is spent, so the synthesis call has time to run.
    prepareStep: ({ stepNumber }) =>
      shouldFinalize(stepNumber, now() - startedAt, { maxSteps, softMs })
        ? { toolChoice: "none" as ToolChoice<ToolSet> }
        : {},
  });

  let gatherFinish: unknown = null;
  try {
    for await (const part of gather.fullStream) {
      const t = (part as { type?: unknown })?.type;
      if (isReasoning(t)) continue;
      if (t === "finish") { gatherFinish = part; continue; }   // hold — `finish` ends the converter
      if (t === "text-delta") textLen += String((part as { text?: string }).text ?? "").length;
      else if (t === "tool-call") toolCalls += 1;
      yield part;
    }

    if (textLen > 0) {
      // The model answered on its own — emit the held finish to end cleanly.
      if (gatherFinish) yield gatherFinish;
    } else {
      // The model gathered but never wrote an answer → guaranteed synthesis, no tools.
      phase = "synth";
      let prior: any[] = [];
      try { prior = (await gather.response).messages ?? []; } catch { prior = []; }
      const synth = streamText({
        model,
        system: SYNTHESIS_SYSTEM,
        messages: [...convo, ...prior, { role: "user", content: SYNTHESIS_USER }],
        abortSignal,
      });
      for await (const part of synth.fullStream) {
        const t = (part as { type?: unknown })?.type;
        if (isReasoning(t)) continue;
        if (t === "start" || t === "start-step") continue;   // avoid a second run-start
        if (t === "text-delta") synthLen += String((part as { text?: string }).text ?? "").length;
        yield part;   // synth's text-* and its `finish` end the stream cleanly
      }
    }
  } finally {
    // Observability: grep Vercel logs for [agent]. textLen/synthLen tell us the answer landed.
    console.log("[agent]", JSON.stringify({ phase, ms: now() - startedAt, toolCalls, gatherText: textLen, synthText: synthLen }));
  }
}

/** Compose the run's abort signal with the hard-deadline backstop. */
export function withDeadline(runSignal: AbortSignal, hardMs: number = HARD_ABORT_MS): AbortSignal {
  return AbortSignal.any([runSignal, AbortSignal.timeout(hardMs)]);
}
