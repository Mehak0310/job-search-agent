"""Deterministic heuristic fit, never an interview probability."""
import re
from typing import Protocol

from .models import JobInput, Profile, WorkMode, key


class MatchEvaluator(Protocol):
    def evaluate(self, job: JobInput, profile: Profile) -> dict: ...


def tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", key(value)))


class DeterministicMatcher:
    def evaluate(self, job: JobInput, profile: Profile) -> dict:
        reasons, missing, disqualifiers = [], [], []
        title = tokens(job.title)
        title_fit = max(len(title & tokens(t)) / max(len(tokens(t)), len(title), 1) for t in profile.target_titles)
        score = round(35 * title_fit)
        if title_fit >= 0.5:
            reasons.append("Title overlaps target roles")
        else:
            missing.append("Title has limited overlap with target roles")
        required, known = set(job.skills), set(profile.skills)
        matched = sorted(required & known)
        absent = sorted(required - known)
        if required:
            score += round(35 * len(matched) / len(required))
            if matched:
                reasons.append("Relevant skills: " + ", ".join(matched))
            missing.extend("Skill: " + s for s in absent)
        else:
            missing.append("Job skills not supplied")
        location = key(job.location)
        if any(place in location for place in profile.locations) or job.work_mode==WorkMode.REMOTE and "india" in location and "remote india" in profile.locations:
            score += 15
            reasons.append("Location matches preferences")
        else:
            disqualifiers.append("Location is outside configured preferences")
        if job.work_mode in profile.work_modes and job.work_mode != WorkMode.UNKNOWN:
            score += 10
            reasons.append("Work mode matches preferences")
        elif job.work_mode == WorkMode.UNKNOWN:
            missing.append("Work mode is unknown")
        else:
            disqualifiers.append("Work mode is outside configured preferences")
        if job.min_experience is None and job.max_experience is None:
            missing.append("Job experience requirement is unknown")
        elif profile.experience_years is None:
            missing.append("Candidate experience is unspecified; compatibility not assessed")
        elif job.min_experience is not None and profile.experience_years < job.min_experience:
            disqualifiers.append("Below stated minimum experience")
        elif job.max_experience is not None and profile.experience_years > job.max_experience:
            missing.append("Candidate experience exceeds stated range; review role level")
        else:
            score += 5
            reasons.append("Experience fits stated range")
        text = key(" ".join([job.title, job.company, job.description]))
        for exclusion in profile.exclusions:
            if exclusion in text:
                disqualifiers.append("Exclusion matched: " + exclusion)
        score = max(0, min(100, score - 20 * len(disqualifiers)))
        return {"score": score, "reasons": reasons, "missing_requirements": missing, "potential_disqualifiers": disqualifiers}
