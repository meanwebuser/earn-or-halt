# Test report

Timestamp: 2026-08-08 01:56:03 UTC+3

Environment:

- Python 3.13.5
- OpenSSL 3.5.5
- POSIX shell syntax checked with `sh -n`

Passed:

- Python bytecode compilation for runtime, bootstrap helpers, tools and tests.
- 10 unit tests: economic policy, persistent halt, SQLite ledger/job lifecycle, mock provider and safe tar extraction.
- End-to-end signed bootstrap smoke test:
  1. generate secp256k1 release key;
  2. build deterministic `release.tar.gz`;
  3. create signed manifest;
  4. resolve local pointer;
  5. verify SHA-256 and ECDSA;
  6. install immutable release;
  7. start API;
  8. execute one profitable job;
  9. verify 29 cents revenue, 1 cent cost and 28 cents profit;
  10. request persistent halt and observe process exit;
  11. modify one artifact byte and verify bootstrap rejection.

Not exercised in this environment:

- A live Ethereum transaction or paid RPC endpoint.
- A live IPFS/IPNS publish operation; the adapters and local pointer path are included.
- Docker image build, because Docker was not available in the execution environment.
- A paid OpenAI-compatible provider; the deterministic mock provider was used.
