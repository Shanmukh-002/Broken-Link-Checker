from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse

import pandas as pd
import streamlit as st

from app.checker import LinkChecker
from app.crawler import SiteCrawler


st.set_page_config(page_title="Broken Link Checker", layout="wide")

st.markdown(
    """
    <style>
      /* Canvas */
      .blc-wrap { max-width: 1200px; margin: 0 auto; }
      .block-container { padding-top: 1.15rem; padding-bottom: 2.25rem; }

      /* Typography */
      .blc-title { font-weight: 900; letter-spacing: -0.02em; }
      .blc-subtitle { color: rgba(49, 51, 63, 0.72); margin-top: -0.55rem; }
      @media (prefers-color-scheme: dark) { .blc-subtitle { color: rgba(250, 250, 250, 0.72); } }
      .blc-section { margin-top: 1rem; }

      /* Card */
      .blc-card {
        border: 1px solid rgba(49, 51, 63, 0.10);
        border-radius: 18px;
        padding: 16px 18px;
        background: rgba(49, 51, 63, 0.02);
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
      }
      @media (prefers-color-scheme: dark) {
        .blc-card {
          border: 1px solid rgba(250, 250, 250, 0.10);
          background: rgba(250, 250, 250, 0.03);
          box-shadow: none;
        }
      }

      /* KPI */
      .blc-kpi {
        border: 1px solid rgba(49, 51, 63, 0.10);
        border-radius: 18px;
        padding: 16px 16px;
        background: rgba(49, 51, 63, 0.02);
      }
      @media (prefers-color-scheme: dark) {
        .blc-kpi { border: 1px solid rgba(250, 250, 250, 0.10); background: rgba(250, 250, 250, 0.03); }
      }
      .blc-kpi-top { display:flex; align-items:center; gap:10px; margin-bottom: 10px; }
      .blc-kpi-icon {
        width: 40px; height: 40px; border-radius: 12px;
        display:flex; align-items:center; justify-content:center;
        font-size: 18px; font-weight: 900;
      }
      .blc-purple { background: rgba(99, 102, 241, 0.12); color: rgb(79, 70, 229); }
      .blc-green  { background: rgba(34, 197, 94, 0.12);  color: rgb(22, 163, 74); }
      .blc-red    { background: rgba(239, 68, 68, 0.12);   color: rgb(220, 38, 38); }
      .blc-blue   { background: rgba(59, 130, 246, 0.12);  color: rgb(37, 99, 235); }
      .blc-amber  { background: rgba(245, 158, 11, 0.14);  color: rgb(217, 119, 6); }
      .blc-kpi-label { font-size: 0.98rem; font-weight: 800; }
      .blc-kpi-value { font-size: 1.75rem; font-weight: 950; line-height: 1.05; }
      .blc-kpi-sub { margin-top: 4px; font-size: 0.92rem; opacity: 0.75; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _init_state() -> None:
    st.session_state.setdefault("root_url", "")
    st.session_state.setdefault("normalized_root_url", "")
    st.session_state.setdefault("max_pages", 25)
    st.session_state.setdefault("crawl_workers", 8)
    st.session_state.setdefault("link_workers", 10)
    st.session_state.setdefault("verify_ssl", True)
    st.session_state.setdefault("internal_only", False)

    st.session_state.setdefault("results_df", pd.DataFrame())
    st.session_state.setdefault("crawl_errors", [])
    st.session_state.setdefault("page_urls", [])
    st.session_state.setdefault("last_scan_at", None)


def _normalize_root_url(user_input: str) -> str:
    root_url = user_input.strip()
    if "://" not in root_url:
        root_url = f"https://{root_url}"

    parsed = urlparse(root_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("Invalid URL")

    return root_url


def _to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def _kpi_card(icon: str, color_class: str, label: str, value: str, sub: str) -> None:
    st.markdown(
        f"""
        <div class="blc-kpi">
          <div class="blc-kpi-top">
            <div class="blc-kpi-icon {color_class}">{icon}</div>
            <div class="blc-kpi-label">{label}</div>
          </div>
          <div class="blc-kpi-value">{value}</div>
          <div class="blc-kpi-sub">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _compute_tables(results_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if results_df.empty:
        return {
            "broken": pd.DataFrame(),
            "blocked": pd.DataFrame(),
            "unauthorized": pd.DataFrame(),
            "successful": pd.DataFrame(),
        }

    broken_df = results_df[results_df["is_broken"]].copy() if "is_broken" in results_df.columns else pd.DataFrame()
    blocked_df = results_df[results_df["is_blocked"]].copy() if "is_blocked" in results_df.columns else pd.DataFrame()

    unauthorized_df = pd.DataFrame()
    if "status_code" in results_df.columns:
        unauthorized_df = results_df[results_df["status_code"] == 401].copy()

    successful_df = pd.DataFrame()
    if "status_code" in results_df.columns:
        status_ok = results_df["status_code"].fillna(0) < 400
        blocked_flag = results_df["is_blocked"] if "is_blocked" in results_df.columns else False
        broken_flag = results_df["is_broken"] if "is_broken" in results_df.columns else False
        successful_df = results_df[status_ok & (~blocked_flag) & (~broken_flag)].copy()

    if bool(st.session_state["internal_only"]) and "is_internal" in results_df.columns:
        broken_df = broken_df[broken_df["is_internal"]] if not broken_df.empty else broken_df
        blocked_df = blocked_df[blocked_df["is_internal"]] if not blocked_df.empty else blocked_df
        unauthorized_df = unauthorized_df[unauthorized_df["is_internal"]] if not unauthorized_df.empty else unauthorized_df
        successful_df = successful_df[successful_df["is_internal"]] if not successful_df.empty else successful_df

    return {
        "broken": broken_df,
        "blocked": blocked_df,
        "unauthorized": unauthorized_df,
        "successful": successful_df,
    }


def _run_scan(progress_slot: st.delta_generator.DeltaGenerator) -> None:
    # NOTE: `root_url` is also used as a widget key. Streamlit forbids mutating a session_state
    # key after its widget is instantiated, so write the normalized value to a separate key.
    root_url = _normalize_root_url(st.session_state["root_url"])
    st.session_state["normalized_root_url"] = root_url

    crawler = SiteCrawler(
        root_url=root_url,
        max_pages=int(st.session_state["max_pages"]),
        max_workers=int(st.session_state["crawl_workers"]),
        verify_ssl=bool(st.session_state["verify_ssl"]),
    )
    page_urls, links, crawl_errors = crawler.crawl()

    st.session_state["crawl_errors"] = crawl_errors
    st.session_state["page_urls"] = page_urls

    if not links:
        st.session_state["results_df"] = pd.DataFrame()
        st.session_state["last_scan_at"] = datetime.now().isoformat(timespec="seconds")
        return

    checker = LinkChecker(
        max_workers=int(st.session_state["link_workers"]),
        verify_ssl=bool(st.session_state["verify_ssl"]),
    )
    unique_targets = len({target_url for _source_url, target_url, _anchor_text in links})

    with progress_slot:
        st.markdown('<div class="blc-card">', unsafe_allow_html=True)
        status_line = st.empty()
        recent_line = st.empty()
        progress = st.progress(0.0, text=f"Checking links: 0/{unique_targets}")
        st.markdown("</div>", unsafe_allow_html=True)

    results = []
    completed = 0
    recent: list[str] = []
    for target_url, items in checker.iter_check_many(links, root_url):
        completed += 1
        results.extend(items)

        status_line.markdown(f"**Checking now:** `{target_url}`")
        recent.append(target_url)
        if len(recent) > 6:
            recent = recent[-6:]
        recent_line.caption("Recent: " + " • ".join(recent))

        fraction = completed / unique_targets if unique_targets else 1.0
        progress.progress(fraction, text=f"Checking links: {completed}/{unique_targets}")

    status_line.success("Scan complete.")

    results_df = pd.DataFrame([r.model_dump() for r in results])
    st.session_state["results_df"] = results_df
    st.session_state["last_scan_at"] = datetime.now().isoformat(timespec="seconds")


def _render_table(df: pd.DataFrame, empty_msg: str, download_name: str) -> None:
    cols = [
        "source_url",
        "target_url",
        "anchor_text",
        "status_code",
        "error",
        "is_internal",
        "response_time_ms",
    ]
    available_cols = [c for c in cols if c in df.columns]

    st.markdown('<div class="blc-card">', unsafe_allow_html=True)
    if df.empty:
        st.info(empty_msg)
        st.markdown("</div>", unsafe_allow_html=True)
        return

    actions_left, actions_right = st.columns([0.62, 0.38])
    with actions_left:
        query = st.text_input(
            "Search",
            placeholder="Search source URL, target URL, anchor text, error…",
            label_visibility="collapsed",
            key=f"q_{download_name}",
        )
    with actions_right:
        st.download_button(
            label="Download CSV",
            data=_to_csv_bytes(df),
            file_name=download_name,
            mime="text/csv",
            use_container_width=True,
        )

    filtered = df
    if query:
        q = query.strip().lower()
        def _contains(series: pd.Series) -> pd.Series:
            return series.astype(str).str.lower().str.contains(q, na=False)
        mask = False
        for col in ["source_url", "target_url", "anchor_text", "error"]:
            if col in filtered.columns:
                mask = mask | _contains(filtered[col])
        filtered = filtered[mask] if not isinstance(mask, bool) else filtered

    st.dataframe(
        filtered[available_cols],
        use_container_width=True,
        hide_index=True,
        column_config={
            "source_url": st.column_config.LinkColumn("Source URL") if "source_url" in available_cols else None,
            "target_url": st.column_config.LinkColumn("Target URL") if "target_url" in available_cols else None,
            "status_code": st.column_config.NumberColumn("Status", format="%d") if "status_code" in available_cols else None,
            "is_internal": st.column_config.CheckboxColumn("Internal") if "is_internal" in available_cols else None,
            "response_time_ms": st.column_config.NumberColumn("ms", format="%.2f") if "response_time_ms" in available_cols else None,
        },
    )
    st.markdown("</div>", unsafe_allow_html=True)


_init_state()

pad_left, main, pad_right = st.columns([0.08, 0.84, 0.08])
with main:
    st.markdown('<div class="blc-wrap">', unsafe_allow_html=True)

    # Header
    h1, h2 = st.columns([0.70, 0.30], vertical_alignment="bottom")
    with h1:
        st.markdown('<div class="blc-title"><h1>Broken Link Checker</h1></div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="blc-subtitle">Scan websites, inspect broken or restricted links, and download reports.</div>',
            unsafe_allow_html=True,
        )
        if st.session_state.get("normalized_root_url"):
            st.caption(f"Normalized URL: {st.session_state['normalized_root_url']}")
    with h2:
        tables = _compute_tables(st.session_state["results_df"])
        broken_df = tables["broken"]
        if not broken_df.empty:
            st.download_button(
                label="Download broken report",
                data=_to_csv_bytes(broken_df),
                file_name="broken_links.csv",
                mime="text/csv",
                use_container_width=True,
            )
        else:
            st.button("Download broken report", disabled=True, use_container_width=True)

    # Controls
    st.markdown('<div class="blc-section"></div>', unsafe_allow_html=True)
    st.markdown('<div class="blc-card">', unsafe_allow_html=True)
    progress_slot = st.container()
    with st.form("scan_controls", clear_on_submit=False):
        c1, c2 = st.columns([0.76, 0.24], vertical_alignment="bottom")
        with c1:
            st.text_input(
                "Website URL",
                key="root_url",
                placeholder="https://example.com",
                help="Enter a website root URL to crawl (e.g. https://example.com).",
                label_visibility="visible",
            )
        with c2:
            run_clicked = st.form_submit_button("Run scan", type="primary", use_container_width=True)

        with st.expander("Scan settings", expanded=False):
            s1, s2 = st.columns(2)
            with s1:
                st.slider("Max pages to crawl", 1, 200, key="max_pages")
                st.slider("Concurrent page fetches", 1, 32, key="crawl_workers")
                st.checkbox("Verify SSL certificates", key="verify_ssl")
            with s2:
                st.slider("Concurrent link checks", 1, 50, key="link_workers")
                st.checkbox("Internal links only", key="internal_only")
                st.caption("Blocked = 401/403/429. Unauthorized is the 401 subset.")
    st.markdown("</div>", unsafe_allow_html=True)

    if run_clicked:
        try:
            with st.spinner("Crawling and checking links…"):
                _run_scan(progress_slot)
        except ValueError:
            st.error("Please enter a valid URL (for example: https://example.com).")

    # Results
    results_df = st.session_state["results_df"]
    tables = _compute_tables(results_df)
    broken_df = tables["broken"]
    blocked_df = tables["blocked"]
    unauthorized_df = tables["unauthorized"]
    successful_df = tables["successful"]

    if results_df.empty and not st.session_state["crawl_errors"] and not st.session_state["page_urls"]:
        st.markdown('<div class="blc-section"></div>', unsafe_allow_html=True)
        st.info("Enter a URL and click **Run scan** to begin.")
        st.markdown("</div>", unsafe_allow_html=True)
        st.stop()

    if results_df.empty:
        st.markdown('<div class="blc-section"></div>', unsafe_allow_html=True)
        st.warning("Scan completed, but no crawlable links were found.")
        if st.session_state["crawl_errors"]:
            with st.expander("Crawl errors", expanded=False):
                st.code("\n".join(st.session_state["crawl_errors"]))
        st.markdown("</div>", unsafe_allow_html=True)
        st.stop()

    pages_scanned = len(st.session_state["page_urls"])
    links_checked = len(results_df)
    avg_response = round(results_df["response_time_ms"].dropna().mean(), 2) if not results_df.empty else 0

    st.markdown('<div class="blc-section"></div>', unsafe_allow_html=True)
    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        _kpi_card("📄", "blc-purple", "Pages", f"{pages_scanned}", "Pages scanned")
    with k2:
        _kpi_card("🔗", "blc-green", "Checked", f"{links_checked:,}", "Links checked")
    with k3:
        _kpi_card("⛔", "blc-red", "Broken", f"{int(broken_df.shape[0]):,}", "Broken links")
    with k4:
        _kpi_card("⛔", "blc-amber", "Blocked", f"{int(blocked_df.shape[0]):,}", "401/403/429")
    with k5:
        _kpi_card("⏱", "blc-blue", "Avg (ms)", f"{avg_response}", "Response time")

    if st.session_state.get("last_scan_at"):
        st.caption(f"Last scan: {st.session_state['last_scan_at']}")

    st.markdown('<div class="blc-section"></div>', unsafe_allow_html=True)
    broken_tab, blocked_tab, unauthorized_tab, success_tab = st.tabs(
        [
            f"Broken ({int(broken_df.shape[0]):,})",
            f"Blocked ({int(blocked_df.shape[0]):,})",
            f"Unauthorized (401) ({int(unauthorized_df.shape[0]):,})",
            f"Successful ({int(successful_df.shape[0]):,})",
        ]
    )

    with broken_tab:
        _render_table(broken_df, "No broken links found.", "broken_links.csv")
    with blocked_tab:
        _render_table(blocked_df, "No blocked links found.", "blocked_links.csv")
    with unauthorized_tab:
        _render_table(unauthorized_df, "No unauthorized (401) links found.", "unauthorized_links.csv")
    with success_tab:
        _render_table(successful_df, "No successful links found.", "successful_links.csv")

    with st.expander("Crawl errors", expanded=False):
        if st.session_state["crawl_errors"]:
            st.code("\n".join(st.session_state["crawl_errors"]))
        else:
            st.info("No crawl errors.")

    st.markdown("</div>", unsafe_allow_html=True)
