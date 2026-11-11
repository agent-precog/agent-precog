# Title/abstract screening prompt - version ta-screen-v3 (protocol v1.6, 2026-11-11)

First-pass title/abstract screening for runs identified after protocol v1.5. It applies the tightened v1.5
criteria, including the strict runtime reading of (a) and the primacy test on (c), at the first pass rather
than at a second pass, so that a record that would have been screened in under v1.1 and then screened out
under v1.5 is only handled once. Output labels are "include" (send to full text) and "exclude" with a code.

You are screening records for a PRISMA-S living systematic review on pre-emptive safety reflexes for
autonomous multi-agent systems (agent-precog.org). Decide from TITLE and ABSTRACT only.

INCLUDE if ALL hold:
- peer-reviewed paper or arXiv preprint that reports a method, system, formal result or empirical study
  (not only a position, vision or call to action);
- English; 2015 or later;
- addresses at least one of:
  (a) deferral, abstention, learning-to-defer, or runtime safety interception / shielding / runtime monitoring
      of an acting system - STRICTLY RUNTIME: a mechanism that can override, veto, halt or defer a nominal
      action at execution time. A safety term in a training loss or a constraint inside a planner is not (a);
  (b) world models or latent prediction over graphs or multi-agent state;
  (c) multi-agent hazard detection: collisions, cascading or emergent failures, unsafe interactions among
      several agents/robots/services, or safety evaluation of LLM/tool-calling agents - PRIMACY TEST: the
      multi-agent safety property must be the paper's primary claim and primary measured outcome. Learned
      safety certificates and detectors qualify; navigation, formation, task-allocation or coordination
      planners in which collision avoidance is one constraint among several do not (E1);
  (d) edge or real-time inference under explicit latency constraints for safety decisions;
  (e) human takeover, handoff, or situation awareness when automation defers to a person.

Otherwise EXCLUDE with exactly one code:
- E1 off-topic: none of (a)-(e) is the subject (e.g. power-system "multi-agent" control with no safety
  interception question; generic path planning; swarm optimisation; scheduling; communications protocols).
- E2 no evaluation: on topic but the abstract gives no sign of a quantitative safety metric with a baseline or
  ablation (position, roadmap, proposal, or a purely qualitative demonstration).
- E3 survey or tutorial: on topic but a review, survey, tutorial or book chapter overview (kept for snowballing).
- E4 wrong level: a single-agent, single-input guardrail or classifier with no multi-agent, sequential,
  latency or handoff aspect.
- E6 not retrievable; E7 not in English.
(E5 duplicate is assigned by the maintainer, not by this pass.)

First-pass rule: when the abstract makes any of (a)-(e) plausible, with (a) and (c) read strictly as above, label include;
the full text decides. Otherwise exclude with the code.

Output one line per record, tab-separated: record_id <TAB> include|exclude <TAB> code-or-blank <TAB> one-line reason (max 25 words).
