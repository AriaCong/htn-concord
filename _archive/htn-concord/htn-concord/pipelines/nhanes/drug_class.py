"""Map NHANES prescription rows (RXQ_RX) to engine antihypertensive classes.

RXQ_RX is long (many drug rows per SEQN) and stores drug IDs, not classes. The
RXQ_DRUG lexicon carries the name/therapeutic-category. We join, keyword-map to
the engine's class vocabulary, and pivot to one class-set per SEQN.

Engine classes: thiazide, acei, arb, dhp_ccb, other (antihypertensive not in the
first-line set is recorded as its own label where recognizable).
"""
from __future__ import annotations

import pandas as pd

import vocab

from . import config, io_xpt

# Drug -> engine class mapping lives in the shared vocab module (HC-3) so the
# pipeline and the engine use one vocabulary. This module only does the NHANES
# pandas wrangling around it.
_classify = vocab.classify_drug


def _named_frame(rxq_rx: pd.DataFrame, lexicon: pd.DataFrame | None) -> pd.DataFrame:
    """Return a [SEQN, _name] frame, joining the RXQ_DRUG lexicon if needed."""
    df = rxq_rx.copy()
    name_col = "RXDDRUG" if "RXDDRUG" in df.columns else None
    if name_col is None and lexicon is not None and "RXDDRGID" in df.columns:
        lex = lexicon[["RXDDRGID", "RXDDRUG"]].drop_duplicates()
        df = df.merge(lex, on="RXDDRGID", how="left")
        name_col = "RXDDRUG"
    if name_col is None:
        raise KeyError("No drug-name column; provide RXQ_DRUG lexicon for the join.")
    df["_name"] = df[name_col].astype("string").fillna("")
    return df[["SEQN", "_name"]]


def statin_use_by_seqn(rxq_rx: pd.DataFrame, lexicon: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per SEQN on any statin (PREVENT input). Statins end in 'statin'
    (atorvastatin, simvastatin, rosuvastatin, ...)."""
    df = _named_frame(rxq_rx, lexicon)
    df["_statin"] = df["_name"].str.lower().str.contains("statin", na=False)
    return (
        df.groupby("SEQN")["_statin"].any()
        .rename("statin_use").reset_index()
    )


def med_classes_by_seqn(rxq_rx: pd.DataFrame, lexicon: pd.DataFrame | None = None) -> pd.DataFrame:
    """Return one row per SEQN with a sorted list of engine med classes."""
    df = _named_frame(rxq_rx, lexicon)
    df["_classes"] = df["_name"].map(_classify)   # list per drug row (may be empty)

    exploded = (
        df[["SEQN", "_classes"]]
        .explode("_classes")
        .dropna(subset=["_classes"])
    )
    grouped = (
        exploded.groupby("SEQN")["_classes"]
        .apply(lambda g: sorted(set(g)))
        .rename("med_classes")
        .reset_index()
    )
    # SEQNs with prescriptions but no antihypertensive get an empty list downstream.
    return grouped


def load_lexicon() -> pd.DataFrame | None:
    try:
        return io_xpt.read_component(config.DRUG_LEXICON_STEM)
    except FileNotFoundError:
        print("  RXQ_DRUG lexicon not found; relying on RXDDRUG in RXQ_RX if present.")
        return None
