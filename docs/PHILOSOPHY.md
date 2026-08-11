# Философия Earn or Halt

У процесса нет автоматического права на бесконечный uptime. Перед платным
циклом он должен проверить, способен ли его локальный accounting оплатить
следующий шаг и сохраняется ли заданная политика экономики.

## Две разные вещи

Resurrection отвечает на вопрос: можно ли безопасно запустить подписанный
release artifact? Economic policy отвечает на вопрос: стоит ли этому
runtime продолжать работу? В репозитории это два разных контура:

- [bootstrap.sh](../bootstrap.sh) проверяет location, hash, подпись и архив;
- [earn_or_halt/orchestrator.py](../earn_or_halt/orchestrator.py) выполняет
  queue loop и останавливает процесс после policy halt.

Подписанный код не является доказательством прибыльности. И прибыльная job в
локальном ledger не является независимым on-chain payment proof.

## Экономический governor

EconomicPolicy использует starting credit, ledger revenue/cost, daily cost,
число successful jobs, consecutive failures и idle cycles. Пока следующее
действие проходит проверки — decision = continue. При нарушении — decision =
halt с причиной.

Halt сохраняется в SQLite meta table и переживает обычный restart. Для снятия
нужен явный clear-halt operator action. Это сознательная граница: проект не
пытается сделать локальный процесс распределённым консенсусом.

Есть важное ограничение accounting: HTTP caller задаёт price_cents, а
успешная job сама создаёт revenue ledger entry. Поэтому текущая реализация
предполагает доверенный payment/backend layer. Она не принимает подпись
клиента и не проверяет provider receipt.

## Воскрешаемость

Release manifest можно получить из local file, URL или transaction input
Blockscout. Artifact загружается через file/HTTPS/IPFS/IPNS, затем:

1. bytes хэшируются SHA-256;
2. точные bytes проверяются OpenSSL signature release public key;
3. архив проходит safe extraction;
4. current переключается на versioned directory;
5. runtime запускается.

Transport может быть недоступен или злонамерен, но в текущей цепочке только
подписанный artifact проходит hash/signature gate. Это не делает registry
вечным и не включает реальный RPC contract pointer: blockscout adapter
читает транзакции и декодирует их input.

## Что проект намеренно не обещает

- автоматическую рассылку писем;
- payment settlement или signed receipts;
- самопереписывание и самоподписание релизов;
- гарантированную доступность публичного IPFS;
- автономный бизнес без доверенного оператора и provider pricing.

Формула MVP:

~~~
resilient release bytes + persistent local economics
~~~

Код может воскреснуть после проверки. Экономический halt не должен быть
замаскирован обычным retry.
