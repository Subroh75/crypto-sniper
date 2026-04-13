from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass
from typing import Any, Dict, Optional

import streamlit as st


# =========================================================
# PAGE SETUP
# =========================================================
st.set_page_config(
    page_title="Crypto AI Lab",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =========================================================
# STYLES
# =========================================================
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2rem;
        max-width: 1400px;
    }

    .main-title {
        font-size: 2rem;
        font-weight: 800;
        color: #111111;
        margin-bottom: 0.15rem;
    }

    .sub-title {
        font-size: 1rem;
        color: #444444;
        margin-bottom: 1.2rem;
    }

    .panel {
        border: 1px solid rgba(0,0,0,0.10);
        border-radius: 16px;
        padding: 14px 16px;
        background: #ffffff;
        margin-bottom: 12px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }

    .panel-title {
        font-size: 0.84rem;
        color: #444444;
        font-weight: 700;
        margin-bottom: 6px;
        text-transform: none;
    }

    .panel-value {
        font-size: 1.08rem;
        color: #111111;
        font-weight: 800;
        margin-bottom: 3px;
    }

    .panel-sub {
        font-size: 0.86rem;
        color: #666666;
        line-height: 1.4;
    }

    .agent-card {
        border: 1px solid rgba(0,0,0,0.10);
        border-radius: 16px;
        padding: 14px 16px;
        background: #ffffff;
        margin-bottom: 12px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }

    .agent-title {
        font-size: 0.96rem;
        color: #111111;
        font-weight: 800;
        margin-bottom: 8px;
    }

    .agent-body {
        font-size: 0.95rem;
        color: #222222;
        line-height: 1.55;
    }

    .summary-box {
        border-radius: 14px;
        padding: 14px 16px;
        background: #f7f8fa;
        border: 1px solid rgba(0,0,0,0.08);
        color: #111111;
        font-size: 0.95rem;
        line-height: 1.5;
        margin-top: 6px;
        margin-bottom: 14px;
    }

    .section-head {
        font-size: 1.18rem;
        font-weight: 800;
        color: #111111;
        margin-top: 0.6rem;
        margin-bottom: 0.8rem;
    }

    .tiny-muted {
        font-size: 0.82rem;
        color: #666666;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# UTILS
# =========================================================
def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def score_band(score: float, max_score: float) -> str:
    if max_score <= 0:
        return "Balanced"
    ratio = score / max_score
    if ratio >= 0.80:
        return "Strong"
    if ratio >= 0.60:
        return "Constructive"
    if ratio >= 0.40:
        return "Balanced"
    if ratio >= 0.20:
        return "Cautious"
    return "Weak"


def direction_label(value: float) -> str:
    if value >= 0.60:
        return "Strong upside pressure"
    if value >= 0.20:
        return "Moderate upside pressure"
    if value > -0.20:
        return "Flat to mixed"
    if value > -0.60:
        return "Moderate downside pressure"
    return "Strong downside pressure"


def stability_label(value: float) -> str:
    if value >= 0.75:
        return "Very stable"
    if value >= 0.55:
        return "Stable"
    if value >= 0.35:
        return "Moderately stable"
    if value >= 0.20:
        return "Choppy"
    return "Highly erratic"


def breakout_label(value: float) -> str:
    if value >= 0.80:
        return "Breakout setup is strong"
    if value >= 0.60:
        return "Breakout setup is improving"
    if value >= 0.40:
        return "Breakout setup is possible"
    if value >= 0.20:
        return "Breakout setup is weak"
    return "No meaningful breakout setup"


def noise_label(value: float) -> str:
    if value >= 0.80:
        return "Very noisy"
    if value >= 0.60:
        return "Noisy"
    if value >= 0.40:
        return "Moderate noise"
    if value >= 0.20:
        return "Relatively clean"
    return "Very clean"


def strength_label_5(score: float) -> str:
    if score >= 4.5:
        return "Exceptional"
    if score >= 3.8:
        return "Strong"
    if score >= 3.0:
        return "Healthy"
    if score >= 2.0:
        return "Mixed"
    return "Weak"


# =========================================================
# HUMAN-LANGUAGE SIGNAL MODEL
# =========================================================
@dataclass
class HumanSignalComponents:
    volume_strength_score: float = 0.0
    volume_strength_text: str = "Weak participation"

    price_expansion_score: float = 0.0
    price_expansion_text: str = "Weak expansion"

    position_in_range_score: float = 0.0
    position_in_range_text: str = "Sitting low in its range"

    trend_alignment_score: float = 0.0
    trend_alignment_text: str = "Trend is mixed"

    short_term_direction_value: float = 0.0
    short_term_direction_text: str = "Flat to mixed"

    price_stability_value: float = 0.5
    price_stability_text: str = "Moderately stable"

    breakout_potential_value: float = 0.0
    breakout_potential_text: str = "No meaningful breakout setup"

    noise_level_value: float = 0.5
    noise_level_text: str = "Moderate noise"

    market_structure: str = "Mixed structure"
    timing_quality: str = "Average setup"
    risk_posture: str = "Neutral risk"
    momentum_view: str = "Momentum is mixed"
    action_bias: str = "Wait for confirmation"

    conviction_score: float = 0.0
    conviction_text: str = "Balanced"

    summary_line: str = ""

    def to_agent_payload(self) -> Dict[str, Any]:
        return {
            "volume_strength": {
                "score_out_of_5": round(self.volume_strength_score, 2),
                "assessment": self.volume_strength_text,
            },
            "price_expansion": {
                "score_out_of_5": round(self.price_expansion_score, 2),
                "assessment": self.price_expansion_text,
            },
            "position_in_range": {
                "score_out_of_2": round(self.position_in_range_score, 2),
                "assessment": self.position_in_range_text,
            },
            "trend_alignment": {
                "score_out_of_3": round(self.trend_alignment_score, 2),
                "assessment": self.trend_alignment_text,
            },
            "short_term_direction": self.short_term_direction_text,
            "price_stability": self.price_stability_text,
            "breakout_potential": self.breakout_potential_text,
            "noise_level": self.noise_level_text,
            "market_structure": self.market_structure,
            "timing_quality": self.timing_quality,
            "risk_posture": self.risk_posture,
            "momentum_view": self.momentum_view,
            "action_bias": self.action_bias,
            "conviction": {
                "score_out_of_10": round(self.conviction_score, 2),
                "assessment": self.conviction_text,
            },
            "summary_line": self.summary_line,
        }


# =========================================================
# TRANSLATION LAYER
# =========================================================
def build_human_signal_components(
    *,
    volume_score: float,
    price_expansion_score: float,
    range_score: float,
    trend_score: float,
    slope_value: float,
    stability_value: float,
    breakout_value: float,
    noise_value: float,
) -> HumanSignalComponents:
    volume_score = clamp(safe_float(volume_score), 0.0, 5.0)
    price_expansion_score = clamp(safe_float(price_expansion_score), 0.0, 5.0)
    range_score = clamp(safe_float(range_score), 0.0, 2.0)
    trend_score = clamp(safe_float(trend_score), 0.0, 3.0)

    slope_value = clamp(safe_float(slope_value), -1.0, 1.0)
    stability_value = clamp(safe_float(stability_value, 0.5), 0.0, 1.0)
    breakout_value = clamp(safe_float(breakout_value), 0.0, 1.0)
    noise_value = clamp(safe_float(noise_value, 0.5), 0.0, 1.0)

    conviction_raw = volume_score + price_expansion_score + range_score + trend_score
    conviction_score = (conviction_raw / 15.0) * 10.0

    volume_text = f"{strength_label_5(volume_score)} participation"
    price_text = f"{strength_label_5(price_expansion_score)} expansion"

    if range_score >= 1.6:
        range_text = "Closing near the upper end of its range"
    elif range_score >= 0.9:
        range_text = "Holding in the middle of its range"
    else:
        range_text = "Sitting low in its range"

    if trend_score >= 2.5:
        trend_text = "Trend is aligned"
    elif trend_score >= 1.8:
        trend_text = "Trend is improving"
    elif trend_score >= 1.1:
        trend_text = "Trend is mixed"
    else:
        trend_text = "Trend is misaligned"

    if conviction_raw >= 10.5:
        momentum_view = "Momentum is expanding"
    elif conviction_raw >= 8.0:
        momentum_view = "Momentum is constructive"
    elif conviction_raw >= 5.0:
        momentum_view = "Momentum is mixed"
    else:
        momentum_view = "Momentum is weak"

    if trend_score >= 2.2 and range_score >= 1.2 and slope_value > 0.15:
        market_structure = "Bullish structure"
    elif trend_score <= 1.0 and range_score <= 0.8 and slope_value < -0.15:
        market_structure = "Bearish structure"
    elif abs(slope_value) < 0.2 and breakout_value < 0.5:
        market_structure = "Range-bound structure"
    else:
        market_structure = "Transitioning structure"

    if breakout_value >= 0.7 and stability_value >= 0.5 and noise_value <= 0.45:
        timing_quality = "High-quality setup"
    elif breakout_value >= 0.55 and noise_value <= 0.60:
        timing_quality = "Good setup"
    elif breakout_value >= 0.35:
        timing_quality = "Average setup"
    else:
        timing_quality = "Low-quality setup"

    if conviction_raw >= 10.0 and noise_value <= 0.35 and stability_value >= 0.55:
        risk_posture = "Aggressive risk is acceptable"
    elif conviction_raw >= 7.0 and noise_value <= 0.60:
        risk_posture = "Controlled risk is preferred"
    elif conviction_raw >= 5.0:
        risk_posture = "Small risk only"
    else:
        risk_posture = "Avoid size until conditions improve"

    if market_structure == "Bullish structure" and breakout_value >= 0.55:
        action_bias = "Lean long on pullbacks"
    elif market_structure == "Bearish structure" and breakout_value >= 0.45:
        action_bias = "Lean short into weakness"
    elif breakout_value < 0.5:
        action_bias = "Wait for confirmation"
    else:
        action_bias = "Trade only with tight risk"

    summary_line = (
        f"{momentum_view}. {market_structure}. {timing_quality}. "
        f"Preferred stance: {action_bias.lower()}."
    )

    return HumanSignalComponents(
        volume_strength_score=volume_score,
        volume_strength_text=volume_text,
        price_expansion_score=price_expansion_score,
        price_expansion_text=price_text,
        position_in_range_score=range_score,
        position_in_range_text=range_text,
        trend_alignment_score=trend_score,
        trend_alignment_text=trend_text,
        short_term_direction_value=slope_value,
        short_term_direction_text=direction_label(slope_value),
        price_stability_value=stability_value,
        price_stability_text=stability_label(stability_value),
        breakout_potential_value=breakout_value,
        breakout_potential_text=breakout_label(breakout_value),
        noise_level_value=noise_value,
        noise_level_text=noise_label(noise_value),
        market_structure=market_structure,
        timing_quality=timing_quality,
        risk_posture=risk_posture,
        momentum_view=momentum_view,
        action_bias=action_bias,
        conviction_score=conviction_score,
        conviction_text=score_band(conviction_raw, 15.0),
        summary_line=summary_line,
    )


def make_human_language_components_from_signal_dict(signal: Dict[str, Any]) -> HumanSignalComponents:
    volume_score = signal.get("volume_strength_score", signal.get("volume_score", 0.0))
    price_score = signal.get("price_expansion_score", signal.get("price_score", 0.0))
    range_score = signal.get("position_in_range_score", signal.get("range_score", 0.0))
    trend_score = signal.get("trend_alignment_score", signal.get("trend_score", 0.0))

    slope_value = signal.get("short_term_direction_value", signal.get("slope", 0.0))
    stability_value = signal.get("price_stability_value", signal.get("stability", 0.5))
    breakout_value = signal.get("breakout_potential_value", signal.get("breakout", 0.0))
    noise_value = signal.get("noise_level_value", signal.get("volatility", signal.get("noise", 0.5)))

    return build_human_signal_components(
        volume_score=volume_score,
        price_expansion_score=price_score,
        range_score=range_score,
        trend_score=trend_score,
        slope_value=slope_value,
        stability_value=stability_value,
        breakout_value=breakout_value,
        noise_value=noise_value,
    )


# =========================================================
# AGENT PROMPTS
# =========================================================
def build_agent_system_prompt(role: str) -> str:
    return textwrap.dedent(
        f"""
        You are the {role} agent inside a crypto intelligence app.

        Rules:
        1. Speak only in plain human language.
        2. Never mention internal model names, internal labels, acronyms, factor codes, hidden references, or shorthand.
        3. Use only these customer-facing terms:
           Volume Strength
           Price Expansion
           Position in Range
           Trend Alignment
           Short-Term Direction
           Price Stability
           Breakout Potential
           Noise Level
           Market Structure
           Timing Quality
           Risk Posture
           Momentum View
           Action Bias
        4. Be concise, clear, and decision-oriented.
        5. Write like you are speaking to a customer, not an engineer.
        """
    ).strip()


def build_agent_user_prompt(
    role: str,
    symbol: str,
    timeframe: str,
    components: HumanSignalComponents,
    extra_context: Optional[Dict[str, Any]] = None,
) -> str:
    payload = components.to_agent_payload()
    context = extra_context or {}

    return textwrap.dedent(
        f"""
        Role: {role}
        Asset: {symbol}
        Timeframe: {timeframe}

        Human-language signal components:
        {json.dumps(payload, indent=2)}

        Additional context:
        {json.dumps(context, indent=2)}

        Produce:
        1. one sentence for the market read
        2. one sentence for timing
        3. one sentence for risk
        4. one sentence for the next best action

        Never mention hidden systems or internal mechanics.
        """
    ).strip()


# =========================================================
# LOCAL FALLBACK AGENTS
# =========================================================
def local_agent_response(
    role: str,
    symbol: str,
    timeframe: str,
    components: HumanSignalComponents,
) -> str:
    if role == "Market Analyst":
        return (
            f"{symbol} on {timeframe} shows {components.momentum_view.lower()} within "
            f"{components.market_structure.lower()}. "
            f"Volume Strength is described as {components.volume_strength_text.lower()} and "
            f"Trend Alignment is {components.trend_alignment_text.lower()}."
        )

    if role == "Timing Analyst":
        return (
            f"Timing Quality is {components.timing_quality.lower()}. "
            f"Short-Term Direction is {components.short_term_direction_text.lower()}, "
            f"while Breakout Potential is {components.breakout_potential_text.lower()}."
        )

    if role == "Risk Analyst":
        return (
            f"Risk Posture is {components.risk_posture.lower()}. "
            f"Price Stability is {components.price_stability_text.lower()} and Noise Level is "
            f"{components.noise_level_text.lower()}, so position size should match setup quality."
        )

    if role == "Execution Coach":
        return (
            f"Action Bias is {components.action_bias.lower()}. "
            f"Focus on clean confirmation rather than forcing activity, especially when conditions are mixed."
        )

    return components.summary_line


# =========================================================
# AI LAB PACK
# =========================================================
def generate_ai_lab_pack(
    *,
    symbol: str,
    timeframe: str,
    raw_signal: Dict[str, Any],
    extra_context: Optional[Dict[str, Any]] = None,
    llm_callable: Optional[Any] = None,
) -> Dict[str, Any]:
    components = make_human_language_components_from_signal_dict(raw_signal)

    roles = [
        "Market Analyst",
        "Timing Analyst",
        "Risk Analyst",
        "Execution Coach",
    ]

    outputs: Dict[str, str] = {}

    for role in roles:
        system_prompt = build_agent_system_prompt(role)
        user_prompt = build_agent_user_prompt(
            role=role,
            symbol=symbol,
            timeframe=timeframe,
            components=components,
            extra_context=extra_context,
        )

        if llm_callable is not None:
            try:
                result = llm_callable(system_prompt, user_prompt)
                outputs[role] = (result or "").strip()
                if not outputs[role]:
                    outputs[role] = local_agent_response(role, symbol, timeframe, components)
            except Exception:
                outputs[role] = local_agent_response(role, symbol, timeframe, components)
        else:
            outputs[role] = local_agent_response(role, symbol, timeframe, components)

    return {
        "components": components,
        "agent_payload": components.to_agent_payload(),
        "agent_outputs": outputs,
    }


# =========================================================
# RENDER HELPERS
# =========================================================
def metric_box(title: str, value: str, subtitle: str = "") -> None:
    st.markdown(
        f"""
        <div class="panel">
            <div class="panel-title">{title}</div>
            <div class="panel-value">{value}</div>
            <div class="panel-sub">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def agent_card(title: str, body: str) -> None:
    st.markdown(
        f"""
        <div class="agent-card">
            <div class="agent-title">{title}</div>
            <div class="agent-body">{body}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_translated_components(components: HumanSignalComponents) -> None:
    st.markdown('<div class="section-head">Signal Breakdown</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)

    with c1:
        metric_box("Volume Strength", f"{components.volume_strength_score:.1f} / 5", components.volume_strength_text)
        metric_box("Price Expansion", f"{components.price_expansion_score:.1f} / 5", components.price_expansion_text)
        metric_box("Position in Range", f"{components.position_in_range_score:.1f} / 2", components.position_in_range_text)
        metric_box("Trend Alignment", f"{components.trend_alignment_score:.1f} / 3", components.trend_alignment_text)

    with c2:
        metric_box("Short-Term Direction", components.short_term_direction_text)
        metric_box("Price Stability", components.price_stability_text)
        metric_box("Breakout Potential", components.breakout_potential_text)
        metric_box("Noise Level", components.noise_level_text)

    st.markdown('<div class="section-head">Market Read</div>', unsafe_allow_html=True)

    a1, a2, a3 = st.columns(3)
    with a1:
        metric_box("Market Structure", components.market_structure)
    with a2:
        metric_box("Timing Quality", components.timing_quality)
    with a3:
        metric_box("Risk Posture", components.risk_posture)

    b1, b2 = st.columns(2)
    with b1:
        metric_box("Momentum View", components.momentum_view)
    with b2:
        metric_box("Action Bias", components.action_bias)

    st.markdown(
        f'<div class="summary-box">{components.summary_line}</div>',
        unsafe_allow_html=True,
    )


def render_ai_lab_output(
    symbol: str,
    timeframe: str,
    components: HumanSignalComponents,
    agent_outputs: Dict[str, str],
) -> None:
    st.markdown('<div class="section-head">AI Lab</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="tiny-muted">{symbol} · {timeframe}</div>',
        unsafe_allow_html=True,
    )

    render_translated_components(components)

    st.markdown('<div class="section-head">Agent Desk</div>', unsafe_allow_html=True)

    ordered_roles = [
        "Market Analyst",
        "Timing Analyst",
        "Risk Analyst",
        "Execution Coach",
    ]

    for role in ordered_roles:
        agent_card(role, agent_outputs.get(role, ""))


# =========================================================
# OPTIONAL LLM CALL HOOK
# Replace this with your real OpenAI call when ready.
# =========================================================
def llm_callable(system_prompt: str, user_prompt: str) -> str:
    """
    Plug your real LLM call here later.

    Example shape:
        response = client.responses.create(
            model="gpt-5.4",
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.output_text.strip()

    For now this returns an empty string so the local agent fallback is used.
    """
    return ""


# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.markdown("## Crypto AI Lab")
    st.markdown("Human-language agent intelligence")
    st.markdown("---")

    selected_symbol = st.text_input("Symbol", value="BTC")
    selected_timeframe = st.selectbox("Timeframe", ["15m", "1h", "4h", "1d"], index=1)

    st.markdown("### Input Signals")

    volume_score = st.slider("Volume Strength", 0.0, 5.0, 3.7, 0.1)
    price_expansion_score = st.slider("Price Expansion", 0.0, 5.0, 3.4, 0.1)
    range_score = st.slider("Position in Range", 0.0, 2.0, 1.4, 0.1)
    trend_score = st.slider("Trend Alignment", 0.0, 3.0, 2.2, 0.1)

    slope_value = st.slider("Short-Term Direction", -1.0, 1.0, 0.35, 0.05)
    stability_value = st.slider("Price Stability", 0.0, 1.0, 0.58, 0.05)
    breakout_value = st.slider("Breakout Potential", 0.0, 1.0, 0.66, 0.05)
    volatility_value = st.slider("Noise Level", 0.0, 1.0, 0.34, 0.05)

    st.markdown("---")
    last_price = st.number_input("Last Price", min_value=0.0, value=84250.0, step=10.0)
    change_percent = st.number_input("24h Change %", value=2.35, step=0.1)

    run_lab = st.button("Run AI Lab", use_container_width=True)


# =========================================================
# MAIN HEADER
# =========================================================
st.markdown('<div class="main-title">Crypto AI Lab</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">Agents consume only customer-facing language and respond without hidden references.</div>',
    unsafe_allow_html=True,
)


# =========================================================
# RAW SIGNAL ASSEMBLY
# Replace these values with your real engine outputs later.
# =========================================================
raw_signal = {
    "volume_score": volume_score,
    "price_score": price_expansion_score,
    "range_score": range_score,
    "trend_score": trend_score,
    "slope": slope_value,
    "stability": stability_value,
    "breakout": breakout_value,
    "volatility": volatility_value,
}


# =========================================================
# MAIN APP
# =========================================================
ai_lab_pack = generate_ai_lab_pack(
    symbol=selected_symbol,
    timeframe=selected_timeframe,
    raw_signal=raw_signal,
    extra_context={
        "last_price": last_price,
        "change_percent": change_percent,
    },
    llm_callable=llm_callable,
)

components = ai_lab_pack["components"]
agent_payload = ai_lab_pack["agent_payload"]
agent_outputs = ai_lab_pack["agent_outputs"]

col_left, col_right = st.columns([2.2, 1.1])

with col_left:
    render_ai_lab_output(
        symbol=selected_symbol,
        timeframe=selected_timeframe,
        components=components,
        agent_outputs=agent_outputs,
    )

with col_right:
    st.markdown('<div class="section-head">Snapshot</div>', unsafe_allow_html=True)
    metric_box("Asset", selected_symbol)
    metric_box("Timeframe", selected_timeframe)
    metric_box("Last Price", f"{last_price:,.2f}")
    metric_box("24h Change", f"{change_percent:.2f}%")
    metric_box("Conviction", f"{components.conviction_score:.1f} / 10", components.conviction_text)

    st.markdown('<div class="section-head">Download</div>', unsafe_allow_html=True)

    report = {
        "asset": selected_symbol,
        "timeframe": selected_timeframe,
        "components": agent_payload,
        "agent_outputs": agent_outputs,
        "market_context": {
            "last_price": last_price,
            "change_percent": change_percent,
        },
    }

    st.download_button(
        label="Download AI Lab Report",
        data=json.dumps(report, indent=2),
        file_name=f"{selected_symbol.lower()}_{selected_timeframe}_ai_lab_report.json",
        mime="application/json",
        use_container_width=True,
    )

    with st.expander("Payload sent to agents"):
        st.json(agent_payload)

    with st.expander("Prompt rule"):
        st.code(
            """
Agents must speak only in human language.
Never mention internal model names, internal factor names, acronyms,
hidden references, shorthand labels, or engine terminology.
            """.strip()
        )


if not run_lab:
    st.caption("Adjust the inputs in the sidebar and click Run AI Lab. The app already updates live.")
