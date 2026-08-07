# Implementation notes from the source draft

Исходный MD содержал архитектурную идею и несколько взаимно несовместимых черновиков. В ZIP сохранена идея, но исправлены места, из-за которых прежний набор файлов не запускался:

- репозиторий и package называются `earn-or-halt`, а не `agent-bootstrap`;
- восстановлены полностью обрезанные `bootstrap.sh`, `orchestrator.py` и HTTP service;
- удалён фиктивный CID `bafy...demo` из исполняемого кода;
- нет ручной реализации Ethereum Keccak/RLP с неверным `v`;
- release ECDSA key отделён от Ethereum publisher key;
- подпись проверяет точные байты архива, а не JSON с нестабильной сериализацией;
- IPFS/IPNS и Blockscout оформлены transport adapters, локальный режим не зависит от них;
- приватный release key не передаётся runtime;
- распаковка tar защищена от path traversal и специальных файлов;
- self-removal seed выключен по умолчанию;
- runtime не занимается скрытой персистентностью, массовой рассылкой или добычей чужих API keys;
- добавлены persistent ledger, экономическая policy, API, unit tests и end-to-end smoke test.
