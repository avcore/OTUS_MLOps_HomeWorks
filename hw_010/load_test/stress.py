#!/usr/bin/env python3
"""
stress.py — имитация атаки / пиковой нагрузки на fraud-api.

Льёт N RPS на /predict в течение указанного времени → CPU подов растёт →
HPA скейлит до 6 → Prometheus замечает CPU > 80% × 5 минут → срабатывает
алерт FraudApiSaturatedAtMaxReplicas.

Требует: pip install httpx

Запуск:
    python stress.py --url http://158.160.X.X --rps 200 --duration 600

Для DDoS-имитации (срабатывание alert): rps >= 300, duration >= 600 секунд.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import random
import time

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("stress")


SAMPLE_TX = {
    "step":            500,
    "type":            "TRANSFER",
    "amount":          800_000.0,
    "nameOrig":        "C123",
    "oldbalanceOrg":   800_000.0,
    "newbalanceOrig":  0.0,
    "nameDest":        "C456",
    "oldbalanceDest":  0.0,
    "newbalanceDest":  0.0,
}


def randomize(tx: dict) -> dict:
    return dict(
        tx,
        step=random.randint(1, 700),
        amount=round(random.expovariate(1 / 100_000), 2),
        oldbalanceOrg=round(random.expovariate(1 / 300_000), 2),
        newbalanceOrig=round(random.expovariate(1 / 300_000), 2),
        oldbalanceDest=round(random.expovariate(1 / 300_000), 2),
        newbalanceDest=round(random.expovariate(1 / 300_000), 2),
    )


async def worker(client: httpx.AsyncClient, url: str, queue: asyncio.Queue,
                 stats: dict) -> None:
    while True:
        await queue.get()
        try:
            r = await client.post(f"{url}/predict", json=randomize(SAMPLE_TX), timeout=10.0)
            stats["ok" if r.status_code == 200 else "fail"] += 1
        except Exception:
            stats["fail"] += 1
        finally:
            queue.task_done()


async def producer(queue: asyncio.Queue, rps: int, duration: int) -> None:
    """Кладёт `rps` задач в очередь раз в секунду в течение `duration`."""
    end = time.monotonic() + duration
    while time.monotonic() < end:
        sec_start = time.monotonic()
        for _ in range(rps):
            queue.put_nowait(1)
        elapsed = time.monotonic() - sec_start
        await asyncio.sleep(max(0, 1.0 - elapsed))


async def reporter(stats: dict, duration: int) -> None:
    end = time.monotonic() + duration + 5
    last_ok = 0
    while time.monotonic() < end:
        await asyncio.sleep(5)
        delta_ok = stats["ok"] - last_ok
        last_ok = stats["ok"]
        log.info("ok=%d fail=%d (last 5s: %.0f rps)",
                 stats["ok"], stats["fail"], delta_ok / 5)


async def main_async(args):
    queue: asyncio.Queue = asyncio.Queue(maxsize=args.rps * 2)
    stats = {"ok": 0, "fail": 0}

    limits = httpx.Limits(max_connections=args.concurrency, max_keepalive_connections=args.concurrency)
    async with httpx.AsyncClient(limits=limits) as client:
        # Воркеры
        workers = [
            asyncio.create_task(worker(client, args.url, queue, stats))
            for _ in range(args.concurrency)
        ]
        # Продюсер + репортер
        prod_task = asyncio.create_task(producer(queue, args.rps, args.duration))
        rep_task = asyncio.create_task(reporter(stats, args.duration))

        await prod_task
        await queue.join()
        rep_task.cancel()
        for w in workers:
            w.cancel()

    log.info("=" * 60)
    log.info("DONE. ok=%d fail=%d duration=%ds → avg %.1f rps",
             stats["ok"], stats["fail"], args.duration,
             (stats["ok"] + stats["fail"]) / args.duration)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url",         required=True, help="http://<EXTERNAL_IP>")
    p.add_argument("--rps",         type=int, default=200,
                   help="Целевая интенсивность (200..400 для теста алерта)")
    p.add_argument("--duration",    type=int, default=600,
                   help="Сколько секунд лить (>= 360 для срабатывания 5-мин окна)")
    p.add_argument("--concurrency", type=int, default=50,
                   help="Сколько одновременных HTTP-соединений")
    args = p.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
