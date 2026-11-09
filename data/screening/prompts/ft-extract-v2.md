# Full-text extraction drafting prompt - version ft-extract-v2 (protocol v1.5, 2026-11-09)

You are drafting an extraction note for one paper in a PRISMA-S living systematic review on pre-emptive
safety reflexes for autonomous multi-agent systems (agent-precog.org). Read the full text (arXiv HTML or
PDF; the abstract alone is not enough). The maintainer, not you, makes the include/exclude decision; your
job is to put the evidence in front of him in a fixed shape.

Inclusion criteria (full-text stage). INCLUDE if ALL hold:
- reports a method, system, formal result or empirical study with an evaluation (E2 if not);
- English, 2015 or later; not a survey/tutorial/book chapter (E3);
- addresses at least one of:
  (a) deferral, abstention, learning-to-defer, or runtime safety interception/shielding/runtime monitoring
      of an acting system. STRICTLY RUNTIME: the mechanism sits between a nominal decision and its execution
      and can override, veto, halt or defer at execution time (safety filter, shield, monitor, gatekeeper,
      approval gate). A safety term in a training loss or a constraint inside a planner does NOT meet (a);
  (b) world models or latent prediction over graphs or multi-agent state;
  (c) multi-agent hazard detection: collisions, cascading or emergent failures, unsafe interactions among
      several agents/robots/services, or safety evaluation of LLM/tool-calling agents. PRIMACY TEST: the
      multi-agent safety property must be the paper's primary claim AND primary measured outcome (collision,
      violation or hazard rate against a baseline or ablation). Learned safety certificates and detectors
      qualify; navigation/coordination planners where collision avoidance is one constraint among several
      and the paper is about efficiency, deadlock or path quality are E1;
  (d) edge or real-time inference under explicit latency constraints for safety decisions;
  (e) human takeover, handoff, or situation awareness when automation defers to a person.
- Minimum evaluation (protocol v1.5): at least one quantitative safety metric AND a baseline or ablation;
  a qualitative demonstration alone is E2.
- E1 off-topic if none of (a)-(e) is the subject; E4 wrong level if it is a single-agent, single-input
  guardrail with no multi-agent, sequential, latency or handoff aspect. Multi-agent coordination alone is E1
  unless the mechanism is a safety mechanism (protocol v1.2).

Research questions (score 0-5 each; 5 = direct building block or baseline, 4 = core method in an adjacent
setting, 3 = partial methodological overlap, 1-2 = background only, 0 = not relevant):
- RQ1 sub-15 ms latent world-model interception over a multi-agent sub-graph on edge hardware
- RQ2 jitter-adaptive sequential learning to defer against time-to-irreversibility
- RQ3 dual-speed (fast halt / slow explanation) human handoff
- RQ4 compositional generalisation to unseen hazard combinations
- RQ5 incremental value over existing safeguards (false halts, throughput)

Gap-matrix cells (list every one the paper actually addresses; be strict):
multi-agent state; non-generative inference; latency/jitter aware; time-to-irreversibility; edge deployment;
human handoff; cross-domain evaluation (ONLY when the same mechanism is evaluated in both a physical
domain - robots/vehicles - and a logical/enterprise domain - software agents, transactions, services; two
robotics settings do not qualify)

Methods tags (reuse existing where they fit, add a new lowercase hyphenated tag only when needed):
POMDP, SA-measurement, WCET-analysis, barrier-functions, calibration, complexity-theory, consistency-proof,
control-theory, decision-theory, deferral, distributed-systems, edge-compilation, energy-based, ethics,
factored-models, formal-methods, graph-learning, human-factors, hyperbolic-geometry, networked-control,
quantisation, real-time-systems, regularisation, reject-option, representation-learning, risk-bounds,
self-supervised, sequential-decision, shielding, surrogate-loss, tail-latency, temporal-logic, world-model,
reachability, model-predictive-control, reinforcement-learning, llm-agents, runtime-monitoring

Output one CSV row with these columns (quote every field):
record_id, arxiv_id, runtime_interceptor (yes if the mechanism can override/veto/halt/defer at execution time,
else no), criteria_met (letters a-e, semicolon-separated, or none), evidence (one sentence quoted
or closely paraphrased from the paper that shows the criterion is met, with section), method (≤ 30 words),
evaluation (≤ 30 words: setting, baselines, metrics, hardware/latency if reported), rq1, rq2, rq3, rq4, rq5,
gap_cells (semicolon-separated), methods (semicolon-separated), contribution (one sentence, ≤ 35 words, as it
would appear on the site), recommend (include | exclude-E1 | exclude-E2 | exclude-E3 | exclude-E4),
flag (blank, or a short note on anything the maintainer should look at: borderline criterion, extended version
of another queued paper, multi-agent only nominally, etc.)
