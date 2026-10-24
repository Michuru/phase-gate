### Reference detector landscape (for context)

If the user asks "what would tool X say?", these are the current characteristics:

- **GPTZero (2025)** uses RL adversarial self-training plus a learned classifier ensemble, not just
  perplexity + burstiness. Produces a 4-class output (human / slight / moderate / full AI-assist).
  Older "GPTZero relies on perplexity + burstiness" framing is stale.
- **Binoculars** is a strong zero-shot baseline but has the Claude blind spot above.
- **Pangram 3.0** claims 99.98% accuracy with 1-in-10,000 FPR and 97% on humanized text per vendor
  benchmarks (independent replication pending).
- **EditLens** estimates AI-edit fraction rather than binary authorship (94.7 F1 binary, 90.4 F1 ternary).
- **Ghostbuster** is the canonical black-box (no token probs needed) detector — 99 F1 in-domain,
  degrades out-of-domain.
- **DependencyAI** uses syntactic dependency n-grams + LightGBM, cross-lingual without LLM access.
