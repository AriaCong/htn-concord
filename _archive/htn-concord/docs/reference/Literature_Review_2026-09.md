# Literature review — full sweep of 2026-09-09

**Purpose.** A whole-field sweep of work adjacent to HTN-Concord, classified into nine categories, with
ground-truth source, database, and evaluated models recorded per paper. Supersedes and absorbs
`Literature_Landscape_2026-08.md` (2026-08-05, 27 entries) — that file stays as the record of what was
known at the pilot-design freeze; this one is the working list.

**Browsable version:** https://claude.ai/code/artifact/61426d77-601f-44df-bd8f-896aeee8b5d1
(filterable by category and threat level; same content, same figures).

**Verification levels — respect them.** `full` = paper full text fetched and figures checked;
`abs` = official abstract page only; `search` = search-result snippet only, **must be read in full
before citation**. This sweep: 4 full · 9 abs · 47 search.

**Chinese pair:** not yet written (open action, sub-project A).

---

## 0. Four conclusions that change the manuscript

1. **"Turning a guideline into an executable program" is no longer a claim.** At least six 2026 papers
   occupy it: CPGPrompt, MedGuideX, GuideSkill, Guideline2Graph, MedGUIDE, MEGA-CDP. The engine is
   *inherited practice*; cite all six in related work and move the novelty to RQ2.

2. **But nobody uses the engine as the label source.** Their guideline programs are a tree the model
   walks (CPGPrompt), a training signal (MedGuideX), or an output verifier (T2D-Bench). The largest,
   MEGA-CDP, has GPT-5.2 *generate* the reference pathways and GPT-5.4 Mini *judge* the answers —
   exactly the route Principle 1 rejects. This is the strongest available argument for our design.

3. **The closest prior art for C0−C1 is n = 80.** Roeschl et al. (JMIRx Med 2025) compared original
   medical reports against **manually written** case summaries on 80 aortic-stenosis patients
   (κ −0.47…0.22 → −0.02…0.63). Manual summaries cannot guarantee information invariance, so that
   delta confounds "easier to read" with "summary quietly added facts." Our renderer proves invariance
   by test at 4,806 patients.

4. **The nearest methodological relative is in oncology, not hypertension.** ODBB (arXiv 2608.28592)
   uses a **fully deterministic scorer with zero LLM inference**, 14 typed failure labels, and two
   oncologists validating 225 items (weighted κ 0.939 / 0.790). That is the bar for HC-49 and HC-71 —
   and proof the "deterministic scoring + clinician validation" route is publishable.

---

## 1. Executable guidelines / guideline structuring — the direct competitors

| Paper | ID / venue | What it does | Ground truth | Data | Models | Threat | V |
|---|---|---|---|---|---|---|---|
| **CPGPrompt** | [2601.03475](https://arxiv.org/abs/2601.03475), 2026-01 | Narrative guideline → decision tree the LLM executes | not stated in abstract | synthetic vignettes; headache, low back pain, prostate cancer | not listed | high | abs |
| **MedGuideX** | [2605.26567](https://arxiv.org/abs/2605.26567), 2026-05 | Extracts executable decision logic → factual + counterfactual training data | derived from executable guideline logic | 4 reasoning benchmarks (unnamed) | not listed | high | abs |
| **GuideSkill** | [2607.26160](https://arxiv.org/abs/2607.26160), 2026-07 | Guidelines → executable functions emitting diagnostic-support scores | guideline-derived skills | 4 benchmarks | Qwen3.5-9B + 3 backbones | high | abs |
| **Guideline2Graph** | [2604.02477](https://arxiv.org/abs/2604.02477), 2026-04 | Multimodal parsing of guideline PDFs (flowcharts, tables) → executable decision graphs | n/a (construction) | guideline documents | n/a | med | search |
| **MedGUIDE** | [2505.11613](https://arxiv.org/abs/2505.11613), NeurIPS 2025 | 55 NCCN decision trees, 17 cancers → 7,747 MCQs from LLM-generated scenarios | NCCN trees + LLM scenarios + reward-model/judge filtering | NCCN; synthetic scenarios | 25 models | high | search |
| **MEGA-CDP** | [2608.26592](https://arxiv.org/abs/2608.26592), 2026-08 | 2,274 EN/CN guidelines → 42,353 cases with reference decision pathways; single- and multi-turn | **GPT-5.2 generates the reference pathways**; human check on ~5.4% of guidelines | 2,274 CPGs, synthetic vignettes | 16: Gemini-3.1-Pro-Preview, GPT-5.4, Claude-Sonnet-4.6, Qwen3 family, DeepSeek-R1-Distill-32B, gpt-oss-120b, LLaMA-3.3-70B, HuatuoGPT-o1 7B/72B, Baichuan-M3-235B | high | **full** |
| **CPGBench** | [2603.25196](https://arxiv.org/abs/2603.25196), 2026-03 | 3,418 guidelines, 9 countries, 24 specialties → 32,155 recommendations, one multi-turn dialogue each | guideline text; 56 clinicians validated | 3,418 CPG documents | 8 LLMs | med | abs |
| **MedProbeBench** | [2604.18418](https://arxiv.org/abs/2604.18418), 2026-04 | Evaluates deep-research agents *generating* guideline reports; 1,200+ rubric criteria | guidelines as expert reference | guideline corpus | deep-research agents (best 0.631) | low | search |
| **T2D-Bench** | [2606.24145](https://arxiv.org/abs/2606.24145), 2026-06 | Multi-layer KG (UMLS/DrugBank/SIDER + computable ADA 2026 rules) + 100 vignettes + Evidence Gate | graph "must-trigger" evidence IDs | UMLS, DrugBank, SIDER, ADA SoC 2026 | not located | med | search |
| **AMEGA** | [npj Digit Med 2024](https://www.nature.com/articles/s41746-024-01356-6) | 20 scenarios, 13 specialties, 135 open questions, 1,337 weighted scoring elements | scoring elements + **GPT-4 as grader** | self-authored scenarios | 17 LLMs; GPT-4 41.9/50 vs new graduate 25.8/50 | med | search |

**Consequence.** Frame the engine as inherited. The differentiators that survive: engine as *label
source*, reasoning-trace output, treatment initiation rather than diagnosis, matched synthetic and
real-EHR arms on one schema, clinician adjudication of the encoding.

---

## 2. Guideline-concordance studies on real patient data

| Paper | ID / venue | What it does | Ground truth | Data | Models | Threat | V |
|---|---|---|---|---|---|---|---|
| **Roeschl et al.** | [JMIRx Med 2025](https://xmed.jmir.org/2025/1/e74899) | 80 severe aortic stenosis (SAVR 24 / TAVR 56); original reports vs **manually written** summaries | institutional heart-team decision, 2022 | single-centre real records, n=80 | BioGPT, GPT-3.5, GPT-4, GPT-4 Turbo, GPT-4o, LLaMA-2, Mistral, PaLM 2, DeepSeek-R1 | **high** | search |
| **ODBB** | [2608.28592](https://arxiv.org/abs/2608.28592), 2026-08 | 2,005 oncology decision points: 1,586 NCCN items (69 cancer workspaces, frozen 2026-03) + 419 CRC case-report items | NCCN nodes; **deterministic scorer, zero LLM inference**, 14 failure labels; 2 oncologists on 225 items | NCCN + PubMed CRC case reports | 9: Claude Sonnet 4.6, GPT-5.5, Gemini 2.5 Pro, Gemini 3.1 Pro Preview, Qwen 3.6-Plus, DeepSeek V4 Pro, GLM-5, GLM-5.1, Minimax M2.7 | **high** | **full** |
| HCC treatment | [PubMed 41528959](https://pubmed.ncbi.nlm.nih.gov/41528959/), 2026-01 | National registry; concordance with physician decisions | **physician behaviour**, not guideline | national HCC registry | ChatGPT-4o 31.1%, Gemini 2.0 32.7%, Claude 3.5 26.8% | med | search |
| Breast cancer MDT | [PubMed 42121209](https://pubmed.ncbi.nlm.nih.gov/42121209/) | Agreement with radiology-led tumour board | MDT consensus | single centre | not located | low | search |
| Musculoskeletal CPG | [PubMed 39173690](https://pubmed.ncbi.nlm.nih.gov/39173690/), 2024 | LLM advice vs evidence-based CPGs | CPG recommendations | guideline items | contemporary general models | low | search |
| Paediatric ABA (parent-facing) | [PubMed 42509602](https://pubmed.ncbi.nlm.nih.gov/42509602/) | 27 PIDS/IDSA recommendations reworded as parent prompts | PIDS/IDSA | 27 recommendations | not located | low | search |

**Note on ODBB's key numbers** (worth quoting): 42.1% of items answered correctly by *zero* of nine
models; in 3–9% of items models stated the correct next step in reasoning but did not commit to it.
Gold-answer audit on 80 zero-correct items: 95% traced to NCCN nodes, 2.5% flagged clinically wrong.

**Note on HCC.** Its reference standard is what physicians actually did. That is precisely what
HTN-Concord avoids — physician behaviour carries therapeutic inertia and confounding by indication.
Cite it when defending the choice of guideline-as-reference.

---

## 3. Hypertension-specific

| Paper | ID / venue | What it does | Ground truth | Data | Models | Threat | V |
|---|---|---|---|---|---|---|---|
| **LLMs in Common Hypertension Scenarios** | [Hypertension (AHA) 2026](https://www.ahajournals.org/doi/10.1161/HYPERTENSIONAHA.125.25492) | 51 vignettes, 3 blinded raters, accuracy + safety scales | human blinded expert rating | 51 self-authored vignettes | GPT-4 (83% acc / 86% safe), Gemini, Med-PaLM; experts 92% / 93% | **high** | search |
| Cascade Framework agent | [PubMed 41064862](https://pubmed.ncbi.nlm.nih.gov/41064862/), Hypertension 2026 | Dify-built cascade agent; 6-configuration benchmark + external validation in a suspected-hypertension cohort | not located | real suspected-HTN cohort | ChatGPT-4o, ChatGPT-4o-mini, DeepSeek-V3 (± Cascade) | med | search |
| Multitype prompt engineering | [npj Digit Med 2026](https://www.nature.com/articles/s41746-026-02645-y) | Prompt strategies for HTN treatment decisions | expert judgement | HTN decision items | ChatGPT-4.1 + Guidance-Self-Consistency 91.3%; DeepSeek-V3 zero-shot 62.7% | med | search |
| Secondary hypertension | [PMC13409298](https://pmc.ncbi.nlm.nih.gov/articles/PMC13409298/) | 10 expert-written cases, blinded cross-sectional | expert consensus | 10 vignettes | GPT-5.2, Claude Sonnet 4.6, Gemini 3.0 Pro | low | search |
| Free-tier vs ESC 2024 | [PMC13015764](https://pmc.ncbi.nlm.nih.gov/articles/PMC13015764/) | 40 questions on diagnosis, targets, lifestyle, comorbidity | ESC 2024 text | 40 questions | free-tier models | low | search |
| ChatHTN | [Sci Rep 2026](https://www.nature.com/articles/s41598-026-47937-1) | Hypertension consultation model | not located | not located | fine-tuned model | low | search |
| HTN medication recommendation (non-LLM) | [JMIR Med Inform 2025](https://medinform.jmir.org/2025/1/e74170) | Graph/neural model over comorbidity–lab–drug synergies | actual prescriptions | **MIMIC-III / MIMIC-IV, ICD-9 HTN anchors selected with clinical guidance** | in-house model | med | search |

**Two things to carry into the manuscript.**
- The prompt-engineering paper moves one model from 62.7% to 91.3% by prompt strategy alone. That is
  the strongest external argument that our **absolute** scores are uninterpretable and the ladder
  deltas carry the paper.
- The JMIR Med Inform paper confirms an ICD-anchored MIMIC hypertension cohort is a recognised design
  — a precedent for HC-13's cohort route, though its target is prescription imitation, not concordance.

---

## 4. Abstention and uncertainty

| Paper | ID / venue | What it does | Key finding for us | Threat | V |
|---|---|---|---|---|---|
| **ClinDet-Bench** | [2602.22771](https://arxiv.org/abs/2602.22771), 2026-02 | Built from clinical scoring systems; splits incomplete-information scenarios into **determinable** vs **undeterminable** | Models fail *both ways* — premature judgement **and** excessive abstention — while explaining the scoring knowledge correctly. Maps one-to-one onto our two abstention rates. | high | abs |
| **Knowing When to Abstain** (MedAbstain / MedQAbstain) | [EACL 2026 · 2601.12471](https://arxiv.org/abs/2601.12471) | Medical MCQA rebuilt with gold answer removed and an explicit "I abstain" option; conformal prediction + adversarial perturbation | (a) models overcommit even when the question is hidden → the metric discriminates; (b) **an explicit abstain option moves abstention far more than input perturbation** → our prompt's ABSTAIN presentation is an experimental variable, freeze and disclose it | med | abs |
| When silence is safer | [npj Digit Med 2026](https://www.nature.com/articles/s41746-026-02882-1) | Decision-theoretic framework for answer-vs-withhold under harm | Position our two-rate reporting inside this framework rather than inventing terminology | med | search |
| Abstention as prompt artifact | [2507.16199](https://arxiv.org/abs/2507.16199) | Abstention rate shifts with prompt wording | Same warning, independently | med | search |
| KnowGuard | [2509.24816](https://arxiv.org/abs/2509.24816) | Knowledge-driven abstention for multi-round reasoning | Method candidate if we ever add an abstention-improving condition | low | search |

---

## 5. Medication safety and contraindications

| Paper | ID / venue | What it does | Ground truth | Data | Models | Threat | V |
|---|---|---|---|---|---|---|---|
| **RxSafeBench** | [2511.04328](https://arxiv.org/abs/2511.04328) | Risks **embedded in** doctor–patient dialogue; 2,443 scenarios (1,063 contraindication, 1,380 interaction), 3-option MCQ | **RxRisk DB**: 6,725 contraindications, 28,781 interactions, 14,906 indication–drug pairs (35k+ entries) | synthetic consultations | Qwen2-7B/72B, Llama-3.1-8B/70B/405B, DeepSeek-R1, GPT-4, ChatGLM-Turbo | **high** | **full** |
| **RxEval** | [2605.14543](https://arxiv.org/abs/2605.14543), 2026-05 | Pick the medication–dose–route triple from real prescriptions plus perturbation-generated distractors | real prescriptions | 1,547 questions / 584 patients / 18 diagnostic categories / 969 drugs | 16 LLMs; best EM 46.10%, F1 45.18–77.10 | med | abs |
| Counterfactual sensitivity | [2608.03028](https://arxiv.org/abs/2608.03028), 2026-08 | Can patient information *withdraw* a safety warning? | counterfactual patient attributes | synthetic | not located | med | search |
| CSEDB | [npj Digit Med](https://www.nature.com/articles/s41746-025-02277-8) | 32 physicians, 30 metrics, 2,069 items; safety and effectiveness on separate tracks | physician-designed criteria | 2,069 items | not located | med | search |
| NHS primary-care med reviews | [2512.21127](https://arxiv.org/abs/2512.21127) | Real-world medication safety review | pharmacist/clinician review | NHS primary care | not located | low | search |
| MPIB | [2602.06268](https://arxiv.org/abs/2602.06268) | Medical prompt-injection attacks | n/a | synthetic attacks | not located | low | search |

**Direct bearing on HC-95.** RxSafeBench's headline: best contraindication accuracy 59.27%
(DeepSeek-R1), interaction accuracy 38.12%; models are markedly worse when risk is **implied** rather
than explicitly stated. That is precisely the property our facts-only renderer creates, so the stress
set should be designed to be comparable — but ours adds a decision label, an abstention option, and a
false-positive rate, which RxSafeBench does not have. Counterfactual sensitivity (2608.03028) is the
citation for `contraindication_false_positive`: models keep warnings after the trigger is gone.

---

## 6. Reasoning traces and failure localization

| Paper | ID / venue | What it does | Key finding for us | Threat | V |
|---|---|---|---|---|---|
| **From Scores to Steps** | [EMNLP 2025 · 2509.16584](https://arxiv.org/abs/2509.16584) | Rebuilds MedCalc-Bench and scores **formula selection / entity extraction / arithmetic separately**; automatic error attribution | GPT-4o falls **62.7% → 43.6%** under the granular framework. The single best evidence that one headline score hides errors. MedRaC (RAG + Python execution) lifts models 16.35% → 53.19%. | high | search |
| **Internal Representation, Not Clinical Knowledge** | [2605.29889](https://arxiv.org/abs/2605.29889), 2026-05 | **2×2**: structured vs natural-language input × MCQ vs free-text output on the same triage cases; sparse autoencoders locate where features go silent | The closest existing paired, information-invariant input design to C0−C1. Small models (4B/12B/Qwen), triage task, mechanistic goal. Backs our design's legitimacy; we must state the difference (attributable decision loss, not internal representation). | high | search |
| Clinical Reasoning Graphs | [2606.29876](https://arxiv.org/abs/2606.29876), 2026-06 | 5 node types / 7 edge types ontology over diagnostic traces | Graph similarity 0.488 when both correct vs 0.484 when both wrong → competence without consistency. **Direct argument for reporting across-replicate SD (k=5), not just a mean.** | med | abs |
| FaithMed | [2607.01440](https://arxiv.org/abs/2607.01440), 2026-07 | Clinician rubrics + step-level process reward RL | Trace-scoring comparator, but it is a *training* method and its reference steps are rubrics, not a computable engine | med | search |
| MedThink-Bench + LLM-w-Rationale | [npj Digit Med 2025](https://www.nature.com/articles/s41746-025-02208-7) | 500 questions, expert-annotated fine-grained reasoning trajectories, LLM-as-judge step scoring | **The prevailing way to score traces: human-annotated trajectories + an LLM judge.** Our difference — engine-generated trace, no LLM judge — belongs in related work explicitly. | med | search |
| MedRECT | [2511.00421](https://arxiv.org/abs/2511.00421) | Error localization *within* clinical text | Reasoning models 71.4–83.7% vs non-reasoning 42.2–52.6% on sentence extraction | low | search |
| Why LLM clinical reasoning fails | [medRxiv 2026.01.26.26344845](https://www.medrxiv.org/content/10.64898/2026.01.26.26344845) | Sparse autoencoders on clinical failure | Mechanistic complement, not a competitor | low | search |

---

## 7. Real-EHR benchmarks

| Paper | ID / venue | Database | Ground truth | Models | Threat | V |
|---|---|---|---|---|---|---|
| **RealICU** | [2605.13542](https://arxiv.org/abs/2605.13542), 2026-05 | **MIMIC-IV**; Gold 94 patients / 930 windows, Scale 11,862 windows | **hindsight**: senior physicians label after seeing the full trajectory, not the action actually taken | memory-augmented and standard agents | med | abs |
| **EHRBench** | [2605.30637](https://arxiv.org/abs/2605.30637), 2026-05 | **MIMIC-III, MIMIC-IV, PROMOTE** (private, anti-contamination); 960,067 QA items | LLM relation extraction (HuatuoGPT-o1-8B) + KB verification (SemMedDB/UMLS/PubMed) + deterministic templating | 31 models incl. GPT-5.2 (70.91%), GPT-4.1, Llama-3.3-70B (67.28%), Med42-8B, UltraMedical-8B | med | **full** |
| ClinEnv | [2606.02568](https://arxiv.org/abs/2606.02568), 2026-06 | MIMIC-IV + MIMIC-IV-Note | not located | not located | med | search |
| LongMedBench | [2607.09322](https://arxiv.org/abs/2607.09322), 2026-07 | MIMIC-IV; 335 patients, 19.72 visits each | not located | not located | low | search |
| EHRStruct | [2511.08206](https://arxiv.org/abs/2511.08206) | Synthea (synthetic) + eICU | structured tables | not located | low | search |
| CliBench | [2406.09923](https://arxiv.org/abs/2406.09923) | MIMIC family | ICD-10-PCS / LOINC / ATC codes | not located | low | search |

**Two EHRBench results worth quoting.** Treatment selection (69.33%) is substantially easier than
diagnosis (55.02%) and prognosis (46.67%); and **medical fine-tuning gives no consistent gain** over
general models. Also note its anti-contamination move — a private cohort — which is the alternative
solution to the limitation we can only declare.

**RealICU's hindsight labelling** is an independent statement of our position: do not use what the
clinician actually did as ground truth.

**ClinEnv** states outright that it is a research benchmark and not a CDS tool — the same
intended-use posture as Experiment Design §8. Cite it there.

---

## 8. Computation and tool use

| Paper | ID / venue | What it does | Key numbers | Threat | V |
|---|---|---|---|---|---|
| **LLM pipeline for CV risk scores** | [PMC13492338](https://pmc.ncbi.nlm.nih.gov/articles/PMC13492338/) / medRxiv 2025.11.11.25340002 | Separates LLM extraction from **deterministic score computation**; CHA₂DS₂-VASc, HAS-BLED, EuroSCORE II from unstructured text | Krippendorff α **0.78** (pipeline) vs 0.32 (standalone LLM) vs 0.39 (LLM+RAG) vs 0.31 (treating physicians) | high | search |
| MedCalc-Pro | [2607.02879](https://arxiv.org/abs/2607.02879), 2026-07 | Four-stage agent: query rewrite → retrieve/rerank → tool select → execute | — | med | search |
| MedMCP-Calc | [2601.23049](https://arxiv.org/abs/2601.23049), 2026-01 | Fuzzy clinician-style queries, multi-step decisions, MCP tools over structured EHR | — | med | search |

The CV-risk pipeline is the citation that justifies C3 (tool access): extraction and computation
should be separated, and the effect size is large. Our contribution extends it from *computing a
score* to *making the treatment decision the score feeds*.

---

## 9. Methodology and reporting

| Paper | ID / venue | Why it matters | Threat | V |
|---|---|---|---|---|
| **TRIPOD-LLM** | [Nat Med 2025](https://www.nature.com/articles/s41591-024-03425-5) | Our primary reporting framework. **19 main items, 50 subitems**; 14 main + 32 subitems apply across all categories. Interactive checklist site available. HC-93 must transcribe item numbers from the paper. | high | search |
| **The evaluation illusion of LLMs in medicine** | [npj Digit Med 2025](https://www.nature.com/articles/s41746-025-01963-x) | **Only ~5% of medical LLM evaluations run on real EHR data**; the rest are vignettes, expert-written questions, or MCQ exams. Best single sentence for the introduction, and a direct defence of Task C. | high | search |
| Construct validity (position) | [ICML 2025 · 2503.10694](https://arxiv.org/abs/2503.10694) | The frame under which to state "concordance with one guideline's formalization ≠ clinical correctness" | med | search |
| Beyond the Leaderboard | [2508.04325](https://arxiv.org/abs/2508.04325) | Same family, supporting citation | low | search |
| **RAG vs GraphRAG on NICE CKD** | [medRxiv 2025.11.25.25341010](https://www.medrxiv.org/content/10.1101/2025.11.25.25341010v1) | The ready-made C3g comparator, and it predicts the result shape: GraphRAG wins on thresholds and algorithmic decisions via multi-hop, **loses on clarity** (long excerpts obscure the recommendation). C3g must cite it and report a delta, not a first. | high | search |
| EyeRAG | [npj Digit Med 2026](https://www.nature.com/articles/s41746-026-02860-7) | Guideline-only knowledge graph (OphthaKG) + GraphRAG; scored by LLM judges | med | search |
| **Shifting Thresholds (2025 vs 2017)** | [doi 10.1016/j.jacadv.2025.102546](https://doi.org/10.1016/j.jacadv.2025.102546) | NHANES-based eligibility shift under the new guideline. **Not a competitor — an external sanity check** our stage and eligibility distribution must match. | med | search |
| LLM-as-a-Judge in Healthcare (scoping) | [2605.25273](https://arxiv.org/abs/2605.25273), 2026-05 | The cheapest citation for *why we do not use an LLM judge*: it lays out the human-alignment limits of the practice | med | search |
| CLEAR: noise and ambiguity | [2605.01011](https://arxiv.org/abs/2605.01011) | Adjacent to the motivation for the `hard` level; a source of noise types for the HC-51 distractor library | low | search |
| PhysicianBench | [2605.02240](https://arxiv.org/abs/2605.02240) | Agent-shaped, orthogonal to our single-shot structured output | low | search |

---

## 10. What is still unoccupied

1. **A deterministic engine as the label source, emitting a reasoning trace, on treatment initiation.**
   No paper satisfies all of: ground truth computed by hand-written rules (not LLM-generated, not
   hand-annotated) · citation anchors · step-comparable trace · treatment rather than diagnosis.

2. **A large, information-invariant read-vs-reason split.** Roeschl (n=80, manual summaries) and
   Internal Representation (paired 2×2, but triage, small models, mechanistic) bracket it. Nobody has
   done it on treatment decisions, at thousands of cases, with a renderer that *proves* invariance.

3. **Abstention reported as two rates against the same ground truth as the decision.** ClinDet-Bench
   and MedAbstain establish that models fail both ways, but on MCQA, with abstention decoupled from a
   treatment label.

4. **Synthetic and real-EHR arms sharing one schema and one engine.** The real-EHR benchmark family
   and the guideline benchmark family do not intersect, so cross-benchmark drops cannot separate
   "harder text" from "different task."

**Already taken — do not claim:** guideline structuring (six papers); a contraindication stress set
(RxSafeBench); guideline graph vs flat retrieval (NICE CKD).

**Ready to borrow:** step-wise scoring (From Scores to Steps); extraction/computation separation
(CV-risk pipeline); the 5%-real-EHR statistic (evaluation illusion); ODBB's validation design
(deterministic scorer + stratified clinician audit + gold-answer audit of zero-correct items).

---

## 11. Open actions

| # | Action | Where |
|---|---|---|
| 1 | Read in full before citing anything marked `search` (47 of 60) | sub-project D |
| 2 | Rewrite the novelty claim away from "executable guideline" in Master Plan §0 and Experiment Design intro | D |
| 3 | Adopt ODBB's validation design as the template for HC-49 and HC-71 | HC-49 / HC-71 |
| 4 | Freeze and disclose how the prompt presents ABSTAIN (MedAbstain finding) | HC-48 / HC-94 |
| 5 | Benchmark the HC-95 stress set against RxSafeBench's reported rates | HC-95 |
| 6 | Validate the NHANES stage distribution against *Shifting Thresholds* | HC-92 follow-up |
| 7 | Transcribe TRIPOD-LLM's 19 items / 50 subitems from the paper | HC-93 |
| 8 | Write the Chinese pair of this document | A |
