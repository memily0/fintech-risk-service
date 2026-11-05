# Вопросы Для Уточнения Источников

Дата: 05.11.2026. Это подготовленный список, не отправленные письма,
не заявки на платную подписку и не утверждение юридического запрета.

## Общий Профиль Для Всех Обращений

ArcShift готовит публичный веб-сервис с самостоятельной регистрацией,
в первую очередь для мониторинга российской среды с международным контекстом.
Предполагаются датированные показатели/графики, сохранение истории и snapshots,
производные индикаторы, обучение и применение модели конкретного stress proxy,
PDF отчёты и при наличии соответствующих прав CSV/JSON/read API.
Командных банковских портфелей, автоматических сделок и кредитных решений нет.

Billing/платные subscriptions в V1 не выбраны, но проект развивается как
продукт и может получить коммерческое применение. Не просим разрешения
под видом personal/research use, если фактически планируется публичный сервис.
Сначала нужны условия бесплатного разрешённого варианта; расходы на feeds
не согласованы. Ни согласие на тариф, ни подписание договора не подразумеваются.

Уточнить по каждому способу отдельно: ingestion/storage/backups; публичный
display; model training/inference; распространение derived outputs/weights;
PDF; raw downloadable history; read API. Если отдельный способ не разрешён,
попросить назвать допустимый ограниченный вариант и применимые условия.

## 1. Банк России

Ряды: официальные R01235/R01239, genuine KeyRate, curve 1/2/5/10 лет.
Основание вопроса: [описание использования сайта](https://www.cbr.ru/About/?PrtId=use),
[соглашение](https://www.cbr.ru/user_agreement/),
[DailyInfo](https://www.cbr.ru/development/dws/).

- Как соотносятся разрешение воспроизведения со ссылкой и отдельная формулировка
  о коммерческих целях именно для такого продукта и перечисленных рядов?
- Допустимы ли перечисленные способы использования без отдельного соглашения?
  Отличается ли показ исходных значений от публичного derived model output?
- Требуется ли отдельное уведомление о включении источника/гиперссылки в сервис?
- Есть ли отдельные права Мосбиржи на размещённую у ЦБ бескупонную кривую?
- Какой источник/поле отражает публикацию, announcement и effective time,
  есть ли сведения о revisions и рекомендуемые request limits?

## 2. Московская Биржа

Ряды: IMOEX official daily CLOSE, curve при применимости.
Документы: [ISS](https://www.moex.com/a2920),
[policy](https://www.moex.com/en/datapolicy/), [tariffs](https://www.moex.com/s1147).

- Есть ли разрешённый бесплатный EOD/delayed profile для нашего точного набора?
- Какие права требуются для chart display, storage, rolling indicators,
  model training/inference и выдачи вероятности/драйверов без raw quotes?
- Какие отдельные условия применяются к reports, downloadable history и API?
- Как трактуется curve, полученная с сайта ЦБ, и нужны ли дополнительные права?
- Какие session/field считать окончательным daily close, как отражаются
  revisions, holiday sessions и допустимые технические лимиты?

## 3. Росстат

Искомый ряд: Россия в целом, все товары и услуги, monthly CPI к тому же
месяцу прошлого года. Candidate IDs: витрина 11521100300010200001,
ЕМИСС 31074; их точная resource equivalence ещё не подтверждена.
[FAQ](https://rosstat.gov.ru/folder/165737),
[цены](https://www.rosstat.gov.ru/statistics/price/),
[open-data terms](https://rosstat.gov.ru/opendata).

- Какой прямой официальный machine-readable resource и какие точные codes
  соответствуют указанным dimensions, units и месячной частоте?
- Распространяются ли open-data terms на этот resource, включая коммерческий
  display, derived models, exports и API, и как правильно указывать источник?
- Где доступны фактические publication timestamps, история пересмотров,
  архивные releases/vintages и технический регламент обновления?
- Можно ли подтвердить набор без выбора по порядку строк и есть ли стабильный
  schema/dictionary endpoint? Копия NSEDC автоматически не считается идентичной.

## 4. EIA

Точный кандидат: Europe Brent Spot Price FOB, daily RBRTE, USD/barrel,
не Brent futures. [Серия](https://www.eia.gov/dnav/pet/hist/RBRTED.htm),
[reuse](https://www.eia.gov/about/copyrights_reuse.php),
[историческое описание происхождения](https://www.eia.gov/analysis/handbook/pdf/STEO_Crude_Oil_Price.pdf).

- Применима ли общая EIA reuse policy именно к этому опубликованному ряду
  во всех перечисленных способах использования, несмотря на стороннее происхождение?
- Нужно ли отдельное разрешение владельца underlying data для public
  display/derived model/export/API? Если да, какой путь его получения?
- Какой официальный delivery method, revision policy, release time/timezone
  и request budget соответствуют этому ряду? Как оформлять атрибуцию?

## 5. Cboe

Точный кандидат: VIX index daily close, не futures/ETF.
[Официальная история](https://www.cboe.com/tradable-products/vix/vix-historical-data).

- Какие права есть у публичного historical file для storage, public display,
  model training/inference, derived outputs и downstream exports/API?
- Есть ли бесплатный допустимый EOD profile для описанного продукта?
- Какой resource/field и timestamp/timezone задают final daily close;
  как различаются версии/методологические изменения индекса и revisions?
- Разрешена ли передача model artifacts и predictions отдельно от raw values?

## 6. S&P Dow Jones Indices Или Уполномоченный Поставщик

Точный кандидат: S&P 500 price index daily close, не total return и не ETF.
[Метаданные и owner notices](https://fred.stlouisfed.org/series/SP500).

- Как получить соответствующие display/non-display/derived-model права
  для public registered service, отдельно от доступа через Yahoo или FRED?
- Есть ли разрешённый бесплатный EOD вариант с нужной историей, либо какие
  ограничения и условия применяются без выбора платного тарифа сейчас?
- Допустимы ли отчёты, CSV/JSON/API и передача trained artifacts/predictions?
- Какие exact identifier, provider, close convention, revisions и history depth
  доступны? Не считать 10-летний FRED extract полной заменой legacy history.

## 7. CME Или Уполномоченный Поставщик Gold Futures

Нужен источник, сопоставимый с legacy GC=F, а не произвольное spot gold.
[Описание соглашения](https://www.cmegroup.com/market-data/files/market-data-license-agreement-updates-june-2026.pdf).

- Какой product/contract и continuous roll rule эквивалентны нужному ряду?
  Это Close или settlement, в какой валюте/единицах и timezone?
- Какие права покрывают хранение, display, training/inference, public derived
  outputs, exports/API и model artifacts? Есть ли допустимый бесплатный профиль?
- Какие corrections, history и технические лимиты доступны для выбранной серии?

## Как Фиксировать Ответ

Для каждого источника сохранить документ/ответ, дату, exact series/resource,
permitted purpose и условия атрибуции, ограничения пользователей/выгрузок,
стоимость если указана и решение ответственного. Не переносить разрешение
одного ряда или способа использования на все остальные. Молчание и технический
HTTP 200 не считаются разрешением. Внешние обращения требуют отдельного
решения об отправке; на этом шаге никакие контакты не используются.
