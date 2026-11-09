# Протокол Оценки Модели ArcShift V1

Дата: 09.11.2026. Manifest: `ru-stress-onset-eval.candidate.1`.
Статус: **proposed_not_authorized**. Этот документ не разрешает M04, fit,
скачивание данных, создание весов или выпуск сигнала.

## 1. Зафиксированная Задача

Протокол использует существующие определения, не копирует их формулу:

- контракт задачи: `v1-task.2`, `ru_market_stress_onset_v1`;
- измеритель: `ru-domestic-market-stress.1`;
- target: `ru_domestic_stress_onset.1`;
- хеш измерителя импортируется из `arcshift_v1.stress_definition.MEASUREMENT_SHA256`;
- горизонт: один, 30 календарных дней, окно `(t, t+30]`;
- origin: 09:00 `Europe/Moscow`, только при известном `E(t)=0`;
- `E(t)=1`, `E(t)=unknown` и неполное будущее окно не входят в risk set;
- `t+30` входит, `t+31` не входит; `label_end >= fold_cutoff` исключается.

Старые `future_composite_stress_event_candidate.1`, горизонты 7/90 дней,
пятикомпонентный target и результаты `model-boosting-mvp@066653b` относятся к
другим задачам. Они не являются baseline quality или prior evidence для V1.

Машиночитаемый кандидат находится в `models/validation/evaluation.py` и
получает ID/хеш из канонических объектов. Formula/hash не дублируются.

## 2. Point-In-Time Fold

Каждый outer/inner fold получает отдельные неизменяемые:

1. `data_snapshot_id` и `calendar_snapshot_id` target-панели;
2. `feature_snapshot_id` и `feature_schema_id`;
3. точный `available_through`, равный fold cutoff 09:00 МСК;
4. target ID, measurement ID/hash и horizon;
5. список origins и причины исключения каждой неподдержанной строки.

Snapshot, подготовленный после fold cutoff, запрещён даже если его значения
кажутся историческими. Для каждого исходного наблюдения действует fixing rule
из `ru-domestic-market-stress.1`: последняя ревизия, полученная не позже
следующего дневного cutoff, после этого неизменна. Поздняя поставка/ревизия не
ремонтирует старый outcome и не меняет train rows прошлого fold.

Код `fold_training_batch` работает только с `synthetic=True`, требует точного
совпадения индексов target/features и возвращает данные без создания модели.
Legacy `scripts/train_crisis_model.py` остаётся отдельным baseline-кодом: он не
является реализацией этого point-in-time протокола и не получает допуск M04.

## 3. Origins, Coverage И Folds

После допуска snapshot формируются четыре expanding outer folds с
непересекающимися test-периодами и три expanding inner folds внутри каждого
outer train. Между train и test применяется purge: target допускается только
при `label_end < fold_cutoff`. Точные четыре даты нельзя честно зафиксировать
до появления admitted panel и отчёта о coverage; после фиксации они становятся
частью immutable manifest до открытия outer outcomes.

Baseline и comparator оцениваются на одном пересечении origins. Для каждой
исключённой строки сохраняется одна или несколько причин:

- origin не `at_risk` (`already_in_stress` или `current_state_unknown`);
- незрелая или неполная метка;
- источник/календарь/ревизия неизвестны на cutoff;
- mandatory feature отсутствует, stale или unsupported;
- feature schema/version не совпадает;
- источник не допущен для model use.

Отчёт содержит общее число candidate origins, число зрелых risk-set origins,
matched coverage и доли исключений по причинам для каждого fold. Удаление строк
ради улучшения метрики запрещено.

## 4. Конечное Сравнение И Run Budget

На одинаковых origins сравниваются только:

1. `training_prevalence_constant`: доля положительных зрелых train targets,
   без estimator fit;
2. `l2_logistic_regression_c_1`: одна L2-logistic regression с `C=1.0`.

Числовые признаки, schema и missingness policy должны быть зафиксированы до
M04. Кандидат использует median imputation и standardization, обученные только
внутри соответствующего train. Feature selection, broad grid,
MFS/multi-task и другие модели не входят в этот candidate.

Калибровка: sigmoid только на inner out-of-fold predictions, если в development
части есть минимум 20 positive и 20 negative outcomes. Иначе score остаётся
`calibration_status=not_established` и не называется вероятностью. Outer fold
не выбирает preprocessing, calibrator, threshold, feature set или model family.

Максимум на один outer fold: три inner logistic fits, один final outer-train
logistic fit и один sigmoid calibration fit — пять estimator fits. Для четырёх
folds максимум 20. Prevalence baseline не требует fit. Failed run учитывается в
лимите и сохраняется. Final full-data fit и artifact отсутствуют в этом бюджете
и требуют отдельного решения после outer evaluation.

## 5. Метрики И Episode Semantics

Primary comparison-кандидат: paired разность Brier score относительно
prevalence baseline на matched origins. Также обязательны:

- log loss, calibration intercept/slope и reliability table;
- ROC AUC и average precision с prevalence рядом;
- coverage и unavailable reasons;
- при заранее утверждённом threshold: false alarms, false alarms/year,
  warning days/burden, precision, episode recall, missed episodes;
- lead time до первого подтверждённого начала эпизода;
- результаты каждого fold и все failed/negative runs.

Соседние положительные дни одного эпизода не считаются разными событиями.
Warning matching, cooldown и dedup version фиксируются до outer test. Интервалы
неопределённости используют заранее выбранный temporal block bootstrap; block
length и числовые acceptance bounds пока не утверждены и поэтому блокируют M04.

## 6. Threshold И Решения До Outer Test

Ярославу/product owner требуется до открытия outer outcomes утвердить:

- максимальную нагрузку предупреждений или стоимость false alarm/miss;
- правило выбора threshold на development predictions;
- numeric bounds для Brier/calibration, coverage, episode recall, misses и lead;
- точные outer cutoffs, temporal bootstrap block length и warning policy ID;
- допустимость sigmoid minimum `20/20` либо новую заранее обоснованную границу.

До решения threshold curves допустимы только как development evidence.
Actionable warning не создаётся; `warning_threshold_status` остаётся
`pending_product_decision`.

## 7. Model-Часть Q01

| Сценарий | Evidence сейчас | Статус |
| --- | --- | --- |
| A17 | unknown mandatory segment/current state не становится no-stress | synthetic pass |
| A18 | неподдержанный horizon/stale/missing остаётся unavailable | synthetic/API pass; real sources pending |
| A19 | index alignment, полное окно, strict cutoff, late revision | synthetic pass |
| A20 | версии, matched origins, порядок fit/calibration/threshold | protocol proposed; outer not run |
| A21 | fitted/OOS/live разделены | documented; artifact/history pending |
| A22 | task/target/measurement/schema/snapshot identity | synthetic boundary pass; serving artifact pending |
| A23 | warning dedup и private review | integration tests; real warning policy pending |
| A24 | policy immutability, outer не используется для tuning | protocol proposed; outer not run |
| A30 | target/horizon/errors/calibration/economic limits | documented; UI/reviewer acceptance pending |

Synthetic tests не доказывают empirical validity, calibration, model quality,
source rights или экономический эффект и не закрывают release gates.

## 8. M04/M05

M04 остаётся запрещён до одновременного выполнения: admitted data/features и
права model use; точные source calendars/availability; неизменяемые snapshots;
утверждённые outer/inner cutoffs, threshold/business constraints, numeric
acceptance bounds, bootstrap rule и manifest review Ярославом/Настей; явное
разрешение на finite fit.

M05 возможен только после M04 candidate decision. Он отдельно проверяет exact
feature schema/hash, task/target/horizon, cutoff, dependency lock, artifact
registry, unavailable behavior, rollback и совместимость serving contract.
