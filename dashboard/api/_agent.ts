/**
 * The assistant's agentic loop, built as a CopilotKit v2 "aisdk" factory so we can do
 * the one thing the classic BuiltInAgent config cannot: GUARANTEE a written answer.
 *
 * The bug this fixes (2026-07-29): on hard multi-source questions the model ran ~16
 * queries and hit Vercel's 120s function wall BEFORE writing anything — the run was
 * killed mid-stream and the user saw silence. The classic config only exposes a static
 * `maxSteps`, and the AI SDK ends the tool loop WITHOUT a final answer when that limit
 * is reached (vercel/ai #13075). Neither a higher ceiling nor a prompt nudge can force
 * an answer.
 *
 * This module mirrors BuiltInAgent's classic streamText construction (context → system,
 * message conversion, server + client tool merge — see @copilotkit/runtime agent/index)
 * and adds exactly two things:
 *   1. `prepareStep` — when the step OR time budget is spent, disable tools for the next
 *      step (`toolChoice: "none"`). A step with no tool call is terminal, so the model is
 *      forced to synthesize an answer from what it already gathered, then the run ends.
 *   2. a composed deadline `abortSignal` — a hard backstop that fires before the 120s wall.
 *
 * Because the soft deadline forces synthesis with time to spare, the hard abort should
 * almost never fire. Our usage touches none of the classic config's complex paths
 * (interrupts, resume, MCP, editable state), so this faithful-but-simpler replica behaves
 * identically up to the moment the guard trips.
 */
import { streamText, stepCountIs, type ToolChoice, type ToolSet } from "ai";
import {
  resolveModel,
  convertMessagesToVercelAISDKMessages,
  convertToolDefinitionsToVercelAITools,
  convertToolsToVercelAITools,
  type ToolDefinition,
} from "@copilotkit/runtime/v2";

/** Backstop on the tool loop. Time is the real limit (below), so this rarely binds. */
export const MAX_STEPS = 15;
/** Force a tool-free final answer at ~70s — leaves ~35s to write before the abort. */
export const SOFT_DEADLINE_MS = 70_000;
/** Hard abort before Vercel's 120s wall, so WE stop the run, not an ungraceful kill. */
export const HARD_ABORT_MS = 105_000;

/**
 * Injected as the system message on the forced-finalize step. Without it, a model
 * denied tools tends to narrate the tool call it WANTED to make ("get_data({...})")
 * as prose instead of answering. This tells it to synthesize from what it already has.
 */
export const FINALIZE_INSTRUCTION =
  "\n\n## Answer now — you are out of time\n" +
  "You cannot call any more tools. Do NOT write tool calls, function syntax, or code. " +
  "Using ONLY the data already returned by earlier tool calls in this conversation, write " +
  "the best plain-prose answer you can for the user, and briefly name anything you could " +
  "not finish. If no data was retrieved yet, say so plainly and suggest a narrower question. " +
  "An answer in words is required.";

/**
 * The budget decision, pure and unit-testable: should the next step be forced to answer
 * (tools off) because the step ceiling or the time budget is spent? Extracted so CI can
 * guard the boundaries without a live model call.
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
  /** Override the soft deadline (tests force an immediate finalize). */
  softDeadlineMs?: number;
  /** Override the step ceiling (tests). */
  maxSteps?: number;
}

/**
 * Build the streamText run for one agent turn. Returns the streamText result; the caller
 * (CopilotKit's factory path) consumes `.fullStream`.
 */
export function buildAgentStream(input: any, opts: BuildAgentStreamOptions) {
  const now = opts.now ?? (() => Date.now());
  const startedAt = now();
  const softMs = opts.softDeadlineMs ?? SOFT_DEADLINE_MS;
  const maxSteps = opts.maxSteps ?? MAX_STEPS;

  // useAgentContext() data arrives on input.context — append it to the system prompt
  // exactly as the classic agent does, so "what am I looking at?" grounding is preserved.
  let system = opts.systemPrompt;
  if (input?.context && input.context.length > 0) {
    const parts = [opts.systemPrompt, "\n## Context from the application\n"];
    for (const ctx of input.context) parts.push(`${ctx.description}:\n${ctx.value}\n`);
    system = parts.join("");
  }

  const messages = convertMessagesToVercelAISDKMessages(input?.messages ?? [], {
    forwardSystemMessages: false,
  });
  messages.unshift({ role: "system", content: system });

  const tools: ToolSet = {
    ...convertToolsToVercelAITools(input?.tools ?? []),          // client tools (render_chart/table)
    ...convertToolDefinitionsToVercelAITools(opts.serverTools),  // server tools (with execute)
  };

  return streamText({
    model: resolveModel(opts.model),
    messages,
    tools,
    stopWhen: stepCountIs(maxSteps),
    abortSignal: opts.abortSignal,
    prepareStep: ({ stepNumber }) => {
      // Disable tools AND tell the model to synthesize → it must answer in words, from
      // the data already gathered, and the tool-free step ends the run.
      if (shouldFinalize(stepNumber, now() - startedAt, { maxSteps, softMs })) {
        return { toolChoice: "none" as ToolChoice<ToolSet>, system: system + FINALIZE_INSTRUCTION };
      }
      return {};
    },
  });
}

/** Compose the run's abort signal with the hard-deadline backstop. */
export function withDeadline(runSignal: AbortSignal, hardMs: number = HARD_ABORT_MS): AbortSignal {
  return AbortSignal.any([runSignal, AbortSignal.timeout(hardMs)]);
}
