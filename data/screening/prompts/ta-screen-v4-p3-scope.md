# ta-screen-v4, Pillar 3 scope addendum (maintainer ruling, 2026-11-13)

Applied on top of ta-screen-v4 to every Pillar 3 record that passed the broad first screen. The broad screen had passed any paper proposing or evaluating abstention, a reject option, selective prediction or deferral; the maintainer narrowed the pillar to its stated focus. Text given to the screening model:

- These records come from the Pillar 3 search (learning to defer and safety interception) and ALREADY passed a broad first screen. You are re-screening them under the maintainer's narrower scope ruling of 2026-11-13. Label a record include ONLY if a decision to abstain, reject, defer or hand off is the paper's MAIN contribution (not one component, one evaluation metric or a side result) AND at least one of the following holds:
  (i) the deferral or hand-off is to a human expert, or to a safeguard or fallback system, including learning to defer and human-AI teams with a learned deferral rule;
  (ii) the setting is sequential or multi-step: reinforcement learning, agents, trajectories, online or streaming decisions in which abstaining or deferring is an action taken over time;
  (iii) deferral among multiple experts;
  (iv) a safety-critical runtime decision: a shield, runtime monitor or gate that halts, vetoes or hands off an action in a deployed or simulated system;
  (v) foundational theory of the reject option, selective classification or learning to defer: optimal reject rules, consistency of surrogate losses, generalisation or regret bounds, formal analysis.
  Otherwise exclude:
  - E4 for one-shot selective prediction or a classifier with a reject option applied to some domain, an uncertainty or confidence estimator evaluated by risk-coverage, or a language model that abstains from answering single questions, when none of (i)-(v) holds;
  - E1 when abstention or deferral is only a component, a metric or incidental; when a model cascade or router defers to a larger model purely for cost or accuracy with no safety or human element; when it is the human labeller or crowd worker who abstains; or when "reject option classification" means a fairness relabelling method.
  - E2, E3 and E7 as the prompt defines them. Whole proceedings volumes are E1.
  When a record plausibly meets one of (i)-(v) but the abstract is too thin to be sure, include it. In the reason, name which of (i)-(v) applies for includes.
- "Deferral" or "abstention" in an unrelated sense (blood-donor deferral, tax or payment deferral, deferred maintenance, deferred rendering or execution, alcohol or voting abstention) is E1.
