# ========================================================================================
# 【实验 1：MIMIC 病历可行性检查】（2026-09-23，不调用任何大模型）
# 问题：真实出院小结里写的数值，和 MIMIC 结构化表对得上吗？缺血脂时，PREVENT 结论还能判定吗？
# 结论写在：cv-llm-risk-extraction/docs/feasibility_2026-09-23.md
# 运行顺序：01_sample.py → 01b_extract_subset.sh → 02_compare.py；03_determinability.py 独立运行
# 数据规则：MIMIC 派生数据（feasibility/out/）只能留在本机，不能上传、发给 API 或发布。
#
# 本文件：第 3 步，小结数值 vs 结构化表。只用正则表达式，不用大模型。
# 做什么：
#   1. 化验值：从小结的 "Pertinent Results" 模板行（带时间）和正文叙述里抽出数值，
#      去 labevents 表里找有没有同一时间、同一数值的记录。
#   2. 覆盖率：每份小结里写了哪些变量，结构化表里有哪些。
#   3. 血压：小结里的血压和急诊分诊 / 生命体征、以及入院前最后一次门诊血压（OMR）比较。
# 输入：01 和 01b 生成的 out/*_sample.csv
# 输出：out/value_matches.csv、out/bp_matches.csv、out/coverage.csv，并打印汇总
# 原始位置：cv-llm-risk-extraction/feasibility/02_compare.py
# ========================================================================================

"""Compare values written in 50 discharge summaries against MIMIC structured tables.

Deterministic regex extraction only; no LLM. Two kinds of note values:
  * "results" values: the templated Pertinent Results lines
    ("___ HH:MMAM BLOOD Glucose-<n> UreaN-<n> Creat-<n> ...", format only). These carry a time of day,
    so each can be matched to a labevents row by (itemid, time of day, value).
  * narrative values ("Cr 1.4", "LDL 120", "A1c 7.2") with no time anchor; matched by value
    against any labevents row of the same item in [admit - 365 d, discharge].
BP in the note is compared with ED triage/vitals of the same admission and with the most
recent outpatient OMR reading before admission.

Writes out/value_matches.csv, out/bp_matches.csv, out/coverage.csv, and prints a summary.
"""
from pathlib import Path
import re
import pandas as pd

OUT = Path(__file__).parent / "out"

# 小结模板行里的化验名 → (变量名, labevents 的 itemid)
ITEMS = {  # note token -> (variable, labevents itemids)
    "Creat": ("creatinine", [50912]),
    "K": ("potassium", [50971]),
    "Glucose": ("glucose", [50931]),
    "Cholest": ("total_chol", [50907]),
    "HDL": ("hdl", [50904]),
    "LDLcalc": ("ldl", [50905]),
    "LDLmeas": ("ldl", [50906]),
    "Triglyc": ("trig", [51000]),
    "%HbA1c": ("a1c", [50852]),
}
VAR_ITEMS = {}
for _, (v, ids) in ITEMS.items():
    VAR_ITEMS.setdefault(v, set()).update(ids)

# 正文叙述里的写法（如 "Cr 1.4"、"LDL 120"）→ 抓数值的正则
NARR = {  # narrative patterns: variable -> regex capturing the number
    "creatinine": r"\b(?:creatinine|creat|cr)\b[^0-9\n]{0,15}?(\d{1,2}\.\d)",
    "potassium": r"\b(?:potassium|K)\b[^0-9\n]{0,6}?([2-7]\.\d)\b",
    "total_chol": r"\b(?:total cholesterol|cholesterol|TC)\b[^0-9\n]{0,15}?(\d{2,3})\b",
    "hdl": r"\bHDL\b[^0-9\n]{0,10}?(\d{2,3})\b",
    "ldl": r"\bLDL\b[^0-9\n]{0,10}?(\d{2,3})\b",
    "a1c": r"\b(?:HbA1c|A1c|A1C|hemoglobin A1c)\b[^0-9\n]{0,12}?(\d{1,2}(?:\.\d)?)\b",
}

TIME_BLOOD = re.compile(r"(\d{1,2}):(\d{2})\s*([AP]M)\s+BLOOD\s+(.*)")
TOKEN = re.compile(r"(%?[A-Za-z][A-Za-z0-9/%]*)-(\d+(?:\.\d+)?)\*?")
CONT = re.compile(r"^\s*(?:%?[A-Za-z][A-Za-z0-9/%]*-\d+(?:\.\d+)?\*?\s*)+$")
BP = re.compile(r"\b(?:BP|B/P|Blood Pressure|bp)\b[:\s=]*(\d{2,3})\s*/\s*(\d{2,3})")


def to_minutes(h, m, ap):
    h = int(h) % 12 + (12 if ap == "PM" else 0)
    return h * 60 + int(m)


# 解析 "06:30AM BLOOD Glucose-98 Creat-0.9 ..." 这种模板行（可能跨多行），
# 返回 (变量, 数值, 一天中的分钟数)，用来和 labevents 按时间对齐
def results_values(text):
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        m = TIME_BLOOD.search(lines[i])
        if not m:
            i += 1
            continue
        tod = to_minutes(*m.group(1, 2, 3))
        body = m.group(4)
        j = i + 1
        while j < len(lines) and CONT.match(lines[j]) and not TIME_BLOOD.search(lines[j]):
            body += " " + lines[j]
            j += 1
        for name, val in TOKEN.findall(body):
            if name in ITEMS:
                out.append((ITEMS[name][0], float(val), tod))
        i = j
    return out


# 判断一个血压读数出现在「入院查体」还是「出院查体」段落
def section_of(text, pos):
    head = text[:pos].lower()
    a, d = head.rfind("admission"), head.rfind("discharge")
    # "Discharge Date" in the header block would otherwise dominate; require an exam cue.
    a2 = max(head.rfind("admission exam"), head.rfind("admission physical"), head.rfind("on admission"))
    d2 = max(head.rfind("discharge exam"), head.rfind("discharge physical"), head.rfind("on discharge"))
    if max(a2, d2) < 0:
        return "unlabelled"
    return "admission" if a2 > d2 else "discharge"


notes = pd.read_csv(OUT / "sample_notes.csv")
labs = pd.read_csv(OUT / "labs_sample.csv", low_memory=False)
labs["charttime"] = pd.to_datetime(labs.charttime)
labs["tod"] = labs.charttime.dt.hour * 60 + labs.charttime.dt.minute
adm = pd.read_csv(OUT / "adm_sample.csv", parse_dates=["admittime", "dischtime"])
omr = pd.read_csv(OUT / "omr_sample.csv", parse_dates=["chartdate"])
omr = omr[omr.result_name.str.startswith("Blood Pressure")].copy()
omr[["sbp", "dbp"]] = omr.result_value.str.split("/", expand=True).apply(pd.to_numeric, errors="coerce")
eds = pd.read_csv(OUT / "ed_edstays_sample.csv")
tri = pd.read_csv(OUT / "ed_triage_sample.csv")
evs = pd.read_csv(OUT / "ed_vitalsign_sample.csv")

vrows, brows, crows = [], [], []
for n in notes.itertuples():
    a = adm[adm.hadm_id == n.hadm_id].iloc[0]
    win_lo, win_hi = a.admittime - pd.Timedelta(days=365), a.dischtime
    L = labs[(labs.subject_id == n.subject_id)]
    L_adm = L[(L.charttime >= a.admittime - pd.Timedelta(hours=24)) & (L.charttime <= a.dischtime)]
    L_yr = L[(L.charttime >= win_lo) & (L.charttime <= win_hi)]

    # --- (1) 模板行数值：按「同一时间 + 同一数值」匹配结构化化验 ---
    rv = results_values(n.text)
    for var, val, tod in rv:
        ids = VAR_ITEMS[var]
        cand = L_adm[L_adm.itemid.isin(ids)]
        same_t = cand[cand.tod == tod]
        exact = same_t[(same_t.valuenum - val).abs() < 0.051]
        any_val = cand[(cand.valuenum - val).abs() < 0.051]
        status = ("time+value" if len(exact) else
                  "time only (value differs)" if len(same_t) else
                  "value only (time differs)" if len(any_val) else
                  "no structured row")
        vrows.append(dict(note_id=n.note_id, kind="results", var=var, note_value=val, status=status))

    # --- (2) 叙述数值：没有时间，只在入院前 365 天到出院之间按数值匹配 ---
    for var, pat in NARR.items():
        for m in re.finditer(pat, n.text, flags=re.I if var != "potassium" else 0):
            # skip the templated results lines, already handled above
            line = n.text[n.text.rfind("\n", 0, m.start()) + 1: n.text.find("\n", m.end())]
            if "BLOOD" in line or CONT.match(line):
                continue
            val = float(m.group(1))
            cand = L_yr[L_yr.itemid.isin(VAR_ITEMS[var])]
            hit = cand[(cand.valuenum - val).abs() < 0.051]
            status = "value in window" if len(hit) else ("item in window, value absent" if len(cand) else "no structured row")
            # chance baseline: would a value shifted by one clinically small step also "match"?
            step = 0.3 if val < 20 else 7
            shifted = bool(((cand.valuenum - (val + step)).abs() < 0.051).any()) or bool(((cand.valuenum - (val - step)).abs() < 0.051).any())
            vrows.append(dict(note_id=n.note_id, kind="narrative", var=var, note_value=val, status=status,
                              shifted_also_matches=shifted, n_window_rows=len(cand)))

    # --- (3) 覆盖率 ---
    # coverage: does the note state it / do structured tables hold it
    stated = {v for v, _, _ in rv} | {r["var"] for r in vrows if r["note_id"] == n.note_id}
    for var, ids in VAR_ITEMS.items():
        crows.append(dict(note_id=n.note_id, prevent_ok=n.prevent_ok, var=var,
                          in_note=var in stated,
                          in_labs_admission=bool(L_adm.itemid.isin(ids).any()),
                          in_labs_year=bool(L_yr.itemid.isin(ids).any())))

    # --- (4) 血压：小结 vs 急诊读数 vs 门诊（OMR）读数 ---
    # BP
    stays = eds[eds.hadm_id == n.hadm_id].stay_id
    ed_bp = pd.concat([tri[tri.stay_id.isin(stays)][["sbp", "dbp"]],
                       evs[evs.stay_id.isin(stays)][["sbp", "dbp"]]]).dropna()
    o = omr[(omr.subject_id == n.subject_id) & (omr.chartdate < a.admittime.normalize())]
    o_last = o.sort_values("chartdate").tail(1)
    o_365 = o[o.chartdate >= a.admittime.normalize() - pd.Timedelta(days=365)]
    bps = list(BP.finditer(n.text))
    for m in bps:
        s, d = int(m.group(1)), int(m.group(2))
        brows.append(dict(
            note_id=n.note_id, section=section_of(n.text, m.start()), sbp=s, dbp=d,
            ed_exact=bool(((ed_bp.sbp == s) & (ed_bp.dbp == d)).any()),
            ed_n=len(ed_bp),
            ed_min_sbp_diff=(ed_bp.sbp - s).abs().min() if len(ed_bp) else None,
            omr_last_sbp=o_last.sbp.iloc[0] if len(o_last) else None,
            omr_last_days=(a.admittime.normalize() - o_last.chartdate.iloc[0]).days if len(o_last) else None,
            omr_365_n=len(o_365),
        ))
    if not bps:
        brows.append(dict(note_id=n.note_id, section="none", sbp=None, dbp=None, ed_exact=False,
                          ed_n=len(ed_bp), omr_last_sbp=o_last.sbp.iloc[0] if len(o_last) else None,
                          omr_last_days=None, omr_365_n=len(o_365)))

V, B, C = pd.DataFrame(vrows), pd.DataFrame(brows), pd.DataFrame(crows)
V.to_csv(OUT / "value_matches.csv", index=False)
B.to_csv(OUT / "bp_matches.csv", index=False)
C.to_csv(OUT / "coverage.csv", index=False)

pd.set_option("display.width", 160)
print("\n== Templated results values: match against labevents (same admission) ==")
r = V[V.kind == "results"]
print(pd.crosstab(r["var"], r["status"], margins=True))
print("\n== Narrative values: match against labevents (admit-365d .. discharge) ==")
nv = V[V.kind == "narrative"]
print(pd.crosstab(nv["var"], nv["status"], margins=True))
print("  chance baseline (value +/- one step would also match):",
      nv.assign(s=nv.shifted_also_matches.astype(float)).groupby("var").s.mean().round(2).to_dict())
print("  median structured rows in window per narrative value:", nv.groupby("var").n_window_rows.median().to_dict())
print("\n== Coverage per note (of 50) ==")
cov = C.groupby("var")[["in_note", "in_labs_admission", "in_labs_year"]].sum()
print(cov)
print("\n  by PREVENT stratum, total_chol / hdl present:")
print(C[C["var"].isin(["total_chol", "hdl"])].groupby(["prevent_ok", "var"])[["in_note", "in_labs_admission", "in_labs_year"]].sum())
print("\n== BP ==")
bp = B[B.section != "none"]
print("notes with >=1 BP:", B[B.section != "none"].note_id.nunique(), "/ 50; BP mentions:", len(bp))
print(bp.section.value_counts().to_string())
adm_bp = bp[bp.section == "admission"]
print("admission-exam BP exactly equal to an ED triage/vital reading:", int(adm_bp.ed_exact.sum()), "/", len(adm_bp),
      "| of those with any ED reading:", int(adm_bp[adm_bp.ed_n > 0].ed_exact.sum()), "/", int((adm_bp.ed_n > 0).sum()))
print("admission-exam BP: median |SBP - closest ED SBP| =", adm_bp.ed_min_sbp_diff.median())
per_note = B.drop_duplicates("note_id")
print("notes with an outpatient OMR BP in the year before admission:", int((per_note.omr_365_n > 0).sum()), "/ 50")
w = bp.dropna(subset=["omr_last_sbp"])
if len(w):
    diff = (w.sbp - w.omr_last_sbp).abs()
    print("|note SBP - last OMR SBP|: median %.0f, IQR %.0f-%.0f, share >=20 mmHg %.2f (n=%d mentions)"
          % (diff.median(), diff.quantile(.25), diff.quantile(.75), (diff >= 20).mean(), len(w)))
