# Earn or Halt

> **Зарабатывай или остановись.**
>
> Код должен уметь воскресать.
> Убыточная экономика — нет.

Большинство «автономных агентов» пытаются решить одну задачу:
**как продолжать работать как можно дольше?**

Earn or Halt задаёт вопрос раньше:
**а зачем этому процессу вообще продолжать работать?**

Если сервис создаёт больше ценности, чем сжигает, он получает право
на следующий цикл.

Если денег не хватает, маржа исчезла, ошибки копятся или работа никому
не нужна — он не делает вид, что всё нормально. Он записывает `halt`
и останавливается.

Не падает.
Не «временно деградирует».
Не перезапускается контейнером ещё тысячу раз.

**Принимает экономическое решение умереть.**

---

## Философия

У программы нет естественного права на uptime.

Есть стартовый кредит.
Есть работа.
Есть подтверждённая выручка.
Есть фактическая стоимость.

Перед каждой потенциально платной операцией агент считает:

```text
available = starting_credit + revenue - cost
margin    = (revenue - cost) / revenue
```

Пока экономика выдерживает — `continue`.

Когда следующий шаг уже нельзя честно оплатить — `halt`.

`halt` хранится в SQLite и переживает обычный перезапуск. Это не retry,
не backoff и не случайная ошибка процесса. Стереть решение может только
явное действие оператора.

Вторая половина идеи — resurrection loop.

Сам процесс смертен. Его релиз — восстанавливаем.

Минимальный seed находит указатель через локальный файл, HTTPS или
Blockscout, загружает архив через HTTPS/IPFS/IPNS, проверяет точные байты
релиза и только после этого запускает код.

Transport может соврать.
Подпись — нет.

Blockscout, IPFS и IPNS сообщают, **где искать**.
Право на исполнение даёт только release public key.

Отсюда вся конструкция:

```text
resilient code + mortal economics
```

**Не бессмертный агент.**

**Агент, который каждый цикл заново зарабатывает право существовать.**

---

## Что это сейчас

Рабочий MVP автономного B2B-сервиса, состоящий из двух независимых
контуров.

### 1. Economic runtime ⚖️

Runtime:

- принимает задания на генерацию B2B-черновиков;
- создаёт результат через `mock` или OpenAI-compatible provider;
- записывает подтверждённую выручку и фактическую стоимость;
- перед платной операцией спрашивает economic policy: `continue` или
  `halt`;
- сохраняет очередь, ledger и halt-флаг в SQLite;
- отдаёт состояние через HTTP API.

Проект **не рассылает письма сам**. Он только создаёт черновики и
API-результаты.

### 2. Signed resurrection bootstrap ♻️

Bootstrap:

1. получает release manifest из файла, URL или последней подходящей
   транзакции Blockscout;
2. загружает `release.tar.gz` через `file://`, HTTPS, IPFS или IPNS;
3. сверяет SHA-256;
4. проверяет ECDSA/secp256k1-подпись точных байтов архива;
5. безопасно распаковывает релиз;
6. атомарно переключает `current` на новую версию;
7. запускает runtime.

Bootstrap не доверяет transport и не передаёт runtime приватный release
key.

---

## Самое важное различие

### Halt — не crash

Crash означает: «что-то сломалось, попробуй снова».

Halt означает: «продолжение работы нарушает заданную экономику».

Обычный рестарт не должен превращать убыточную систему в вечный
пылесос для денег.

### Resurrection — не self-modification

Runtime не переписывает и не подписывает собственный код.

Release собирается отдельным операторским pipeline. Поэтому захваченный
процесс не получает автоматического права закрепить себя в следующем
релизе.

Ethereum publisher key и release signing key тоже разделены:
компрометация указателя не даёт права подписать исполняемый код.

---

## Когда агент останавливается

Policy записывает постоянный halt-флаг, когда выполняется хотя бы одно
условие:

- следующая операция дороже доступного кредита;
- следующий расход превысит дневной лимит;
- grace-период закончился без выручки;
- маржа после grace-периода ниже заданного минимума;
- достигнут предел последовательных ошибок;
- достигнут настроенный предел пустых циклов;
- оператор вызвал `POST /v1/halt`.

По умолчанию:

```text
starting credit          100 cents
grace period             3 successful jobs
minimum margin           20%
daily cost cap           500 cents
consecutive failures     5
```

Все значения настраиваются через environment variables.

---

## Запуск за минуту

Нужен Python 3.11+.

```bash
cp .env.example .env
set -a; . ./.env; set +a
python3 -m earn_or_halt run
```

Проверка:

```bash
curl http://127.0.0.1:8787/healthz
```

Создание первой задачи:

```bash
curl -sS http://127.0.0.1:8787/v1/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "recipient_name": "Анна",
    "recipient_title": "директор по развитию",
    "company": "Example Industrial",
    "icp": "региональная производственная компания",
    "offer": "автоматизировать обработку входящих заявок с помощью ИИ",
    "tone": "коротко и по делу",
    "price_cents": 29,
    "wait_seconds": 10
  }'
```

По умолчанию используется `mock`-провайдер. Поэтому весь экономический
цикл проверяется без API-ключей, Ethereum и IPFS.

При установленном `EOH_API_TOKEN` добавь:

```text
Authorization: Bearer <token>
```

---

## Посмотреть, жив ли он экономически

```bash
curl -sS http://127.0.0.1:8787/v1/state
```

Ответ содержит:

- текущее состояние процесса;
- доступный кредит;
- выручку и расходы;
- рассчитанную маржу;
- решение policy;
- причину halt, если она есть.

Принудительная остановка:

```bash
curl -sS http://127.0.0.1:8787/v1/halt \
  -H 'Content-Type: application/json' \
  -d '{"reason":"operator decision"}'
```

Сброс после осознанного решения оператора:

```bash
python3 -m earn_or_halt clear-halt
```

---

## HTTP API

| Метод | Путь | Что делает |
|---|---|---|
| `GET` | `/healthz` | Liveness без авторизации |
| `GET` | `/v1/state` | Экономика, policy и runtime state |
| `GET` | `/v1/jobs` | Последние задания |
| `GET` | `/v1/jobs/{id}` | Одно задание |
| `POST` | `/v1/jobs` | Поставить задание в очередь |
| `POST` | `/v1/generate` | Поставить и немного подождать результат |
| `POST` | `/v1/ledger` | Записать revenue/cost/credit/refund |
| `POST` | `/v1/halt` | Записать постоянный halt |
| `POST` | `/v1/clear-halt` | Явно снять halt, пока API отвечает |

`price_cents` означает уже подтверждённую выручку по успешно выполненной
задаче. В production это значение должен выставлять доверенный payment
или backend layer, а не конечный клиент.

Полное описание: [`docs/API.md`](docs/API.md).

---

## Подключить настоящую модель

```bash
export EOH_PROVIDER=openai-compatible
export EOH_LLM_BASE_URL=https://provider.example/v1
export EOH_LLM_API_KEY=...
export EOH_PRIMARY_MODEL=your-primary-model

# Необязательный fallback
export EOH_FALLBACK_BASE_URL=https://fallback.example/v1
export EOH_FALLBACK_API_KEY=...
export EOH_FALLBACK_MODEL=your-fallback-model
```

Стоимость одной операции задаётся явно:

```bash
export EOH_PROVIDER_COST_CENTS=1
```

Проект намеренно не угадывает цены провайдера. Экономическое решение
должно опираться на известную стоимость, а не на красивую иллюзию
точности.

---

## Resurrection demo 🔒

Локальный demo использует тот же bootstrap-flow, но без внешней сети:

```bash
./scripts/demo-local.sh
```

Скрипт:

1. создаёт временную пару release keys;
2. собирает `release.tar.gz`;
3. подписывает точные байты архива;
4. создаёт `file://` manifest;
5. запускает релиз через `bootstrap.sh`;
6. проверяет API и runtime state.

Полная проверка:

```bash
make test
make smoke
```

---

## Цепочка доверия

```text
Blockscout / HTTPS / IPFS / IPNS
                │
                │  только location metadata
                ▼
          manifest.json
                │
                │  artifact + sha256 + signature
                ▼
          release.tar.gz
                │
        ┌───────┴────────┐
        │ SHA-256        │
        │ ECDSA verify   │
        │ safe extract   │
        └───────┬────────┘
                ▼
        immutable release
                │
                ▼
            current
                │
                ▼
        economic runtime
                │
        continue / halt
```

Transport отвечает за доступность.

Release key отвечает за доверие.

Economic policy отвечает за право продолжать работу.

Это три разные обязанности. Они не должны сливаться в один приватный
ключ и один бесконечно живущий процесс.

---

## Формат release manifest

```json
{
  "schema": "earn-or-halt.release.v1",
  "version": "0.1.0",
  "created_at": "2026-08-08T00:00:00Z",
  "artifact": "ipfs://bafy...",
  "sha256": "64 lowercase hex characters",
  "signature": "base64 DER ECDSA signature over release.tar.gz"
}
```

Подпись ставится на **точные байты архива**, а не на заново
сериализованный JSON. Поэтому пробелы, Unicode и порядок ключей в
manifest не ломают проверку подписи.

---

## Собрать подписанный релиз

```bash
./tools/generate_release_key.sh .release-keys
python3 tools/build_release.py --output ./release.tar.gz
python3 tools/create_manifest.py \
  --artifact ./release.tar.gz \
  --artifact-uri "file://$(pwd)/release.tar.gz" \
  --private-key .release-keys/release-private.pem \
  --version 0.1.0 \
  --output ./manifest.json
```

Запуск seed:

```bash
EOH_POINTER_SOURCE=file \
EOH_POINTER_FILE="$(pwd)/manifest.json" \
EOH_RELEASE_PUBKEY="$(pwd)/.release-keys/release-public.pem" \
EOH_INSTALL_ROOT="$(pwd)/.install" \
EOH_DATA_DIR="$(pwd)/.data" \
EOH_FOREGROUND=1 \
./bootstrap.sh
```

---

## IPFS/IPNS

При наличии локального Kubo:

```bash
./tools/publish_ipfs.sh \
  ./release.tar.gz \
  .release-keys/release-private.pem \
  0.1.0 \
  ./manifest.json \
  earn-or-halt-release
```

Скрипт выводит `ipfs://...` и, если указано имя ключа, `ipns://...`.

Публичные IPFS gateways считаются best-effort transport. Для реального
развёртывания добавь собственный gateway в `EOH_IPFS_GATEWAYS`.

---

## Blockscout pointer

В `raw_input` или `input` последней входящей транзакции должна лежать
UTF-8 строка:

```text
ipns://<name>
```

или:

```text
https://registry.example/manifest.json
```

Запуск:

```bash
export EOH_POINTER_SOURCE=blockscout
export EOH_BLOCKSCOUT_BASE=https://eth.blockscout.com
export EOH_VANITY_ADDRESSES=0xAddress1,0xAddress2
./bootstrap.sh
```

Опциональная публикация pointer-транзакции:

```bash
pip install -r requirements-eth.txt
EOH_ETH_RPC_URL=... \
EOH_VANITY_ADDRESS=0x... \
EOH_ETH_PRIVATE_KEY=... \
python3 tools/publish_eth_pointer.py 'ipns://k51...'
```

Ethereum wallet key и release signing key должны быть разными.

---

## Docker

```bash
docker compose up --build
```

Compose запускает runtime напрямую.

Resurrection seed удобнее держать отдельным минимальным слоем, куда
копируются только:

```text
bootstrap.sh
bootstrap/
release-public.pem
```

---

## Что здесь уже настоящее

- POSIX bootstrap под Alpine;
- pointer sources: `file`, `url`, `blockscout`;
- resource schemes: `file://`, HTTPS, IPFS, IPNS;
- параллельная гонка IPFS gateways;
- SHA-256 и ECDSA/secp256k1 verification;
- безопасная распаковка без traversal, symlink, hardlink и device files;
- immutable releases и атомарный `current` symlink;
- SQLite queue, ledger и persistent halt;
- жёсткая economic policy;
- HTTP API без внешних runtime-зависимостей;
- `mock` и OpenAI-compatible providers с fallback;
- unit tests и end-to-end resurrection smoke test.

## Чего здесь пока нет

- платёжной интеграции;
- автоматической массовой рассылки;
- гарантированного публичного IPFS storage;
- автоматического ценообразования по тарифам провайдеров;
- самопереписывания runtime;
- магического «полностью автономного бизнеса».

Это MVP механизма.

Он уже доказывает главную мысль:

> **воскресить код можно автоматически;**
>
> **воскресить провальную экономику — только самообманом.**

---

## Структура

```text
earn-or-halt/
├── bootstrap.sh              # минимальный resurrection seed
├── bootstrap/                # resolver, downloader, safe extractor
├── earn_or_halt/             # API, queue, ledger, policy, providers
├── tools/                    # release, IPFS and Ethereum helpers
├── scripts/                  # local demo and smoke tests
├── tests/
├── docs/
├── Dockerfile
└── docker-compose.yml
```

Подробнее:

- [`docs/DESIGN.md`](docs/DESIGN.md) — архитектурные решения;
- [`docs/API.md`](docs/API.md) — HTTP API;
- [`docs/IMPLEMENTATION_NOTES.md`](docs/IMPLEMENTATION_NOTES.md) — что
  исправлено относительно исходного черновика;
- [`docs/TEST_REPORT.md`](docs/TEST_REPORT.md) — проверенные сценарии;
- [`SECURITY.md`](SECURITY.md) — границы безопасности.

---

## Одна строка

**Earn or Halt — это автономный сервис, который умеет воскресить свой
подписанный код, но отказывается воскресать экономически, пока не
докажет, что создаёт больше ценности, чем стоит его следующий цикл.**
