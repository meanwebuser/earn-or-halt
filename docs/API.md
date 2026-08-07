# HTTP API

Все `/v1/*` endpoints требуют `Authorization: Bearer <EOH_API_TOKEN>`, если token задан. `/healthz` всегда открыт.

## POST /v1/jobs

```json
{
  "recipient_name": "Анна",
  "recipient_title": "директор по развитию",
  "company": "Example Industrial",
  "company_url": "https://example.com",
  "icp": "производственная компания",
  "tone": "коротко",
  "offer": "автоматизация обработки заявок",
  "metadata": {"crm_id": "lead-42"},
  "price_cents": 29,
  "estimated_cost_cents": 1
}
```

`company` и `offer` обязательны. Ответ `202` содержит job.

## POST /v1/generate

Тот же body плюс `wait_seconds`. Endpoint ждёт не более 120 секунд. Возвращает `200`, когда job выполнен, `502` при ошибке либо `202`, если job ещё в очереди.

## POST /v1/ledger

```json
{"kind":"credit","amount_cents":500,"note":"operator top-up"}
```

Разрешённые `kind`: `revenue`, `cost`, `credit`, `refund`.

## POST /v1/halt

```json
{"reason":"manual maintenance"}
```

Halt записывается постоянно. Worker завершится на следующей проверке policy.
