# Earn or Halt

**Зарабатывай или остановись.** Запускаемый MVP автономного B2B-сервиса с двумя независимыми контурами:

1. **Economic governor** — принимает задачи на генерацию черновиков писем, считает подтверждённую выручку и стоимость, после чего продолжает работу либо необратимо ставит halt-флаг.
2. **Signed resurrection bootstrap** — получает адрес подписанного релиза из файла, URL или последней транзакции Blockscout, загружает архив через HTTPS/IPFS/IPNS, проверяет SHA-256 и ECDSA-подпись, безопасно распаковывает и запускает процесс.

Проект ничего не рассылает сам. Он только готовит черновики и API-результаты. Встроенный `mock`-провайдер позволяет полностью проверить продукт без платных ключей, Ethereum и IPFS.

## Что уже работает

- POSIX `bootstrap.sh`, пригодный для Alpine.
- Источники pointer: `file`, `url`, `blockscout`.
- Ресурсы: `file://`, `https://`, `ipfs://`, `ipns://`.
- Параллельная гонка IPFS-гейтвеев.
- Подпись точных байтов `release.tar.gz` через OpenSSL ECDSA/secp256k1.
- Проверка SHA-256 до распаковки.
- Защищённая распаковка без traversal, symlink, hardlink и device-файлов.
- SQLite-очередь, ledger и постоянный halt-флаг.
- Жёсткие правила по марже, дневным затратам, доступному кредиту, числу ошибок и простою.
- HTTP API без внешних Python-зависимостей.
- `mock` и OpenAI-compatible LLM providers с fallback.
- Опциональный безопасный сбор контекста с публичного HTTPS-сайта компании.
- Локальный resurrection smoke test.
- Опциональные скрипты публикации в Kubo/IPNS и Ethereum.

## Самый быстрый запуск

```bash
cp .env.example .env
set -a; . ./.env; set +a
python3 -m earn_or_halt run
```

Проверка:

```bash
curl http://127.0.0.1:8787/healthz
```

Создание задачи:

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

При установленном `EOH_API_TOKEN` добавь заголовок:

```text
Authorization: Bearer <token>
```

## Экономическая логика

На каждой итерации процесс вычисляет:

```text
available = starting_credit + revenue - cost
margin    = (revenue - cost) / revenue
```

Процесс записывает halt-флаг и завершается, когда выполняется хотя бы одно условие:

- следующая операция не помещается в доступный кредит;
- будет превышен дневной предел затрат;
- после grace-периода маржа ниже минимальной;
- достигнут предел последовательных ошибок;
- достигнут настроенный предел пустых циклов;
- оператор вызвал `POST /v1/halt`.

Halt сохраняется в SQLite и переживает перезапуск. Сброс:

```bash
python3 -m earn_or_halt clear-halt
```

## API

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/healthz` | liveness без авторизации |
| `GET` | `/v1/state` | состояние, решение policy и экономика |
| `GET` | `/v1/jobs` | последние задачи |
| `GET` | `/v1/jobs/{id}` | одна задача |
| `POST` | `/v1/jobs` | поставить задачу в очередь |
| `POST` | `/v1/generate` | поставить задачу и немного подождать результат |
| `POST` | `/v1/ledger` | вручную записать revenue/cost/credit/refund |
| `POST` | `/v1/halt` | постоянная остановка |
| `POST` | `/v1/clear-halt` | сброс halt-флага, пока процесс ещё отвечает |

`price_cents` — уже подтверждённая выручка по успешно выполненной задаче. В продакшене это поле должен выставлять доверенный payment/backend слой, а не конечный клиент.

## OpenAI-compatible provider

```bash
export EOH_PROVIDER=openai-compatible
export EOH_LLM_BASE_URL=https://provider.example/v1
export EOH_LLM_API_KEY=...
export EOH_PRIMARY_MODEL=your-primary-model

# Необязательно
export EOH_FALLBACK_BASE_URL=https://fallback.example/v1
export EOH_FALLBACK_API_KEY=...
export EOH_FALLBACK_MODEL=your-fallback-model
```

Стоимость одной операции задаётся явно через `EOH_PROVIDER_COST_CENTS`. Проект не угадывает цены конкретного провайдера.

## Локальный resurrection demo

Команда создаёт временную пару ключей, собирает релиз, подписывает архив, формирует `file://`-манифест и запускает его через тот же bootstrap, который затем используется с IPFS/Blockscout:

```bash
./scripts/demo-local.sh
```

Полная автоматическая проверка:

```bash
make test
make smoke
```

## Формат релизного манифеста

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

Подпись вычисляется по **точным байтам архива**. Bootstrap не восстанавливает JSON для проверки подписи, поэтому пробелы, порядок ключей и разные реализации JSON не ломают цепочку доверия.

## Создание подписанного релиза

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

Скрипт выводит `ipfs://...` и, если передано имя ключа, `ipns://...`. В production публичные гейтвеи не должны быть единственным критическим каналом: добавь собственный gateway в `EOH_IPFS_GATEWAYS`.

## Blockscout pointer

В `raw_input`/`input` последней входящей транзакции на один из адресов должна лежать UTF-8 строка:

```text
ipns://<name>
```

или:

```text
https://registry.example/manifest.json
```

Затем:

```bash
export EOH_POINTER_SOURCE=blockscout
export EOH_BLOCKSCOUT_BASE=https://eth.blockscout.com
export EOH_VANITY_ADDRESSES=0xAddress1,0xAddress2
./bootstrap.sh
```

Опциональный отправитель pointer-транзакции:

```bash
pip install -r requirements-eth.txt
EOH_ETH_RPC_URL=... \
EOH_VANITY_ADDRESS=0x... \
EOH_ETH_PRIVATE_KEY=... \
python3 tools/publish_eth_pointer.py 'ipns://k51...'
```

Ethereum-кошелёк и ключ подписи релиза должны быть разными ключами.

## Docker

```bash
docker compose up --build
```

Docker запускает сам runtime, без resurrection seed. Seed удобнее тестировать локально или в отдельном минимальном образе, куда копируются только `bootstrap.sh`, каталог `bootstrap/` и публичный ключ релиза.

## Структура

```text
earn-or-halt/
├── bootstrap.sh
├── bootstrap/                 # resolver, downloader, safe extractor
├── earn_or_halt/              # API, queue, ledger, policy, providers
├── tools/                     # release/IPFS/Ethereum helpers
├── scripts/                   # demo and smoke tests
├── tests/
├── docs/
├── Dockerfile
└── docker-compose.yml
```

## Границы MVP

- Нет платёжной интеграции: доверенный backend должен подтверждать `price_cents`.
- Нет автоматической массовой рассылки.
- Runtime не переписывает собственный код и не хранит release private key.
- Ethereum и IPFS не нужны для локального или Docker-запуска.
- Публичные IPFS gateways считаются best-effort transport, а не гарантированным хранилищем.

См. также [`docs/DESIGN.md`](docs/DESIGN.md), [`docs/API.md`](docs/API.md), [`docs/IMPLEMENTATION_NOTES.md`](docs/IMPLEMENTATION_NOTES.md) и [`SECURITY.md`](SECURITY.md).
