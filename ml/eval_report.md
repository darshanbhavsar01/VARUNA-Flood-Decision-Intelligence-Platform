# Flood Risk Model — Evaluation (complaint-verified waterlogging risk)

Model: BQML BOOSTED_TREE_CLASSIFIER, auto class weights, trained on split=train (<=2023). Temporal eval. Heavy class imbalance -> read PR-AUC & recall@top-20, not accuracy.

| split | rows | pos% | ROC-AUC | PR-AUC | recall@top20/day | precision | recall | f1 |
|---|---|---|---|---|---|---|---|---|
| val | 72,468 | 1.846% | 0.8660 | 0.1577 | 0.5633 | 0.0704 | 0.7578 | 0.1288 |
| test | 35,838 | 2.531% | 0.8664 | 0.2072 | 0.5944 | 0.1069 | 0.7398 | 0.1868 |

## Global feature importance (gain)

| feature | gain |
|---|---|
| ward_flood_baseline | 0.5755 |
| rain_prev_3d | 0.0595 |
| rain_prev_1d | 0.0569 |
| velocity_prev_3d | 0.0553 |
| rain_fcst_1d | 0.0494 |
| month | 0.0352 |
| rain_prev_7d | 0.016 |
| velocity_prev_1d | 0.0094 |
| historical_flood_count | 0.0061 |
| is_low_lying | 0.0041 |
| is_monsoon | 0.0022 |