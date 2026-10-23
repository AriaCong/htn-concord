"""Unit tests for drug -> engine-class mapping, incl. combination pills."""
import pandas as pd

from pipelines.nhanes import drug_class


def test_single_agents():
    assert drug_class._classify("LISINOPRIL") == ["acei"]
    assert drug_class._classify("LOSARTAN") == ["arb"]
    assert drug_class._classify("AMLODIPINE") == ["dhp_ccb"]
    assert drug_class._classify("HYDROCHLOROTHIAZIDE") == ["thiazide"]
    assert drug_class._classify("METOPROLOL") == ["beta_blocker"]


def test_combination_pills_return_all_components():
    assert drug_class._classify("HYDROCHLOROTHIAZIDE; LISINOPRIL") == ["acei", "thiazide"]
    assert drug_class._classify("AMLODIPINE; BENAZEPRIL") == ["acei", "dhp_ccb"]
    assert drug_class._classify("HYDROCHLOROTHIAZIDE / LOSARTAN") == ["arb", "thiazide"]


def test_false_positives_excluded():
    assert drug_class._classify("PRILOCAINE") == []      # not acei
    assert drug_class._classify("IBUPROFEN") == []
    assert drug_class._classify("") == []
    assert drug_class._classify(None) == []


def test_med_classes_by_seqn_pivots_and_dedupes():
    rxq = pd.DataFrame({
        "SEQN": [1, 1, 2, 3],
        "RXDDRUG": ["LISINOPRIL", "AMLODIPINE", "HYDROCHLOROTHIAZIDE; LOSARTAN", "IBUPROFEN"],
    })
    out = drug_class.med_classes_by_seqn(rxq).set_index("SEQN")["med_classes"]
    assert out.loc[1] == ["acei", "dhp_ccb"]
    assert out.loc[2] == ["arb", "thiazide"]
    assert 3 not in out.index          # no antihypertensive -> not present
