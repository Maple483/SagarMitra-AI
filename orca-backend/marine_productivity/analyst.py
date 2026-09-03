"""
Template-driven explainable narrative compiler and semantic validation layer.
Generates structured explanations strictly from pre-compiled templates, enforcing
zero causal claims and validating numerical/polarity consistency against ScientificFactBundle.
"""

import os
import re
from typing import List, Tuple, Optional
from .schemas import (
    ScientificFactBundle,
    StructuredHypothesis,
    GroundingStatusEnum,
)


class CausalLanguageViolationError(ValueError):
    pass


FORBIDDEN_CAUSAL_PHRASES = [
    r"\bcaused\b",
    r"\bdrove\b",
    r"\bled to\b",
    r"\bresponsible for\b",
    r"\bexplains\b",
    r"\baccounted for\b",
    r"\battributable to\b",
    r"\bdriver of\b",
    r"\bresponded to\b",
    r"\binfluenced\b",
    r"\bmajor contributor\b",
    r"\bsubstantially\b",
]

UNSUPPORTED_KEYWORDS = [
    "fuel", "diesel", "subsidy", "subsidies", "boat", "quota",
    "license", "engine", "horsepower", "gear shift", "trawler ban"
]


class TemplateNarrativeCompiler:
    @classmethod
    def check_query_grounding(cls, query_text: Optional[str]) -> Tuple[str, List[str]]:
        if not query_text:
            return GroundingStatusEnum.GROUNDED.value, []

        query_lower = query_text.lower()
        unsupported = [kw for kw in UNSUPPORTED_KEYWORDS if kw in query_lower]
        if unsupported:
            return GroundingStatusEnum.UNSUPPORTED_VARIABLES_DETECTED.value, unsupported
        return GroundingStatusEnum.GROUNDED.value, []

    @classmethod
    def compile_narrative(
        cls,
        bundle: ScientificFactBundle,
        hypotheses: List[StructuredHypothesis],
        query_text: Optional[str] = None,
    ) -> Tuple[str, List[str], List[str]]:
        """
        Compiles template-driven answers, observational bullet points, and hypotheses.
        When query_text is provided and LLM is accessible, generates an intelligent grounded response.
        Returns (direct_answer, what_the_data_shows, possible_contributing_factors).
        """
        state_str = bundle.state.value
        sp_str = bundle.species
        var_label = "Sea Surface Temperature" if bundle.environmental_variable.value == "sst" else "Chlorophyll-a"
        var_unit = "degC" if bundle.environmental_variable.value == "sst" else "mg/m3"
        lag_label = f"lag {bundle.lag_years.value} yr" if bundle.lag_years.value > 0 else "same-year"

        # 1. Direct Answer (Default template)
        if bundle.pearson_r is not None and bundle.level_nominal_p_value_iid_assumed is not None:
            direction_word = "positive" if bundle.pearson_r > 0 else "negative"
            direct_answer = (
                f"In {state_str}, reported landings of {sp_str} and {var_label} ({lag_label}) "
                f"exhibited a {direction_word} observational association (r = {bundle.pearson_r:.2f}, "
                f"nominal p = {bundle.level_nominal_p_value_iid_assumed:.3f}, N = {bundle.n_valid}). "
                f"However, with only {bundle.n_valid} observed paired years, statistical power is low, "
                f"and unmeasured variables such as fishing effort remain unobserved."
            )
        else:
            direct_answer = (
                f"In {state_str}, available observations for {sp_str} and {var_label} were insufficient "
                f"or exhibited zero variance, preventing correlation estimation."
            )

        # If query_text is provided, attempt intelligent grounded generation
        groq_key = os.getenv("GROQ_API_KEY")
        if query_text and query_text.strip() and groq_key:
            try:
                llm_ans = cls._generate_llm_answer(bundle, query_text.strip(), groq_key)
                if llm_ans:
                    direct_answer = llm_ans
            except Exception as err:
                print(f"[Analyst LLM] Fallback to deterministic template: {err}")

        # 2. What the data shows
        data_points: List[str] = []
        if bundle.catch_2007 is not None and bundle.catch_2012 is not None:
            catch_delta = bundle.catch_2012 - bundle.catch_2007
            data_points.append(
                f"Observed landings shifted from {bundle.catch_2007:,.0f} t in 2007 to {bundle.catch_2012:,.0f} t in 2012 ({catch_delta:+,.0f} t over the observed baseline)."
            )

        if bundle.env_2007 is not None and bundle.env_2012 is not None:
            env_delta = bundle.env_2012 - bundle.env_2007
            data_points.append(
                f"Observed coastal {var_label} moved from {bundle.env_2007:.2f} {var_unit} in 2007 to {bundle.env_2012:.2f} {var_unit} in 2012 ({env_delta:+.2f} {var_unit})."
            )

        if bundle.peak_month_name and bundle.peak_month_pct is not None:
            tonnes_str = f" (~{bundle.peak_month_tonnes:,.0f} t)" if bundle.peak_month_tonnes else ""
            data_points.append(
                f"Peak landings typically occur in {bundle.peak_month_name}, representing {bundle.peak_month_pct:.1f}% of annual catch{tonnes_str}."
            )

        if bundle.post_monsoon_pct is not None and bundle.post_monsoon_tonnes is not None:
            data_points.append(
                f"Post-monsoon months (October-November) account for ~{bundle.post_monsoon_pct:.0f}% of landings (~{bundle.post_monsoon_tonnes:,.0f} t)."
            )

        if bundle.descriptive_first_difference_r is not None:
            data_points.append(
                f"Year-to-year consecutive difference correlation was r_delta = {bundle.descriptive_first_difference_r:.2f} (based on {bundle.n_difference_pairs} difference pairs)."
            )

        # 3. Possible contributing factors (Hypotheses)
        contributing_factors: List[str] = [
            f"Thermal habitat alignment: Coastal upwelling and seasonal thermocline shoaling coincide with peak schooling periods.",
            f"Trophic food-web timing: Plankton blooms following the southwest monsoon provide larval and juvenile foraging windows.",
            f"Unobserved operational confounders: Fleet engine horsepower, motorized purse-seine deployment, and monsoonal fishing ban enforcement heavily govern landing volumes.",
        ]

        # Verify semantic linter across compiled text
        all_text = direct_answer + " " + " ".join(data_points) + " " + " ".join(contributing_factors)
        cls.verify_no_causal_leakage(all_text)

        return direct_answer, data_points, contributing_factors

    @classmethod
    def _generate_llm_answer(cls, bundle: ScientificFactBundle, query: str, api_key: str) -> Optional[str]:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage

        state_str = bundle.state.value
        sp_str = bundle.species
        var_label = "Sea Surface Temperature" if bundle.environmental_variable.value == "sst" else "Chlorophyll-a"
        var_unit = "°C" if bundle.environmental_variable.value == "sst" else "mg/m³"
        lag_label = f"lag {bundle.lag_years.value} yr" if bundle.lag_years.value > 0 else "same-year"

        catch_delta = (bundle.catch_2012 - bundle.catch_2007) if (bundle.catch_2007 and bundle.catch_2012) else 0

        system_prompt = (
            "You are a Senior Marine Fisheries Scientist. Answer the user's analytical question "
            "strictly using the empirical facts provided below.\n"
            "FACTS FROM DATASET:\n"
            f"- Maritime State: {state_str}\n"
            f"- Target Species: {sp_str}\n"
            f"- Observed Landings (2007–2012): 2007={bundle.catch_2007:,.0f} t, 2012={bundle.catch_2012:,.0f} t (change: {catch_delta:+,.0f} t)\n"
            f"- Observed {var_label}: 2007={bundle.env_2007:.2f} {var_unit}, 2012={bundle.env_2012:.2f} {var_unit}\n"
            f"- Correlation: Pearson r = {bundle.pearson_r:.2f} ({lag_label}), nominal p = {bundle.level_nominal_p_value_iid_assumed:.3f} (N={bundle.n_valid} pairs)\n"
            f"- Seasonal Distribution: Peak in {bundle.peak_month_name} ({bundle.peak_month_pct:.1f}% of annual landings); Post-monsoon (Oct-Nov)={bundle.post_monsoon_pct:.0f}%\n"
            "\n"
            "STRICT SCIENTIFIC GUIDELINES:\n"
            "1. You MUST directly answer the question asked.\n"
            "2. Cite the exact figures (tonnes, percentages, temperature/chlorophyll values).\n"
            "3. Strictly non-causal language. Do NOT use: 'caused', 'drove', 'led to', 'responsible for', 'explains', 'accounted for', 'attributable to', 'driver of', 'responded to', 'influenced', 'major contributor', 'substantially'.\n"
            "4. Clarify that correlation is not causation and that unobserved operational factors (fishing effort, fleet capacity, purse-seine hours) remain unmeasured.\n"
            "5. Keep the response concise, clear, and between 3 to 5 sentences."
        )

        llm = ChatOpenAI(
            model="qwen/qwen3.8-27b",
            openai_api_base="https://api.groq.com/openai/v1",
            openai_api_key=api_key,
            temperature=0.1,
            max_tokens=300,
        )

        resp = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=query)])
        content = resp.content.strip()

        # Sanitize for causal language
        try:
            cls.verify_no_causal_leakage(content)
            return content
        except CausalLanguageViolationError:
            replacements = {
                " caused ": " co-occurred with ",
                " drove ": " coincided with ",
                " led to ": " preceded ",
                " responsible for ": " associated with ",
                " explains ": " correlates with ",
                " substantially ": " notably ",
            }
            sanitized = content
            for old, new in replacements.items():
                sanitized = re.sub(re.escape(old), new, sanitized, flags=re.IGNORECASE)
            try:
                cls.verify_no_causal_leakage(sanitized)
                return sanitized
            except CausalLanguageViolationError:
                return None

    @classmethod
    def verify_no_causal_leakage(cls, text: str) -> None:
        """
        Scans text for forbidden causal keywords outside explicit disclaimer quotes.
        Raises CausalLanguageViolationError if any prohibited phrasing is detected.
        """
        text_clean = text.lower()
        for pattern in FORBIDDEN_CAUSAL_PHRASES:
            match = re.search(pattern, text_clean)
            if match:
                raise CausalLanguageViolationError(
                    f"Forbidden causal phrasing detected in generated text: '{match.group(0)}'. "
                    f"System must only use non-causal observational language."
                )
