# Classic (non-LLM) Algorithms Behind Akinator-Style Guessing Games

> Method note (researcher, 2026-11-25): direct page fetching was blocked in this session (wikipedia.org, akinator.com and patents.google.com did not resolve). All findings below come from web-search result summaries/snippets of the cited URLs, not from reading the full pages. The worked numeric examples are my own derivations and are labelled as such under "Inferences". Most primary sources on Akinator and 20Q are old (2005–2013); I found no 2025–2026 technical disclosure from Elokence.

## 1. What is publicly known about how Akinator works (confirmed vs. speculation)

### Takeaway
Elokence has never published Akinator's algorithm. The confirmed facts are only these: it runs on Elokence's in-house engine "Limule", it launched in 2007, it has been played billions of times, it asks up to about 25 questions before its first guess, it learns from players, and after failed guesses it asks the player for the character's name. Descriptions of it as Bayesian, a decision tree or "halving the candidates" are informed speculation by outsiders.

### Cited Findings
**Confirmed / official or near-official**
- Elokence's own FAQ says Akinator uses "the program Limule published by Elokence.com. The algorithm we use is an original creation. How we created it is our little secret." — [Akinator official page "Everything you've always wanted to know about Akinator"](https://en.akinator.com/content/6/everything-you-ve-always-wanted-to-know-about-akinator) (via search snippet)
- English Wikipedia infobox: developer Elokence; engine Limule; release August 2007. — [Wikipedia: Akinator](https://en.wikipedia.org/wiki/Akinator)
- Wikipedia: implementation details "are not shared but they fall in the field of statistical classification or expert systems". The system "learns the best questions to ask through experience from past players". If it guesses wrong several times, the game "will prompt the user to input the item's name to expand its database of choices". — [Wikipedia: Akinator](https://en.wikipedia.org/wiki/Akinator)
- Question budget: a guess comes before 25 questions are asked (web version). — [Wikipedia: Akinator](https://en.wikipedia.org/wiki/Akinator); [Kotaku game page](https://kotaku.com/games/akinator)
- Usage: "since it was first published, the game was played billions of times" (2023 peer-reviewed paper on Akinator's question asking, dating it to about 2007 and Elokence). — [MDPI Big Data & Cognitive Computing 7(1):26 (2023)](https://www.mdpi.com/2504-2289/7/1/26)
- A French video interview with creator Arnaud Mégret, "Les secrets d'Akinator", cites "5 milliards de parties jouées, 15 ans de loyaux services" (5 billion games, 15 years, so about 2022). — [YouTube](https://www.youtube.com/watch?v=V08q9FEmnwY) (title/description snippet only)
- Answer options: yes / no / don't know / probably / probably not. These are softer than binary answers. — [DEV Community: ChatGPT vs Akinator](https://dev.to/cloutboi/chatgpt-vs-akinator-4ie1)

**People and dates (sources conflict)**
- French sources credit Arnaud Mégret (head of a start-up in Mainvilliers) with creating the game in 2007, and say Elokence was founded at the end of 2007. — [PLKR: "Akinator, le génie qui devine..."](https://www.plkr.org/akinator-genie/); [serer.fr: Arnaud Megret : Akinator](https://serer.fr/?p=1548)
- Other sources say it was developed in 2007 by "two French programmers, Jeff Deleau and Arnaud Megret". A low-quality site instead names "Antoine Teissier". — summarised in search results incl. [Wikipedia](https://en.wikipedia.org/wiki/Akinator); [IBTimes](https://ibtimes.com/how-does-akinator-work-behind-genie-reads-your-mind-1514510). Conflicting; Mégret is the most consistent name.
- Conflict: an August 2007 release versus "Elokence founded end of 2007". The engine or company may predate the formal incorporation. Unresolved.

**Speculation / secondary claims (label as such)**
- The French blog PLKR describes Limule as an inference engine whose "approach is probabilistic, close to a Bayesian model". This is a secondary claim, not an Elokence statement. — [PLKR](https://www.plkr.org/akinator-genie/)
- A commentator quoted by IBTimes reasons that the game likely tries to split the remaining possibilities as close to half as possible with each question. — [IBTimes: How does Akinator work?](https://ibtimes.com/how-does-akinator-work-behind-genie-reads-your-mind-1514510)
- The 2023 MDPI paper notes that Akinator "needs some strategy for selecting questions, otherwise it would need to ask an enormous number of questions", and links the likely strategy to binary-search-style splitting. — [MDPI 2023](https://www.mdpi.com/2504-2289/7/1/26)
- Fan sources claim that after a correct guess, "your answers and the score it has obtained are stored in that character's data". — [akinator.my (fan site)](https://akinator.my/) (unverified)
- Mobile version: NamuWiki says up to 30 questions before the first guess (5 more than web) and a maximum of 80 questions before the genie "loses". — [NamuWiki: Akinator](https://en.namu.wiki/w/Akinator) (unverified for the current web game)
- Knowledge-base size: published numbers range from "over 3,000 characters" to "millions of entities". All come from unofficial sites with no citation. — summarised in search results ([casavirginia.mx](https://casavirginia.mx/meet-akinator-the-black-award-winning-ai-that-can-guess-your-character-in-just-a-few-questions), [akinator.lol](https://akinator.lol/)). Treat as unknown.

### Inferences
- The behaviour Akinator shows publicly is consistent with a probabilistic classifier over a character x question table learned from play. That behaviour is: it accepts "probably"/"don't know", it recovers from a wrong answer, it keeps playing after a wrong guess, and it improves with play. A strict decision tree that eliminates candidates outright would not behave this way. The "close to Bayesian" description fits this, but it remains unconfirmed.
- The wording "learns the best questions to ask through experience" suggests that question selection uses learned answer statistics, such as information gain over learned probabilities, rather than a hand-built tree.

### Gaps
- No official character/question counts, knowledge-base schema or moderation process found. Elokence is known to review user-submitted content, but I found no source describing it.
- No official description of how contradictory answers are weighted, or of the stopping threshold.
- No 2024–2026 technical update from Elokence. I could not verify whether Akinator now uses any LLM or ML components.

## 2. Core algorithms: information gain, Bayesian updates, decision trees, 20Q neural net

### Takeaway
The standard recipe has four parts. (a) Keep a posterior P(c | answers) over candidates. (b) Ask the question with the largest expected information gain, which equals the largest expected drop in posterior entropy. (c) Update the posterior with Bayes' rule using learned likelihoods P(answer | candidate, question). (d) Guess when one candidate dominates. ID3-style trees are the noiseless, offline special case of the same idea. 20Q's "neural network" is a learned object x question weight matrix used in two modes: score objects from the answers, and rank questions.

### Cited Findings
- Entropy and information gain as used in ID3: H(S) = −Σ_i p_i log2 p_i; Gain(S,A) = H(S) − Σ_v P(v) · H(S_v). — [Temple CIS587: Building Classification Models: ID3 and C4.5](https://cis.temple.edu/~giorgio/cis587/readings/id3-c45.html); [UPenn CIS519 decision-tree lecture](https://www.cis.upenn.edu/~cis519/fall2015/lectures/02_DecisionTrees.pdf)
- ID3 is Quinlan 1986 (some references give 1979). C4.5 is Quinlan 1993. C4.5 uses gain ratio = Gain / SplitInfo to correct ID3's bias toward many-valued attributes, and it skips missing values in gain/entropy computations. — [Wikipedia: C4.5](https://en.wikipedia.com/wiki/C4.5); [Temple CIS587](https://cis.temple.edu/~giorgio/cis587/readings/id3-c45.html)
- Bayesian adaptive questionnaires choose "the question that maximizes the information gain". Expected entropy is each answer's posterior entropy weighted by that answer's predictive probability. — [Bayesian Network Models for Adaptive Testing, arXiv:1511.08488](https://arxiv.org/pdf/1511.08488); [ADAPQUEST, arXiv:2112.14476](https://arxiv.org/pdf/2112.14476)
- Optimal 20-questions strategy: "ask questions that will split the field of remaining possibilities roughly in half each time". — [Wikipedia: Twenty questions](https://en.wikipedia.org/wiki/Twenty_questions)
- Noisy 20 questions: Jedynak, Frazier & Sznitman show the greedy policy (minimise expected posterior entropy each step) is Bayes-optimal under an entropy loss. Under symmetric noise, bisecting the posterior gives globally optimal policies. — [Jedynak, Frazier, Sznitman, "Twenty Questions with Noise" (2011)](https://people.orie.cornell.edu/pfrazier/pub/2011_JedynakFrazierSznitman_20questions.pdf)
- Hobbyist Bayes implementation (Akinator clone): it applies Bayes' rule to score each character against the answers, but picks the next question at random, with no entropy step. This is a useful baseline and shows why info-gain selection matters. — [Medium/Analytics Vidhya: Building Akinator with Python using Bayes Theorem](https://medium.com/analytics-vidhya/building-akinator-with-python-using-bayes-theorem-216253c98daa); another variant: [Medium: How I Built an Akinator-Style AI Using Bayes' Theorem](https://medium.com/@iamanuragtiwari101/how-i-built-an-akinator-style-ai-using-bayes-theorem-and-a-little-bit-of-magic-df2273e3f580)
- An open-source Akinator-like engine in T-SQL (KB) orders candidate questions by entity weight. — [GitHub nesterovsky-bros/KB](https://github.com/nesterovsky-bros/KB)

**20Q (Robin Burgener)**
- Patent application "Artificial neural network guessing method and game": US 2006/0230008 A1 (appl. 11/102,105, filed 2005-04-08, status Abandoned), with counterparts CA2505071A1, AU2005203266A1 and EP1710735A1 (EP withdrawn). The claims describe guessing "an object that a user is thinking of, from a set of target objects" with a neural network organised as a matrix of target objects x questions. In the first mode, answers are inputs and objects are outputs, and the network ranks objects. In the second mode it ranks questions. The description mentions demographic factors when teaching the network. — [Google Patents US20060230008A1](https://patents.google.com/patent/US20060230008A1/en); [CA2505071A1](https://patents.google.com/patent/CA2505071A1/en); [Wikipedia: 20Q](https://en.wikipedia.org/wiki/20Q)
- "The game uses the neural-network to choose the next question as well as deciding what to guess." Online version has about 10 million synaptic connections; handheld about 250,000. — [Mavromatic (2005)](https://www.mavromatic.com/2005/11/20q-knows-what-you-are-thinking/)
- "Because 20Q does not simply follow a binary decision tree, answering a question incorrectly will not throw it completely off." It guesses right 80% of the time in 20 questions and 98% if allowed 25. Burgener would not reveal exactly how ("he has a patent to protect"). — [Scienceline (2006): Twenty Questions, Ten Million Synapses](https://scienceline.org/2006/07/tech-schrock-20q/)
- The network learns only by playing; no data is added except visitors' answers. On a miss, the player types the correct object, which joins the network. By Sept 2006: more than 10,000 objects and more than 45 million games. — [20Q.net Q&A](https://www.20q.net/flat/rbqanda.html); [Boing Boing (2005)](https://boingboing.net/2005/05/10/cool-tools-on-20q-a.html)
- The handheld used a pruned network covering 2,000 of the 10,000 most popular objects. — [Coding Horror: Animal, Vegetable, or Mineral?](https://blog.codinghorror.com/animal-vegetable-or-mineral/)
- Grokipedia describes "millions of weighted connections" between questions and objects, adjusted from player responses. This is weak-quality corroboration only. — [Grokipedia: 20Q](https://grokipedia.com/page/20Q)

### Inferences (formulas and worked examples are my derivations)
**Ideal question count.** With N equally likely candidates and noiseless yes/no answers, each answer gives at most 1 bit, so you need at least ⌈log2 N⌉ questions:
- N = 1,000 → 9.97, so 10 questions. N = 100,000 → 16.6, so 17. N = 1,000,000 → 19.93, so 20 (2^20 = 1,048,576). 25 questions cover 2^25 ≈ 33.5M in the ideal case.
- Five-way answers carry at most log2 5 ≈ 2.32 bits in theory. In practice they mostly carry under 1 bit, because players rarely choose "probably" or "don't know" in a way that partitions the candidates. Real games need more questions than log2 N because of noise and imperfect splits.

**Bayesian update.** Posterior: P(c | a_1..a_t) ∝ P(c) · Π_t P(a_t | c, q_t). Do this in log space: score_c += log P(a_t | c, q_t).
- Example: 4 candidates with uniform prior 0.25. Q = "Is your character female?" P(yes | c) = A 0.95, B 0.90, C 0.05, D 0.10. Answer "yes". Unnormalised: 0.2375, 0.225, 0.0125, 0.025 (sum 0.5). Posterior: A 0.475, B 0.45, C 0.025, D 0.05. C and D are down-weighted but not eliminated.

**Expected information gain (mutual information).**
IG(q) = H(C) − Σ_a P(a) · H(C | a) = H(A_q) − Σ_c P(c) · H(A_q | c), where P(a) = Σ_c P(c) P(a | c, q).
- The second form is computationally cheaper. The per-cell answer entropy H(A_q | c) can be precomputed, so each turn needs only one weighted sum plus the entropy of the predictive answer distribution.
- Example above: P(yes) = 0.5, so H(A) = 1 bit. Mean per-candidate noise entropy = avg(h(0.95)=0.286, h(0.9)=0.469, h(0.05)=0.286, h(0.1)=0.469) = 0.378. IG = 0.622 bits. Check via the first form: posterior entropy after "yes" = 1.378 bits (same after "no" by symmetry), and 2 − 1.378 = 0.622.
- An unbalanced question (yes-probability 0.95 for A only, 0.05 for the others) gives P(yes) = 0.275, H(A) = 0.849, IG = 0.849 − 0.286 = 0.562 bits. That is less than the balanced split, which is the formal version of "halve the candidates".
- A noiseless perfect halving gives exactly 1 bit. Noise ε costs about h(ε) bits per question (h(0.05) ≈ 0.29), so with 5% noise a binary question yields at most about 0.71 bits. N = 1M would then need about 20/0.71 ≈ 28 questions, roughly matching 20Q's "80% at 20 questions, 98% at 25".

**Decision trees (ID3/C4.5) vs. the online Bayesian loop.** ID3 precomputes a tree offline by greedy max-gain splits on a hard attribute table. This is fast (O(depth) per game), but one wrong answer sends the player down the wrong subtree. It also needs retraining when the data changes, and handles "don't know" poorly; C4.5's missing-value handling only partly helps. The online loop recomputes the gain each turn against a soft posterior, which tolerates noise and incorporates new data immediately.

**20Q-style net vs. naive Bayes.** The patent's two-mode object x question matrix behaves like a naive-Bayes log-likelihood table. Mode 1 sums weights for the given answers to score objects; mode 2 ranks questions by how well they discriminate among the top-scoring objects. This equivalence is my interpretation; the patent snippets do not give the update rule.

### Gaps
- I could not read the 20Q patent full text, so the exact weight update, answer encoding (20Q also offers "Unknown/Sometimes/Probably/Doubtful/Irrelevant") and question-ranking formula are not confirmed here.
- I found no primary Quinlan paper in the results; the formulas come from course notes.

## 3. Knowledge-base representation and learning from games

### Takeaway
Represent the knowledge base as a sparse 3-D count tensor n[c, q, a] (candidate x question x answer option). Turn it into smoothed likelihoods P(a | c, q) with Dirichlet/Laplace pseudo-counts. After each game whose true answer is known, add the player's answers to that candidate's row. 20Q and (reportedly) Akinator learn this way, purely from play.

### Cited Findings
- 20Q learns only from games: the yes/no answers of visitors. Missed objects are typed in by the player and added. — [20Q.net Q&A](https://www.20q.net/flat/rbqanda.html); [Boing Boing](https://boingboing.net/2005/05/10/cool-tools-on-20q-a.html)
- The 20Q structure is a matrix of target objects x questions with weights (patent claims). — [Google Patents US20060230008A1](https://patents.google.com/patent/US20060230008A1/en)
- Akinator "learns the best questions to ask through experience from past players". — [Wikipedia](https://en.wikipedia.org/wiki/Akinator). After a correct guess, answers are stored in the character's data (fan claim). — [akinator.my](https://akinator.my/)
- A codemia write-up speculates that Akinator recalibrates question weights from how players answer. — [codemia.io](https://codemia.io/knowledge-hub/path/what_kind_of_algorithm_is_behind_the_akinator_game_1) (speculative)

### Inferences (implementation design, mine)
- **Schema:** `counts[c][q] = [n_yes, n_prob, n_dk, n_probnot, n_no]`, stored sparsely. Most (c, q) cells are never observed: with 100k characters x 5k questions there are 5x10^8 cells. Unobserved cells fall back to a per-question global prior (the population answer distribution for q), or to "don't know"-heavy uniform.
- **Smoothed likelihood:** P(a | c, q) = (n_cqa + α·π_qa) / (Σ_a n_cqa + α), where π_q is the global answer distribution for q and α is about 1–5. Example: "Harry Potter / wears glasses?" counts 940 / 30 / 10 / 5 / 15 with α = 1 per option gives P(yes) = 941/1005 = 0.936 and P(no) = 16/1005 = 0.016. Never zero.
- **Learning update:** at game end with confirmed identity c*, for each asked (q_t, a_t) increment n[c*, q_t, a_t]. Optionally do not credit answers from games that ended in a wrong guess the player never corrected. Optionally cap or decay counts so that changing facts (e.g. "is alive?") can drift.
- **New questions:** a player-proposed question starts as a column of global priors. Gather data by occasionally asking it, for example epsilon-exploration, or by asking it at the end of games where the identity is known. Use moderation, since Elokence reportedly moderates user content, though I found no citation for that.
- **Sanity/fraud:** weight each game's contribution by how consistent it was with the consensus row, to limit trolling.

### Gaps
- No source describes Akinator's actual schema, smoothing or anti-vandalism measures.

## 4. Tolerating noisy or wrong answers

### Takeaway
Never set a likelihood to 0. Use soft likelihood tables for the five answer types, so a contradicted candidate loses a bounded amount of log-probability and can recover. Theory (Rényi–Ulam games and noisy 20 questions) quantifies the extra questions lies cost and shows that greedy posterior-bisection is optimal under symmetric noise.

### Cited Findings
- 20Q "does not simply follow a binary decision tree", so an incorrect answer "will not throw it completely off". — [Scienceline](https://scienceline.org/2006/07/tech-schrock-20q/)
- Akinator accepts "probably" and "don't know", allowing softer updates than hard elimination. — [DEV Community](https://dev.to/cloutboi/chatgpt-vs-akinator-4ie1)
- Noisy 20 questions (Ulam's game) was introduced by Rényi and rediscovered by Ulam. In Rényi's model the oracle lies at random with fixed probability; in Ulam's, the number of lies is bounded and may be adversarial. — [Asynchronous Decentralized 20 Questions, arXiv:1511.03144](https://arxiv.org/pdf/1511.03144); [Collaborative 20 Questions, arXiv:1306.1922](https://arxiv.org/pdf/1306.1922)
- The probabilistic bisection algorithm (Horstein's scheme) comes from coding over a binary symmetric channel with feedback. — [arXiv:1511.03144](https://arxiv.org/pdf/1511.03144)
- Greedy min-expected-entropy is Bayes-optimal; bisecting the posterior is optimal under symmetric noise. — [Jedynak et al. 2011](https://people.orie.cornell.edu/pfrazier/pub/2011_JedynakFrazierSznitman_20questions.pdf)
- "Half-lie" Rényi–Ulam variant applied to microscopy search. — [Nature Sci. Rep. 2017](https://www.nature.com/articles/s41598-017-14876-x)
- Survey: "Twenty Questions with Random Error" (Foundations and Trends). — [ACM DL](https://dl.acm.org/doi/abs/10.1561/0100000144)

### Inferences (mine)
- **Five-answer likelihood table:** a common practical alternative to per-cell counts maps answers to targets {yes 1.0, probably 0.75, don't know 0.5, probably not 0.25, no 0.0}. Store the mean target per (c, q) and compute P(a | c, q) via a kernel around that mean plus a noise floor ε (e.g. 0.02–0.05). "Don't know" should be nearly uninformative: give it a likelihood that is about equal across candidates unless the data show it is character-specific.
- **Cost of one lie:** with the smoothed example above, a wrong "no" multiplies the true character's odds by 0.016/0.936 ≈ 1/59, about −5.9 bits. Two or three subsequent strongly diagnostic answers (each worth about 3–4 bits of likelihood ratio) recover it. With hard elimination it would be lost forever.
- **Ulam bound for one lie:** with q yes/no questions and at most one lie you need 2^q ≥ N·(q+1) (volume bound). For N = 10^6, q = 25 works (33.5M ≥ 26M) but q = 24 does not, so one lie costs at least about 5 extra questions over the noiseless 20. This matches Akinator's and 20Q's roughly 25-question budgets.
- **Robustness extras:** use a temperature on the likelihoods (raise to a power below 1) to avoid overconfidence from naive-Bayes correlated questions, such as "is male?" and "has a beard?". After a rejected guess, multiply that candidate by a small factor rather than 0, in case the player misclicked.

### Gaps
- I found no source on Akinator's actual noise model, or on player error rates per answer type.
- I could not retrieve a citable source for Pelc's result that 25 questions are needed for 10^6 with one lie; the bound above is derived.

## 5. Stopping/guessing and learning new characters

### Takeaway
Guess when the top posterior exceeds a threshold, or when the question budget is hit (Akinator: about 25 on the web; 20Q: 20, extendable to 25). On a wrong guess, suppress that candidate and continue. After repeated failure, ask the player for the name, and seed or create that character's row from the game's answers.

### Cited Findings
- Akinator makes its guess before 25 questions. Repeated wrong guesses prompt the player to supply the answer. — [Wikipedia: Akinator](https://en.wikipedia.org/wiki/Akinator)
- Mobile Akinator reportedly asks up to 30 questions before a guess and up to 80 in total before giving up. — [NamuWiki](https://en.namu.wiki/w/Akinator) (unverified)
- 20Q: 80% correct at 20 questions, 98% at 25. On a miss, the user types the object, which is added. — [Scienceline](https://scienceline.org/2006/07/tech-schrock-20q/); [20Q.net Q&A](https://www.20q.net/flat/rbqanda.html)
- Implementation blogs describe guessing "once one candidate clearly leads". — [DEV Community](https://dev.to/cloutboi/chatgpt-vs-akinator-4ie1)

### Inferences (mine)
- **Stopping rule:** guess if p_max ≥ τ (e.g. τ ≈ 0.85–0.95), or if p_max / p_second ≥ r (e.g. r ≥ 10), or if the turn count reaches the budget. A decision-theoretic version: guess when p_max · V_win > E[value of asking one more question]. Also guess early if the best remaining IG falls below a floor (e.g. 0.05 bits), since more questions won't help.
- **After a wrong guess:** set P(c_guessed) to a small value (or 0), renormalise, and continue asking. Optionally lower τ for later guesses and give the player a "continue" option, as Akinator does.
- **New character:** if the name the player supplies does not exist, fuzzy-match it against existing names and aliases to avoid duplicates, then create a row whose counts equal this game's answers. Unobserved questions inherit global priors. Hold the row in a moderation queue, and possibly ask the player 2–5 extra high-coverage questions to bootstrap it. If the name exists, add this game's answers to its counts. That is exactly the case where the KB was wrong or incomplete, so it is the most valuable training signal.
- **New question:** to separate the failed guess from the true character, ask "what question would distinguish X from Y?" This is the classic "animal game" expert-system learning loop.

### Gaps
- No public Akinator threshold value or formula.

## 6. Computational cost and optimizations

### Takeaway
Naive expected-information-gain selection costs O(N · Q · A) per turn (candidates x questions x answer options). That is about 10^9 operations for 100k x 2k x 5, so production systems must prune candidates to the probability-mass "head" and restrict which questions are considered. Vectorised or sparse computation makes this practical, at milliseconds per turn.

### Cited Findings
- The 20Q handheld fit only 2,000 of 10,000 objects and about 250k connections, against about 10M online. This is evidence that pruning or compression to the most popular objects is a standard trade-off. — [Coding Horror](https://blog.codinghorror.com/animal-vegetable-or-mineral/); [Mavromatic](https://www.mavromatic.com/2005/11/20q-knows-what-you-are-thinking/)
- The KB T-SQL engine ranks questions by entity weight inside a database, a set-based alternative to in-memory scoring. — [GitHub nesterovsky-bros/KB](https://github.com/nesterovsky-bros/KB)
- Greedy one-step entropy minimisation is optimal in the noisy-20Q model, so no expensive multi-step lookahead is required. — [Jedynak et al. 2011](https://people.orie.cornell.edu/pfrazier/pub/2011_JedynakFrazierSznitman_20questions.pdf)

### Inferences (mine)
- **Posterior update** is cheap: O(N) per answer (one column lookup plus an add in log space).
- **Question selection** is the hot path. Optimisations:
  1. **Candidate pruning:** use only the top-K candidates covering ≥ 99–99.9% of posterior mass (K ≈ 200–2,000) for IG computation. The tail contributes negligibly but stays in the posterior, so it can resurface.
  2. **Use the cheap IG form:** IG = H(Σ_c p_c L_cq) − Σ_c p_c H(L_cq), with H(L_cq) precomputed per cell. This is one dense matrix-vector product, P (K) times likelihoods (K x Q·A), plus a weighted sum of precomputed entropies.
  3. **Sparsity:** cells equal to the question's global prior contribute identically. Compute with sparse matrices and add the default-cell contribution analytically.
  4. **Question pre-filtering:** drop already-asked questions and their near-duplicates, which are highly correlated (e.g. via precomputed question-question mutual information). Consider only questions with enough data for the current top candidates.
  5. **Early turns:** the first 1–3 questions from a uniform or popularity prior are identical for every game, so precompute and cache them, or a shallow tree of them.
  6. **Numerics:** use log-space scores, float32 and SIMD/BLAS. 2,000 x 5,000 x 5 = 5x10^7 multiply-adds takes about 10 ms on one modern CPU core with BLAS.
- **Learning:** count increments are O(questions asked) per game, about 25. Recompute the smoothed likelihoods and per-cell entropies lazily or in batch.

### Gaps
- No public figures on Akinator's or 20Q's server-side compute or latency. The cost estimates above are my own back-of-envelope figures.
