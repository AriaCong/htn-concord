# Literature landscape — sweep of 2026-08-05

**Purpose.** Papers found in the 2026-08-05 sweep that are **not** in the Notion "Reference Papers"
page (compiled 2026-07-24, 8 papers). That page remains the authoritative synthesis for those 8;
this file is the delta and must be folded into it during sub-project D.

**Status:** raw landscape capture. Abstracts fetched for the four executable-guideline papers;
the remainder are captured from search results and titles and **must be read in full before
citation**. Nothing here has been read cover-to-cover.

**Chinese pair:** not yet written — created in sub-project A/D alongside the Notion fold-in.

---

## 0. The headline change since 2026-07-24

**"Executable / computable guideline" is no longer a distinctive framing.** Four papers published
in 2026 occupy ground the Notion synthesis treats as open. The project survives, but the abstract
must not lead with the engine as the novelty — it must lead with the **failure-mechanism
localization** (RQ2) and specifically the **C0−C1 extraction-burden delta**.

---

## 1. Executable-guideline cluster — highest threat, same core mechanism

| Paper | ID | What it does | Threat | Why HTN-Concord survives |
|---|---|---|---|---|
| **CPGPrompt** — *Translating Clinical Guidelines into LLM-Executable Decision Support* | arXiv 2601.03475 | Narrative guideline → structured decision tree; LLM navigates it. Headache, low back pain, prostate cancer. Synthetic vignettes | Same "guideline as executable structure" framing | The LLM *navigates* the tree — the tree is not the answer key. No real EHR. Ground-truth construction unstated in the abstract. Reported failure classes (negation handling, temporal reasoning) are HTN-Concord's predicted classes |
| **MedGuideX** — *Internalizing Decision Logic from Executable Guidelines into LLMs* | arXiv 2605.26567 | Extracts structured decision rules from CPGs; ground truth derived from **deterministic executable guidelines** rather than human annotation | Closest hit on Principle 1 (clinician-free deterministic ground truth) | It is a *training* method, not a benchmark. No reasoning-trace scoring. Diagnosis-flavored (central serous chorioretinopathy, infective endocarditis) |
| **GuideSkill** — *Evolving Executable LLM Agent Skills for Guideline-Grounded Clinical Reasoning* | arXiv 2607.26160 (Jul 2026) | 3,938 CPGs (NICE, WHO, CDC, PubMed) → executable functions over 473 ICD-10 categories. Evaluated on MedCaseReasoning, ER-Reason, MIMIC-CDM-FI, MedThink-Bench. Three-way error taxonomy: candidate omission 60.9%, skill under-scoring 12.6%, distractor selection 26.6% | Scale, plus an error taxonomy in HTN-Concord's space | **Their stated limitation is "fully automated skill generation lacking physician verification" — precisely HC-49.** Diagnosis (ICD codes), not treatment initiation. Ground truth is a diagnosis code, not a guideline decision with a trace |
| **Guideline2Graph** — *Profile-Aware Multimodal Parsing for Executable Clinical Decision Graphs* | arXiv 2604.02477 | Multimodal parsing of guideline PDFs including flowcharts/tables → executable decision graphs | Direct prior art for **C3g** | A construction method, not an evaluation of LLMs against the graph. C3g must cite it as prior art and state the delta |

**Action for the manuscript:** cite all four in related work. Frame HTN-Concord's engine as
*inherited practice*, not novelty, and move the novelty claim to RQ2.

---

## 2. Abstention cluster — comparators for `abstention_appropriateness`

| Paper | Venue / ID | Relevance |
|---|---|---|
| *When silence is safer: a review and decision-theoretic framework for LLM abstention in healthcare* | npj Digital Medicine 2026 (s41746-026-02882-1) | **The citation to engage.** Decision-theoretic formalization of the answer-vs-withhold tradeoff under harm. HTN-Concord's two-rate reporting (over/under-abstention) should be positioned against this framework |
| *Knowing When to Abstain: Medical LLMs Under Clinical Uncertainty* | EACL 2026 (aclanthology 2026.eacl-long.291) / arXiv 2601.12471 | MedQAbstain / MedAbstain benchmarks; conformal prediction + adversarial perturbation + explicit abstain option |
| **KnowGuard** — *Knowledge-Driven Abstention for Multi-Round Clinical Reasoning* | arXiv 2509.24816 | Method comparator |
| *LLM Abstention Can Be a Prompt Artifact, in Addition to Genuine Uncertainty* | arXiv 2507.16199 | **Methodological caution.** Abstention rates move with prompt phrasing — relevant to how HTN-Concord's prompt presents the ABSTAIN option |

**Key supporting finding:** models *systematically overcommit and rarely abstain even when the
question itself is hidden*. This is direct evidence that `abstention_appropriateness` is a
discriminative metric rather than a formality.

**Caution:** the field-wide finding that an explicit abstain option raises abstention far more than
input perturbations means HTN-Concord's prompt design is itself an experimental variable. Fix it in
the freeze and disclose it.

---

## 3. Medication safety / contraindication — comparators for HC-95 and `unsafe_recommendation`

| Paper | ID | Relevance |
|---|---|---|
| **RxSafeBench** — *Identifying Medication Safety Issues of LLMs in Simulated Consultation* | arXiv 2511.04328 | **Direct comparator for the HC-95 stress set.** Thousands of contraindications and drug interactions; finding: models fail when risk is *implied* rather than explicitly stated — exactly HTN-Concord's facts-only vignette design |
| **Rx-LLM** — benchmarking suite for medication-related tasks | PMC12704647 | Comparator |
| *ChatGPT Performance Deteriorated in Patients with Comorbidities When Providing Cardiological Therapeutic Consultations* | PMC12249446 | **Empirical support for the multi-constraint failure claim** — performance degrades with comorbidity load, which is HTN-Concord's central mechanism hypothesis |
| *Vulnerability of LLMs to Prompt Injection When Providing Medical Advice* | PMC12717619 | Prompt injection induced unsafe/contraindicated recommendations in 94.4% of trials. Out of scope but useful for the safety framing |

---

## 4. Failure localization / trace faithfulness — comparators for RQ2

| Paper | ID | Relevance |
|---|---|---|
| **FaithMed** — *Training LLMs For Faithful Evidence-Based Medical Reasoning* | arXiv 2607.01440 | Grounds intermediate reasoning steps in supporting evidence. Direct comparator for `trace_concordance` |
| **Clinical Reasoning Graphs** — *Structured Evaluation of LLM Diagnostic Reasoning Reveals Competence Without Consistency* | arXiv 2606.29876 | Structured reasoning evaluation; the "competence without consistency" finding bears on the k=5 replicate design |
| **MedRECT** — *A Medical Reasoning Benchmark for Error Correction in Clinical Texts* | arXiv 2511.00421 | Error *localization* within clinical text; reasoning models 71.4–83.7% vs non-reasoning 42.2–52.6% on sentence extraction |
| *Why Large Language Models' Clinical Reasoning Fails: Insights from Explainable Deep Learning* | medRxiv 2026.01.26.26344845 | Mechanistic interpretability (sparse autoencoders) applied to clinical failure |
| *Contrastive Attribution in the Wild* | arXiv 2604.17761 | General failure-attribution method |

**Note:** the extraction→reasoning error-compounding claim ("a misclassified assertion on page 3
becomes a phantom adverse event on page 14") appears in this cluster and is the same mechanism as
HTN-Concord's error-propagation measurement in Task C.

---

## 5. MIMIC-IV benchmark family — competes for Task C

| Paper | ID | Note |
|---|---|---|
| **RealICU** — *Do LLM Agents Understand Long-Context ICU Data?* | arXiv 2605.13542 | Hindsight-grounded MIMIC-IV benchmark. Two failure modes reported: **recall-safety tradeoff** and **anchoring bias to early interpretations** — a failure taxonomy in HTN-Concord's space |
| **ClinEnv** — interactive multi-stage long-horizon EHR environment | arXiv 2606.02568 | Explicitly states it is a research benchmark, not a CDS tool — the same intended-use posture as HTN-Concord §8 |
| **ClinicalMC** — multi-course clinical decision-making | arXiv 2606.03157 | |
| **RxEval** — prescription-level benchmark for LLM medication recommendation | arXiv 2605.14543 | Closest on the *medication recommendation* task specifically |
| **CliBench** | arXiv 2406.09923 | Treatment procedures, lab orders, prescriptions against ICD-10-PCS / LOINC / ATC |

---

## 6. Supporting — cite, do not fear

| Paper | ID | Why it helps |
|---|---|---|
| *Shifting Thresholds: Changes in Antihypertensive Eligibility Under the 2025 Versus 2017 Hypertension Guidelines* | JACC: Advances, 10.1016/j.jacadv.2025.102546 / PMC12859489 | **The epidemiological companion to the NHANES cohort.** Validate HTN-Concord's stage/eligibility distribution against it — an external sanity check on the substrate |
| NHANES 2021–2023: ~80% of US adults with HTN above the <130/80 goal | ACC journal scan, Feb 2026 | Population framing for the introduction |
| *Development and validation of RAG and GraphRAG for complex clinical cases* (NICE CKD guidelines) | medRxiv 2025.11.25.25341010 | **Ready-made C3g comparator.** Finding: GraphRAG best on thresholds and algorithmic decisions via multi-hop, but worse on clarity (long guideline excerpts obscure the recommendation). Directly predicts the C3g result shape |
| **CSEDB** — clinical safety-effectiveness dual-track benchmark | npj Digital Medicine, s41746-025-02277-8 | 32 physicians, 30 metrics, 2,069 items. Precedent for separating safety from effectiveness in reporting — the same choice as keeping `unsafe_recommendation` out of the concordance headline |
| **HL7 FHIR Clinical Guidelines (CPG) IG** v2.0.0 | hl7.org/fhir/uv/cpg | The standards-track answer to "why not just use FHIR CPG?" — a reviewer will ask. Prepare a one-paragraph answer |

---

## 7. Positioning conclusion

What survives as genuinely unoccupied, after all of the above:

> A deterministic guideline engine used as the **label source** — not a verifier of model text
> (T2D-Bench), not a training signal (MedGuideX), not a tree the model walks (CPGPrompt) — emitting
> a **reasoning trace**, on a **treatment-initiation** decision rather than diagnosis, with
> **matched synthetic-vignette and real-EHR arms sharing one schema and one engine**, and with
> **clinician adjudication of the encoding itself** (HC-49 — the stated limitation of GuideSkill).

**The sharpest single asset is the C0−C1 delta.** Roeschl et al. produced that result with Cohen's
κ on 80 aortic-stenosis patients using *manually written* summaries. HTN-Concord can produce it at
4,806 patients with a deterministic renderer where
`test_every_level_carries_every_decision_relevant_value` *proves* difficulty changes presentation
and not information. No other group is positioned to make that claim cleanly.

---

## 8. Open actions

| # | Action | Sub-project |
|---|---|---|
| 1 | Fold §1–§6 into the Notion "Reference Papers" page; keep one authoritative synthesis, not two | D |
| 2 | Read in full before citing anything outside §1 — only the four executable-guideline abstracts were fetched | D |
| 3 | Rewrite the novelty claim away from "executable guideline" in Master Plan §0 and the Experiment Design intro | D |
| 4 | Validate the NHANES stage distribution against *Shifting Thresholds* | D or B6 |
| 5 | Prepare the one-paragraph "why not FHIR CPG IG" answer | D |
| 6 | Write the Chinese pair of this document | A |
