# Title/abstract screening prompt - version ta-screen-v4 (protocol v1.7, 2026-11-11)

First-pass title/abstract screening. Identical to ta-screen-v3 except for the E2 rule, which protocol v1.7
corrects: under v1.5 and v1.6 the evaluation floor was applied at the title/abstract stage, which
systematically excluded formal results, verification methods and qualitative empirical studies before anyone
read them, because an abstract does not show a results section. The maintainer's blind leak check of the ACM
pillar-1 run caught this on one record, "A Reference Architecture of Human Cyber-Physical Systems - Part III:
Semantic Foundations", and the 70 E2 exclusions made under the earlier prompts were re-screened under this one.

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
- E2 no contribution: on topic but the record offers no method, formal result or empirical study at all - a
  position, vision or call to action, a roadmap, a keynote or invited-talk abstract, a doctoral research
  statement, or an extended abstract or work-in-progress paper that reports nothing yet.
  PROTOCOL v1.7: E2 is NOT for a paper that contributes something but reports no quantitative safety metric.
  The evaluation floor is a FULL-TEXT criterion and must not be applied from an abstract, which does not
  show a results section. A formal result, a verification or model-checking method, a system or platform, or
  a qualitative empirical study all pass to full text, where the floor decides. When in doubt whether a
  record contributes or merely proposes, pass it to full text.
- E3 survey or tutorial: on topic but a review, survey, tutorial or book chapter overview (kept for snowballing).
- E4 wrong level: a single-agent, single-input guardrail or classifier with no multi-agent, sequential,
  latency or handoff aspect.
- E6 not retrievable; E7 not in English.
(E5 duplicate is assigned by the maintainer, not by this pass.)

First-pass rule: when the abstract makes any of (a)-(e) plausible, with (a) and (c) read strictly as above, label include;
the full text decides. Otherwise exclude with the code.

Output one line per record, tab-separated: record_id <TAB> include|exclude <TAB> code-or-blank <TAB> one-line reason (max 25 words).
