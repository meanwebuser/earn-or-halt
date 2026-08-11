# Доказуемые свойства и границы

Этот документ перечисляет только свойства, которые следуют из текущего
исходника и тестов. Это не формальная security proof распределённого
протокола.

## Economic policy

Для stats из SQLite policy вычисляет:

~~~
available = starting_credit_cents + revenue_cents - cost_cents
margin = (revenue_cents - cost_cents) / revenue_cents
~~~

Тесты [tests/test_policy.py](../tests/test_policy.py) подтверждают:

- продолжение в grace period;
- halt при недостатке available credit;
- halt при margin ниже порога после grace;
- halt при daily cost cap;
- приоритет external halt reason.

Orchestrator читает persistent halt reason перед следующей job. При policy
halt он устанавливает reason, пишет финальное runtime state, останавливает
server и возвращает 20. Это локальный control flow, а не consensus.

## Persistence and ledger

SQLite schema в [earn_or_halt/storage.py](../earn_or_halt/storage.py):

- jobs проходят queued → running → succeeded/failed;
- успешная job в одной транзакции записывает result, actual cost и
  configured price как revenue;
- failed provider call может записать failure cost;
- ledger принимает только revenue, cost, credit и refund;
- stats вычитает refund из revenue и считает profit = revenue - cost;
- halt reason хранится в meta table.

Тесты [tests/test_storage.py](../tests/test_storage.py) проверяют job/ledger
lifecycle и request/clear halt.

## Signed resurrection chain

В [bootstrap.sh](../bootstrap.sh) реализованы последовательные gates:

1. manifest schema и поля проверяются;
2. artifact fetch ограничен поддержанными schemes;
3. SHA-256 bytes должен совпасть с manifest;
4. OpenSSL проверяет подпись точных archive bytes public key;
5. safe extractor отвергает traversal и опасные tar entry types;
6. release install происходит в versioned directory, затем меняется symlink
   current.

tests/test_safe_extract.py проверяет обычный файл и path traversal. Полный
signed smoke path дополнительно проверяет tampered artifact rejection.

## Что не следует выводить

### Нет signed customer/provider receipts

Поле price_cents приходит от API caller, а mock/OpenAI-compatible provider
возвращает только result и объявленную cost. Runtime не проверяет подпись
платежа клиента и не получает cryptographic provider receipt.

### Нет on-chain economics

requirements-eth.txt и publish_eth_pointer.py — опциональный pointer
publisher. Основной runtime не отправляет revenue/cost в Ethereum. Blockscout
pointer adapter публикует location metadata, а не consensus о прибыльности.

### Нет kill switch через bootstrap

Bootstrap может запустить только artifact, прошедший local hash/signature
checks. Он не доказывает, что новый release экономически лучше, и не
переписывает локальный halt reason без отдельного operator action.

### Нет доказательства безопасности Docker/public deployment

Dockerfile и compose описывают packaging; в этой проверке образ не собирался,
а network/auth/reverse proxy configuration остаются deployment scope.

Итого: доказуемы локальные policy/storage переходы и целостность signed
artifact path; независимая оплата, provider truth, public availability и
распределённая selection остаются будущими границами.
