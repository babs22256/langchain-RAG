"""并发压力测试：模拟 N 个用户「同时」使用本系统。

场景：
    setup   预注册压测用户（不计入指标）
    local   登录 -> 会话列表 -> 新建会话 -> 消息列表 -> 知识库统计（零 API 成本）
    rag     登录 -> 新建会话 -> SSE 流式问答（真实调用 DeepSeek + 硅基流动）
    read    纯读接口：/health 与 /sessions（测框架与 SQLite 读并发上限）

用法：
    python _loadtest.py --scenario setup --users 100
    python _loadtest.py --scenario local --users 100
    python _loadtest.py --scenario rag   --users 100 --report _report.txt

说明：所有请求通过 asyncio.Event 同步起跑，模拟「100 人同一秒点击」的惊群场景。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from dataclasses import dataclass, field

import httpx

QUESTIONS = [
    "星耀 X1 Pro 的电池容量是多少？",
    "星耀 X1 Pro 支持多少瓦的快充？",
    "星耀 X1 Pro 的防水等级是多少？",
    "云净 X800 空调适合多大面积的房间？",
    "云净 X800 空调的运行噪音是多少分贝？",
    "冰川 BCD-520 冰箱的容量是多少升？",
    "净水器 J600 的过滤精度是多少？",
    "取暖器 H9 的功率是多少瓦？",
    "清风 A2 手机售价多少？",
    "星耀手表 Watch 3 支持哪些运动模式？",
]

TEST_PWD = "loadtest123"
PREFIX = "loadtest_"

TIMEOUT = 180  # SSE 读超时（秒），由 --timeout 覆盖
RUN_ID = f"{random.randint(0, 9999):04d}"  # 每次运行唯一，保证冷启动可重复测量


# --------------------------------------------------------------------------- #
# 指标采集
# --------------------------------------------------------------------------- #
@dataclass
class Rec:
    name: str
    latency: float
    ok: bool
    status: int = 0
    error: str = ""
    ttft: float | None = None          # 首字延迟（仅 SSE）
    cached: bool | None = None         # 是否命中 LLM 缓存
    retrieve_time: float | None = None  # 服务端检索耗时
    generate_time: float | None = None  # 服务端生成耗时


class Collector:
    def __init__(self) -> None:
        self.recs: list[Rec] = []

    def add(self, rec: Rec) -> None:
        self.recs.append(rec)  # asyncio 单线程，append 原子安全

    # -- 统计 ------------------------------------------------------------ #
    def _groups(self) -> dict[str, list[Rec]]:
        g: dict[str, list[Rec]] = {}
        for r in self.recs:
            g.setdefault(r.name, []).append(r)
        return g

    @staticmethod
    def _pct(vals: list[float], p: float) -> float:
        if not vals:
            return 0.0
        s = sorted(vals)
        k = (len(s) - 1) * p / 100.0
        f = int(k)
        c = min(f + 1, len(s) - 1)
        return s[f] + (s[c] - s[f]) * (k - f)

    def summarize(self, wall: float) -> dict:
        out: dict[str, dict] = {}
        for name, rs in self._groups().items():
            ok = [r for r in rs if r.ok]
            lat = [r.latency for r in ok]
            ttfts = [r.ttft for r in ok if r.ttft is not None]
            serv_ret = [r.retrieve_time for r in ok if r.retrieve_time is not None]
            serv_gen = [r.generate_time for r in ok if r.generate_time is not None]
            errs: dict[str, int] = {}
            for r in rs:
                if not r.ok:
                    key = f"HTTP {r.status}" if r.status else r.error[:60]
                    errs[key] = errs.get(key, 0) + 1
            out[name] = {
                "total": len(rs),
                "ok": len(ok),
                "fail": len(rs) - len(ok),
                "err_rate": round((len(rs) - len(ok)) / len(rs) * 100, 2),
                "qps": round(len(rs) / wall, 2) if wall > 0 else 0.0,
                "avg": round(statistics.fmean(lat), 3) if lat else 0.0,
                "p50": round(self._pct(lat, 50), 3),
                "p95": round(self._pct(lat, 95), 3),
                "p99": round(self._pct(lat, 99), 3),
                "max": round(max(lat), 3) if lat else 0.0,
                "ttft_p50": round(self._pct(ttfts, 50), 3) if ttfts else None,
                "ttft_p95": round(self._pct(ttfts, 95), 3) if ttfts else None,
                "srv_retrieve_p50": round(self._pct(serv_ret, 50), 3) if serv_ret else None,
                "srv_generate_p50": round(self._pct(serv_gen, 50), 3) if serv_gen else None,
                "errors": errs,
            }
        return out

    def cache_stats(self) -> dict | None:
        hits = [r for r in self.recs if r.cached is not None]
        if not hits:
            return None
        h = sum(1 for r in hits if r.cached)
        return {"total": len(hits), "hits": h, "miss": len(hits) - h,
                "hit_rate": round(h / len(hits) * 100, 2)}


# --------------------------------------------------------------------------- #
# 通用请求封装
# --------------------------------------------------------------------------- #
async def timed(col: Collector, name: str, coro) -> httpx.Response | None:
    t = time.perf_counter()
    try:
        r = await coro
    except Exception as e:  # 网络异常/超时
        col.add(Rec(name, time.perf_counter() - t, False, 0,
                    f"{type(e).__name__}: {e}"[:160]))
        return None
    dt = time.perf_counter() - t
    ok = 200 <= r.status_code < 300
    col.add(Rec(name, dt, ok, r.status_code, "" if ok else r.text[:160]))
    return r


async def sse_chat(client: httpx.AsyncClient, base: str, col: Collector,
                   headers: dict, session_id: int, question: str, name: str) -> None:
    """SSE 流式问答：记录端到端耗时、首字延迟、服务端分段耗时、缓存命中。"""
    t0 = time.perf_counter()
    ttft: float | None = None
    retrieve_time: float | None = None
    generate_time: float | None = None
    cached: bool | None = None
    tokens = 0
    try:
        async with client.stream(
            "POST", f"{base}/chat/stream",
            json={"session_id": session_id, "message": question},
            headers=headers, timeout=TIMEOUT,
        ) as r:
            if r.status_code != 200:
                body = (await r.aread()).decode("utf-8", "ignore")[:160]
                col.add(Rec(name, time.perf_counter() - t0, False, r.status_code, body))
                return
            buf = ""
            async for chunk in r.aiter_text():
                if ttft is None and chunk.strip():
                    ttft = time.perf_counter() - t0
                buf += chunk
                while "\n\n" in buf:
                    block, buf = buf.split("\n\n", 1)
                    ev, data = None, None
                    for line in block.split("\n"):
                        if line.startswith("event: "):
                            ev = line[7:].strip()
                        elif line.startswith("data: "):
                            data = line[6:]
                    if ev == "meta" and data:
                        try:
                            retrieve_time = json.loads(data).get("retrieve_time")
                        except Exception:
                            pass
                    elif ev == "token":
                        tokens += 1
                    elif ev == "done" and data:
                        try:
                            d = json.loads(data)
                            generate_time = d.get("generate_time")
                            cached = d.get("cached")
                        except Exception:
                            pass
    except Exception as e:
        col.add(Rec(name, time.perf_counter() - t0, False, 0,
                    f"{type(e).__name__}: {e}"[:160]))
        return
    col.add(Rec(name, time.perf_counter() - t0, True, 200, "",
                ttft=ttft, cached=cached,
                retrieve_time=retrieve_time, generate_time=generate_time))


async def login(client, base, col, username, password) -> str | None:
    r = await timed(col, "auth.login",
                    client.post(f"{base}/auth/login",
                                json={"username": username, "password": password}))
    if r is None or r.status_code != 200:
        return None
    return r.json().get("access_token")


# --------------------------------------------------------------------------- #
# 场景实现
# --------------------------------------------------------------------------- #
async def scn_setup(args, col: Collector) -> None:
    """预注册 N 个压测用户（并发 8，仅为准备数据）。"""
    sem = asyncio.Semaphore(8)
    async with httpx.AsyncClient(timeout=60) as client:
        async def one(i: int) -> None:
            async with sem:
                u = f"{PREFIX}{i:03d}"
                try:
                    r = await client.post(f"{args.base}/auth/register",
                                          json={"username": u, "password": TEST_PWD})
                    if r.status_code == 201:
                        print(f"  + {u}")
                    elif r.status_code == 400:
                        print(f"  = {u} (已存在)")
                    else:
                        print(f"  ! {u} HTTP {r.status_code} {r.text[:80]}")
                except Exception as e:
                    print(f"  ! {u} {type(e).__name__}: {e}")

        await asyncio.gather(*(one(i) for i in range(args.users)))
    print(f"[setup] 处理完毕，共 {args.users} 个用户")


async def scn_read(args, col: Collector, start_evt: asyncio.Event) -> None:
    """纯读：/health，验证框架裸吞吐上限。"""
    async with httpx.AsyncClient(timeout=60) as client:
        async def one() -> None:
            await start_evt.wait()
            await timed(col, "GET /health", client.get(f"{args.base}/health"))

        await asyncio.gather(*(one() for _ in range(args.users)))


async def scn_local(args, col: Collector, start_evt: asyncio.Event) -> None:
    """本地接口链路：登录 -> 会话列表 -> 新建会话 -> 拉消息 -> 知识库统计。"""
    async with httpx.AsyncClient(timeout=60) as client:
        admin_token = await login(client, args.base, col, args.admin_user, args.admin_pwd)

        async def one(i: int) -> None:
            await start_evt.wait()
            u = f"{PREFIX}{i:03d}"
            token = await login(client, args.base, col, u, TEST_PWD)
            if token is None:
                return
            h = {"Authorization": f"Bearer {token}"}

            await timed(col, "sessions.list", client.get(f"{args.base}/sessions", headers=h))
            r = await timed(col, "sessions.create",
                            client.post(f"{args.base}/sessions", headers=h))
            if r is not None and r.status_code == 200:
                sid = r.json()["id"]
                await timed(col, "messages.list",
                            client.get(f"{args.base}/sessions/{sid}/messages", headers=h))
            if admin_token:
                ah = {"Authorization": f"Bearer {admin_token}"}
                await timed(col, "kb.stats", client.get(f"{args.base}/kb/stats", headers=ah))
                await timed(col, "kb.documents", client.get(f"{args.base}/kb/documents", headers=ah))

        await asyncio.gather(*(one(i) for i in range(args.users)))


async def scn_rag(args, col: Collector, start_evt: asyncio.Event) -> None:
    """真实 RAG：登录 -> 建会话 -> SSE 问答（每用户随机选题）。"""
    pool = QUESTIONS * max(1, args.users // max(1, len(QUESTIONS)) + 1)
    async with httpx.AsyncClient(
        timeout=180,
        limits=httpx.Limits(max_connections=args.users + 50,
                            max_keepalive_connections=args.users + 50),
    ) as client:
        async def one(i: int) -> None:
            await start_evt.wait()
            u = f"{PREFIX}{i:03d}"
            token = await login(client, args.base, col, u, TEST_PWD)
            if token is None:
                return
            h = {"Authorization": f"Bearer {token}"}
            r = await client.post(f"{args.base}/sessions", headers=h)
            if r.status_code != 200:
                col.add(Rec("sessions.create", 0.0, False, r.status_code, r.text[:120]))
                return
            sid = r.json()["id"]
            q = pool[i % len(pool)]
            if args.nonce:
                # 附加唯一工单号，强制每个请求都是缓存未命中（冷启动）
                q = f"{q}（工单号 A{i:06d}-{RUN_ID}）"
            await sse_chat(client, args.base, col, h, sid, q, "chat.stream")

        await asyncio.gather(*(one(i) for i in range(args.users)))


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
async def run(args) -> None:
    col = Collector()
    scenarios = {
        "setup": scn_setup,
        "read": scn_read,
        "local": scn_local,
        "rag": scn_rag,
    }
    fn = scenarios[args.scenario]

    print(f"=== 压测场景 [{args.scenario}] 并发 {args.users} | {args.base} ===")

    if args.scenario == "setup":
        await fn(args, col)
        return

    # 起跑屏障：所有协程创建完毕、连接池预建后，同一瞬间放开，模拟「100人同时点击」
    start_evt = asyncio.Event()
    runner = asyncio.create_task(fn(args, col, start_evt))
    await asyncio.sleep(1.0)
    print(f">>> 同时释放 {args.users} 个并发请求")
    t0 = time.perf_counter()
    start_evt.set()
    await runner
    wall = time.perf_counter() - t0

    summary = col.summarize(wall)
    cache_info = col.cache_stats()

    lines = []
    lines.append("")
    lines.append("=" * 96)
    lines.append(f"压测结果  场景={args.scenario}  并发={args.users}  总墙钟={wall:.3f}s")
    lines.append("=" * 96)
    lines.append(f"{'接口':<20}{'请求':>6}{'成功':>6}{'失败':>6}{'错误率':>9}{'QPS':>9}"
                 f"{'均值':>9}{'P50':>9}{'P95':>9}{'P99':>9}{'最大':>9}")
    lines.append("-" * 96)
    for name, s in summary.items():
        lines.append(
            f"{name:<20}{s['total']:>6}{s['ok']:>6}{s['fail']:>6}"
            f"{str(s['err_rate'])+'%':>9}{s['qps']:>9}{s['avg']:>9}"
            f"{s['p50']:>9}{s['p95']:>9}{s['p99']:>9}{s['max']:>9}"
        )
    lines.append("-" * 96)

    for name, s in summary.items():
        extra = []
        if s["ttft_p50"] is not None:
            extra.append(f"首字延迟 P50={s['ttft_p50']}s P95={s['ttft_p95']}s")
        if s["srv_retrieve_p50"] is not None:
            extra.append(f"服务端检索 P50={s['srv_retrieve_p50']}s")
        if s["srv_generate_p50"] is not None:
            extra.append(f"服务端生成 P50={s['srv_generate_p50']}s")
        if extra:
            lines.append(f"[{name}] " + " | ".join(extra))
        if s["errors"]:
            lines.append(f"[{name}] 错误分布: {json.dumps(s['errors'], ensure_ascii=False)}")

    if cache_info:
        lines.append(f"[缓存] LLM 缓存命中 {cache_info['hits']}/{cache_info['total']} "
                     f"= {cache_info['hit_rate']}%")

    text = "\n".join(lines)
    print(text)

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"\n报告已写入 {args.report}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", required=True,
                   choices=["setup", "read", "local", "rag"])
    p.add_argument("--users", type=int, default=100)
    p.add_argument("--timeout", type=float, default=180.0,
                   help="SSE 读超时（秒），压测高并发时建议调大")
    p.add_argument("--nonce", action="store_true",
                   help="给每个问题附加唯一工单号，强制缓存未命中")
    p.add_argument("--base", default="http://127.0.0.1:8000")
    p.add_argument("--admin-user", default="admin")
    p.add_argument("--admin-pwd", default="123456")
    p.add_argument("--report", default="")
    args = p.parse_args()
    global TIMEOUT
    TIMEOUT = args.timeout
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
