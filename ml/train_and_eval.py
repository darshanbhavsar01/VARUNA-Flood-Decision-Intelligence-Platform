"""Train the BQML flood-risk model, evaluate it honestly, and populate risk_scores.

  python ml/train_and_eval.py --city bengaluru [--score-date YYYY-MM-DD]

Steps:
  1. CREATE MODEL varuna.risk_model  (BOOSTED_TREE_CLASSIFIER, auto class weights,
     global explain on) trained ONLY on split='train' (<=2023).
  2. Evaluate on val (2024) and test (2025): ROC-AUC, PR-AUC (avg precision),
     precision/recall/f1, and recall@top-20-wards/day. Written to ml/eval_report.md.
  3. Score a reference day with ML.EXPLAIN_PREDICT -> risk_scores (horizon 24h) with
     per-ward top feature attributions (JSON) for the explainability panel.

Honest framing (§8a): this is complaint-verified waterlogging risk, not ground-truth
flood prediction. Metrics reflect heavy class imbalance (~1-2.5% positive).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATASET = "varuna"
LOCATION = "asia-south1"
MODEL = f"{DATASET}.risk_model"
FEATURES = f"{DATASET}.risk_features"
DROP_COLS = "city_id, ward_id, day, split"   # not model inputs


def q1(client, sql):
    return list(client.query(sql).result())[0]


def evaluate_split(client, split):
    ev = q1(client, f"""
      SELECT * FROM ML.EVALUATE(MODEL `{MODEL}`,
        (SELECT * EXCEPT({DROP_COLS}) FROM `{FEATURES}` WHERE split='{split}'))
    """)
    # PR-AUC (average precision) computed from predicted probabilities
    pr = q1(client, f"""
      WITH p AS (
        SELECT label AS y, (SELECT prob FROM UNNEST(predicted_label_probs)
                            WHERE label=1) AS score
        FROM ML.PREDICT(MODEL `{MODEL}`,
          (SELECT * EXCEPT({DROP_COLS}) FROM `{FEATURES}` WHERE split='{split}'))
      ),
      ranked AS (
        SELECT y, score,
          SUM(y) OVER (ORDER BY score DESC) AS tp,
          COUNT(*) OVER (ORDER BY score DESC) AS k,
          SUM(y) OVER () AS total_pos
        FROM p
      ),
      pts AS (   -- precision/recall at each distinct score threshold
        SELECT MAX(tp/k) AS precision, tp/total_pos AS recall
        FROM ranked GROUP BY tp, total_pos
      )
      SELECT ROUND(SUM(precision * d_recall),4) AS pr_auc FROM (
        SELECT precision, recall - LAG(recall,1,0) OVER (ORDER BY recall) AS d_recall
        FROM pts
      )
    """).pr_auc
    # recall@top-20 wards per day
    r20 = q1(client, f"""
      WITH p AS (
        SELECT day, label AS y,
               (SELECT prob FROM UNNEST(predicted_label_probs) WHERE label=1) score
        FROM ML.PREDICT(MODEL `{MODEL}`,
          (SELECT * FROM `{FEATURES}` WHERE split='{split}'))
      ),
      ranked AS (
        SELECT day, y, ROW_NUMBER() OVER (PARTITION BY day ORDER BY score DESC) rk
        FROM p
      ),
      per_day AS (
        SELECT day, SUM(y) pos, SUM(IF(rk<=20, y, 0)) caught
        FROM ranked GROUP BY day HAVING pos > 0
      )
      SELECT ROUND(AVG(caught/pos),4) recall_at_20 FROM per_day
    """).recall_at_20
    return ev, pr, r20


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", required=True)
    ap.add_argument("--score-date", help="reference day to score; default = max test day")
    ap.add_argument("--skip-train", action="store_true",
                    help="reuse existing risk_model (e.g. if training already ran)")
    args = ap.parse_args()
    if not os.environ.get("GOOGLE_CLOUD_PROJECT"):
        sys.exit("Set GOOGLE_CLOUD_PROJECT + `gcloud auth application-default login`.")
    import yaml
    cfg = yaml.safe_load(
        (REPO / "configs" / f"{args.city}.yaml").read_text(encoding="utf-8"))
    city_id = cfg["city_id"]   # canonical id ('blr'), NOT the config filename
    from google.cloud import bigquery
    client = bigquery.Client(location=LOCATION)

    # 1) train
    if args.skip_train:
        print("Skipping training; reusing existing risk_model.")
    else:
        print("Training risk_model (BOOSTED_TREE_CLASSIFIER)...")
        client.query(f"""
          CREATE OR REPLACE MODEL `{MODEL}`
          OPTIONS(
            model_type='BOOSTED_TREE_CLASSIFIER',
            input_label_cols=['label'],
            auto_class_weights=TRUE,
            enable_global_explain=TRUE,
            max_iterations=50, learn_rate=0.1, subsample=0.85,
            early_stop=TRUE, min_rel_progress=0.005
          ) AS
          SELECT * EXCEPT({DROP_COLS}) FROM `{FEATURES}` WHERE split='train'
        """).result()
        print("  trained.")

    # 2) evaluate
    lines = ["# Flood Risk Model — Evaluation (complaint-verified waterlogging risk)", "",
             "Model: BQML BOOSTED_TREE_CLASSIFIER, auto class weights, trained on "
             "split=train (<=2023). Temporal eval. Heavy class imbalance -> read "
             "PR-AUC & recall@top-20, not accuracy.", "",
             "| split | rows | pos% | ROC-AUC | PR-AUC | recall@top20/day | "
             "precision | recall | f1 |", "|---|---|---|---|---|---|---|---|---|"]
    print("\nEvaluating...")
    for split in ("val", "test"):
        ev, pr, r20 = evaluate_split(client, split)
        meta = q1(client, f"SELECT COUNT(*) n, ROUND(100*AVG(label),3) p "
                          f"FROM `{FEATURES}` WHERE split='{split}'")
        lines.append(f"| {split} | {meta.n:,} | {meta.p}% | "
                     f"{ev.roc_auc:.4f} | {pr:.4f} | {r20:.4f} | "
                     f"{ev.precision:.4f} | {ev.recall:.4f} | {ev.f1_score:.4f} |")
        print(f"  {split}: ROC-AUC={ev.roc_auc:.4f} PR-AUC={pr:.4f} "
              f"recall@20={r20:.4f} recall={ev.recall:.4f}")

    # global feature importance
    lines += ["", "## Global feature importance (gain)", "", "| feature | gain |", "|---|---|"]
    for row in client.query(f"""
      SELECT feature, ROUND(attribution,4) gain
      FROM ML.GLOBAL_EXPLAIN(MODEL `{MODEL}`) ORDER BY attribution DESC
    """).result():
        lines.append(f"| {row.feature} | {row.gain} |")
    (REPO / "ml" / "eval_report.md").write_text("\n".join(lines), encoding="utf-8")
    print("  wrote ml/eval_report.md")

    # 3) score reference day -> risk_scores with per-ward explanations
    score_date = args.score_date or q1(
        client, f"SELECT MAX(day) d FROM `{FEATURES}` WHERE split='test'").d
    print(f"\nScoring {score_date} -> risk_scores (horizon 24h) with explanations...")
    client.query(f"""
      DELETE FROM `{DATASET}.risk_scores`
      WHERE city_id='{city_id}' AND horizon_hrs=24
        AND DATE(computed_at)=DATE('{score_date}')
    """).result()
    client.query(f"""
      INSERT INTO `{DATASET}.risk_scores`
        (city_id, ward_id, horizon_hrs, score, computed_at, top_features)
      SELECT '{city_id}' AS city_id, ward_id, 24 AS horizon_hrs,
        IF(predicted_label=1, probability, 1-probability) AS score,
        TIMESTAMP('{score_date}') AS computed_at,
        TO_JSON(ARRAY(
          SELECT AS STRUCT a.feature, ROUND(a.attribution,4) AS attribution
          FROM UNNEST(top_feature_attributions) a
        )) AS top_features
      FROM ML.EXPLAIN_PREDICT(MODEL `{MODEL}`,
        (SELECT * FROM `{FEATURES}`
         WHERE split='test' AND day=DATE('{score_date}')),
        STRUCT(5 AS top_k_features))
    """).result()
    top = q1(client, f"""
      SELECT COUNT(*) n, ROUND(MAX(score),3) hi FROM `{DATASET}.risk_scores`
      WHERE city_id='{city_id}' AND DATE(computed_at)=DATE('{score_date}')
    """)
    print(f"  scored {top.n} wards for {score_date}; max risk={top.hi}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
