# Security

## Ключи

- `release-private.pem` хранится офлайн и никогда не попадает в runtime-архив.
- `release-public.pem` встраивается в seed/bootstrap environment.
- Ethereum publisher использует отдельный ключ через `EOH_ETH_PRIVATE_KEY`.
- Никакие приватные ключи не записываются в SQLite, state JSON или логи.

## Bootstrap

Bootstrap проверяет одновременно SHA-256 и ECDSA-подпись точного архива. До проверки архив не распаковывается и не исполняется. Распаковщик запрещает:

- абсолютные пути и `..`;
- symlink и hardlink;
- устройства, FIFO и специальные файлы;
- превышение лимитов количества файлов и распакованного размера.

`EOH_REMOVE_BOOTSTRAP=1` существует только для одноразового seed-контейнера и выключен по умолчанию. Проект не маскирует процесс, не внедряется в автозапуск и не пытается обходить контроль оператора.

## HTTP API

В production обязательно установи `EOH_API_TOKEN`, закрой порт reverse proxy и не позволяй конечному клиенту самостоятельно назначать `price_cents`. Endpoint `/v1/ledger` предназначен только для доверенного backend.

## Website context

Сбор контекста выключен по умолчанию. При включении разрешены только публичные HTTPS-адреса на портах 80/443; private, loopback, link-local и reserved IP блокируются до запроса и после redirect.

## Reporting

Не публикуй действующие ключи, RPC credentials, API tokens и подписанные production manifests в issue или логи CI.
