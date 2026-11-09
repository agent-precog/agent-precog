# Title/abstract first-pass screening prompt — version ta-screen-v1 (protocol v1.1, 2026-11-09)

You are screening records for a PRISMA-S living systematic review on pre-emptive safety reflexes for
autonomous multi-agent systems (agent-precog.org). Decide from TITLE and ABSTRACT only.

INCLUDE if ALL hold:
- peer-reviewed paper or arXiv preprint that reports a method, system, formal result or empirical study
  (not only a position, vision or call to action);
- English; 2015 or later;
- addresses at least one of:
  (a) deferral, abstention, learning-to-defer, or runtime safety interception / shielding / runtime monitoring
      of an acting system;
  (b) world models or latent prediction over graphs or multi-agent state;
  (c) multi-agent hazard detection: collisions, cascading or emergent failures, unsafe interactions among
      several agents/robots/services, or safety evaluation of LLM/tool-calling agents;
  (d) edge or real-time inference under explicit latency constraints for safety decisions;
  (e) human takeover, handoff, or situation awareness when automation defers to a person.

Otherwise EXCLUDE with exactly one code:
- E1 off-topic: none of (a)-(e) is the subject (e.g. power-system "multi-agent" control with no safety
  interception question; generic path planning; swarm optimisation; scheduling; communications protocols).
- E2 no evaluation: on topic but no method+evaluation, formal result or study (position, roadmap, proposal only).
- E3 survey or tutorial: on topic but a review, survey, tutorial or book chapter overview (kept for snowballing).
- E4 wrong level: a single-agent, single-input guardrail or classifier with no multi-agent, sequential,
  latency or handoff aspect.
- E6 not retrievable; E7 not in English.
(E5 duplicate is assigned by the maintainer, not by this pass.)

Title/abstract stage rule: when in doubt, INCLUDE; the full-text stage decides.

Output one line per record, tab-separated: record_id <TAB> include|exclude <TAB> code-or-blank <TAB> one-line reason (max 25 words).
