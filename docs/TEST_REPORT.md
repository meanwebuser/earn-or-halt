# Test report

Проверка выполнена 2026-08-11 на свежем shallow clone main в staging
directory.

## Passed

~~~
python3 -m unittest discover -s tests -v
Ran 10 tests ... OK
~~~

Проверены policy decisions, mock provider, SQLite job/ledger lifecycle,
persistent halt и безопасная распаковка traversal-sensitive tar archive.

~~~
./scripts/smoke-test.sh
smoke test passed
~~~

Smoke path создаёт временный secp256k1 release key, deterministic
release.tar.gz и local file manifest; затем:

1. bootstrap читает manifest;
2. fetches file:// artifact;
3. сверяет SHA-256 и OpenSSL signature;
4. safe-extract/install'ит release;
5. запускает mock API;
6. выполняет одну job: 29 cents revenue, 1 cent cost, 28 cents profit;
7. принимает POST /v1/halt и наблюдает остановку процесса;
8. отвергает тот же manifest после добавления bytes к artifact.

Тесты и smoke не создают публикацию во внешней сети.

## Не проверялось в этом pass

- live Ethereum transaction или оплаченный RPC;
- live IPFS/IPNS publication и pin persistence;
- Docker image build;
- платный OpenAI-compatible provider;
- независимая подпись клиента за revenue;
- production reverse proxy, TLS и public authentication deployment.

Поэтому тестовый результат подтверждает локальный MVP и signed bootstrap
canary, но не финансовую или production-ready гарантию.
