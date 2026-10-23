#!/bin/zsh
# ========================================================================================
# 【实验 1：MIMIC 病历可行性检查】第 2 步：从 MIMIC 原始大表里筛出这 50 个病人的记录
#
# 当时是直接在终端执行的命令，没有存成脚本。这里按 2026-09-23 会话记录里的原始命令
# 原样整理，逻辑没有改动；只加了注释，并合并成一个文件。
#
# 输入：out/sample_notes.csv（01_sample.py 生成）+ MIMIC-IV 3.1 hosp 表 + MIMIC-IV-ED 2.2 表
# 输出（全部是 MIMIC 受控数据，只能留在本机）：
#   out/subjects.txt              50 个病人的 subject_id
#   out/labs_sample.csv           这些人的化验（只保留 9 个相关 itemid）
#   out/omr_sample.csv            门诊记录（含门诊血压）
#   out/adm_sample.csv            入院记录（入院 / 出院时间）
#   out/ed_{edstays,triage,vitalsign}_sample.csv   急诊就诊、分诊、生命体征
# 运行位置：cv-llm-risk-extraction/feasibility/
# ========================================================================================
set -e
PY="/Users/aria/Documents/PhD GenAI/htn-concord-main/htn-concord/.venv/bin/python"
H="/Users/aria/Documents/PhD GenAI/htn-concord-main/Data/mimic-iv-3.1/hosp"
E="/Users/aria/Documents/PhD GenAI/htn-concord-main/Data/mimic-iv-ed-2.2/ed"

# 1) 取出 50 个病人的 subject_id，一行一个
"$PY" -c "
import pandas as pd;s=pd.read_csv('out/sample_notes.csv');open('out/subjects.txt','w').write('\n'.join(map(str,s.subject_id)))"

# 2) 化验表很大，边解压边用 awk 过滤：保留表头，以及「病人在名单里 且 itemid 属于下列 9 项」的行
#    50852 HbA1c · 50904 HDL · 50905/50906 LDL · 50907 总胆固醇 · 50912 肌酐
#    50931 血糖 · 50971 血钾 · 51000 甘油三酯
#    （awk 第一段读名单 NR==FNR；第 2 列是 subject_id，第 5 列是 itemid）
gzip -dc "$H/labevents.csv.gz" | awk -F, 'NR==FNR{s[$1]=1;next} FNR==1||(($2 in s)&&($5~/^(50852|50904|50905|50906|50907|50912|50931|50971|51000)$/))' out/subjects.txt - > out/labs_sample.csv

# 3) 门诊记录和入院记录：第 1 列是 subject_id，只保留名单里的人
gzip -dc "$H/omr.csv.gz"        | awk -F, 'NR==FNR{s[$1]=1;next} FNR==1||($1 in s)' out/subjects.txt - > out/omr_sample.csv
gzip -dc "$H/admissions.csv.gz" | awk -F, 'NR==FNR{s[$1]=1;next} FNR==1||($1 in s)' out/subjects.txt - > out/adm_sample.csv

# 4) 急诊三张表：同样按第 1 列 subject_id 过滤
for f in edstays triage vitalsign; do
  gzip -dc "$E/$f.csv.gz" | awk -F, 'NR==FNR{s[$1]=1;next} FNR==1||($1 in s)' out/subjects.txt - > out/ed_${f}_sample.csv
done

wc -l out/*_sample.csv
