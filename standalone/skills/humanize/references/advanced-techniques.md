## Advanced techniques (optional, when stakes are high)

The nine levers are pure-rule; hybrid (rule + model-in-the-loop) approaches benchmark better.
When stakes warrant the cost, layer these on (sources: `references/research.md`):

1. **Detector-scored best-of-N.** Generate 3–5 variants; score each against a real detector
   (GPTZero, Pangram, Binoculars), a banned-word count, or a perplexity probe; ship the lowest.
2. **Iterative paraphrase pass.** Run the output through a second LLM with "paraphrase this,
   keep the meaning." Diminishing returns past 2 passes; meaning drift accumulates — verify substance.
3. **Writer-profile distillation.** When the user supplies writing samples, distill style
   hypotheses first (this is protocol step 0; follow the procedure there). Beats raw few-shot.
4. **Self-rewrite distance check.** Ask a different LLM to "rewrite this in different words."
   Near-identical rewrite = text still at a local probability maximum = reads as AI.
5. **Embedding-guided synonym swap.** When tooling is available, prefer substitutions that
   explicitly lower detector scores over Lever 1's static word list.
6. **Disfluency injection (casual register only).** Light hesitations, mid-thought restarts,
   "wait actually" corrections. Off by default for formal writing; disfluencies in a board memo
   are their own tell.

**Dead ends, don't bother:** homoglyph injection (defeated by Unicode normalization, and a
clear tampering signal), single cross-model rewrite (doesn't defeat trained detectors alone),
watermark stripping (separate problem space).
