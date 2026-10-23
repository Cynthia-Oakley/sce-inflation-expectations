"""近期11个预测月(2025-11..2026-09)逐月信息可得性审计。

纯离线：只读本地物化产物与来源证据，不调用任何API、不重新下载。
回答Codex在 kimi_engineering_tasks.md 顶部提出的问题：
  每个预测窗口截止(as_of)前，
  (a) 可用的最新SCE微观版本及其公开时间；
  (b) 截止前最后公开的全国SCE汇总值及发布时间；
并按用户要求扩展到环境信号(CPI/就业/油价/新闻)与人口画像时点。
拿不到的证据标 unknown；观测月/抓取时间不充当发布时间。

输出: outputs/sce_recent_availability_20261023_v1/
  monthly_availability.jsonl  逐月一行
  summary.json                汇总与结论
  manifest.json               输入/输出文件 sha256
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAT = ROOT / "outputs/sce_fullperiod_materialized_20261022_v2"
OUT = ROOT / "outputs/sce_recent_availability_20261023_v1"
RELEASE_EVIDENCE = ROOT / "data/raw/sce_baselines_latest_20261007/release_evidence.json"
MICRO_REFRESH_MANIFEST = ROOT / "data/raw/sce_micro_refresh_20261021/manifest.json"
MICRO_AUDIT_MANIFEST = ROOT / "data/raw/sce_audit_20260928/manifest.json"

RECENT_MONTHS = [f"2025-{m:02d}" for m in (11, 12)] + [f"2026-{m:02d}" for m in range(1, 10)]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    releases = json.load(open(RELEASE_EVIDENCE))
    # (published_date, reference_period, record) 按发布时间排序
    releases = sorted(releases, key=lambda r: r["published_date"])

    micro_refresh = json.load(open(MICRO_REFRESH_MANIFEST))
    micro_latest_wave = micro_refresh["notes"]["findings"]["micro_latest_max_month"]

    rows = []
    all_violations = []
    for month in RECENT_MONTHS:
        ym = month.replace("-", "")
        mdir = MAT / ym
        env_receipt = json.load(open(mdir / "environment_receipt.json"))
        env = json.load(open(mdir / "environment.json"))
        pop_receipt = json.load(open(mdir / "population_receipt.json"))
        as_of = parse_dt(env_receipt["as_of"])

        # --- 环境信号: published_at 是否全部 <= as_of ---
        signals = env["provider_args"]["signals_by_step"]["0"]
        sig_viol = [
            {
                "signal_id": s["signal_id"],
                "reference_period": s.get("reference_period"),
                "published_at": s.get("published_at"),
            }
            for s in signals
            if s.get("published_at") and parse_dt(s["published_at"]) > as_of
        ]
        elig = {}
        for s in signals:
            elig[s.get("eligibility", "?")] = elig.get(s.get("eligibility", "?"), 0) + 1
        pub_dts = [parse_dt(s["published_at"]) for s in signals if s.get("published_at")]
        latest_sig = max(pub_dts) if pub_dts else None

        # --- 新闻事件: pub_date(日粒度) 是否不晚于 as_of 当天 ---
        # as_of 均为当日 23:59:59 地方时；同日新闻视为截止前可得。
        as_of_date = as_of.date().isoformat()
        events = env["provider_args"]["events_by_step"]["0"]
        ev_viol = [
            {"event_id": e["event_id"], "pub_date": e["pub_date"], "headline": e["headline"][:80]}
            for e in events
            if e["pub_date"] > as_of_date
        ]
        same_day_events = sum(1 for e in events if e["pub_date"] == as_of_date)
        ev_dates = sorted(e["pub_date"] for e in events)

        # --- 截止前最后公开的全国SCE汇总(发布按日粒度比较) ---
        avail = [r for r in releases if r["published_date"] <= as_of_date]
        last_rel = avail[-1] if avail else None
        next_rel = releases[len(avail)] if len(avail) < len(releases) else None
        sce_aggregate = {
            "last_public_reference_period": last_rel["reference_period"] if last_rel else None,
            "published_date": last_rel["published_date"] if last_rel else None,
            "source_url": last_rel["source_url"] if last_rel else None,
            "local_file": last_rel["file"] if last_rel else None,
            "local_file_sha256": last_rel["sha256"] if last_rel else None,
            "one_year_median_excerpt": (last_rel["inflation_passages"][0][:200] if last_rel else None),
            "next_release_after_as_of": (
                {"reference_period": next_rel["reference_period"], "published_date": next_rel["published_date"]}
                if next_rel else None
            ),
        }

        # --- 微观数据版本(全体11月共用同一结论) ---
        micro = {
            "latest_wave_in_local_copy": micro_latest_wave,
            "published_at": None,
            "published_at_status": "unknown — FRBNY 不对 microdata 文件给出带日期的发布记录；"
                                   "本地只有抓取时间(2026-09-28/2026-10-21, 哈希一致)，不能当作发布时间",
            "evidence": ["data/raw/sce_micro_refresh_20261021/manifest.json",
                          "data/raw/sce_audit_20260928/manifest.json"],
        }

        population = {
            "synthetic": pop_receipt.get("synthetic"),
            "frame_n": pop_receipt.get("frame_n"),
            "synthetic_source_wave": pop_receipt.get("synthetic_source_wave"),
            "note": pop_receipt.get("synthetic_note"),
            "timing_inherits": "microdata publish boundary (unknown) — 画像来自微观，发布时点同样未知",
        }

        violations = []
        if sig_viol:
            violations.append({"kind": "signal_published_after_as_of", "items": sig_viol})
        if ev_viol:
            violations.append({"kind": "event_published_after_as_of", "items": ev_viol})
        for v in violations:
            all_violations.append({"month": month, **v})

        rows.append({
            "target_month": month,
            "as_of": env_receipt["as_of"],
            "sce_aggregate": sce_aggregate,
            "microdata": micro,
            "population": population,
            "environment": {
                "signals_n": len(signals),
                "eligibility_counts": elig,
                "latest_signal_published_at": latest_sig.isoformat() if latest_sig else None,
                "events_n": len(events),
                "event_pub_date_range": [ev_dates[0], ev_dates[-1]] if ev_dates else None,
                "same_day_as_cutoff_events_n": same_day_events,
                "source_status": env["provider_args"].get("source_status"),
                "receipt_gaps": env_receipt.get("gaps", []),
            },
            "forward_looking_violations": violations,
        })

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "近期11个无微观月 2025-11..2026-09；纯离线审计，新API调用=0",
        "months_checked": len(rows),
        "months_with_forward_looking_violations": sorted({v["month"] for v in all_violations}),
        "violations": all_violations,
        "key_findings": [
            "环境信号/新闻的 published_at 与 pub_date 全部不晚于各自 as_of（逐月核验，0违规）"
            if not all_violations else "存在 as_of 之后发布的内容，见 violations",
            "SCE微观最新月=2025-10；FRBNY不给微观文件发布日期，published_at=unknown，"
            "严格B线资格仍不能凭现有证据认证",
            "eia_gasoline=current_fred_snapshot_vintage_unverified：现价快照可能含事后修订，"
            "属轻度前视风险；nyt=archive_metadata_text_vintage_unverified",
        ],
    }

    jsonl_path = OUT / "monthly_availability.jsonl"
    with open(jsonl_path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary_path = OUT / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    inputs = [RELEASE_EVIDENCE, MICRO_REFRESH_MANIFEST, MICRO_AUDIT_MANIFEST]
    for month in RECENT_MONTHS:
        mdir = MAT / month.replace("-", "")
        inputs += [mdir / "environment_receipt.json", mdir / "environment.json", mdir / "population_receipt.json"]
    manifest = {
        "created_at": summary["generated_at"],
        "script": "scripts/build_sce_recent_availability.py",
        "new_api_calls": 0,
        "inputs": {str(p.relative_to(ROOT)): sha256_of(p) for p in inputs},
        "outputs": {
            str(jsonl_path.relative_to(ROOT)): sha256_of(jsonl_path),
            str(summary_path.relative_to(ROOT)): sha256_of(summary_path),
        },
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(json.dumps({k: summary[k] for k in ("months_checked", "months_with_forward_looking_violations")}, ensure_ascii=False))
    for r in rows:
        a = r["sce_aggregate"]
        print(r["target_month"], "as_of", r["as_of"][:10],
              "| last SCE agg:", a["last_public_reference_period"], "pub", a["published_date"],
              "| sig", r["environment"]["signals_n"], "ev", r["environment"]["events_n"])


if __name__ == "__main__":
    main()
