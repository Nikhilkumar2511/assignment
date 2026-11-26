# LLM-based and Hybrid Approaches to 20-Questions / Akinator-style Guessing

Research note on method and verification: direct fetches of arxiv.org, aclanthology.org, proceedings.neurips.cc, huggingface.co and deep20bench.com were blocked by this session's network policy. github.com could be fetched. Figures marked "(snippet)" come from search-engine extraction of the paper, not from a full read. Some snippet tables were garbled, so check those figures against the PDF before publishing.

## 1. How well do LLMs play 20 questions as the guesser when simply prompted?

### Takeaway
When simply prompted, LLMs are weak and inconsistent guessers. In the Apple Entity-Deduction Arena (2023, using mid-2023 models), even GPT-4-0613 solved only 31% of "Things" and 50% of "Celebrities" within 20 turns, and open models were far lower. Newer frontier models (2025-2026) do better on easy or self-chosen targets, but there are few independent, consistent benchmarks for them.

### Cited Findings
- **Entity-Deduction Arena (EDA)**, Zhang, Lu & Jaitly (Apple), "Probing the Multi-turn Planning Capabilities of LLMs via 20 Question Games". ICLR 2024 and ACL 2024. The guesser asks questions; the judge knows the entity and may answer only "Yes", "No" or "Maybe". Datasets are Things and Celebrities. — [arXiv 2310.01468](https://arxiv.org/html/2310.01468v3); [ACL 2024](https://aclanthology.org/2024.acl-long.82.pdf); [code](https://github.com/apple/ml-entity-deduction-arena)
- In the EDA repo the answerer model defaults to GPT-3.5-turbo. The guesser is selectable: gpt-4, gpt-3.5-turbo, claude-1, claude-2, vicuna-7b/13b, and others. — [GitHub README](https://github.com/apple/ml-entity-deduction-arena)
- EDA results on **Things** (format: model: avg turns (lower is better) / success rate / score), from the [GitHub README](https://github.com/apple/ml-entity-deduction-arena):
  - GPT-4-0613: 17.8 / 0.31 / 0.26
  - GPT-3.5-turbo-0613: 18.2 / 0.28 / 0.23
  - Claude-2: 18.4 / 0.21 / 0.18
  - Claude-1: 18.8 / 0.16 / 0.13
  - Vicuna-13B v1.3: 18.4 / 0.18 / 0.15
  - Vicuna-7B v1.3: 19.5 / 0.09 / 0.07
  - Mistral-7B-Instruct v0.2: 18.9 / 0.13 / 0.11
- EDA results on **Celebrities**, from the [GitHub README](https://github.com/apple/ml-entity-deduction-arena):
  - GPT-4-0613: 17.3 / 0.50 / 0.40
  - GPT-3.5-turbo: 18.8 / 0.27 / 0.21
  - Claude-2: 17.6 / 0.31 / 0.26
  - Claude-1: 17.7 / 0.29 / 0.25
  - Vicuna-13B: 18.7 / 0.22 / 0.18
  - Vicuna-7B: 19.6 / 0.06 / 0.05
  - Mistral-7B: 18.2 / 0.22 / 0.20
- Another version of the EDA paper (ACL) reportedly gives different GPT-4 self-play figures (40% / 48%). The numbers vary between versions. — [search summary of ACL PDF](https://aclanthology.org/2024.acl-long.82.pdf) (snippet)
- **UoT paper, direct-prompting baselines:** on the "Common" 20Q dataset, GPT-4 with direct prompting reached 49.0% success, against 70.9% with UoT. — [UoT, arXiv 2402.03271](https://arxiv.org/html/2402.03271v3) (snippet; appendix table)
- **BED-LLM, naive prompting baselines** (2025, snippet figures):
  - GPT-4o "Prompt-Only": 45% on Animals and 34% on Things.
  - Mistral-Large Prompt-Only: 33% on Animals and 14-19% on Celebrities (the figure differs between versions).
  - GPT-4o-mini naive QA: 44% on Animals.
  - Source: [BED-LLM arXiv 2508.21184](https://arxiv.org/pdf/2508.21184); [ICLR 2026 paper note](https://en.papernotes.org/ICLR2026/llm_agent/bed-llm_intelligent_information_gathering_with_llms_and_bayesian_experimental_de/)
- **GuessingGame** (Hutson et al., EMNLP 2025): open-domain, with no candidate list, and Oracle / Guesser / Checker roles run as separate LLM instances. With binary yes/no questions, LLaMA-3.3-70B reached 32.1% success; with open-ended questions, 39.4%. 858 games in total. — [EMNLP 2025](https://aclanthology.org/2025.emnlp-main.876/); [arXiv 2509.19593](https://arxiv.org/html/2509.19593v1); [code](https://github.com/cincynlp/GuessingGame)
- **Multi-Turn Puzzles (arXiv 2508.10142, 2025):** in their Twenty Questions task the average turns were Gemini 2.5 Pro Exp 6.3, Claude 3.5 Sonnet 6.2 and GPT-4o 15.1. The authors say models "perform well" on Twenty Questions compared with their other tasks. Their setup (a secret noun, scored on logical consistency) is easier and different from EDA, so the numbers are not comparable. — [arXiv 2508.10142](https://arxiv.org/html/2508.10142v3) (snippet)
- **Deep20Bench** (a 20Q leaderboard for current models). The two sources disagree:
  - A Hacker News post claims Claude Opus 5 leads with 12.34 average questions, followed by Kimi K3 at 12.74.
  - The leaderboard page, as seen in a search snippet, lists Claude Sonnet 5 (high) at 14.74 (rank 10) and GPT-5 Nano (medium) at 15.49.
  - Sources: [HN](https://news.ycombinator.com/item?id=49119862); [leaderboard](https://deep20bench.com/editions/1.0/results/) (not fetchable; snippet only)
- **Small GitHub pilot** (48 games, reusing the EDA test split): Gemini won 17/24 games as guesser and GPT won 10/24. GPT often "guessed inside its questions", which inflates its scores. — [Maaz-R-Khan/llm20questions](https://github.com/Maaz-R-Khan/llm20questions) (snippet)
- **LMRL-Gym** (2023) includes a 20Q task in which the reward depends on how early the guesser gets it right. It is used as an RL benchmark. — [arXiv 2311.18232](https://arxiv.org/html/2311.18232)
- **Opinion, not measurement:** a Medium essay argues GPT-5 still loses to Akinator because it asks pattern-matched questions rather than computing splits. — [Medium](https://medium.com/@agieternal/the-genie-vs-the-god-why-a-20-year-old-app-akinator-still-humiliates-gpt-5-eedc69c1b824)

### Inferences
- With an unrestricted entity space (EDA Things), a plain-prompted LLM guesser should be expected to fail on most games, even with a frontier model, unless scaffolding is added. Celebrities is easier than Things, likely because names cluster in well-known taxonomies.
- Scores depend heavily on the setup: the answerer model, a closed versus open candidate space, whether "Maybe" or "pass" answers are allowed, and how guesses are counted. Numbers across papers should not be compared directly.
- The newest models (2026) appear to need about 12-15 questions on Deep20Bench. This suggests large gains over 2023, but that evidence is unverified.

### Gaps
- I could not verify Deep20Bench's methodology, its answerer model or the exact leaderboard (the site was blocked, and the two sources conflict).
- I found no independent, peer-reviewed 20Q guesser numbers for GPT-5, Gemini 2.5/3 or Claude 4.x on the EDA protocol.
- I found nothing specifically called "GuessBench". The closest equivalents are GuessingGame (EMNLP 2025) and Deep20Bench.
- BIG-bench "twenty_questions": UoT uses a "bigbench" 20Q dataset ([UoT repo](https://github.com/zhiyuanhubj/UoT)), but I did not retrieve per-model BIG-bench scores.

## 2. Methods to improve question asking (EIG, UoT, tree search, RL/DPO, self-play, BED)

### Takeaway
Explicitly computing expected information gain (EIG) over an LLM-generated or fixed candidate set gives the largest improvements without training. UoT reports +38-58% relative gains in success, and BED-LLM reports about +37 points on average and up to 91-95% success. Training with DPO or RL helps smaller models, but the gains are more modest.

### Cited Findings
- **Uncertainty of Thoughts (UoT)**, Hu et al., NeurIPS 2024.
  - How it works: the LLM generates N candidate questions and simulates the Yes/No answers that would follow each one. This partitions a "possibility set" of candidate entities. The method computes an information-gain-based reward and propagates it through a simulated tree J levels deep, then picks the question with the highest expected reward. — [arXiv 2402.03271](https://arxiv.org/html/2402.03271v3); [NeurIPS](https://neurips.cc/virtual/2024/poster/96142)
  - Reported gains differ between versions: the NeurIPS abstract says +38.1% on average in task success over direct prompting across LLMs, and the repo and later version say +57.8%. Over the DPOS baseline, the repo reports +54.9% for GPT-3.5 and +21.1% for GPT-4. — [GitHub](https://github.com/zhiyuanhubj/UoT); [NeurIPS abstract](https://proceedings.neurips.cc/paper_files/paper/2024/hash/2b0e14abd8128e6bf98b6b0bec1cfcbf-Abstract.html)
  - Repo configuration options:
    - `--n_potential_actions`: number of candidate questions.
    - `--n_extend_layers`: simulation depth.
    - `--n_pruned_nodes`: pruning (a positive number keeps that many nodes; a negative number keeps a proportion).
    - `--reward_lambda`: the uncertainty-aware reward.
  - Open-set mode: the first 3 rounds use direct prompting (DPOS). After that, the possibility set is regenerated each round with sizes 10, 10, 10, 5, 5, 5.
  - Models supported: llama-2-70b-chat, gpt-3.5/4, claude-2/3, gemini-1.0-pro, mistral, Gemma. The examiner (answerer) model is fixed to GPT-4.
  - Datasets: 20Q (bigbench and "common"), medical diagnosis (DX, MedDG) and troubleshooting (FloDial). — [GitHub](https://github.com/zhiyuanhubj/UoT)
- **BED-LLM** (2025; listed under ICLR 2026 by a paper-notes site):
  - How it works: an iterative Bayesian experimental design loop. The LLM proposes candidate questions and hypotheses. The method estimates EIG under the current belief, starting from a uniform prior over the hypotheses, and filters out hypotheses inconsistent with past answers. When one hypothesis remains it asks "Is it ⟨item⟩?".
  - Average gain: +37.4 points of success over direct prompting. Success "more than doubl[es] in over half of setups and never decreas[es]".
  - Results by model:
    - Mistral-Large: Animals 33% → 95%; Celebrities 14% or 19% → 91%.
    - GPT-4o: Animals 45% → 93%; Things 34% → 64%.
    - GPT-4o-mini: Animals 44% → 88%.
    - GPT-4o-mini questioner with a Qwen2.5-72B answerer (Animals): 72%, against Prompt-Only 30% and a "Split" baseline 53%.
  - Sources: [arXiv 2508.21184](https://arxiv.org/pdf/2508.21184); [paper note](https://en.papernotes.org/ICLR2026/llm_agent/bed-llm_intelligent_information_gathering_with_llms_and_bayesian_experimental_de/) (snippets)
- **Learning to Ask Informative Questions** (Mazzaccara, Testoni & Bernardi; Findings of EMNLP 2024):
  - Method: sample several questions from LLaMA-2-Chat-7B, score each by EIG over the candidate set, and pair low-EIG with high-EIG questions as DPO preference data.
  - Results: success rose from 44.4% to 51.1%, average questions fell from 9.5 to 6.3, and EIG rose from 0.31 to 0.38 on the INLG16 candidate set. The gains generalize to unseen domains.
  - Sources: [arXiv 2406.17453](https://arxiv.org/html/2406.17453v3) (snippet; the table was garbled); code at dmazzaccara/LearningToAsk.
- **PAPRIKA, "Training a Generally Curious Agent"** (2025):
  - Method: SFT plus preference fine-tuning on self-generated multi-turn trajectories across many games, including 20Q (1,500 train tasks, 367 test tasks, 20-turn limit).
  - Results: Llama-3.1-8B-Instruct's average success across the whole task suite reportedly rose about 47% relative after training on about 22.5k trajectories. That figure comes from a third-party summary and is not specific to 20Q. The best-of-K sampling ceiling for 20Q during data collection was 84.0%.
  - Sources: [arXiv 2502.17543](https://arxiv.org/html/2502.17543v4); [project page](https://paprika-llm.github.io); [dataset](https://huggingface.co/datasets/ftajwar/paprika_SFT_dataset) (snippets)
- **Active Task Disambiguation with LLMs** (2025):
  - Method: at each step, prompt the LLM for N=20 animals consistent with the requirements gathered so far, then pick the question with the highest EIG over that sampled set. The answerer is GPT-4o-mini, and games last 10 rounds to save cost.
  - Caveat noted by the authors: with long requirement lists, the LLM generates candidates that violate them.
  - Source: [arXiv 2502.04485](https://arxiv.org/pdf/2502.04485) (snippet)
- **GuessingGame (EMNLP 2025):**
  - A one-SD increase in Bayesian information gain per question corresponded to a 43% reduction in expected game length; for ConceptNet-based IG the figure was 19%.
  - Prompt constraints alone raised LLaMA-3.3-70B's success from 39.4% to 80.0% (no repeated question types) and to 97.4% (open-ended questions only).
  - Source: [arXiv 2509.19593](https://arxiv.org/html/2509.19593v1)
- **Belief-state reward RL:** one 2026 belief-management paper reports that RL with belief-state rewards reduced failure rates by 70.9% on average, while explicit belief-tracking prompts gave only limited gains. It is not specific to 20Q. — [arXiv 2605.30219](https://arxiv.org/html/2605.30219v1) (snippet)
- **Further work, seen only as snippets:**
  - Amortising Bayesian experimental design for sequential information gathering (2026). — [arXiv 2607.03426](https://arxiv.org/pdf/2607.03426)
  - Amortizing sequential experimental design in reasoning LLMs (2026). It has a judge estimate p(answer | candidate, question) over yes, no and maybe for a list of guesses. — [arXiv 2610.20832](https://arxiv.org/pdf/2610.20832)
- **Older RL for 20Q with a knowledge base and no LLM:** policy-gradient questioners using a learned intermediate reward. — [Hu et al. 2018, arXiv 1808.07645](https://arxiv.org/html/1808.07645.pdf)
- **Self-play RL** (Self-Questioning LMs, 2025) exists, but it was tested on math and coding, not 20Q. — [arXiv 2508.03682](https://arxiv.org/html/2508.03682v1)

### Inferences
- The improvement ranking is fairly consistent:
  1. Explicit EIG over an explicit hypothesis set (BED-LLM, UoT) gives the biggest gains with no training.
  2. Fine-tuning (DPO on EIG preferences, PAPRIKA) helps small models.
  3. Plain prompting is weakest.
- Simple prompt constraints (ban repeated question types, require a structured format) are cheap and gave large gains in GuessingGame. They are worth adding before heavier machinery.
- UoT and BED-style methods multiply LLM calls per turn: N candidate questions × candidate hypotheses × simulated answers × depth. Cost grows quickly, but caching per-entity answers can amortize it.

### Gaps
- I could not retrieve exact UoT 20Q tables (success rate and mean conversation length per model) or its token cost figures. The snippet values (GPT-4 UoT 79.3 / 71.2) had no reliable column labels.
- I found no MCTS-specific 20Q LLM paper with numbers beyond UoT's tree search.
- I found no PPO-on-20Q LLM result with numbers. LMRL-Gym provides the environment, but I did not retrieve its 20Q scores.

## 3. Hybrid architectures: LLM plus explicit Bayesian belief, and filling the entity × question probability matrix

### Takeaway
The strongest designs keep the belief state outside the LLM: an explicit distribution over candidate entities, updated by Bayes' rule using P(answer | entity, question). The LLM generates candidates and questions and estimates the likelihoods, either offline (precomputing a matrix) or on demand.

### Cited Findings
- **BED-LLM:** the LLM proposes questions and hypotheses. Belief over hypotheses starts uniform and is updated, with hypotheses that contradict prior answers filtered out. Questions are chosen by maximum EIG. The model guesses once one candidate remains. — [arXiv 2508.21184](https://arxiv.org/pdf/2508.21184) (snippet)
- **UoT:** an LLM-generated "possibility set" serves as the hypothesis space. For each candidate question, the LLM simulates which candidates would answer yes or no, and the split gives the information gain. — [arXiv 2402.03271](https://arxiv.org/html/2402.03271v3); [GitHub](https://github.com/zhiyuanhubj/UoT)
- **GuessingGame Bayesian metric:** maintains a distribution over semantic concepts, updated with relevance scores from an "Interpreter" LLM. Concepts whose posterior falls below a cutoff are pruned. An alternative metric filters candidates using ConceptNet assertions and measures entropy reduction. — [EMNLP 2025](https://aclanthology.org/2025.emnlp-main.876.pdf) (snippet)
- **Ways to fill P(answer | entity, question) with an LLM:**
  - (a) Prompt the answerer to return probabilities for Yes and No given the entity and question.
  - (b) For non-reasoning models, read the probabilities from token log-probabilities of "Yes" and "No". — "From Prompts to Posteriors" (2026), [arXiv 2610.29331](https://arxiv.org/pdf/2610.29331) (snippet)
  - (c) Have a judge output p(yes / no / maybe | candidate is true, question), summing to 1, across a list of candidate guesses. — [arXiv 2610.20832](https://arxiv.org/pdf/2610.20832) (snippet)
- **Neural Akinator / ai-akinator** (GitHub), a production-style hybrid. Details from the [README](https://github.com/Mohammed-Darrige/ai-akinator):
  - Belief and selection: the engine is a deterministic Bayesian engine with "no turn-time LLM calls". It covers 110 animal targets and a pool of 90 questions in Turkish, English and Arabic. Trait values are `likely`, `unlikely`, `variable`, `not_applicable` or missing; uncertain and missing traits permit both outcomes with calibrated likelihoods.
  - Answers: a yes/no answer applies a strict constraint filter plus a likelihood update. "Unknown" leaves the posterior unchanged and marks the question as asked.
  - Selection and guessing: questions are chosen by a bounded 2-question information-gain lookahead, at a mean of 4.96 ms per selection (p90 15.61 ms). The engine guesses when exactly one compatible candidate remains.
  - Benchmark: 330/330 games won with truthful answers, averaging 7.11 questions, or 9.30 with two initial "unknown" answers. The benchmark is in-sample.
  - Limitation: hard elimination has "no error rescue", so a single wrong answer loses the true target.
  - LLMs appear only in optional post-game verification and moderated storage adapters.
- **Simple Bayes Akinator clone (blog):**
  - Starts all characters at equal probability and applies Bayes' theorem after each answer.
  - Stops at 20 questions or when one character reaches 95% posterior.
  - Source: [Medium, Tiwari](https://medium.com/@iamanuragtiwari101/how-i-built-an-akinator-style-ai-using-bayes-theorem-and-a-little-bit-of-magic-df2273e3f580) (snippet)
- **A design using a known candidate set:** a 2026 paper's answerer responds from an explicit entity-attribute list, which is effectively a lookup matrix, to avoid unstable LLM beliefs. — [arXiv 2603.25187, "Probing the Lack of Stable Internal Beliefs in LLMs"](https://arxiv.org/pdf/2603.25187) (snippet)
- **Earlier knowledge-base 20Q without LLMs:** RL over generic knowledge bases. — [OpenReview](https://openreview.net/pdf?id=FlR4Wyubayy)

### Inferences
- A recommended pattern synthesized from these sources:
  1. Offline: use an LLM to generate the entity catalogue and question bank, and fill the matrix with soft probabilities (via log-probs or elicited probabilities, with several samples averaged).
  2. Online: run pure Bayes updates and EIG selection, which are cheap and deterministic.
  3. Use the LLM only for open-catalogue fallbacks, such as generating new candidates or new questions when the posterior is flat or the top candidate is rejected.
- Use soft likelihoods (for example P(yes | entity) = 0.9 rather than 1.0) plus a noise floor instead of hard elimination. This avoids the ai-akinator failure where one wrong answer kills the true target.
- Akinator-style systems also learn from players over time, updating the matrix after a revealed answer. An LLM can bootstrap the cold-start matrix, and player data can then correct it. This is my inference; I found no published system documenting it.

### Gaps
- I found no source reporting the calibration accuracy of LLM-filled entity × question matrices against human-labelled truth.
- I found no published cost comparison between precomputed matrices and on-the-fly LLM likelihood calls.

## 4. Embeddings and retrieval for narrowing candidates or clustering questions

### Takeaway
I found no published 20Q system that uses vector search to narrow candidates. Its use is an inference from general retrieval practice.

### Cited Findings
- Recent 20Q LLM work usually assumes a small known candidate set. Open-candidate variants require the model to generate its own candidates. — [Re-Search, arXiv 2611.14487](https://arxiv.org/pdf/2611.14487) (snippet)
- In general retrieval practice, embeddings plus ANN indexes (such as HNSW) shrink a corpus to about 30-50 items, which a stronger model then reranks. Embedding recall can be imperfect; one benchmark reports paraphrase Recall@20 dropping from 0.80 to 0.65. — [DEV benchmark post](https://dev.to/peter-white-1492/should-our-llm-wiki-use-vector-search-we-benchmarked-it-before-deciding-fkf) (snippet; not 20Q-specific)
- An LLM asked to enumerate candidates consistent with a long list of constraints produces violating candidates. This motivates verifying candidates with an external filter or knowledge base. — [arXiv 2502.04485](https://arxiv.org/pdf/2502.04485) (snippet)

### Inferences
- Plausible uses, none of them validated in the literature I found:
  - Embed the accumulated Q/A transcript, or an LLM-written description of "what we know", and retrieve the top-K entities from a large catalogue (for example Wikidata) as the possibility set for EIG.
  - Cluster or deduplicate candidate questions by embedding similarity so the engine never asks near-duplicate questions.
  - Map players' free-text answers or questions onto canonical attributes.
- Retrieval recall is the risk: if the true entity falls out of the top-K, a hard filter can never recover it. Keep a "rest of catalogue" mass or periodically re-retrieve.

### Gaps
- I found no empirical study of embedding-based candidate retrieval for 20Q or Akinator.

## 5. Failure modes (inconsistent beliefs, repetition, hallucination, premature guessing, cost)

### Takeaway
The dominant failures are implicit state tracking (forgetting or contradicting earlier answers), redundant or overly narrow questions, premature specific guesses, weak final disambiguation, and inconsistency in the LLM acting as answerer. Most are fixed by keeping state explicit outside the model.

### Cited Findings
- EDA frames the guesser's task as needing state tracking and planning: it must avoid redundant queries and stay consistent with prior answers. — [arXiv 2310.01468](https://arxiv.org/html/2310.01468v3)
- A 2026 20Q case study names four failure patterns: weak final disambiguation, accumulating ambiguity (late ambiguous questions and repeated "pass" answers), inconsistent belief-state updates (the model had evidence for "bear-like" but did not update), and searching at the wrong abstraction level. — [arXiv 2608.14808, "Do LLMs Know What to Ask and When?"](https://arxiv.org/pdf/2608.14808) (snippet; unverified)
- Repetition: banning repeated question types raised LLaMA-3.3-70B's success from 39.4% to 80.0%, which implies repetition is a major failure source. — [GuessingGame](https://arxiv.org/html/2509.19593v1)
- GPT "guessed inside its questions", asking about a specific entity disguised as an attribute question. — [llm20questions](https://github.com/Maaz-R-Khan/llm20questions) (snippet)
- LLM answerers can flip Yes/No across samples for the same question, so a single noisy answer can mislead the guesser. — [arXiv 2401.05302](https://arxiv.org/pdf/2401.05302) (snippet; ToM context)
- A belief-tracking paper argues that such failures "primarily arise from unreliable implicit state tracking rather than limitations in high-level reasoning". — [PDDL-Mind, arXiv 2604.17819](https://arxiv.org/html/2604.17819v1) (snippet)
- LLM-generated candidate lists violate accumulated constraints when there are many of them. — [arXiv 2502.04485](https://arxiv.org/pdf/2502.04485)
- In LLM-native engines, a hard-elimination design has no recovery from a wrong answer. — [ai-akinator](https://github.com/Mohammed-Darrige/ai-akinator)
- Geographic and cultural bias: a 2025 paper studies how the geographic origin of entities affects LLM entity-deduction ability. — [arXiv 2508.05525](https://arxiv.org/html/2508.05525v1) (title and snippet only)

### Inferences
- Mitigations:
  - Keep an explicit list of asked questions and answers.
  - Deduplicate new questions against it (string or embedding similarity).
  - Use soft Bayes updates that tolerate answer noise.
  - Gate guesses on posterior thresholds (for example top-1 ≥ 0.8–0.95, or top-1/top-2 odds).
  - Force "category before instance" with a minimum number of questions or a ceiling on entropy before any specific guess.
- Cost per game: plain prompting needs about 20 calls with a growing context. UoT or BED-style EIG needs N questions × K candidates × simulations per turn, which can mean hundreds or thousands of LLM calls per game unless likelihoods are cached or precomputed.

### Gaps
- I found no published per-game dollar or token costs for UoT or BED-LLM (I could not fetch the full papers).
- I found no quantitative rates of hallucinated facts specifically in 20Q answer likelihoods.

## 6. Concrete prompt patterns and structured output (JSON) designs

### Takeaway
Published systems use a small set of recurring patterns: a fixed answer vocabulary (Yes / No / Maybe or pass), a per-turn candidate list, candidate-question generation with simulated answers, probability elicitation, and a separate checker. I could not retrieve exact prompt templates (the arXiv and ACL PDFs were blocked).

### Cited Findings
- EDA: the judge must reply only "Yes", "No" or "Maybe". The guesser and judge prompts live in the repo scripts `GPT_Q20.py` and `GPT_Q20_celebrity.py`. — [GitHub](https://github.com/apple/ml-entity-deduction-arena)
- An LLM reasoning-game paper prompts the model to list candidate objects each round alongside its question, a prompt-level substitute for an explicit belief. — [arXiv 2412.06394](https://arxiv.org/html/2412.06394v4) (snippet)
- Active Task Disambiguation: "generate a list of N=20 animals that adhere to the current set of requirements", then score questions against that list. — [arXiv 2502.04485](https://arxiv.org/pdf/2502.04485)
- GuessingGame separates roles (Oracle, Guesser, Checker) into separate LLM instances to prevent information leakage. The prompts are released. — [github.com/cincynlp/GuessingGame](https://github.com/cincynlp/GuessingGame) (via [arXiv 2509.19593](https://arxiv.org/html/2509.19593v1))
- Probability-elicitation answerer: assign probabilities to "Yes" and "No" given how well the entity fits, or read token log-probs. — [arXiv 2610.29331](https://arxiv.org/pdf/2610.29331)
- Judge over a candidate list: p(yes / no / maybe | guess is true, question), summing to 1, for each listed guess. — [arXiv 2610.20832](https://arxiv.org/pdf/2610.20832)
- Question-type classifier labels (constraint-seeking, hypothesis-seeking, unknown) are used to analyse question strategy. — [arXiv 2607.03426](https://arxiv.org/pdf/2607.03426) (snippet)

### Inferences
- A practical JSON design implied by these patterns (my synthesis, not taken from any one source):
  - Guesser turn output:
    - `{"candidates":[{"name":...,"p":...}], "candidate_questions":[{"q":..., "expected_yes_fraction":...}], "action":"ask"|"guess", "question":..., "guess":...}`
  - Likelihood call output:
    - `{"entity":..., "question":..., "p_yes":0.0-1.0, "p_no":..., "p_unknown":...}`
    - Batch many entities per call for cost.
- Use constrained or structured decoding (JSON schema) to prevent malformed outputs. Keep the belief math in code, not in the model's prose.

### Gaps
- I did not obtain the verbatim prompts from EDA, UoT, BED-LLM or GuessingGame (the repos exist, but I did not fetch the script contents).
- I found no engineering blog that documents JSON schemas for an LLM Akinator clone in detail.
