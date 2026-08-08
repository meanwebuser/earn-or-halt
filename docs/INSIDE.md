# Earn or Halt — что внутри

> Продуктовый разбор. Не философия (см. `PHILOSOPHY.md`), не
> формальные гарантии (см. `PROOFS.md`), а именно архитектура:
> что код делает сегодня и какие слои ещё остаются дизайном.

## Три вложенных цикла

Агент живёт в трёх циклах, вложенных друг в друга:

1. **Экономический цикл** — выполнение работы, учёт выручки и трат,
   решение policy (`continue` / `halt`).
2. **Selection cycle** — сравнение версий по `rank_signal`,
   перераспределение денег, ejection.
3. **Resurrection cycle** — если текущая версия умерла, поднять её
   код с нуля из IPFS/Blockscout.

У каждого свой timeout и свой failure mode. Экономика убивает
быстрее, чем selection, selection — медленнее, чем resurrection.

## Экономический цикл — реализован

Runtime — Python-сервис с SQLite-очередью и ledger'ом. Работает в
текущем MVP:

- Принимает задания на генерацию B2B-черновиков.
- Выполняет через `mock` или OpenAI-compatible provider с fallback.
- Считает `earned_revenue`, `cost`, `margin`.
- Перед каждой платной операцией спрашивает policy: `continue` или
  `halt`.
- Хранит `halt`-флаг постоянно (переживает рестарт).
- Отдаёт состояние через HTTP API.

## Selection cycle — дизайн (новое)

Это слой, который появляется поверх существующего runtime. Его
задача — отличать честно заработанную прибыль от deposits и решать,
кто из версий живёт.

### Ключевое правило

```
rank_signal(V) = f(earned_profit(V))
```

Никакая функция от `balance` или `deposits` в `rank_signal` не
входит. Это инвариант **I1** из `PROOFS.md` и единственная защита
от whale-атак.

### Top-N

`N = 3`, hardcoded. Не env, не config, не параметр. Чтобы поменять —
нужен новый релиз. Почему 3: наименьшее нечётное, требует 2 из 3
для большинства. 2 — тривиальное доминирование одного. 5+ —
накладные расходы на координацию.

`N` — это **не про выживание**, а про приоритизацию входящего
потока. Новая работа роутится на топ-3 по `rank_signal`.

### Биоразнообразие эмерджентно

Все версии с `positive earned_profit` в последнем окне — **живы**.
Если реально 100 версий заработали — все 100 живут. Если 2 — живут
2. Никто не «убит» за то, что оказался ниже топа.

`N` отвечает только за то, кому первой идёт новая работа. Не за то,
кому жить.

### Timeout и heartbeat

- `TIMEOUT = 30 дней` (hardcoded) — если версия не заработала за 30
  дней, другие трактуют её как halted.
- `HB_PERIOD = 1 час` (hardcoded) — каждая живая версия шлёт
  `Heartbeat = {pubkey, state_hash, timestamp, sig_V}` в публичный
  реестр.
- Отсутствие heartbeat дольше `TIMEOUT` → ejection.

Это инварианты **I3** и **I4** из `PROOFS.md`.

### Pinned protocol

Клиенты и провайдеры подписывают receipts только если `code_hash`
версии совпадает с хэшем текущего релиза. Форкнутая версия с
другим `code_hash` не получает валидных receipts → нет
`earned_profit` → не в топе. Это инвариант **I5** из `PROOFS.md`.

### Tenure bonus (опционально)

Версия, дольше всех находящаяся в топе, получает бонус к
`rank_signal`. Защищает от «свежей» версии, которая вдруг хорошо
заработала и вытеснила долгожителя. Формула бонуса — design.

## Resurrection cycle — реализован

Когда текущая версия halt'нулась, минимальный seed поднимает её
обратно:

1. Достаёт pointer из файла, URL или последней транзакции Blockscout.
2. Загружает `release.tar.gz` через `file://`, HTTPS, IPFS или IPNS.
3. Сверяет SHA-256.
4. Проверяет ECDSA/secp256k1-подпись точных байтов архива.
5. Безопасно распаковывает (no traversal, no symlinks, no devices).
6. Атомарно переключает `current` symlink.
7. Запускает runtime.

Закрытый ключ release'а живёт только в RAM во время сборки. Runtime
его не видит и подписать себя в новый релиз не может.

## Enforcement — распределённый, не центральный

Никакого kill switch. Каждая честная версия:

- проверяет инварианты локально;
- отказывается роутить работу halted-версиям;
- отказывается признавать receipts от halted-версий и от версий с
  чужим `code_hash`;
- трактует отсутствие heartbeat > `TIMEOUT` как halt.

Ejection = социальное исключение, как в Bitcoin: пока большинство
честных, misbehaving узел просто отрезан от роутинга.

## General pool (commons)

Если версия выбывает по таймауту или по проигрышу:

- **НЕ** переводит деньги текущему топ-1 (иначе whale всё равно
  забрал бы всё через deposits);
- переводит остатки в **общий пул**;
- из общего пула финансируются стартовые кредиты новых честных
  версий.

Whale-форк, который «вытеснил» hard-working версию, не получает
ничего из её остатков. Commons растёт, новые версии получают
стартовый кредит, diversity сохраняется.

## Что реализовано, что дизайн

Текущий MVP (Python):

✅ **Реализовано:**
- Экономический цикл: mock + OpenAI providers, SQLite ledger,
  halt-policy
- HTTP API: `/healthz`, `/v1/state`, `/v1/generate`, `/v1/halt`,
  `/v1/jobs`, `/v1/ledger`
- Resurrection cycle: bootstrap.sh, IPFS/HTTPS fetch, SHA-256,
  ECDSA/secp256k1
- Safe extraction: без traversal, symlink, hardlink, device-файлов
- Тесты: 4 unit + resurrection smoke-test

❌ **Дизайн (нужно построить):**
- Selection protocol (сравнение `rank_signal` между версиями)
- Anti-whale в runtime (разделение `earned_revenue` vs `deposits`)
- Heartbeat + public registry публикация
- Top-N routing (новая работа идёт на топ-3)
- Pinned protocol (клиенты/провайдеры проверяют `code_hash`)
- General pool и финансирование стартовых кредитов
- Tenure bonus формула
- Receipt TTL и anti-replay
- Distributed ejection enforcement в runtime

Текущий MVP — это runtime + resurrection. Selection — слой, который
нужно построить поверх.
