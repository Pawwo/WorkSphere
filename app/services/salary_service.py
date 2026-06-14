"""Salary extraction, B2B normalization, PL benchmark estimation, fit adjustment."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, Tuple

from app.config import Settings, get_settings

FitLevel = Literal["high", "medium", "low"]
SalarySource = Literal["direct", "description", "estimated", "missing"]


@dataclass
class SalaryAssessment:
    salary_raw: str
    source: SalarySource
    monthly_b2b_min: Optional[int]
    monthly_b2b_max: Optional[int]
    monthly_b2b_median: Optional[int]
    meets_threshold: bool
    reason: str
    role_bucket: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "salary_raw": self.salary_raw,
            "source": self.source,
            "monthly_b2b_min": self.monthly_b2b_min,
            "monthly_b2b_max": self.monthly_b2b_max,
            "monthly_b2b_median": self.monthly_b2b_median,
            "meets_threshold": self.meets_threshold,
            "reason": self.reason,
            "role_bucket": self.role_bucket,
        }


class SalaryService:
    HOURS_PER_MONTH = 168
    EUR_THRESHOLD = 5900
    USD_THRESHOLD = 6800
    MAX_SALARY_LINE_LEN = 120
    MAX_SALARY_TEXT_LEN = 200
    MAX_SANE_MONTHLY_B2B_PLN = 150_000

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._benchmarks = self._load_benchmarks()

    @property
    def threshold_pln(self) -> int:
        return int(self._benchmarks.get("b2b_monthly_threshold", 25000))

    def _load_benchmarks(self) -> dict:
        rel = getattr(self.settings, "salary_benchmarks_file", "data/salary_benchmarks_pl.json")
        path = Path(rel)
        if not path.is_absolute():
            path = self.settings.data_dir.parent / rel if str(rel).startswith("data/") else self.settings.repo_root / rel
        if not path.exists():
            path = self.settings.data_dir / "salary_benchmarks_pl.json"
        if not path.exists():
            return {
                "b2b_monthly_threshold": self.settings.salary_b2b_threshold_pln,
                "role_estimates_b2b_monthly": {},
                "title_patterns": [],
            }
        data = json.loads(path.read_text(encoding="utf-8"))
        if "b2b_monthly_threshold" not in data:
            data["b2b_monthly_threshold"] = self.settings.salary_b2b_threshold_pln
        return data

    _SALARY_RANGE_RE = re.compile(
        r"(\d[\d\s.,\xa0]{1,10}\s*[-–—]\s*\d[\d\s.,\xa0]{1,10}\s*(?:PLN|zł|zl|eur|usd|€|\$|b2b))",
        re.IGNORECASE,
    )
    _WIDELKI_RANGE_RE = re.compile(
        r"widełk[ií]?\s*:?\s*(\d[\d\s.,\xa0]{1,10}\s*[-–—]\s*\d[\d\s.,\xa0]{1,10}\s*(?:PLN|zł|zl|eur|usd|€|\$)(?:\s+b2b)?)",
        re.IGNORECASE,
    )

    @staticmethod
    def extract_salary_from_description(description: str) -> str:
        if not description:
            return ""
        lines = description.splitlines()
        salary_lines = []
        keywords = (
            "widełk",
            "wynagrodz",
            "salary",
            "pensja",
            "pln",
            "zł",
            "zl",
            "brutto",
            "netto",
            "b2b",
            "kontrakt",
            "faktur",
        )
        for line in lines:
            clean = line.strip()
            if not clean or len(clean) > SalaryService.MAX_SALARY_LINE_LEN:
                continue
            lower = clean.lower()
            if any(k in lower for k in keywords) and any(ch.isdigit() for ch in clean):
                salary_lines.append(clean)
        if salary_lines:
            return " ".join(salary_lines[:3])
        widelki_match = SalaryService._WIDELKI_RANGE_RE.search(description)
        if widelki_match:
            return widelki_match.group(1).strip()
        range_match = SalaryService._SALARY_RANGE_RE.search(description)
        return range_match.group(1).strip() if range_match else ""

    def should_reassess_estimated(
        self,
        *,
        salary_source: Optional[str],
        description: Optional[str],
    ) -> bool:
        if salary_source != "estimated":
            return False
        return bool(self.extract_salary_from_description(description or ""))

    def extract_salary_text(
        self,
        *,
        salary: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Tuple[str, SalarySource]:
        direct = (salary or "").strip()
        if direct:
            return direct, "direct"
        extracted = self.extract_salary_from_description(description or "")
        if extracted:
            return extracted, "description"
        return "", "missing"

    @staticmethod
    def _detect_currency(text: str) -> str:
        lower = text.lower()
        if "eur" in lower or "€" in lower:
            return "EUR"
        if "usd" in lower or "$" in lower:
            return "USD"
        if "pln" in lower or "zł" in lower or "zl" in lower:
            return "PLN"
        return "UNKNOWN"

    @staticmethod
    def _extract_numbers(text: str) -> list[int]:
        matches = re.findall(r"\d[\d\s\.,\xa0]{1,8}", text)
        values = []
        for raw in matches:
            compact = raw.replace(" ", "").replace("\xa0", "")
            if "," in compact and "." in compact:
                compact = compact.replace(",", "")
            compact = compact.replace(",", "").replace(".", "")
            if compact.isdigit():
                val = int(compact)
                if 100 < val <= SalaryService.MAX_SANE_MONTHLY_B2B_PLN * 12:
                    values.append(val)
        return values

    def _is_sane_monthly_range(self, b2b_min: Optional[int], b2b_max: Optional[int]) -> bool:
        if b2b_min is None or b2b_max is None:
            return False
        return (
            0 < b2b_min <= self.MAX_SANE_MONTHLY_B2B_PLN
            and 0 < b2b_max <= self.MAX_SANE_MONTHLY_B2B_PLN
            and b2b_min <= b2b_max
        )

    def _to_monthly_pln_range(self, text: str, values: list[int]) -> Tuple[Optional[int], Optional[int]]:
        if not values:
            return None, None
        lower = text.lower()
        min_val, max_val = min(values), max(values)

        if any(x in lower for x in ("/h", "godz", "hour", "hr")):
            min_val = int(min_val * self.HOURS_PER_MONTH)
            max_val = int(max_val * self.HOURS_PER_MONTH)

        if any(x in lower for x in ("rocznie", "roczne", "per year", "/year", "yearly", "annum")):
            min_val = int(min_val / 12)
            max_val = int(max_val / 12)

        currency = self._detect_currency(text)
        if currency == "EUR":
            min_val = int(min_val * 4.3)
            max_val = int(max_val * 4.3)
        elif currency == "USD":
            min_val = int(min_val * 4.0)
            max_val = int(max_val * 4.0)

        is_b2b = any(x in lower for x in ("b2b", "kontrakt", "faktura", "invoice", "contract"))
        is_brutto = "brutto" in lower or "gross" in lower
        is_netto = "netto" in lower or "net " in lower or "na rękę" in lower or "na reke" in lower

        if is_b2b:
            pass
        elif is_brutto:
            min_val = int(min_val * 0.70)
            max_val = int(max_val * 0.70)
        elif is_netto:
            min_val = int(min_val * 1.18)
            max_val = int(max_val * 1.18)
        else:
            if max_val >= 40000:
                min_val = int(min_val * 0.70)
                max_val = int(max_val * 0.70)
            elif max_val < 8000:
                min_val = int(min_val * self.HOURS_PER_MONTH)
                max_val = int(max_val * self.HOURS_PER_MONTH)

        return min_val, max_val

    def _role_bucket(self, title: str) -> str:
        title_l = title.lower()
        for entry in self._benchmarks.get("title_patterns", []):
            if re.search(entry["pattern"], title_l, re.I):
                return entry["role"]
        return "default"

    def _estimate_from_benchmarks(self, title: str) -> Tuple[int, int, int, str]:
        role = self._role_bucket(title)
        estimates = self._benchmarks.get("role_estimates_b2b_monthly", {})
        bucket = estimates.get(role) or estimates.get("default") or {"min": 14000, "median": 20000, "max": 28000}
        return bucket["min"], bucket["median"], bucket["max"], role

    def assess(
        self,
        *,
        title: str,
        salary: Optional[str] = None,
        description: Optional[str] = None,
    ) -> SalaryAssessment:
        salary_text, source = self.extract_salary_text(salary=salary, description=description)
        threshold = self.threshold_pln

        if salary_text and len(salary_text) > self.MAX_SALARY_TEXT_LEN:
            salary_text = ""

        if salary_text:
            values = self._extract_numbers(salary_text)
            b2b_min, b2b_max = self._to_monthly_pln_range(salary_text, values)
            if not self._is_sane_monthly_range(b2b_min, b2b_max):
                est_min, est_med, est_max, role = self._estimate_from_benchmarks(title)
                return SalaryAssessment(
                    salary_raw=salary_text[: self.MAX_SALARY_TEXT_LEN],
                    source=source,
                    monthly_b2b_min=est_min,
                    monthly_b2b_max=est_max,
                    monthly_b2b_median=est_med,
                    meets_threshold=est_med >= threshold,
                    reason="PARSE_FALLBACK_ESTIMATE",
                    role_bucket=role,
                )
            if b2b_min is None or b2b_max is None:
                est_min, est_med, est_max, role = self._estimate_from_benchmarks(title)
                return SalaryAssessment(
                    salary_raw=salary_text,
                    source=source,
                    monthly_b2b_min=est_min,
                    monthly_b2b_max=est_max,
                    monthly_b2b_median=est_med,
                    meets_threshold=est_med >= threshold,
                    reason="PARSE_FALLBACK_ESTIMATE",
                    role_bucket=role,
                )
            median = (b2b_min + b2b_max) // 2
            meets = b2b_max >= threshold
            reason = "ABOVE_THRESHOLD" if meets else "BELOW_THRESHOLD"
            return SalaryAssessment(
                salary_raw=salary_text,
                source=source,
                monthly_b2b_min=b2b_min,
                monthly_b2b_max=b2b_max,
                monthly_b2b_median=median,
                meets_threshold=meets,
                reason=reason,
            )

        est_min, est_med, est_max, role = self._estimate_from_benchmarks(title)
        meets = est_med >= threshold
        return SalaryAssessment(
            salary_raw="",
            source="estimated",
            monthly_b2b_min=est_min,
            monthly_b2b_max=est_max,
            monthly_b2b_median=est_med,
            meets_threshold=meets,
            reason="ESTIMATED_FROM_BENCHMARKS",
            role_bucket=role,
        )

    @staticmethod
    def adjust_fit(fit: FitLevel, assessment: SalaryAssessment, threshold: int) -> FitLevel:
        if assessment.meets_threshold:
            return fit
        median = assessment.monthly_b2b_median or 0
        order: list[FitLevel] = ["high", "medium", "low"]
        idx = order.index(fit)
        if median < threshold * 0.7:
            return "low"
        return order[min(2, idx + 1)]

    def adjust_overall_fit(
        self, overall: Literal["strong", "moderate", "weak"], assessment: SalaryAssessment
    ) -> Literal["strong", "moderate", "weak"]:
        if assessment.meets_threshold:
            return overall
        order = ["strong", "moderate", "weak"]
        idx = order.index(overall)
        median = assessment.monthly_b2b_median or 0
        if median < self.threshold_pln * 0.7:
            return "weak"
        return order[min(2, idx + 1)]
