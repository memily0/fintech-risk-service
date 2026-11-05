# Кандидат Контракта Данных V1

Дата: 05.11.2026. Блок V1-01, подшаг 01.2. Россия является основой;
международные ряды нужны как контекст. Отдельного Казахстана нет.

**Результат: подготовлен candidate contract и проверяемые правила нормализации.
Production admission не выполнен. Точный CPI resource/коды измерений,
права использования и техническая проверка реальных ответов остаются открыты.**
Подшаг не объявляется полностью закрытым только из-за готовности документов.

## Что Подготовлено

- [candidate_contract.json](candidate_contract.json): идентичность 13 исходных
  рядов, 6 производных, units, временная семантика и запрещённые подмены.
- [observation.schema.json](observation.schema.json): JSON Schema нормализованной
  исходной записи с lineage, timestamp и явным missing/unknown.
- Локальный проверяющий модуль в research/tools/release/v1_data_contract.py:
  cross-field validation, prospective availability, CPI normalization и
  выбор curve maturities по заголовкам. Это не подключённый production adapter.
- [rights_questions.md](rights_questions.md): профиль использования и семь
  групп точных вопросов правообладателям/поставщикам. Ничего не отправлено.
- [finding_handoff.csv](finding_handoff.csv): связь каждого из 12 предыдущих
  замечаний с проектным решением и оставшейся проверкой.
- [verification.md](verification.md): команды, фактические тесты и ограничения.

## 1. Зафиксированные Проектные Определения

Это решения кандидата, а не утверждение окончательного release scope.
Поле binding_status различает документированный endpoint, найденное семейство
показателя и ещё не выбранного поставщика. Все source rights по-прежнему pending.

| Группа | Кандидат | Ограничение |
| --- | --- | --- |
| USD/RUB, EUR/RUB | Официальные CBR R01235/R01239, RUB за единицу | Не биржевой spot; проверить nominal и effective date |
| Ключевая ставка | CBR DailyInfo KeyRate, отдельный genuine key-rate ряд | Нет refinancing fallback; история определения не ранее 17.09.2013 |
| ОФЗ | Бескупонная кривая ЦБ, maturities 1/2/5/10 лет | Не четыре отдельных bond quotes; maturity берётся из заголовка |
| Инфляция | Национальный all-items CPI, месяц к тому же месяцу прошлого года, индекс минус 100 | Не MoM/YTD/weekly/regional CPI; порядок строк не является selector |
| Brent | EIA Europe Brent Spot FOB, USD/barrel | Не futures; specific-series rights ещё не подтверждены |
| VIX | Cboe VIX daily close как кандидат замены Yahoo | Нужны exact resource, equivalence и права, не готовый feed |
| S&P 500 | Price index daily close | Entitled provider не выбран, ETF/total return не подменяют индекс |
| Gold | Нужен futures continuous ряд с зафиксированным roll | Новый provider и contract/roll ещё не выбраны; spot не эквивалентен |

Для CBR методы подтверждены [официальной документацией](https://www.cbr.ru/development/dws/),
tenors/units кривой [страницей кривой](https://www.cbr.ru/hd_base/zcyc_params/).
Это проверка описания, не запрос к числовому API и не разрешение публичной выдачи.

Временная зона для непроверенных глобальных feeds в JSON является кандидатом
нормализации и входит в open_fields, где требуется подтверждение. Она не
считается подтверждённой временной зоной всех дат источника. В частности,
нельзя смешать время observation и время release EIA в одном наивном date.

## 2. CPI: Что Удалось Уточнить

[FAQ Росстата](https://rosstat.gov.ru/folder/165737) в официальном поисковом
индексе содержит идентификатор витрины 11521100300010200001 и описание
выбора территории, набора товаров, вида показателя и периода. Дополнительная
[официальная FAQ-страница](https://38.rosstat.gov.ru/faq) ссылается также
на ЕМИСС indicator 31074. Это кандидаты идентификации, а не доказательство
точных кодов измерений и эквивалентности конкретного downloaded extract.

Прямые открытия основной страницы цен, FAQ и найденного print-варианта
в этом шаге завершились timeout. Индекс показывает национальную monthly
таблицу с историей с 1991 года, но не дал проверенного прямого XLSX URL.
Поэтому download_resource_url и provider_dimension_codes честно оставлены
null, dimension_codes_verified = false. Сетевой timeout не доказывает
отсутствие источника или запрет доступа с будущего сервера.

Не угадываем адрес файла и не переименовываем NSEDC extract в подтверждённый
первоисточник. В schema задаём наши canonical dimensions; будущий adapter
обязан документированно отобразить в них фактические provider codes.
Проверка canonical dimensions не доказывает корректность такого mapping.

## 3. Время И Доступность

У каждой исходной записи: series/definition/resource IDs, units, reference
period, effective date где применима, published_at или null, received_at,
source_timezone, snapshot ID и receipt hash. Число и статус качества
проверяются вместе: missing/rejected имеют value=null, не 0.

Этот кандидат реализует только **prospective receipt-based** режим:
запись не считается известной сервису раньше фактического получения.
Если publication time известен, он также учитывается; неизвестный остаётся null.
Время фактической публикации, которое позже времени получения якобы уже
опубликованной записи, отклоняется как ошибка метаданных. Scheduled release
и announcement event требуют другого типа записи, это не published observation.

Функция known_and_effective_by проверяет только границу знания и активности
на дату origin с часовым поясом. Она не подтверждает freshness, market calendar,
лицензию, закрытие daily session или пригодность для inference. Это проверяется
отдельными gates. Наличие старой известной записи не означает свежий сигнал.

Не переписываем прошлое: публикация старого значения не делает сегодняшний
revised download его историческим vintage. Для retrospective as-of реконструкции
нужны отдельный протокол, версии и evidence; этот код такую задачу не решает.

## 4. Производные И Совместимость

Сохраняем определения legacy transforms как явных кандидатов: 30 и 252 строки
календарной сетки, не обещание trading-session windows; неаннуализированная
sample std; drawdown от cumulative peak с указанным history anchor;
real key rate как nominal minus trailing released YoY CPI.
Правила fill, history anchor и source freshness пока не утверждены.

Функции и признаки должны наследовать lineage и availability родителей;
производный показатель не получает автоматических прав публикации.
Их расчёт на реальных источниках этим шагом не реализован и не оценён.

Новый genuine key rate отличается от старой склейки. Исправление release
семантики CPI и других источников также меняет inputs. Поэтому старые веса
не подключаются автоматически. Нужны новая версия feature/target protocol,
оценка и решение по артефакту, с сохранением исходных результатов.
Отсутствующий VIX или другая компонента stress target не выбрасывается молча.

## 5. Права И Следующий Шаг

Проверяющий код не является лицензирующей системой и не читает permissions
из записи пользователя. assert_candidate_usage_blocked намеренно всегда
отклоняет display/model_use/export/api_redistribution для текущего кандидата.
Новая production policy потребует отдельного доверенного реестра допусков
и его server-side реализации; данный prototype не выдаёт разрешения.

Ни один из 12 findings не отмечен runtime-fixed: пока это design/test
mitigation, а не исправление работающего builder или подтверждение источника.
Фактический статус в [трекере](../v1_stage_tracker.md) разделяет эти состояния.

Для завершения 01.2 осталось закрепить CPI resource/dimension mapping
и документировать конкретный usage basis там, где он пока неясен.
После этого 01.3: конечный технический probe plan по разрешённым источникам
и отдельный ограниченный прогон. Нельзя вместо этого запускать прежний
batch builder со всей историей и автоматически включать global feeds.

Можно продолжать офлайн проверку нормализаторов и fixtures, пока уточняются
внешние условия. Это не повод снижать admission criteria или выдавать
синтетические примеры за живой dashboard. Product code/weights, Git и
инфраструктура этим шагом не изменены.
